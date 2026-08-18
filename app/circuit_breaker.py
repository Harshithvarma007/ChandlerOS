"""Circuit Breaker — Section 20 of the blueprint.

Per-provider state machine:

    CLOSED --(error_rate > 50% over rolling 20-req/60s window)--> OPEN
    OPEN --(cooldown elapses)--> HALF_OPEN
    HALF_OPEN --(trial request succeeds)--> CLOSED
    HALF_OPEN --(trial request fails)--> OPEN (cooldown doubles, capped at 10min)

An OPEN circuit is a hard exclusion from the Model Router's candidate set —
not a weighted penalty like the rest of provider_health.py. That's the
distinction Section 20 draws explicitly: retrying a definitively-down
provider is pure waste, so this is a gate, not a score input.

In-memory only (per-process), same deferral as provider_health.py — a
KV/D1-backed cache (Section 19) so state survives across instances is
Phase 9/11 scope, not a blocker for this module's interface.
"""
import time
from collections import deque
from dataclasses import dataclass, field

CLOSED = "CLOSED"
OPEN = "OPEN"
HALF_OPEN = "HALF_OPEN"

WINDOW_REQUESTS = 20
WINDOW_SECONDS = 60
ERROR_RATE_THRESHOLD = 0.5
INITIAL_COOLDOWN_S = 30
MAX_COOLDOWN_S = 600
SUSTAINED_HEALTHY_S = 120  # healthy this long after a trip -> cooldown resets to initial on next trip


@dataclass
class _BreakerState:
    state: str = CLOSED
    outcomes: deque = field(default_factory=deque)  # (timestamp, success: bool)
    cooldown_s: int = INITIAL_COOLDOWN_S
    opened_at: float = 0.0
    half_open_trial_in_flight: bool = False
    last_closed_at: float = field(default_factory=time.monotonic)
    transitions: list = field(default_factory=list)  # log for observability/tests


class CircuitBreaker:
    def __init__(self):
        self._states = {}

    def _get(self, provider: str) -> _BreakerState:
        return self._states.setdefault(provider, _BreakerState())

    def _log_transition(self, provider, rec, old_state, new_state, reason):
        entry = {
            "provider": provider, "from": old_state, "to": new_state,
            "reason": reason, "at": time.monotonic(),
        }
        rec.transitions.append(entry)
        print(f"[circuit_breaker] {provider}: {old_state} -> {new_state} ({reason})")

    def _prune_window(self, rec):
        now = time.monotonic()
        while rec.outcomes and (len(rec.outcomes) > WINDOW_REQUESTS or now - rec.outcomes[0][0] > WINDOW_SECONDS):
            rec.outcomes.popleft()

    def get_state(self, provider: str) -> str:
        rec = self._get(provider)
        if rec.state == OPEN and time.monotonic() - rec.opened_at >= rec.cooldown_s:
            self._log_transition(provider, rec, OPEN, HALF_OPEN, "cooldown elapsed")
            rec.state = HALF_OPEN
            rec.half_open_trial_in_flight = False
        return rec.state

    def seconds_since_opened(self, provider: str):
        """None if the provider isn't currently OPEN — used by Chandler
        Fallback (Section 35) to phrase an approximate wait time."""
        rec = self._states.get(provider)
        if rec is None or rec.state != OPEN:
            return None
        return time.monotonic() - rec.opened_at

    def allow_request(self, provider: str) -> bool:
        """CLOSED: always allowed. OPEN: never. HALF_OPEN: exactly one trial
        request; everything else during HALF_OPEN should be routed to a
        different provider by the caller (Model Router), not queued here."""
        state = self.get_state(provider)
        if state == CLOSED:
            return True
        if state == OPEN:
            return False
        rec = self._get(provider)
        if not rec.half_open_trial_in_flight:
            rec.half_open_trial_in_flight = True
            return True
        return False

    def record_success(self, provider: str):
        rec = self._get(provider)
        now = time.monotonic()
        rec.outcomes.append((now, True))
        self._prune_window(rec)

        if rec.state == HALF_OPEN:
            self._log_transition(provider, rec, HALF_OPEN, CLOSED, "trial request succeeded")
            rec.state = CLOSED
            rec.half_open_trial_in_flight = False
            rec.last_closed_at = now
            if now - rec.opened_at > SUSTAINED_HEALTHY_S:
                rec.cooldown_s = INITIAL_COOLDOWN_S

    def record_failure(self, provider: str):
        rec = self._get(provider)
        now = time.monotonic()
        rec.outcomes.append((now, False))
        self._prune_window(rec)

        if rec.state == HALF_OPEN:
            rec.cooldown_s = min(rec.cooldown_s * 2, MAX_COOLDOWN_S)
            rec.opened_at = now
            rec.half_open_trial_in_flight = False
            self._log_transition(provider, rec, HALF_OPEN, OPEN, f"trial failed, cooldown now {rec.cooldown_s}s")
            rec.state = OPEN
            return

        if rec.state == CLOSED and len(rec.outcomes) >= 1:
            error_rate = sum(1 for _, ok in rec.outcomes if not ok) / len(rec.outcomes)
            window_full = len(rec.outcomes) >= WINDOW_REQUESTS or (
                rec.outcomes and now - rec.outcomes[0][0] >= WINDOW_SECONDS
            )
            # Also trip on a smaller sample if error rate is severe, so a
            # provider that fails its first few requests doesn't get to burn
            # through the whole window before anyone notices (Section 20's
            # "small window chosen deliberately since quota exhaustion can
            # flip a provider from fine to fully failing within seconds").
            if error_rate > ERROR_RATE_THRESHOLD and (window_full or len(rec.outcomes) >= 4):
                rec.state = OPEN
                rec.opened_at = now
                self._log_transition(provider, rec, CLOSED, OPEN, f"error_rate={error_rate:.0%} over {len(rec.outcomes)} reqs")

    def reset(self, provider: str = None):
        if provider is None:
            self._states.clear()
        else:
            self._states.pop(provider, None)


_default_breaker = CircuitBreaker()


def get_breaker() -> CircuitBreaker:
    return _default_breaker
