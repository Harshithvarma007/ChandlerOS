"""LLM Gateway — Section 16 of the blueprint, now with Retry Strategy
(Section 21) and Circuit Breaker (Section 20) integration.

    Application -> LLM Gateway -> Model Router -> Provider Adapter -> LLM Provider

The application (ask.py) talks only to this module's interface — it never
imports a provider SDK/adapter directly. Types (GatewayRequest/Response/
Error) live in gateway_types.py so adapters can depend on them without a
circular import back through this orchestration module.

Retry policy (Section 21):
  - Retriable: TIMEOUT, PROVIDER_ERROR, and RATE_LIMITED — but RATE_LIMITED
    is only useful to retry against a *different* provider/model, never the
    same one (that's quota abuse). This module doesn't special-case that:
    the `tried` set below already prevents re-attempting an exact
    (provider, model) pair within one request, so a rate-limited provider
    with no healthy alternative correctly exhausts retries rather than
    hammering itself.
  - Not retriable: CONTEXT_TOO_LONG and UNKNOWN (likely a malformed request
    or a real bug) — raised immediately, no retry.
  - Max 3 attempts total across the whole request, not per provider.
  - Exponential backoff with full jitter (base 200ms, 2x multiplier),
    skipped entirely if the deadline can't plausibly absorb it.
  - Every failure feeds the Circuit Breaker *before* the next attempt picks
    a provider, so a provider that keeps failing trips its own breaker
    quickly rather than continuing to absorb retried traffic.
"""
import random
import time
from dataclasses import replace

from circuit_breaker import get_breaker
from gateway_types import (  # noqa: F401 — re-exported for callers importing from gateway
    CONTEXT_TOO_LONG,
    GatewayError,
    GatewayRequest,
    GatewayResponse,
    NoProviderAvailable,
    PROVIDER_ERROR,
    RATE_LIMITED,
    TIMEOUT,
    UNKNOWN,
)
from provider_health import get_tracker
from providers.registry import get_adapter

MAX_ATTEMPTS = 3
RETRY_BASE_MS = 200
MIN_BUDGET_FOR_RETRY_MS = 500  # Section 21: skip a retry if less than this remains


def _backoff_delay_ms(attempt: int) -> float:
    """Full jitter, base 200ms, 2x multiplier. attempt is 1-indexed; no
    delay before the first attempt."""
    max_delay = RETRY_BASE_MS * (2 ** (attempt - 2))
    return random.uniform(0, max_delay)


def generate(request: GatewayRequest, config=None, tracker=None, breaker=None, budget=None) -> GatewayResponse:
    from model_router import select_candidates  # local import: avoids a load-order dependency on router_config.json

    tracker = tracker or get_tracker()
    breaker = breaker or get_breaker()

    tried = set()
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if budget is not None and budget.remaining_ms() < MIN_BUDGET_FOR_RETRY_MS:
            break  # not enough budget left to plausibly complete another round trip

        candidates = select_candidates(request.task_complexity_hint, config=config, tracker=tracker, breaker=breaker,
                                        estimated_prompt_tokens=request.estimated_prompt_tokens)
        candidates = [c for c in candidates if (c[1], c[2]) not in tried]

        provider_name = model_name = None
        for _, cand_provider, cand_model in candidates:
            if breaker.allow_request(cand_provider):
                provider_name, model_name = cand_provider, cand_model
                break
            # HALF_OPEN trial already claimed for this provider — try the
            # next-best candidate instead of queuing behind it (Section 20).

        if provider_name is None:
            break  # no candidate both unfilled-this-request and allowed right now

        if attempt > 1:
            backoff_ms = _backoff_delay_ms(attempt)
            if budget is not None:
                backoff_ms = min(backoff_ms, max(0.0, budget.remaining_ms() - MIN_BUDGET_FOR_RETRY_MS))
            if backoff_ms > 0:
                time.sleep(backoff_ms / 1000)

        attempt_deadline_ms = request.deadline_ms
        if budget is not None:
            attempt_deadline_ms = min(attempt_deadline_ms, int(budget.remaining_ms()))
        attempt_request = replace(request, deadline_ms=attempt_deadline_ms)

        tried.add((provider_name, model_name))
        adapter = get_adapter(provider_name)

        start = time.monotonic()
        try:
            response = adapter.generate(attempt_request, model_name)
        except GatewayError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            tracker.record_failure(provider_name, exc.normalized_code, latency_ms)
            breaker.record_failure(provider_name)
            last_error = exc
            if not exc.retriable:
                raise
            continue
        else:
            latency_ms = (time.monotonic() - start) * 1000
            tracker.record_success(provider_name, latency_ms)
            breaker.record_success(provider_name)
            response.latency_ms = latency_ms
            return response

    if last_error is not None:
        raise last_error
    raise NoProviderAvailable("No provider candidate was both available and allowed through its circuit breaker")


# --- Streaming (Section 33) ---------------------------------------------
#
# Deliberately NOT the same retry loop as generate(): once a token has been
# shown to the caller, a mid-stream failure can't be un-sent, so there's no
# seamless provider swap — the turn ends honestly with a short closing line
# instead (Section 33: "neither duplicating already-shown content or an
# awkward splice is acceptable"). Only PRE-stream failures (nothing shown
# yet) get a limited retry against the next candidate.

MAX_STREAM_PRESTART_ATTEMPTS = 2

GRACEFUL_MIDSTREAM_CLOSING = "\n\n...and that's the point where I lost the signal — try that again?"
GRACEFUL_TIMEOUT_CLOSING = "\n\n...running out of time on this one — let's call that the answer for now."


def generate_stream(request: GatewayRequest, config=None, tracker=None, breaker=None, budget=None):
    """Yields text deltas as they arrive. Records the outcome into
    provider_health/circuit_breaker the same way generate() does. Doesn't
    return a GatewayResponse — the caller (ask.py) already has the prompt
    and can reconstruct token estimates from the accumulated text; exact
    provider-reported usage isn't reliably available mid-stream across both
    current adapters anyway."""
    from model_router import select_candidates

    tracker = tracker or get_tracker()
    breaker = breaker or get_breaker()

    tried = set()
    last_error = None

    for _attempt in range(MAX_STREAM_PRESTART_ATTEMPTS):
        candidates = select_candidates(request.task_complexity_hint, config=config, tracker=tracker, breaker=breaker,
                                        estimated_prompt_tokens=request.estimated_prompt_tokens)
        candidates = [c for c in candidates if (c[1], c[2]) not in tried]

        chosen = None
        for _, cand_provider, cand_model in candidates:
            if breaker.allow_request(cand_provider):
                chosen = (cand_provider, cand_model)
                break
        if chosen is None:
            break

        provider_name, model_name = chosen
        tried.add(chosen)
        adapter = get_adapter(provider_name)

        attempt_deadline_ms = request.deadline_ms
        if budget is not None:
            attempt_deadline_ms = min(attempt_deadline_ms, int(budget.remaining_ms()))
        attempt_request = replace(request, deadline_ms=attempt_deadline_ms)

        started = False
        start = time.monotonic()
        try:
            for chunk in adapter.generate_stream(attempt_request, model_name):
                started = True
                if budget is not None and budget.exceeded():
                    print("[gateway] timeout_during_stream")
                    yield GRACEFUL_TIMEOUT_CLOSING
                    tracker.record_success(provider_name, (time.monotonic() - start) * 1000)
                    breaker.record_success(provider_name)
                    return
                yield chunk
            tracker.record_success(provider_name, (time.monotonic() - start) * 1000)
            breaker.record_success(provider_name)
            return
        except GatewayError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            tracker.record_failure(provider_name, exc.normalized_code, latency_ms)
            breaker.record_failure(provider_name)
            last_error = exc
            if started:
                yield GRACEFUL_MIDSTREAM_CLOSING
                return
            continue  # pre-stream failure, nothing shown yet — safe to try the next candidate

    if last_error is not None:
        raise last_error
    raise NoProviderAvailable("No provider candidate was both available and allowed through its circuit breaker")
