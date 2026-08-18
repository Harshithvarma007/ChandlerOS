"""Chunking + embedding pipeline — Section 10 of the blueprint, extends ingestion.

Covers the long-form content Graph RAG can't: blog posts (already linked to
Blog entities in the graph) and project READMEs (linked to Project entities).
Semantic/structural chunking (split on markdown headings and paragraphs, not
fixed-width windows), ~300-500 tokens per chunk, ~12% overlap.

Chunks are written into the same knowledge.db (Section 48: no dedicated
graph/vector DB needed at this scale) in a new `chunks` table. Only that
table is touched — entities/relationships/evidence from build_graph.py are
left alone, so this can be re-run independently.
"""
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from embeddings import EMBEDDING_MODEL, EmbeddingError, embed  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "knowledge.db")
RAW_DIR = os.path.join(os.path.dirname(__file__), "raw")
KNOWLEDGE_VERSION = "2026.08.0"

TARGET_WORDS = 380  # ~300-500 tokens at ~0.75-0.8 tokens/word for English prose
OVERLAP_WORDS = 45  # ~12%
MIN_CHUNK_WORDS = 40  # drop trailing fragments smaller than this


EMBED_PACING_SECONDS = 2.0  # spread requests out to avoid bursting the free-tier RPM limit
EMBED_RETRY_BACKOFFS = [15, 30, 60]  # seconds; batch-job-only, not the real retry policy (Phase 4)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def embed_with_retry(text: str):
    for attempt, backoff in enumerate([0] + EMBED_RETRY_BACKOFFS):
        if backoff:
            print(f"    [retry] rate-limited, waiting {backoff}s before retry {attempt}/{len(EMBED_RETRY_BACKOFFS)}...")
            time.sleep(backoff)
        try:
            return embed(text)
        except EmbeddingError as exc:
            if "429" in str(exc) and attempt < len(EMBED_RETRY_BACKOFFS):
                continue
            raise


def _split_oversized_block(para: str):
    """A single block (no blank lines inside it — common in dense READMEs:
    long bullet lists, code-free prose) can still exceed TARGET_WORDS after
    the heading/paragraph split. Fall back to sentence boundaries so no
    chunk grows unbounded; this is still structural, just one level finer
    than paragraph splitting."""
    if len(para.split()) <= TARGET_WORDS:
        return [para]
    sentences = re.split(r"(?<=[.!?])\s+", para)
    if len(sentences) <= 1:
        return [para]  # no sentence boundary found (e.g. a code block) — leave it whole
    return sentences


def split_into_blocks(text: str):
    """Split on markdown headings first, then paragraph breaks — structural,
    not fixed-width. Oversized paragraphs get a sentence-level fallback split
    so the packer in chunk_blocks() always has small-enough pieces to work
    with (see _split_oversized_block)."""
    heading_split = re.split(r"\n(?=#{1,6}\s)", text)
    blocks = []
    for section in heading_split:
        for para in re.split(r"\n\s*\n", section):
            para = para.strip()
            if para:
                blocks.extend(_split_oversized_block(para))
    return blocks


def chunk_blocks(blocks):
    """Greedily pack blocks into ~TARGET_WORDS chunks with word-level overlap
    carried into the next chunk. Never splits a block mid-sentence."""
    chunks = []
    current_words = []

    def flush(carry_overlap=True):
        if len(current_words) < MIN_CHUNK_WORDS and chunks:
            # too small to stand alone — merge into previous chunk instead
            chunks[-1] = chunks[-1] + " " + " ".join(current_words)
            return []
        if current_words:
            chunks.append(" ".join(current_words))
        if carry_overlap and current_words:
            return current_words[-OVERLAP_WORDS:]
        return []

    for block in blocks:
        block_words = block.split()
        if len(current_words) + len(block_words) > TARGET_WORDS and current_words:
            current_words = flush()
        current_words.extend(block_words)

    if current_words:
        if len(current_words) < MIN_CHUNK_WORDS and chunks:
            chunks[-1] = chunks[-1] + " " + " ".join(current_words)
        else:
            chunks.append(" ".join(current_words))

    return chunks


def load_blog_sources(conn):
    """Blog entities are already in the graph, tagged with a date. Match that
    date against posts_parsed.json to pull the full post text."""
    blog_rows = conn.execute("SELECT id, canonical_name, attributes FROM entities WHERE type='Blog'").fetchall()
    date_to_blog = {}
    for row in blog_rows:
        attrs = json.loads(row[2]) if row[2] else {}
        date = attrs.get("date")
        if date:
            date_to_blog[date] = {"id": row[0], "canonical_name": row[1]}

    with open(os.path.join(RAW_DIR, "medium", "posts_parsed.json")) as f:
        posts = json.load(f)

    sources = []
    for post in posts:
        date = post.get("date")
        if date in date_to_blog and post.get("text"):
            blog = date_to_blog[date]
            sources.append(
                {
                    "text": post["text"],
                    "entity_ids": [blog["id"]],
                    "source_ref": f"medium_post:medium/posts_parsed.json#{date}",
                    "source_type": "medium_post",
                }
            )
    return sources


def load_readme_sources(conn):
    """Project entities with a linked README (via entity-level evidence rows
    build_graph.py already wrote)."""
    rows = conn.execute(
        """
        SELECT p.id, p.canonical_name, ev.source_ref
        FROM entities p
        JOIN evidence ev ON ev.entity_id = p.id
            AND ev.source_type = 'github_repo'
            AND ev.source_ref LIKE 'github/readmes/%'
        WHERE p.type = 'Project'
        """
    ).fetchall()

    sources = []
    for entity_id, canonical_name, source_ref in rows:
        path = os.path.join(RAW_DIR, source_ref)
        if not os.path.exists(path):
            print(f"[WARN] README not found for {canonical_name}: {path}")
            continue
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        sources.append(
            {
                "text": text,
                "entity_ids": [entity_id],
                "source_ref": f"github_readme:{source_ref}",
                "source_type": "github_readme",
            }
        )
    return sources


def build(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            source_ref TEXT NOT NULL,
            entity_refs TEXT,
            text TEXT NOT NULL,
            token_count INTEGER,
            embedding_model TEXT NOT NULL,
            embedding TEXT NOT NULL,
            knowledge_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("DELETE FROM chunks")

    sources = load_blog_sources(conn) + load_readme_sources(conn)
    print(f"Loaded {len(sources)} long-form sources to chunk "
          f"({sum(1 for s in sources if s['source_type']=='medium_post')} blog posts, "
          f"{sum(1 for s in sources if s['source_type']=='github_readme')} READMEs)")

    chunk_id = 0
    embed_failures = 0
    for source in sources:
        blocks = split_into_blocks(source["text"])
        pieces = chunk_blocks(blocks)
        for piece in pieces:
            chunk_id += 1
            cid = f"chunk_{chunk_id:04d}"
            token_estimate = int(len(piece.split()) / 0.75)  # rough words->tokens
            try:
                vector = embed_with_retry(piece)
            except EmbeddingError as exc:
                embed_failures += 1
                print(f"[WARN] embedding failed for {cid} ({source['source_ref']}): {exc}")
                continue
            time.sleep(EMBED_PACING_SECONDS)
            conn.execute(
                """
                INSERT INTO chunks (id, source_ref, entity_refs, text, token_count,
                                     embedding_model, embedding, knowledge_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    source["source_ref"],
                    json.dumps(source["entity_ids"]),
                    piece,
                    token_estimate,
                    EMBEDDING_MODEL,
                    json.dumps(vector),
                    KNOWLEDGE_VERSION,
                    now_iso(),
                ),
            )
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"\nWrote {n} chunks (embedding model: {EMBEDDING_MODEL}). Failures: {embed_failures}")
    return n


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    build(conn)
    conn.close()
