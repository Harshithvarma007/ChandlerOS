"""Embedding adapter — single pinned model, versioned (Section 10/45).

Mixing embedding-model outputs in one index silently degrades retrieval, so
the model name is a hard constant here, not an env override like the
generation model — changing it requires re-embedding every chunk.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API_KEY = os.environ.get("GEMINI_API_KEY")
EMBEDDING_MODEL = "gemini-embedding-001"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent"


class EmbeddingError(RuntimeError):
    pass


def embed(text: str, timeout: float = 30.0) -> list:
    if not API_KEY:
        raise EmbeddingError("GEMINI_API_KEY not set in .env")

    try:
        resp = requests.post(
            ENDPOINT,
            params={"key": API_KEY},
            json={"content": {"parts": [{"text": text}]}},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        raise EmbeddingError(f"Embedding request failed: {exc}") from exc

    if resp.status_code != 200:
        raise EmbeddingError(f"Embedding API error {resp.status_code}: {resp.text}")

    data = resp.json()
    try:
        return data["embedding"]["values"]
    except KeyError as exc:
        raise EmbeddingError(f"Unexpected embedding response shape: {data}") from exc
