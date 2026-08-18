"""Vector RAG retrieval — Section 10 of the blueprint.

No Vectorize/dedicated vector DB at this scale (Section 48 decision applies
here too — a few dozen chunks, brute-force cosine similarity in Python is
both simpler and faster than standing up an ANN index). Chunks and their
embeddings live in the same knowledge.db `chunks` table build_chunks.py
writes.
"""
import json
import math
from dataclasses import dataclass, field

from db import get_connection
from embeddings import EMBEDDING_MODEL, embed

TOP_K = 10

# Deterministic rerank weights (Section 10: "not a model where a formula
# suffices"). Applied on top of raw cosine similarity.
ENTITY_OVERLAP_BOOST = 0.08
SOURCE_TYPE_PRIORITY = {
    "medium_post": 0.03,   # long-form authored writing — highest signal for "what was said"
    "github_readme": 0.0,
}


@dataclass
class ChunkResult:
    chunk_id: str
    text: str
    source_ref: str
    entity_refs: list
    similarity: float
    score: float  # similarity + deterministic rerank boosts


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_chunks(query_text: str, resolved_entity_ids=None, knowledge_version=None, conn=None) -> list:
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        resolved_entity_ids = set(resolved_entity_ids or [])
        rows = conn.execute(
            "SELECT id, source_ref, entity_refs, text, embedding_model, embedding, knowledge_version FROM chunks"
        ).fetchall()
        if not rows:
            return []

        # Filtering (Section 10): never mix embedding models or stale knowledge_versions.
        rows = [r for r in rows if r["embedding_model"] == EMBEDDING_MODEL]
        if knowledge_version:
            rows = [r for r in rows if r["knowledge_version"] == knowledge_version]
        if not rows:
            return []

        query_vector = embed(query_text)

        results = []
        for row in rows:
            chunk_vector = json.loads(row["embedding"])
            similarity = _cosine(query_vector, chunk_vector)

            entity_refs = json.loads(row["entity_refs"]) if row["entity_refs"] else []
            overlap = bool(resolved_entity_ids.intersection(entity_refs))
            source_type = row["source_ref"].split(":", 1)[0]

            score = similarity
            if overlap:
                score += ENTITY_OVERLAP_BOOST
            score += SOURCE_TYPE_PRIORITY.get(source_type, 0.0)

            results.append(
                ChunkResult(
                    chunk_id=row["id"],
                    text=row["text"],
                    source_ref=row["source_ref"],
                    entity_refs=entity_refs,
                    similarity=similarity,
                    score=score,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:TOP_K]
    finally:
        if owns_conn:
            conn.close()
