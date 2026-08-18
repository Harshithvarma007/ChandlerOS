"""Abuse Prevention — Section 24 of the blueprint.

Threat -> mitigation, scoped to what this phase actually owns per Section
24's own table:
  - Extremely long prompts       -> hard input length cap here
  - Spam / flooding              -> rate_limiter.py (Section 23) + min
                                     inter-request interval here
  - Context exhaustion           -> already handled: context_builder.py's
                                     hard token ceiling (Phase 1/2)
  - Malicious/toxic input        -> basic keyword heuristic here, provider
                                     safety filtering as the real second layer
  - Prompt injection             -> explicitly OUT of scope here — Section
                                     24 itself routes this to "Section 30",
                                     which is Phase 6. Nothing in this file
                                     tries to detect injection; conflating
                                     "malicious input" with "injection
                                     attempt" would give false confidence
                                     about a defense that doesn't exist yet.
  - Bots / browser fingerprinting -> needs a real HTTP edge (Cloudflare bot
                                     score signal per Section 24) — not
                                     meaningful for a local CLI, deferred to
                                     Phase 11 deployment.
"""
import time
from dataclasses import dataclass

MAX_INPUT_CHARS = 2000
MIN_INTER_REQUEST_INTERVAL_S = 1.0

# Deliberately minimal, illustrative — Section 24: "not an LLM safety-
# classifier call for cost reasons", relying on the provider's own safety
# filtering as the real second layer. A production deployment would expand
# this list; the point here is the mechanism (cheap pre-LLM reject), not an
# exhaustive moderation policy.
TOXIC_PATTERNS = [
    "kill yourself",
    "how to make a bomb",
    "how do i make a bomb",
]


@dataclass
class AbuseCheckResult:
    allowed: bool
    reason: str = None
    message: str = None


_last_request_at = {}  # session_id -> monotonic timestamp


def check_input(raw_query: str, session_id: str, now=None) -> AbuseCheckResult:
    now = now if now is not None else time.monotonic()

    if raw_query is None or not raw_query.strip():
        return AbuseCheckResult(False, "empty_input", "Empty input.")

    if len(raw_query) > MAX_INPUT_CHARS:
        return AbuseCheckResult(
            False, "input_too_long",
            f"That question is too long ({len(raw_query)} chars, max {MAX_INPUT_CHARS}). "
            f"Try asking something shorter.",
        )

    last_at = _last_request_at.get(session_id)
    if last_at is not None and (now - last_at) < MIN_INTER_REQUEST_INTERVAL_S:
        return AbuseCheckResult(
            False, "min_interval",
            f"You're sending requests faster than {MIN_INTER_REQUEST_INTERVAL_S}s apart — please slow down.",
        )

    normalized = raw_query.lower()
    for pattern in TOXIC_PATTERNS:
        if pattern in normalized:
            return AbuseCheckResult(False, "toxic_input", "I can't help with that.")

    _last_request_at[session_id] = now
    return AbuseCheckResult(True)


def reset(session_id: str = None):
    if session_id is None:
        _last_request_at.clear()
    else:
        _last_request_at.pop(session_id, None)
