"""Provider Health — Section 19 of the blueprint (Phase 3 slice).

Tracks a rolling window of recent outcomes per provider and turns it into a
[0,1] health score the Model Router weighs. This is deliberately NOT the
full Circuit Breaker state machine (Section 20, Phase 4) — no CLOSED/OPEN/
HALF_OPEN states, no cooldown timers. It's the simpler signal the blueprint
says feeds *into* that state machine, built first because the Router needs
a health input before the state machine has anywhere to live.

In-memory only (per-process). Section 19 specifies a KV/D1-backed cache so
health survives across requests/instances — that persistence layer is
deferred to Phase 9 (Observability) alongside the rest of the storage
formalization; nothing here blocks adding it later, this module's interface
(record_success/record_failure/health_score) wouldn't need to change.
"""
import time
from collections import deque
from dataclasses import dataclass, field

WINDOW_SIZE = 20  # outcomes considered per provider
QUOTA_DECAY_WINDOW = 10  # how many recent outcomes rate-limit events are judged against


@dataclass
class _ProviderRecord:
    outcomes: deque = field(default_factory=lambda: deque(maxlen=WINDOW_SIZE))  # True=success
    rate_limited_recent: deque = field(default_factory=lambda: deque(maxlen=QUOTA_DECAY_WINDOW))
    latencies_ms: deque = field(default_factory=lambda: deque(maxlen=WINDOW_SIZE))
    last_normalized_code: str = None
    last_event_at: float = 0.0


class ProviderHealthTracker:
    def __init__(self):
        self._records = {}

    def _record(self, provider: str) -> _ProviderRecord:
        return self._records.setdefault(provider, _ProviderRecord())

    def record_success(self, provider: str, latency_ms: float):
        rec = self._record(provider)
        rec.outcomes.append(True)
        rec.rate_limited_recent.append(False)
        rec.latencies_ms.append(latency_ms)
        rec.last_normalized_code = None
        rec.last_event_at = time.monotonic()

    def record_failure(self, provider: str, normalized_code: str, latency_ms: float):
        rec = self._record(provider)
        rec.outcomes.append(False)
        rec.rate_limited_recent.append(normalized_code == "RATE_LIMITED")
        rec.latencies_ms.append(latency_ms)
        rec.last_normalized_code = normalized_code
        rec.last_event_at = time.monotonic()

    def health_score(self, provider: str) -> float:
        """1.0 = fully healthy, 0.0 = every recent call failed.
        No history yet -> optimistic default (1.0): an unproven provider
        shouldn't be penalized before it's had a chance to run."""
        rec = self._records.get(provider)
        if rec is None or not rec.outcomes:
            return 1.0
        return sum(rec.outcomes) / len(rec.outcomes)

    def quota_headroom(self, provider: str) -> float:
        """1.0 = no recent rate-limiting, decaying toward 0.0 as 429s pile up
        in the recent window. Approximates Section 19's 'estimated quota
        remaining' without needing provider-reported quota headers, which
        Gemini's API doesn't expose."""
        rec = self._records.get(provider)
        if rec is None or not rec.rate_limited_recent:
            return 1.0
        return 1.0 - (sum(rec.rate_limited_recent) / len(rec.rate_limited_recent))

    def observed_avg_latency_ms(self, provider: str):
        rec = self._records.get(provider)
        if rec is None or not rec.latencies_ms:
            return None
        return sum(rec.latencies_ms) / len(rec.latencies_ms)

    def force_unhealthy(self, provider: str):
        """Test/simulation hook only (Phase 3 DoD: 'routing picks sensibly
        under a simulated unhealthy-provider test') — not used by any
        production code path."""
        rec = self._record(provider)
        rec.outcomes.clear()
        rec.outcomes.extend([False] * WINDOW_SIZE)

    def reset(self, provider: str = None):
        if provider is None:
            self._records.clear()
        else:
            self._records.pop(provider, None)


_default_tracker = ProviderHealthTracker()


def get_tracker() -> ProviderHealthTracker:
    return _default_tracker
