"""Grounding — Section 29 of the blueprint.

    LLM response -> Claim identification -> Knowledge verification -> Supported?
        yes -> allow
        no  -> regenerate once (stricter reinforcement), then strip/fallback

Strict on entity-relationship claims ("X worked at Y", "X built Y") — these
must trace to a fact actually supplied to the model for THIS request (not
the whole graph, which is the whole point: this catches both fabrication
and evidence the model imagined instead of using what it was given). More
lenient on hedge/opinion phrasing, which Section 14's personality guardrail
already covers separately.

The regenerate-then-fallback orchestration (calling the LLM again) lives in
ask.py, not here — this module is pure claim-extraction and verification,
no LLM calls, fully unit-testable on fixed (answer_text, facts) inputs.
"""
import json
import re
from dataclasses import dataclass, field

from db import get_connection

HEDGE_MARKERS = [
    "i think", "i believe", "in my opinion", "it seems", "you might",
    "probably", "i'd guess", "honestly", "to be fair", "no problem",
]


@dataclass
class Claim:
    sentence: str
    entities_mentioned: list  # canonical names found in the sentence
    is_relationship_claim: bool


@dataclass
class GroundingResult:
    supported: bool
    unsupported_claims: list = field(default_factory=list)  # list[Claim]


def _split_sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _is_hedge(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(marker in lowered for marker in HEDGE_MARKERS)


def _alias_map_for_facts(subgraph_facts, conn=None) -> dict:
    """lowercased alias/canonical string -> canonical_name, scoped to just
    the entities that appear in the facts actually supplied this request
    (a handful of ids, one query) — not a full-graph alias index.

    Base case (canonical names) comes directly from the fact objects, no DB
    round-trip required — this is what keeps the module unit-testable on
    fixture data with synthetic ids (see eval_phase6.py). The DB lookup is
    pure enrichment on top: it adds known aliases (e.g. "Harshith" also
    matching "N Sai Harshith Varma") when the ids resolve to real rows; if
    they don't (synthetic fixtures), matching still works via canonical
    names alone.
    """
    alias_map = {}
    entity_ids = set()
    for fact in subgraph_facts:
        for entity in (fact.source, fact.target):
            alias_map[entity["canonical_name"].lower()] = entity["canonical_name"]
            entity_ids.add(entity["id"])

    if not entity_ids:
        return alias_map

    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        placeholders = ",".join("?" * len(entity_ids))
        rows = conn.execute(
            f"SELECT id, canonical_name, aliases FROM entities WHERE id IN ({placeholders})",
            list(entity_ids),
        ).fetchall()
        for row in rows:
            canonical = row["canonical_name"]
            aliases = json.loads(row["aliases"]) if row["aliases"] else []
            for alias in aliases:
                alias_map[alias.lower()] = canonical
        return alias_map
    finally:
        if owns_conn:
            conn.close()


def _entities_in_sentence(sentence: str, alias_map: dict) -> list:
    lowered = sentence.lower()
    found = set()
    for alias, canonical in alias_map.items():
        if alias and re.search(r"\b" + re.escape(alias) + r"\b", lowered):
            found.add(canonical)
    return list(found)


def identify_claims(answer_text: str, alias_map: dict) -> list:
    claims = []
    for sentence in _split_sentences(answer_text):
        if _is_hedge(sentence):
            claims.append(Claim(sentence=sentence, entities_mentioned=[], is_relationship_claim=False))
            continue
        mentioned = _entities_in_sentence(sentence, alias_map)
        claims.append(Claim(sentence=sentence, entities_mentioned=mentioned, is_relationship_claim=len(mentioned) >= 2))
    return claims


def _fact_pairs(subgraph_facts) -> set:
    """Unordered (entity_a, entity_b) pairs actually present in the facts
    supplied to the model for this request — grounding checks against what
    was given, not the whole graph."""
    return {frozenset({f.source["canonical_name"], f.target["canonical_name"]}) for f in subgraph_facts}


def check_grounding(answer_text: str, subgraph_facts, conn=None) -> GroundingResult:
    alias_map = _alias_map_for_facts(subgraph_facts, conn=conn)
    claims = identify_claims(answer_text, alias_map)
    supported_pairs = _fact_pairs(subgraph_facts)

    unsupported = []
    for claim in claims:
        if not claim.is_relationship_claim:
            continue
        mentioned = claim.entities_mentioned
        found_supported_pair = any(
            frozenset({mentioned[i], mentioned[j]}) in supported_pairs
            for i in range(len(mentioned))
            for j in range(i + 1, len(mentioned))
        )
        if not found_supported_pair:
            unsupported.append(claim)

    return GroundingResult(supported=(len(unsupported) == 0), unsupported_claims=unsupported)


def strip_unsupported(answer_text: str, unsupported_claims: list) -> str:
    """Removes just the unsupported sentences, keeping the rest intact."""
    unsupported_sentences = {c.sentence for c in unsupported_claims}
    kept = [s for s in _split_sentences(answer_text) if s not in unsupported_sentences]
    return " ".join(kept)


def guts_the_answer(original_text: str, stripped_text: str, min_remaining_fraction: float = 0.3) -> bool:
    original_words = len(original_text.split())
    if original_words == 0:
        return True
    return (len(stripped_text.split()) / original_words) < min_remaining_fraction
