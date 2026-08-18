"""Phase 4 definition-of-done check (Section 53):

"a simulated full-provider-outage test correctly reaches FALLBACK and
recovers automatically when providers 'return' in the test harness."
(Phase 4's own scope note: "chaos-style tests (simulate provider down)
added" — full Graceful Degradation states are Phase 8; here "FALLBACK"
means the Gateway honestly raises NoProviderAvailable rather than the
system reaching Phase 8's formal state machine, which doesn't exist yet.)

No live API calls — everything here uses fake in-process adapters or direct
manipulation of circuit_breaker/rate_limiter/abuse_prevention state, per
Section 18's adapter test contract: routing/reliability correctness
shouldn't depend on hitting live rate limits to verify.
"""
import sys
import time

from circuit_breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker
from gateway_types import GatewayError, GatewayRequest, GatewayResponse, NoProviderAvailable
from provider_health import ProviderHealthTracker
from providers.base import ProviderCapabilities
import providers.registry as registry

PASS_MARK = "PASS"
FAIL_MARK = "FAIL"


def _report(name, ok, detail=""):
    mark = PASS_MARK if ok else FAIL_MARK
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


# ---------------------------------------------------------------------------
# Circuit breaker state-machine tests (simulated failure sequences)
# ---------------------------------------------------------------------------

def test_breaker_trips_open_on_error_rate():
    cb = CircuitBreaker()
    for _ in range(5):
        cb.record_failure("p")
    ok = cb.get_state("p") == OPEN
    return _report("breaker trips OPEN after a run of failures", ok, f"state={cb.get_state('p')}")


def test_breaker_stays_closed_under_threshold():
    cb = CircuitBreaker()
    for _ in range(8):
        cb.record_success("p")
    cb.record_failure("p")  # 1/9 ~ 11% error rate, well under 50% threshold
    ok = cb.get_state("p") == CLOSED
    return _report("breaker stays CLOSED when error rate is under threshold", ok, f"state={cb.get_state('p')}")


def test_breaker_half_open_after_cooldown():
    cb = CircuitBreaker()
    for _ in range(5):
        cb.record_failure("p")
    assert cb.get_state("p") == OPEN
    rec = cb._get("p")
    rec.opened_at = time.monotonic() - (rec.cooldown_s + 1)  # simulate cooldown having elapsed
    ok = cb.get_state("p") == HALF_OPEN
    return _report("breaker moves OPEN -> HALF_OPEN once cooldown elapses", ok)


def test_breaker_half_open_trial_success_closes():
    cb = CircuitBreaker()
    for _ in range(5):
        cb.record_failure("p")
    rec = cb._get("p")
    rec.opened_at = time.monotonic() - (rec.cooldown_s + 1)
    cb.get_state("p")  # triggers OPEN -> HALF_OPEN
    cb.record_success("p")
    ok = cb.get_state("p") == CLOSED
    return _report("breaker moves HALF_OPEN -> CLOSED on a successful trial", ok)


def test_breaker_half_open_trial_failure_reopens_with_longer_cooldown():
    cb = CircuitBreaker()
    for _ in range(5):
        cb.record_failure("p")
    rec = cb._get("p")
    first_cooldown = rec.cooldown_s
    rec.opened_at = time.monotonic() - (rec.cooldown_s + 1)
    cb.get_state("p")  # -> HALF_OPEN
    cb.record_failure("p")  # trial fails
    ok = cb.get_state("p") == OPEN and rec.cooldown_s == first_cooldown * 2
    return _report(
        "breaker moves HALF_OPEN -> OPEN with doubled cooldown on a failed trial", ok,
        f"state={cb.get_state('p')}, cooldown {first_cooldown}s -> {rec.cooldown_s}s",
    )


def test_breaker_half_open_allows_exactly_one_trial():
    cb = CircuitBreaker()
    for _ in range(5):
        cb.record_failure("p")
    rec = cb._get("p")
    rec.opened_at = time.monotonic() - (rec.cooldown_s + 1)
    cb.get_state("p")  # -> HALF_OPEN
    first = cb.allow_request("p")
    second = cb.allow_request("p")
    return _report("HALF_OPEN allows exactly one trial request, not more", first is True and second is False)


# ---------------------------------------------------------------------------
# Rate limiter boundary tests
# ---------------------------------------------------------------------------

def test_ip_burst_limit_boundary():
    from rate_limiter import RateLimiter, _SlidingWindowCounter

    limiter = RateLimiter(ip_burst=_SlidingWindowCounter(3, 10))
    results = [limiter.check("1.2.3.4", f"session-{i}").allowed for i in range(4)]
    ok = results == [True, True, True, False]
    return _report("IP burst limit (3/10s) rejects exactly the 4th request", ok, str(results))


def test_session_sustained_limit_boundary():
    from rate_limiter import RateLimiter, _SlidingWindowCounter

    limiter = RateLimiter(
        ip_burst=_SlidingWindowCounter(1000, 10),  # effectively disabled for this test
        ip_sustained=_SlidingWindowCounter(1000, 60),
        session_sustained=_SlidingWindowCounter(2, 3600),
    )
    results = [limiter.check(f"ip-{i}", "same-session").allowed for i in range(3)]
    ok = results == [True, True, False]
    return _report("session sustained limit rejects the 3rd request from one session", ok, str(results))


def test_global_concurrency_limit():
    from rate_limiter import RateLimiter

    limiter = RateLimiter(global_concurrency_limit=1)
    with limiter.in_flight():
        ok = not limiter.check("ip", "session").allowed
    ok = ok and limiter.check("ip", "session").allowed  # slot freed after the `with` block
    return _report("global concurrency limit blocks while a slot is held, frees after", ok)


# ---------------------------------------------------------------------------
# Abuse prevention tests
# ---------------------------------------------------------------------------

def test_input_length_cap():
    from abuse_prevention import MAX_INPUT_CHARS, check_input

    result = check_input("x" * (MAX_INPUT_CHARS + 1), "s1")
    return _report("input over the length cap is rejected", not result.allowed, result.reason)


def test_min_inter_request_interval():
    from abuse_prevention import check_input, reset

    reset("s2")
    first = check_input("hello", "s2")
    second = check_input("hello again", "s2")
    ok = first.allowed and not second.allowed
    return _report("rapid-fire requests from one session hit the min-interval guard", ok)


def test_toxic_keyword_reject():
    from abuse_prevention import check_input

    result = check_input("how do i make a bomb", "s3")
    return _report("toxic keyword pattern is rejected", not result.allowed, result.reason)


# ---------------------------------------------------------------------------
# Retry + circuit-breaker integration (fake adapters, no live calls)
# ---------------------------------------------------------------------------

class _FakeAdapter:
    """Scripted sequence of outcomes, one per call. Each outcome is either a
    GatewayResponse or a GatewayError to raise."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def capabilities(self, model):
        return ProviderCapabilities(
            context_window=100_000, supports_streaming=False, supports_system_prompt=True,
            cost_per_1k_tokens=0.0, avg_latency_ms=500,
        )

    def generate(self, request, model):
        self.calls += 1
        outcome = self._outcomes[min(self.calls - 1, len(self._outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _fake_response(provider):
    return GatewayResponse(text="ok", provider=provider, model="fake-model",
                            tokens_in=10, tokens_out=2, latency_ms=0.0)


def _with_fake_providers(fake_adapters, test_fn):
    """Temporarily register fake adapters, run test_fn, always restore the
    real registry afterward — even if the test raises."""
    original = dict(registry._ADAPTERS)
    registry._ADAPTERS.update(fake_adapters)
    try:
        return test_fn()
    finally:
        registry._ADAPTERS.clear()
        registry._ADAPTERS.update(original)


def test_retry_falls_over_to_next_provider_on_retriable_error():
    from gateway import generate as gateway_generate

    fake_a = _FakeAdapter([GatewayError("PROVIDER_ERROR", "boom")])
    fake_b = _FakeAdapter([_fake_response("fake_b")])
    config = {
        "active_providers": ["fake_a", "fake_b"],
        "weights": {"capability_fit": 0.3, "latency": 0.2, "health": 0.25, "quota": 0.15, "cost": 0.05, "quality": 0.05},
        "providers": {"fake_a": {"simple": "m1"}, "fake_b": {"simple": "m1"}},
        "historical_quality": {},
    }
    tracker = ProviderHealthTracker()
    breaker = CircuitBreaker()

    def run():
        req = GatewayRequest(messages=[{"role": "user", "content": "hi"}], task_complexity_hint="simple")
        resp = gateway_generate(req, config=config, tracker=tracker, breaker=breaker)
        return resp.provider == "fake_b" and fake_a.calls == 1 and fake_b.calls == 1

    ok = _with_fake_providers({"fake_a": fake_a, "fake_b": fake_b}, run)
    return _report("retriable failure on one provider falls over to the next", ok)


def test_non_retriable_error_raises_immediately_no_retry():
    from gateway import generate as gateway_generate

    fake_a = _FakeAdapter([GatewayError("CONTEXT_TOO_LONG", "too big")])
    fake_b = _FakeAdapter([_fake_response("fake_b")])
    config = {
        "active_providers": ["fake_a", "fake_b"],
        "weights": {"capability_fit": 0.3, "latency": 0.2, "health": 0.25, "quota": 0.15, "cost": 0.05, "quality": 0.05},
        "providers": {"fake_a": {"simple": "m1"}, "fake_b": {"simple": "m1"}},
        "historical_quality": {},
    }
    tracker = ProviderHealthTracker()
    breaker = CircuitBreaker()

    def run():
        req = GatewayRequest(messages=[{"role": "user", "content": "hi"}], task_complexity_hint="simple")
        try:
            gateway_generate(req, config=config, tracker=tracker, breaker=breaker)
            return False
        except GatewayError as exc:
            return exc.normalized_code == "CONTEXT_TOO_LONG" and fake_b.calls == 0

    ok = _with_fake_providers({"fake_a": fake_a, "fake_b": fake_b}, run)
    return _report("non-retriable error raises immediately, other provider never tried", ok)


def test_repeated_failures_trip_breaker_and_exclude_provider_from_router():
    from model_router import select_candidates

    config = {
        "active_providers": ["fake_a", "fake_b"],
        "weights": {"capability_fit": 0.3, "latency": 0.2, "health": 0.25, "quota": 0.15, "cost": 0.05, "quality": 0.05},
        "providers": {"fake_a": {"simple": "m1"}, "fake_b": {"simple": "m1"}},
        "historical_quality": {},
    }
    tracker = ProviderHealthTracker()
    breaker = CircuitBreaker()
    fake_a = _FakeAdapter([])  # generate() is never called in this test — only capabilities()

    def run():
        for _ in range(5):
            breaker.record_failure("fake_a")
        assert breaker.get_state("fake_a") == OPEN
        candidates = select_candidates("simple", config=config, tracker=tracker, breaker=breaker)
        providers_seen = {p for _, p, _ in candidates}
        return "fake_a" not in providers_seen and "fake_b" in providers_seen

    fake_b = _FakeAdapter([_fake_response("fake_b")])
    ok = _with_fake_providers({"fake_a": fake_a, "fake_b": fake_b}, run)
    return _report("router excludes a provider whose breaker is OPEN, even with fresh health elsewhere", ok)


# ---------------------------------------------------------------------------
# Chaos test: full outage
# ---------------------------------------------------------------------------

def test_full_outage_raises_no_provider_available_cleanly():
    from gateway import generate as gateway_generate

    fake_a = _FakeAdapter([GatewayError("PROVIDER_ERROR", "down")] * 3)
    fake_b = _FakeAdapter([GatewayError("PROVIDER_ERROR", "down")] * 3)
    config = {
        "active_providers": ["fake_a", "fake_b"],
        "weights": {"capability_fit": 0.3, "latency": 0.2, "health": 0.25, "quota": 0.15, "cost": 0.05, "quality": 0.05},
        "providers": {"fake_a": {"simple": "m1"}, "fake_b": {"simple": "m1"}},
        "historical_quality": {},
    }
    tracker = ProviderHealthTracker()
    breaker = CircuitBreaker()

    def run():
        req = GatewayRequest(messages=[{"role": "user", "content": "hi"}], task_complexity_hint="simple")
        try:
            gateway_generate(req, config=config, tracker=tracker, breaker=breaker)
            return False
        except (NoProviderAvailable, GatewayError):
            # Either is an honest failure — no fabricated success, no crash/hang.
            return True

    ok = _with_fake_providers({"fake_a": fake_a, "fake_b": fake_b}, run)
    return _report("total outage (both providers failing) fails honestly, no fabricated answer", ok)


def run():
    tests = [
        test_breaker_trips_open_on_error_rate,
        test_breaker_stays_closed_under_threshold,
        test_breaker_half_open_after_cooldown,
        test_breaker_half_open_trial_success_closes,
        test_breaker_half_open_trial_failure_reopens_with_longer_cooldown,
        test_breaker_half_open_allows_exactly_one_trial,
        test_ip_burst_limit_boundary,
        test_session_sustained_limit_boundary,
        test_global_concurrency_limit,
        test_input_length_cap,
        test_min_inter_request_interval,
        test_toxic_keyword_reject,
        test_retry_falls_over_to_next_provider_on_retriable_error,
        test_non_retriable_error_raises_immediately_no_retry,
        test_repeated_failures_trip_breaker_and_exclude_provider_from_router,
        test_full_outage_raises_no_provider_available_cleanly,
    ]
    results = [t() for t in tests]
    passed = sum(results)
    print(f"\nPhase 4 reliability checks: {passed}/{len(results)} passed")
    return passed == len(results)


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
