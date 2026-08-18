"""Context Builder — Section 13 of the blueprint.

Merges Graph RAG facts and Vector RAG chunks into one evidence-tagged,
token-budgeted TRUSTED_KNOWLEDGE block. No LLM calls here — pure
deterministic ranking/formatting, unit-testable on fixed inputs.

Graph facts get priority (Section 13: "graph facts preferred for the same
claim, vector kept if it adds detail the graph doesn't") — they fill their
own sub-budget first, vector chunks fill the remainder. True semantic
conflict detection (a vector chunk implying something the graph
contradicts) needs judgment a formula can't provide; deferred to Output
Validation (Section 31, Phase 6) rather than faked here.

Token-budgeted per Section 27 (token_budget.py) — graph and vector each get
a share of the trusted_knowledge budget, estimated via the same word-count
heuristic used across the pipeline (no offline tokenizer available).
"""
from dataclasses import dataclass, field

from token_budget import BUDGET_TOKENS, GRAPH_SHARE, VECTOR_SHARE, estimate_tokens

MAX_GRAPH_TOKENS = int(BUDGET_TOKENS["trusted_knowledge"] * GRAPH_SHARE)
MAX_VECTOR_TOKENS = int(BUDGET_TOKENS["trusted_knowledge"] * VECTOR_SHARE)


@dataclass
class ContextBlock:
    trusted_knowledge_text: str
    evidence_refs: list = field(default_factory=list)
    fact_count: int = 0
    chunk_count: int = 0
    truncated_by_budget: bool = False


def _format_fact(fact) -> str:
    lines = [f"- {fact.source['canonical_name']} {fact.rel_type} {fact.target['canonical_name']} "
             f"(confidence={fact.confidence:.2f}, status={fact.status})"]
    for ev in fact.evidence:
        excerpt = f' — "{ev["excerpt"]}"' if ev["excerpt"] else ""
        lines.append(f'    evidence: {ev["source_type"]}:{ev["source_ref"]}{excerpt}')
    return "\n".join(lines)


def _format_chunk(chunk) -> str:
    return f'- ({chunk.source_ref}, relevance={chunk.score:.2f}):\n    "{chunk.text}"'


def build_context(subgraph, query_understanding, chunks=None) -> ContextBlock:
    chunks = chunks or []
    resolved_ids = {e["id"] for e in query_understanding.resolved_entities}

    def rank_key(fact):
        overlap = int(fact.source["id"] in resolved_ids) + int(fact.target["id"] in resolved_ids)
        return (-overlap, -fact.confidence, fact.status != "active")

    ranked_facts = sorted(subgraph.facts, key=rank_key)
    # Conflict resolution for disputed relationships (Section 8/13): surfaced,
    # never silently dropped, but ranked below active facts (rank_key already
    # penalizes status != "active").

    graph_lines = []
    evidence_refs = []
    used_graph_tokens = 0
    truncated = False
    fact_count = 0

    for fact in ranked_facts:
        block = _format_fact(fact)
        block_tokens = estimate_tokens(block)
        if used_graph_tokens + block_tokens > MAX_GRAPH_TOKENS:
            truncated = True
            break  # drop whole low-rank items rather than cut one in half
        graph_lines.append(block)
        used_graph_tokens += block_tokens
        fact_count += 1
        for ev in fact.evidence:
            evidence_refs.append(f'{ev["source_type"]}:{ev["source_ref"]}')

    for note in subgraph.entity_notes:
        for ev in note["evidence"]:
            ref = f'{ev["source_type"]}:{ev["source_ref"]}'
            if ref not in evidence_refs:
                evidence_refs.append(ref)

    vector_lines = []
    used_vector_tokens = 0
    chunk_count = 0
    seen_source_refs = set()

    for chunk in chunks:  # already ranked by vector_retrieval.py
        if chunk.source_ref in seen_source_refs:
            continue  # dedupe: same source, different chunk of it already included is fine; exact repeat isn't
        block = _format_chunk(chunk)
        block_tokens = estimate_tokens(block)
        if used_vector_tokens + block_tokens > MAX_VECTOR_TOKENS:
            truncated = True
            continue  # a lower-ranked chunk might still fit; don't break, just skip
        vector_lines.append(block)
        used_vector_tokens += block_tokens
        chunk_count += 1
        seen_source_refs.add(chunk.source_ref)
        ref = chunk.source_ref
        if ref not in evidence_refs:
            evidence_refs.append(ref)

    sections = []
    if graph_lines:
        sections.append("GRAPH_FACTS:\n" + "\n".join(graph_lines))
    if vector_lines:
        sections.append("RELATED_CONTENT:\n" + "\n".join(vector_lines))
    text = "\n\n".join(sections)

    return ContextBlock(
        trusted_knowledge_text=text,
        evidence_refs=evidence_refs,
        fact_count=fact_count,
        chunk_count=chunk_count,
        truncated_by_budget=truncated or subgraph.truncated,
    )
