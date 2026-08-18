"""Internal structured response schema — Section 32 of the blueprint.

Never exposed as raw JSON to the end user — the LLM is asked for natural
prose (forcing strict JSON generation adds format-compliance risk and token
overhead for no user-facing benefit); this schema is assembled AROUND that
prose by the pipeline afterward, from what the Context Builder actually
supplied and what Grounding/Output Validation confirmed — not extracted
from a forced-JSON generation. Hidden reasoning is never included: no
chain-of-thought, no "let me think" scaffolding.

This is what makes automated grading (Section 42, Phase 10) and
observability (Sections 37-38, Phase 9) tractable later — a judge or a
trace viewer can check `evidence` against `answer` mechanically. Nothing
consumes this yet; it's built now so those phases have a stable contract
to land on rather than inventing one under time pressure later.
"""
import uuid
from dataclasses import asdict, dataclass

from prompt import PROMPT_VERSION


@dataclass
class EvidenceItem:
    source_ref: str
    type: str  # "graph" | "vector"
    confidence: float


@dataclass
class StructuredResponse:
    answer: str
    evidence: list
    confidence: float
    personality_policy_snapshot: dict
    metadata: dict
    validation_status: str  # "passed" | "regenerated" | "fallback"

    def to_dict(self) -> dict:
        return asdict(self)


def _graph_evidence_items(subgraph_facts) -> list:
    items = []
    for fact in subgraph_facts:
        for ev in fact.evidence:
            items.append(EvidenceItem(source_ref=ev["source_ref"], type="graph", confidence=fact.confidence))
    return items


def _vector_evidence_items(chunks) -> list:
    return [EvidenceItem(source_ref=c.source_ref, type="vector", confidence=min(1.0, max(0.0, c.score))) for c in chunks]


def _aggregate_confidence(evidence_items, validation_status) -> float:
    base = (sum(e.confidence for e in evidence_items) / len(evidence_items)) if evidence_items else 0.5
    if validation_status == "fallback":
        return 0.0
    if validation_status == "regenerated":
        return round(base * 0.85, 3)  # needed a second attempt — slightly less confident even though it passed
    return round(base, 3)


def build_structured_response(
    answer_text: str,
    subgraph_facts,
    chunks,
    policy,
    query_class: str,
    retrieval_strategy: str,
    provider: str,
    model: str,
    knowledge_version: str,
    cache_hit: bool,
    context_truncated: bool,
    validation_status: str,
    trace_id: str = None,
) -> StructuredResponse:
    evidence_items = _graph_evidence_items(subgraph_facts) + _vector_evidence_items(chunks)

    return StructuredResponse(
        answer=answer_text,
        evidence=[asdict(e) for e in evidence_items],
        confidence=_aggregate_confidence(evidence_items, validation_status),
        personality_policy_snapshot=asdict(policy) if policy else {},
        metadata={
            "query_class": query_class,
            "retrieval_strategy": retrieval_strategy,
            "provider": provider,
            "model": model,
            "knowledge_version": knowledge_version,
            "prompt_version": PROMPT_VERSION,
            "personality_version": policy.personality_version if policy else None,
            "cache_hit": cache_hit,
            "context_truncated": context_truncated,
            "validation_status": validation_status,
            "trace_id": trace_id or str(uuid.uuid4()),
        },
        validation_status=validation_status,
    )
