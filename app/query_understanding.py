"""Query Understanding — Section 12 of the blueprint.

Entirely deterministic/rule-based, no LLM call. The entity universe is
small and closed (one person's portfolio), so alias/canonical-name string
matching outperforms a general NER model on both cost and precision.
"""
import re
from dataclasses import dataclass, field

from db import get_connection

MAX_QUERY_LEN = 500  # interacts with Abuse Prevention (Section 24), not enforced fully here

GENERAL_PATTERNS = [
    r"^(hi|hello|hey)\b",
    r"\bwho are you\b",
    r"\bwhat are you\b",
    r"\bwhat can you do\b",
]

RELATIONSHIP_PATTERNS = [
    r"\brelate[sd]?\s+to\b",
    r"\bconnect(s|ion)?\b",
    r"\bwhat connects\b",
    r"\bhow does .* relate\b",
]

MULTI_HOP_PATTERNS = [
    r"\bboth\b",
    r"\band also\b",
    r".+\band\b.+\band\b.+",  # two "and"s is a decent heuristic for compound constraints
]

# Fuzzy/philosophical questions with no discrete entity/relationship to
# traverse — Section 11 routes these to VECTOR_ONLY, so they must NOT be
# forced into the "no entities resolved -> unknown" fallback below.
SEMANTIC_PATTERNS = [
    r"\bphilosophy\b",
    r"\bwhat do you think\b",
    r"\bwhy do you\b",
    r"\bhow do you approach\b",
    r"\bapproach to\b",
    r"\bopinion\b",
    r"\bbelieve\b",
    r"\blessons?\b.*\blearned\b",
]

ENTITY_LOOKUP_PATTERNS = [
    r"\btell me about\b",
    r"\bwhat is\b",
    r"\bwho is\b",
    r"\bdescribe\b",
]

SIMPLE_FACT_PATTERNS = [
    r"\bwhere\b",
    r"\bwhen\b",
    r"\bwhich\b",
    r"\bwhat\b",
    r"\bwho\b",
]

# Ellipsis/pronoun-reference opener heuristic (Section 25/26's
# context_dependent flag). Real pronoun resolution against session history
# is Query Understanding's job once Conversation Memory (Section 28) exists
# — that's a later phase, not built yet. This catches the OBVIOUS surface
# patterns ("what about that one") without pretending to resolve them; it
# exists so caching has a real (if partial) safety signal now rather than
# silently treating every query as cacheable until real session state lands.
CONTEXT_DEPENDENT_PATTERNS = [
    r"^(what|how) about\b",
    r"^and (what about|that|this|it)\b",
    r"^but (what about|that|this|it)\b",
    r"\bthat one\b",
    r"^(that|this|it) (one )?(too|as well)\b",
]

# Classes that don't depend on entity resolution — semantic is vector-only,
# general is a fixed blurb. Everything else needs at least one resolved
# entity or it's not answerable from this knowledge base.
ENTITY_OPTIONAL_CLASSES = {"semantic", "general"}


@dataclass
class QueryUnderstanding:
    raw_query: str
    normalized: str
    query_class: str  # simple_fact | entity_lookup | relationship | multi_hop | semantic | general | unknown
    resolved_entities: list = field(default_factory=list)  # [{id, type, canonical_name}]
    unresolved_mentions: list = field(default_factory=list)
    confidence: float = 0.0
    context_dependent: bool = False  # Section 25/26: disables response/semantic caching for this turn


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)  # strip control characters
    text = re.sub(r"\s+", " ", text)
    return text[:MAX_QUERY_LEN]


def _is_context_dependent(normalized: str) -> bool:
    return any(re.search(pat, normalized) for pat in CONTEXT_DEPENDENT_PATTERNS)


def _classify(normalized: str) -> str:
    for pat in GENERAL_PATTERNS:
        if re.search(pat, normalized):
            return "general"
    for pat in RELATIONSHIP_PATTERNS:
        if re.search(pat, normalized):
            return "relationship"
    for pat in MULTI_HOP_PATTERNS:
        if re.search(pat, normalized):
            return "multi_hop"
    for pat in SEMANTIC_PATTERNS:
        if re.search(pat, normalized):
            return "semantic"
    for pat in ENTITY_LOOKUP_PATTERNS:
        if re.search(pat, normalized):
            return "entity_lookup"
    for pat in SIMPLE_FACT_PATTERNS:
        if re.search(pat, normalized):
            return "simple_fact"
    return "unknown"


def _load_alias_index(conn):
    """canonical/alias string (lowercased) -> entity row. Built fresh per call;
    Phase 1 doesn't need the KV-cached index the blueprint describes for scale."""
    index = {}
    rows = conn.execute("SELECT id, type, canonical_name, aliases FROM entities WHERE status='active'")
    for row in rows:
        index[row["canonical_name"].lower()] = row
        import json

        aliases = json.loads(row["aliases"]) if row["aliases"] else []
        for alias in aliases:
            index[alias.lower()] = row
    return index


def _extract_entities(normalized: str, alias_index: dict):
    """Longest-match-first substring matching against the alias index."""
    resolved = {}
    for name in sorted(alias_index.keys(), key=len, reverse=True):
        if not name:
            continue
        pattern = r"\b" + re.escape(name) + r"\b"
        if re.search(pattern, normalized):
            row = alias_index[name]
            resolved[row["id"]] = {
                "id": row["id"],
                "type": row["type"],
                "canonical_name": row["canonical_name"],
            }
    return list(resolved.values())


def understand(raw_query: str, conn=None) -> QueryUnderstanding:
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        if not raw_query or not raw_query.strip():
            return QueryUnderstanding(raw_query=raw_query or "", normalized="", query_class="unknown", confidence=0.0)

        normalized = _normalize(raw_query)
        query_class = _classify(normalized)
        alias_index = _load_alias_index(conn)
        resolved = _extract_entities(normalized, alias_index)

        if not resolved and query_class != "unknown" and query_class not in ENTITY_OPTIONAL_CLASSES:
            # Ambiguous case: pattern matched a question shape but no known entity.
            # Default to the safer branch (Section 12) — treat as unknown rather than guess.
            query_class = "unknown"

        confidence = 1.0 if (resolved or query_class in ENTITY_OPTIONAL_CLASSES) else 0.0

        return QueryUnderstanding(
            raw_query=raw_query,
            normalized=normalized,
            query_class=query_class,
            resolved_entities=resolved,
            unresolved_mentions=[],
            confidence=confidence,
            context_dependent=_is_context_dependent(normalized),
        )
    finally:
        if owns_conn:
            conn.close()
