"""Cost Tracking / Observability persistence — Sections 37 & 39 of the
blueprint, made queryable rather than log-line-only (main.py's structured
stdout logging already covers the full per-request detail; this is a
lightweight rollup store on top of it).

Deliberately a SEPARATE sqlite file from ingestion/knowledge.db — that file
holds versioned, regenerated content (Section 48: entities/relationships/
chunks tied to a `knowledge_version`); this is runtime operational state
with a completely different lifecycle (grows with traffic, never diffed or
replayed as a "knowledge release"). Mixing the two would conflate a
content artifact with an operational log.

Best-effort only: a logging failure must never break the actual HTTP
response it's describing (Section 37: observability is instrumentation,
not a dependency the request path can fail on) — `record()` swallows its
own errors after printing a warning; `summary()` is read-only and lets
errors surface (it's called directly by an admin-facing endpoint, not from
inside the hot request path).
"""
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "runtime.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS request_log (
    request_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    route TEXT,
    status INTEGER,
    latency_ms REAL,
    provider TEXT,
    model TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    estimated_cost_usd REAL,
    cache_hit INTEGER,
    validation_status TEXT,
    degradation_state TEXT,
    used_llm INTEGER
);
"""


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def record(request_id, route=None, status=None, latency_ms=None, provider=None, model=None,
           tokens_in=None, tokens_out=None, estimated_cost_usd=None, cache_hit=None,
           validation_status=None, degradation_state=None, used_llm=None, **_ignored):
    """`**_ignored` absorbs any extra fields (e.g. stage_timings_ms) that
    aren't part of this rollup schema — the full per-stage breakdown stays
    in stdout logs only (Section 38's waterfall detail); this table is a
    summary store, not a full trace dump."""
    try:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO request_log "
                "(request_id, ts, route, status, latency_ms, provider, model, tokens_in, tokens_out, "
                " estimated_cost_usd, cache_hit, validation_status, degradation_state, used_llm) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    request_id, time.time(), route, status, latency_ms, provider, model, tokens_in, tokens_out,
                    estimated_cost_usd,
                    int(bool(cache_hit)) if cache_hit is not None else None,
                    validation_status, degradation_state,
                    int(bool(used_llm)) if used_llm is not None else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # best-effort — never break the request over a logging failure
        print(f"[cost_ledger] failed to record request {request_id}: {exc}")


def summary(since_hours: float = 24.0) -> dict:
    cutoff = time.time() - since_hours * 3600
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS requests, "
            "       SUM(CASE WHEN used_llm=1 THEN 1 ELSE 0 END) AS llm_calls, "
            "       SUM(CASE WHEN cache_hit=1 THEN 1 ELSE 0 END) AS cache_hits, "
            "       COALESCE(SUM(tokens_in), 0) AS total_tokens_in, "
            "       COALESCE(SUM(tokens_out), 0) AS total_tokens_out, "
            "       COALESCE(SUM(estimated_cost_usd), 0.0) AS total_estimated_cost_usd, "
            "       AVG(latency_ms) AS avg_latency_ms "
            "FROM request_log WHERE ts >= ?",
            (cutoff,),
        ).fetchone()
        by_provider = conn.execute(
            "SELECT provider, COUNT(*) AS calls, COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens "
            "FROM request_log WHERE ts >= ? AND provider IS NOT NULL GROUP BY provider",
            (cutoff,),
        ).fetchall()
        return {
            "since_hours": since_hours,
            "requests": row["requests"] or 0,
            "llm_calls": row["llm_calls"] or 0,
            "cache_hits": row["cache_hits"] or 0,
            "cache_hit_rate": round((row["cache_hits"] or 0) / row["requests"], 3) if row["requests"] else 0.0,
            "total_tokens_in": row["total_tokens_in"],
            "total_tokens_out": row["total_tokens_out"],
            "total_estimated_cost_usd": round(row["total_estimated_cost_usd"], 6),
            "avg_latency_ms": round(row["avg_latency_ms"], 1) if row["avg_latency_ms"] is not None else None,
            "by_provider": [dict(r) for r in by_provider],
        }
    finally:
        conn.close()
