"""Graph RAG traversal — Section 9 of the blueprint.

Bounded BFS from resolved seed entities. Never sends the whole graph:
capped by hop count (3) and node count (25). Edge-type priority is a
static lookup table keyed by query_class, not learned or LLM-decided.
"""
from dataclasses import dataclass, field

from db import get_connection

MAX_HOPS = 3
MAX_NODES = 25

# query_class -> relationship types to prioritize during traversal/truncation
EDGE_PRIORITY = {
    "simple_fact": ["WORKED_AT", "STUDIED", "AUTHORED", "BUILT", "USES", "PUBLISHED"],
    "entity_lookup": ["BUILT", "USES", "DEMONSTRATES", "AUTHORED", "PART_OF", "IMPLEMENTED_WITH"],
    "relationship": ["RELATED_TO", "DEMONSTRATES", "USES", "PART_OF", "WORKED_AT", "IMPLEMENTED_WITH"],
    "multi_hop": ["DEMONSTRATES", "RELATED_TO", "USES", "AUTHORED", "CONTRIBUTED_TO"],
}
DEFAULT_PRIORITY = [
    "WORKED_AT", "AUTHORED", "BUILT", "USES", "DEMONSTRATES", "STUDIED",
    "RESEARCHES", "PUBLISHED", "RELATED_TO", "IMPLEMENTED_WITH", "PART_OF",
    "CONTRIBUTED_TO",
]

# Per-query-class hop budget. "entity_lookup"/"simple_fact" asking about one
# entity only need that entity's own direct facts — without this, hop 2 walks
# through a highly-connected hub (e.g. the Person entity, BUILT-connected to
# every project) and floods the result with facts about *other* entities
# entirely unrelated to the question. "relationship" gets 2 hops so it can
# still bridge two named entities through one intermediate node.
HOP_BUDGET = {
    "simple_fact": 1,
    "entity_lookup": 1,
    "relationship": 2,
}


@dataclass
class Fact:
    relationship_id: str
    source: dict
    rel_type: str
    target: dict
    confidence: float
    status: str
    evidence: list = field(default_factory=list)  # [{source_type, source_ref, excerpt}]


@dataclass
class Subgraph:
    facts: list = field(default_factory=list)
    entity_notes: list = field(default_factory=list)  # entity-level evidence not tied to a relationship
    truncated: bool = False


def _entity(conn, entity_id):
    row = conn.execute("SELECT id, type, canonical_name FROM entities WHERE id=?", (entity_id,)).fetchone()
    return {"id": row["id"], "type": row["type"], "canonical_name": row["canonical_name"]} if row else None


def _fetch_evidence_for_relationship(conn, relationship_id):
    rows = conn.execute(
        "SELECT source_type, source_ref, excerpt FROM evidence WHERE relationship_id=?",
        (relationship_id,),
    ).fetchall()
    return [{"source_type": r["source_type"], "source_ref": r["source_ref"], "excerpt": r["excerpt"]} for r in rows]


def _fetch_evidence_for_entity(conn, entity_id):
    rows = conn.execute(
        "SELECT source_type, source_ref, excerpt FROM evidence WHERE entity_id=?",
        (entity_id,),
    ).fetchall()
    return [{"source_type": r["source_type"], "source_ref": r["source_ref"], "excerpt": r["excerpt"]} for r in rows]


def _neighbor_edges(conn, entity_id):
    """All active relationships touching entity_id, either direction."""
    rows = conn.execute(
        """
        SELECT id, source_id, target_id, type, confidence, status
        FROM relationships
        WHERE (source_id=? OR target_id=?) AND status IN ('active', 'disputed')
        """,
        (entity_id, entity_id),
    ).fetchall()
    return rows


def _priority_rank(rel_type, query_class):
    priority = EDGE_PRIORITY.get(query_class, DEFAULT_PRIORITY)
    return priority.index(rel_type) if rel_type in priority else len(priority)


def _bounded_bfs(conn, seed_ids, query_class):
    """Standard traversal: union of reachable facts within hop/node caps."""
    visited_nodes = set(seed_ids)
    frontier = list(seed_ids)
    facts_by_id = {}
    truncated = False
    max_hops = HOP_BUDGET.get(query_class, MAX_HOPS)

    for _hop in range(max_hops):
        if not frontier or len(visited_nodes) >= MAX_NODES:
            break
        next_frontier = []
        edges_this_hop = []
        for node_id in frontier:
            for edge in _neighbor_edges(conn, node_id):
                edges_this_hop.append(edge)

        # Weight by query_class priority so the highest-relevance edges survive truncation.
        edges_this_hop.sort(key=lambda e: _priority_rank(e["type"], query_class))

        for edge in edges_this_hop:
            other_id = edge["target_id"] if edge["source_id"] in visited_nodes and edge["target_id"] not in visited_nodes else (
                edge["source_id"] if edge["target_id"] in visited_nodes and edge["source_id"] not in visited_nodes else None
            )
            if edge["id"] not in facts_by_id:
                if len(visited_nodes) >= MAX_NODES and other_id is not None:
                    truncated = True
                    continue
                facts_by_id[edge["id"]] = edge
                if other_id is not None:
                    visited_nodes.add(other_id)
                    next_frontier.append(other_id)
        frontier = next_frontier

    facts = []
    for edge in facts_by_id.values():
        source = _entity(conn, edge["source_id"])
        target = _entity(conn, edge["target_id"])
        if not source or not target:
            continue
        facts.append(
            Fact(
                relationship_id=edge["id"],
                source=source,
                rel_type=edge["type"],
                target=target,
                confidence=edge["confidence"],
                status=edge["status"],
                evidence=_fetch_evidence_for_relationship(conn, edge["id"]),
            )
        )
    return facts, truncated


MULTI_HOP_MAX_HOPS = 2  # deliberately tighter than MAX_HOPS — see note below


def _multi_hop_intersection(conn, seed_ids, query_class):
    """Section 9 multi-hop example: reachable Project sets per seed, intersected.

    Restricted to the query_class's prioritized edge types and a 2-hop budget
    (not the general MAX_HOPS=3). Without this restriction, a "hub" entity
    like a popular ProgrammingLanguage bridges unrelated seeds together by hop
    3 (seed A -> concept -> project -> shared language -> every other project
    using that language), which would silently turn the intersection into
    something close to a union. Keeping it to edge types relevant to the
    query class and a shorter hop budget keeps the intersection meaningful.
    """
    if len(seed_ids) < 2:
        return _bounded_bfs(conn, seed_ids, query_class)

    allowed_types = set(EDGE_PRIORITY.get(query_class, DEFAULT_PRIORITY))

    per_seed_projects = []
    per_seed_edges = {}
    for seed_id in seed_ids:
        reachable_project_ids = set()
        edges_seen = []
        frontier = [seed_id]
        visited = {seed_id}
        for _hop in range(MULTI_HOP_MAX_HOPS):
            if not frontier:
                break
            next_frontier = []
            for node_id in frontier:
                for edge in _neighbor_edges(conn, node_id):
                    if edge["type"] not in allowed_types:
                        continue
                    other_id = edge["target_id"] if edge["source_id"] == node_id else edge["source_id"]
                    if other_id in visited:
                        continue
                    visited.add(other_id)
                    other = _entity(conn, other_id)
                    if other and other["type"] == "Project":
                        reachable_project_ids.add(other_id)
                    edges_seen.append(edge)
                    next_frontier.append(other_id)
            frontier = next_frontier
        per_seed_projects.append(reachable_project_ids)
        per_seed_edges[seed_id] = edges_seen

    intersection = set.intersection(*per_seed_projects) if per_seed_projects else set()

    if not intersection:
        # Nothing satisfies all constraints — fall back to the union so the
        # caller still has something to reason about, but this is a weaker
        # answer and the query_understanding/context layer should treat it
        # as lower-confidence than a true intersection hit.
        return _bounded_bfs(conn, seed_ids, query_class)

    facts_by_id = {}
    for seed_id, edges in per_seed_edges.items():
        for edge in edges:
            touches_project = edge["source_id"] in intersection or edge["target_id"] in intersection
            if touches_project and edge["id"] not in facts_by_id:
                facts_by_id[edge["id"]] = edge

    facts = []
    for edge in facts_by_id.values():
        source = _entity(conn, edge["source_id"])
        target = _entity(conn, edge["target_id"])
        if not source or not target:
            continue
        facts.append(
            Fact(
                relationship_id=edge["id"],
                source=source,
                rel_type=edge["type"],
                target=target,
                confidence=edge["confidence"],
                status=edge["status"],
                evidence=_fetch_evidence_for_relationship(conn, edge["id"]),
            )
        )
    return facts, False


def retrieve_subgraph(query_understanding, conn=None) -> Subgraph:
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        seed_ids = [e["id"] for e in query_understanding.resolved_entities]
        if not seed_ids:
            return Subgraph(facts=[], entity_notes=[], truncated=False)

        if query_understanding.query_class == "multi_hop":
            facts, truncated = _multi_hop_intersection(conn, seed_ids, query_understanding.query_class)
        else:
            facts, truncated = _bounded_bfs(conn, seed_ids, query_understanding.query_class)

        entity_notes = []
        for entity_id in seed_ids:
            notes = _fetch_evidence_for_entity(conn, entity_id)
            if notes:
                entity_notes.append({"entity_id": entity_id, "evidence": notes})

        return Subgraph(facts=facts, entity_notes=entity_notes, truncated=truncated)
    finally:
        if owns_conn:
            conn.close()
