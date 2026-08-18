"""Semantic Caching — Section 26 of the blueprint.

Two phrasings of the same question ("what projects have you built with
Python" / "which of your projects use Python") should share a cache entry
— literal-string caching misses this. Reuses the SAME embedding model as
Vector RAG (Section 10) rather than adding a second one.

Small in-memory structure given the scale (Section 26: "Vectorize, or a
small in-memory/KV structure given the scale" — a portfolio site's query
volume doesn't need an ANN index for a few hundred cached entries).

Erring toward *stricter* by default (Section 26): a false cache hit
(wrong-but-plausible cached answer) is worse than a cache miss (a normal
LLM call), so the similarity threshold starts conservative.
"""
import math
import time
from dataclasses import dataclass, field

from embeddings import EMBEDDING_MODEL, embed

SIMILARITY_THRESHOLD = 0.93
TTL_SECONDS = 6 * 3600  # hours-to-a-day per Section 26, not permanent


@dataclass
class _CacheEntry:
    normalized_query: str
    embedding: list
    answer: str
    knowledge_version: str
    personality_version: str
    structured_response: object
    created_at: float = field(default_factory=time.monotonic)


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticCache:
    def __init__(self, threshold: float = SIMILARITY_THRESHOLD, ttl_seconds: float = TTL_SECONDS):
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self._entries = []
        self.hits = 0
        self.misses = 0

    def _prune_expired(self):
        now = time.monotonic()
        self._entries = [e for e in self._entries if now - e.created_at < self.ttl_seconds]

    def lookup(self, raw_query: str, knowledge_version: str, personality_version: str, context_dependent: bool,
               injection_flagged: bool):
        """Metadata gating (Section 26): a semantic match only counts if
        knowledge_version, personality_version, and context_dependent=false
        all match. Injection-flagged or context-dependent queries never hit
        — a cached answer must never be returned to a query pattern designed
        to probe or manipulate the system."""
        if context_dependent or injection_flagged:
            self.misses += 1
            return None

        self._prune_expired()
        if not self._entries:
            self.misses += 1
            return None

        query_vector = embed(raw_query)
        best_entry = None
        best_score = 0.0
        for entry in self._entries:
            if entry.knowledge_version != knowledge_version or entry.personality_version != personality_version:
                continue
            score = _cosine(query_vector, entry.embedding)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is not None and best_score >= self.threshold:
            self.hits += 1
            return best_entry.answer, best_entry.structured_response
        self.misses += 1
        return None

    def store(self, raw_query: str, answer: str, knowledge_version: str, personality_version: str,
              structured_response, context_dependent: bool, injection_flagged: bool):
        if context_dependent or injection_flagged:
            return  # never cache what must never be served back from cache
        vector = embed(raw_query)
        self._entries.append(_CacheEntry(
            normalized_query=raw_query.strip().lower(),
            embedding=vector,
            answer=answer,
            knowledge_version=knowledge_version,
            personality_version=personality_version,
            structured_response=structured_response,
        ))

    def invalidate_all(self):
        """Explicit flush (Section 26) — call on every knowledge release and
        every personality-policy change, not relying on TTL alone."""
        self._entries.clear()

    def stats(self):
        total = self.hits + self.misses
        return {
            "size": len(self._entries), "hits": self.hits, "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
            "embedding_model": EMBEDDING_MODEL,
        }


_default_cache = SemanticCache()


def get_semantic_cache() -> SemanticCache:
    return _default_cache
