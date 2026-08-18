"""Groq provider adapter — Section 18.

OpenAI-compatible chat completions API. Second provider proving the Gateway
abstraction actually holds: ask.py, gateway.py, model_router.py needed zero
changes to support this — only this file plus a registry line and a
router_config.json entry (Engineering Principle 11).

Note: Groq's gpt-oss models are reasoning models — they spend completion
tokens on a "reasoning" field before "content". A too-small max_tokens can
exhaust the budget mid-reasoning and return empty content with
finish_reason="length"; that's surfaced as CONTEXT_TOO_LONG-adjacent rather
than silently returned as an empty answer.
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

API_KEY = os.environ.get("GROQ_API_KEY")
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

MODEL_CAPABILITIES = {
    "openai/gpt-oss-20b": ProviderCapabilities(
        context_window=131072, supports_streaming=True, supports_system_prompt=True,
        cost_per_1k_tokens=0.0, avg_latency_ms=900,  # Groq's whole pitch is inference speed
    ),
    "openai/gpt-oss-120b": ProviderCapabilities(
        context_window=131072, supports_streaming=True, supports_system_prompt=True,
        cost_per_1k_tokens=0.0, avg_latency_ms=1500,
    ),
}


def capabilities(model: str) -> ProviderCapabilities:
    return MODEL_CAPABILITIES.get(model, MODEL_CAPABILITIES["openai/gpt-oss-20b"])


def _messages_to_openai_format(messages):
    return [{"role": m["role"], "content": m["content"]} for m in messages]


def generate(request, model: str) -> GatewayResponse:
    if not API_KEY:
        raise GatewayError(UNKNOWN, "GROQ_API_KEY not set in .env")

    timeout_s = request.deadline_ms / 1000

    try:
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": model,
                "messages": _messages_to_openai_format(request.messages),
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            },
            timeout=timeout_s,
        )
    except requests.exceptions.Timeout as exc:
        raise GatewayError(TIMEOUT, f"Groq request timed out after {timeout_s}s", raw=exc) from exc
    except requests.exceptions.RequestException as exc:
        raise GatewayError(PROVIDER_ERROR, f"Groq request failed: {exc}", raw=exc) from exc

    if resp.status_code == 429:
        raise GatewayError(RATE_LIMITED, f"Groq rate-limited: {resp.text}", raw=resp)
    if resp.status_code == 400 and "context" in resp.text.lower():
        raise GatewayError(CONTEXT_TOO_LONG, f"Groq context too long: {resp.text}", raw=resp)
    if resp.status_code >= 500:
        raise GatewayError(PROVIDER_ERROR, f"Groq server error {resp.status_code}: {resp.text}", raw=resp)
    if resp.status_code != 200:
        raise GatewayError(UNKNOWN, f"Groq API error {resp.status_code}: {resp.text}", raw=resp)

    data = resp.json()
    try:
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
        finish_reason = choice.get("finish_reason", "stop")
    except (KeyError, IndexError) as exc:
        raise GatewayError(UNKNOWN, f"Unexpected Groq response shape: {data}", raw=data) from exc

    if not text and finish_reason == "length":
        # Reasoning-token budget exhausted before any visible content — not a
        # silent empty answer, surfaced as a real (retriable) failure.
        raise GatewayError(
            CONTEXT_TOO_LONG,
            "Groq exhausted max_tokens on internal reasoning before producing content "
            "(gpt-oss models spend completion tokens on a hidden reasoning pass)",
            raw=data,
        )

    usage = data.get("usage", {})
    tokens_in = usage.get("prompt_tokens")
    tokens_out = usage.get("completion_tokens")
    if tokens_in is None:
        tokens_in = int(sum(len(m["content"].split()) for m in request.messages) / 0.75)
    if tokens_out is None:
        tokens_out = int(len(text.split()) / 0.75)

    return GatewayResponse(
        text=text,
        provider="groq",
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=0.0,  # filled in by gateway.generate()
        finish_reason=finish_reason,
    )


def generate_stream(request, model: str):
    """Section 33: unified token-stream interface. Yields only `content`
    deltas — gpt-oss models stream a separate `reasoning` field, which is
    hidden reasoning (Section 32: "explicitly never exposed... reasoning
    text is a place leaked instructions could hide") and is deliberately
    never yielded here, streaming or not."""
    if not API_KEY:
        raise GatewayError(UNKNOWN, "GROQ_API_KEY not set in .env")

    timeout_s = request.deadline_ms / 1000

    try:
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": model,
                "messages": _messages_to_openai_format(request.messages),
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "stream": True,
            },
            timeout=timeout_s,
            stream=True,
        )
    except requests.exceptions.Timeout as exc:
        raise GatewayError(TIMEOUT, f"Groq stream request timed out after {timeout_s}s", raw=exc) from exc
    except requests.exceptions.RequestException as exc:
        raise GatewayError(PROVIDER_ERROR, f"Groq stream request failed: {exc}", raw=exc) from exc

    if resp.status_code == 429:
        raise GatewayError(RATE_LIMITED, f"Groq rate-limited: {resp.text}", raw=resp)
    if resp.status_code >= 500:
        raise GatewayError(PROVIDER_ERROR, f"Groq server error {resp.status_code}: {resp.text}", raw=resp)
    if resp.status_code != 200:
        raise GatewayError(UNKNOWN, f"Groq API error {resp.status_code}: {resp.text}", raw=resp)

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload.strip() == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        try:
            delta = event["choices"][0].get("delta", {})
        except (KeyError, IndexError):
            continue
        text = delta.get("content")
        if text:
            yield text
