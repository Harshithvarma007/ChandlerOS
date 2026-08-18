"""Retrieval Router — Section 11 of the blueprint.

Deterministic query_class -> strategy mapping (no LLM call, no embedding
model call — those come later in the pipeline once a strategy is chosen).
Escalation (GRAPH_ONLY -> GRAPH_PLUS_VECTOR when evidence is thin) lives in
ask.py, since it needs the graph retrieval result to decide, not just the
query_understanding output — the router only picks the *initial* strategy.
"""

GRAPH_ONLY = "GRAPH_ONLY"
VECTOR_ONLY = "VECTOR_ONLY"
GRAPH_PLUS_VECTOR = "GRAPH_PLUS_VECTOR"
NONE_STRATEGY = "NONE"

# Entity-lookup questions about these types benefit from vector nuance
# immediately rather than after an escalation round-trip (Section 11 table:
# "Blog/research question" and "Project question" rows).
VECTOR_PREFERRED_ENTITY_LOOKUP_TYPES = {"Blog", "Publication", "ResearchTopic", "Project"}

MIN_EVIDENCE_COUNT = 2  # below this, GRAPH_ONLY escalates once to GRAPH_PLUS_VECTOR


def decide_strategy(query_understanding) -> str:
    qc = query_understanding.query_class

    if qc in ("general", "unknown"):
        return NONE_STRATEGY

    if qc == "semantic":
        return VECTOR_ONLY

    if qc in ("relationship", "multi_hop"):
        return GRAPH_ONLY

    if qc == "entity_lookup":
        resolved_types = {e["type"] for e in query_understanding.resolved_entities}
        if resolved_types & VECTOR_PREFERRED_ENTITY_LOOKUP_TYPES:
            return GRAPH_PLUS_VECTOR
        return GRAPH_ONLY

    if qc == "simple_fact":
        return GRAPH_ONLY

    return NONE_STRATEGY
