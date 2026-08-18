"""Shared SQLite connection to the knowledge graph (Phase 0 output).

No dedicated graph DB per the blueprint (Section 48) — the graph lives in
ingestion/knowledge.db and is queried relationally.
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "ingestion", "knowledge.db")


def get_connection():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"knowledge.db not found at {DB_PATH} — run ingestion/build_graph.py first"
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_knowledge_version(conn=None) -> str:
    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute("SELECT knowledge_version FROM entities LIMIT 1").fetchone()
        return row["knowledge_version"] if row else "unknown"
    finally:
        if owns_conn:
            conn.close()
