"""Graceful Degradation — Section 34 of the blueprint.

    NORMAL -> DEGRADED -> FALLBACK -> RECOVERY (-> NORMAL)

State is computed centrally from the aggregate of provider health (Section
19: circuit breaker state + health/quota signals) and exposed to whatever
needs to behave differently by state. DEGRADED is largely automatic
already (the circuit breaker already excludes OPEN providers from routing,
Section 20) — this module's real job is detecting the FALLBACK case (zero
providers reachable) and the RECOVERY transition, since those are the two
states that need a structurally different code path (ask.py never
constructs a Gateway request at all in FALLBACK).
"""
import time
from dataclasses import dataclass

from circuit_breaker import CLOSED, HALF_OPEN, OPEN, get_breaker
from provider_health import get_tracker

NORMAL = "NORMAL"
DEGRADED = "DEGRADED"
FALLBACK = "FALLBACK"
RECOVERY = "RECOVERY"

QUOTA_HEADROOM_DEGRADED_THRESHOLD = 0.3  # Section 34: "approaching quota ceilings"
LATENCY_DEGRADED_THRESHOLD_MS = 5000.0
SUSTAINED_STABLE_S = 30  # RECOVERY -> NORMAL only after this long fully healthy (Section 34: "a short observation window")


@dataclass
class DegradationResult:
    state: str
    provider_states: dict  # provider_name -> circuit_breaker state
    reason: str


class DegradationTracker:
    """Tracks how long the system has been continuously fully-healthy, to
    distinguish RECOVERY (just came back, still stabilizing) from a truly
    stable NORMAL — mirrors the same "sustained healthy period" idea the
    circuit breaker itself uses per-provider (Section 20)."""

    def __init__(self):
        self._fully_healthy_since = None

    def compute(self, active_providers, breaker=None, tracker=None) -> DegradationResult:
        breaker = breaker or get_breaker()
        tracker = tracker or get_tracker()

        states = {p: breaker.get_state(p) for p in active_providers}
        now = time.monotonic()

        if not states:
            return DegradationResult(FALLBACK, states, "no providers configured")

        if all(s == OPEN for s in states.values()):
            self._fully_healthy_since = None
            return DegradationResult(FALLBACK, states, "all active providers have an OPEN circuit")

        if any(s == HALF_OPEN for s in states.values()):
            self._fully_healthy_since = None
            return DegradationResult(RECOVERY, states, "a provider is mid-recovery-trial (HALF_OPEN)")

        if any(s == OPEN for s in states.values()):
            self._fully_healthy_since = None
            return DegradationResult(DEGRADED, states,
                                      "at least one provider OPEN, at least one still available")

        # All CLOSED from here — check secondary DEGRADED triggers (quota,
        # latency) before declaring NORMAL/RECOVERY-stabilized.
        low_quota = [p for p in active_providers if tracker.quota_headroom(p) < QUOTA_HEADROOM_DEGRADED_THRESHOLD]
        high_latency = [
            p for p in active_providers
            if (tracker.observed_avg_latency_ms(p) or 0) > LATENCY_DEGRADED_THRESHOLD_MS
        ]
        if low_quota or high_latency:
            self._fully_healthy_since = None
            reason = f"quota headroom low for {low_quota}" if low_quota else f"elevated latency for {high_latency}"
            return DegradationResult(DEGRADED, states, reason)

        if self._fully_healthy_since is None:
            self._fully_healthy_since = now

        if now - self._fully_healthy_since < SUSTAINED_STABLE_S:
            return DegradationResult(RECOVERY, states, "all providers CLOSED but not yet sustained-stable")

        return DegradationResult(NORMAL, states, "all providers CLOSED and stable")

    def reset(self):
        self._fully_healthy_since = None


_default_tracker = DegradationTracker()


def get_degradation_tracker() -> DegradationTracker:
    return _default_tracker
