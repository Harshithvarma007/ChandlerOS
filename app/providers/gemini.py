"""Gemini provider adapter — Section 18.

Auth, request shaping, response parsing, and error-code normalization for
Google's Generative Language API live here and nowhere else. No retry
policy, no routing decisions (Section 18: "what an adapter must never do").
"""
import json
import os

import requests
from dotenv import load_dotenv

from gateway_types import (
    CONTEXT_TOO_LONG,
    GatewayError,
    GatewayResponse,
    PROVIDER_ERROR,
    RATE_LIMITED,
    TIMEOUT,
    UNKNOWN,
)
from providers.base import ProviderCapabilities

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

API_KEY = os.environ.get("GEMINI_API_KEY")
ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
STREAM_ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"

# Per-model capability metadata (Section 16: "each adapter declares static
# capability metadata ... consumed by the Model Router"). avg_latency_ms is a
# rough starting estimate, not yet backed by observed data (Section 19 is
# what replaces this with real p50/p95 — Phase 9).
MODEL_CAPABILITIES = {
    "gemini-flash-latest": ProviderCapabilities(
        context_window=1_048_576, supports_streaming=True, supports_system_prompt=True,
        cost_per_1k_tokens=0.0, avg_latency_ms=1800,
    ),
    "gemini-pro-latest": ProviderCapabilities(
        context_window=1_048_576, supports_streaming=True, supports_system_prompt=True,
        cost_per_1k_tokens=0.0, avg_latency_ms=4500,
    ),
}


def capabilities(model: str) -> ProviderCapabilities:
    return MODEL_CAPABILITIES.get(model, MODEL_CAPABILITIES["gemini-flash-latest"])


def _messages_to_contents(messages):
    # Gemini has no distinct "system" role in this API version; a system
    # message is folded into the first user turn. Fine at Phase 3's scale
    # (single-turn requests) — multi-turn/system-role handling is revisited
    # once Conversation Memory (later phase) needs real multi-turn requests.
    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    return contents


def generate(request, model: str) -> GatewayResponse:
    if not API_KEY:
        raise GatewayError(UNKNOWN, "GEMINI_API_KEY not set in .env")

    endpoint = ENDPOINT_TEMPLATE.format(model=model)
    timeout_s = request.deadline_ms / 1000

    try:
        resp = requests.post(
            endpoint,
            params={"key": API_KEY},
            json={
                "contents": _messages_to_contents(request.messages),
                "generationConfig": {
                    "maxOutputTokens": request.max_tokens,
                    "temperature": request.temperature,
                },
            },
            timeout=timeout_s,
        )
    except requests.exceptions.Timeout as exc:
        raise GatewayError(TIMEOUT, f"Gemini request timed out after {timeout_s}s", raw=exc) from exc
    except requests.exceptions.RequestException as exc:
        raise GatewayError(PROVIDER_ERROR, f"Gemini request failed: {exc}", raw=exc) from exc

    if resp.status_code == 429:
        raise GatewayError(RATE_LIMITED, f"Gemini rate-limited: {resp.text}", raw=resp)
    if resp.status_code == 400 and "context" in resp.text.lower():
        raise GatewayError(CONTEXT_TOO_LONG, f"Gemini context too long: {resp.text}", raw=resp)
    if resp.status_code >= 500:
        raise GatewayError(PROVIDER_ERROR, f"Gemini server error {resp.status_code}: {resp.text}", raw=resp)
    if resp.status_code != 200:
        raise GatewayError(UNKNOWN, f"Gemini API error {resp.status_code}: {resp.text}", raw=resp)

    data = resp.json()
    try:
        candidate = data["candidates"][0]
        parts = candidate["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
        finish_reason = candidate.get("finishReason", "STOP").lower()
    except (KeyError, IndexError) as exc:
        raise GatewayError(UNKNOWN, f"Unexpected Gemini response shape: {data}", raw=data) from exc

    usage = data.get("usageMetadata", {})
    tokens_in = usage.get("promptTokenCount")
    tokens_out = usage.get("candidatesTokenCount")
    if tokens_in is None:  # provider didn't report usage — rough word-count estimate
        tokens_in = int(sum(len(m["content"].split()) for m in request.messages) / 0.75)
    if tokens_out is None:
        tokens_out = int(len(text.split()) / 0.75)

    return GatewayResponse(
        text=text,
        provider="gemini",
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=0.0,  # filled in by gateway.generate() from wall-clock timing
        finish_reason=finish_reason,
    )


def generate_stream(request, model: str):
    """Section 33: unified token-stream interface. Yields text deltas as
    they arrive over SSE. Raises GatewayError (mapped the same way as the
    non-streaming path) if the request fails before any delta is produced;
    a failure *after* streaming has started is the caller's (gateway.py's)
    problem to handle gracefully, per Section 33 — this generator just lets
    the underlying exception propagate mid-iteration."""
    if not API_KEY:
        raise GatewayError(UNKNOWN, "GEMINI_API_KEY not set in .env")

    endpoint = STREAM_ENDPOINT_TEMPLATE.format(model=model)
    timeout_s = request.deadline_ms / 1000

    try:
        resp = requests.post(
            endpoint,
            params={"key": API_KEY, "alt": "sse"},
            json={
                "contents": _messages_to_contents(request.messages),
                "generationConfig": {
                    "maxOutputTokens": request.max_tokens,
                    "temperature": request.temperature,
                },
            },
            timeout=timeout_s,
            stream=True,
        )
    except requests.exceptions.Timeout as exc:
        raise GatewayError(TIMEOUT, f"Gemini stream request timed out after {timeout_s}s", raw=exc) from exc
    except requests.exceptions.RequestException as exc:
        raise GatewayError(PROVIDER_ERROR, f"Gemini stream request failed: {exc}", raw=exc) from exc

    if resp.status_code == 429:
        raise GatewayError(RATE_LIMITED, f"Gemini rate-limited: {resp.text}", raw=resp)
    if resp.status_code >= 500:
        raise GatewayError(PROVIDER_ERROR, f"Gemini server error {resp.status_code}: {resp.text}", raw=resp)
    if resp.status_code != 200:
        raise GatewayError(UNKNOWN, f"Gemini API error {resp.status_code}: {resp.text}", raw=resp)

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        try:
            parts = event["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            continue
        for part in parts:
            text = part.get("text", "")
            if text:
                yield text
