"""Rate Limiting — Section 23 of the blueprint.

Multi-layer because IP-only rate limiting has specific, nameable weaknesses
(Section 23): shared IPs (corporate NAT, CGNAT) punish many legitimate users
behind one address; IP rotation trivially evades a pure-IP limit; neither
stops a single session issuing many rapid requests. Layering IP + session +
global limits closes each gap the others miss.

In-memory sliding-window counters, in-process — same deferral as every
other Phase 3/4 module: the enforcement *logic* here is what would
eventually run at Cloudflare's edge (Workers + KV/Durable Objects, Section
23) before any retrieval or LLM work happens; binding it to that
infrastructure is Phase 11, not this module's job. Checks are ordered
cheapest/most-likely-to-reject first — "rejecting cheaply and early is the
whole point" (Section 23) — so an over-limit request costs approximately
nothing.
"""
import time
from collections import defaultdict, deque
from dataclasses import dataclass

# Starting values from Section 23's table — configurable, not hardcoded.
IP_BURST_LIMIT = 3
IP_BURST_WINDOW_S = 10
IP_SUSTAINED_LIMIT = 10
IP_SUSTAINED_WINDOW_S = 60
SESSION_SUSTAINED_LIMIT = 30
SESSION_SUSTAINED_WINDOW_S = 3600
GLOBAL_CONCURRENCY_LIMIT = 20
GLOBAL_DAILY_BUDGET = 500  # illustrative; real value ties to summed provider free-tier quotas (Section 23)
GLOBAL_DAILY_WINDOW_S = 86400


@dataclass
class RateLimitResult:
    allowed: bool
    layer: str = None  # which layer rejected it, if any
    retry_after_s: float = None


class _SlidingWindowCounter:
    def __init__(self, limit, window_s):
        self.limit = limit
        self.window_s = window_s
        self._hits = defaultdict(deque)

    def _prune(self, key, now):
        dq = self._hits[key]
        while dq and now - dq[0] > self.window_s:
            dq.popleft()

    def check_and_record(self, key, now=None, limit_override=None):
        now = now if now is not None else time.monotonic()
        effective_limit = limit_override if limit_override is not None else self.limit
        self._prune(key, now)
        dq = self._hits[key]
        if len(dq) >= effective_limit:
            return False, max(0.0, self.window_s - (now - dq[0]))
        dq.append(now)
        return True, None

    def reset(self, key=None):
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


class RateLimiter:
    def __init__(self, ip_burst=None, ip_sustained=None, session_sustained=None,
                 global_daily=None, global_concurrency_limit=GLOBAL_CONCURRENCY_LIMIT):
        self.ip_burst = ip_burst or _SlidingWindowCounter(IP_BURST_LIMIT, IP_BURST_WINDOW_S)
        self.ip_sustained = ip_sustained or _SlidingWindowCounter(IP_SUSTAINED_LIMIT, IP_SUSTAINED_WINDOW_S)
        self.session_sustained = session_sustained or _SlidingWindowCounter(
            SESSION_SUSTAINED_LIMIT, SESSION_SUSTAINED_WINDOW_S
        )
        self.global_daily = global_daily or _SlidingWindowCounter(GLOBAL_DAILY_BUDGET, GLOBAL_DAILY_WINDOW_S)
        self.global_concurrency_limit = global_concurrency_limit
        self._in_flight = 0

    def check(self, ip: str, session_id: str) -> RateLimitResult:
        # Viral Mode (Section 36): "all limits are ... re-tightened
        # automatically under Viral Mode" (Section 23). A pure read — this
        # module doesn't own load detection, viral_mode.py does.
        from viral_mode import get_viral_tracker, rate_limit_tightening_factor

        factor = rate_limit_tightening_factor(get_viral_tracker().compute_state().state)

        if self._in_flight >= self.global_concurrency_limit:
            return RateLimitResult(False, "global_concurrency")

        ok, retry_after = self.ip_burst.check_and_record(ip, limit_override=max(1, int(self.ip_burst.limit * factor)))
        if not ok:
            return RateLimitResult(False, "ip_burst", retry_after)

        ok, retry_after = self.ip_sustained.check_and_record(
            ip, limit_override=max(1, int(self.ip_sustained.limit * factor))
        )
        if not ok:
            return RateLimitResult(False, "ip_sustained", retry_after)

        ok, retry_after = self.session_sustained.check_and_record(
            session_id, limit_override=max(1, int(self.session_sustained.limit * factor))
        )
        if not ok:
            return RateLimitResult(False, "session_sustained", retry_after)

        ok, retry_after = self.global_daily.check_and_record("_global")
        if not ok:
            return RateLimitResult(False, "global_daily_budget", retry_after)

        return RateLimitResult(True)

    def in_flight(self):
        return _ConcurrencySlot(self)

    def reset(self):
        self.ip_burst.reset()
        self.ip_sustained.reset()
        self.session_sustained.reset()
        self.global_daily.reset()
        self._in_flight = 0


class _ConcurrencySlot:
    def __init__(self, limiter):
        self.limiter = limiter

    def __enter__(self):
        self.limiter._in_flight += 1
        return self

    def __exit__(self, *exc_info):
        self.limiter._in_flight -= 1
        return False


_default_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    return _default_limiter
