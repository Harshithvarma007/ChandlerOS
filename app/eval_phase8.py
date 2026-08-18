"""Phase 8 definition-of-done check (Section 53):

"a simulated total-outage and simulated 50x-traffic tests both pass without
cost blowout or dishonest responses."

All pure/no-LLM: Graceful Degradation and Viral Mode are both state
machines over circuit-breaker/traffic-counter state, directly simulatable
without touching a real provider. The "never implies a live LLM" check is
structural — it asserts the FALLBACK code path never calls the Gateway at
all, not just that it happens to return the right text this time.
"""
import sys
import time

from chandler_fallback import build_fallback_response
from circuit_breaker import CircuitBreaker
from degradation import DEGRADED, FALLBACK, NORMAL, RECOVERY, DegradationTracker
from provider_health import ProviderHealthTracker
from viral_mode import (
    BUSY,
    HIGH_TRAFFIC,
    NORMAL as VIRAL_NORMAL,
    OBSERVATION_WINDOW_S,
    REQUEST_WINDOW_S,
    VIRAL,
    ViralModeTracker,
    max_output_tokens_for_state,
    rate_limit_tightening_factor,
)

PASS_MARK = "PASS"
FAIL_MARK = "FAIL"


def _report(name, ok, detail=""):
    mark = PASS_MARK if ok else FAIL_MARK
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


# ---------------------------------------------------------------------------
# Graceful Degradation state machine
# ---------------------------------------------------------------------------

def test_all_healthy_is_eventually_normal():
    breaker = CircuitBreaker()
    tracker = DegradationTracker()
    result = tracker.compute(["a", "b"], breaker=breaker)
    ok1 = result.state in (NORMAL, RECOVERY)  # freshly-healthy, not yet sustained -> RECOVERY is correct too
    return _report("all-CLOSED providers settle to NORMAL/RECOVERY, never FALLBACK/DEGRADED", ok1, result.state)


def test_total_outage_is_fallback():
    breaker = CircuitBreaker()
    for _ in range(5):
        breaker.record_failure("a")
        breaker.record_failure("b")
    tracker = DegradationTracker()
    result = tracker.compute(["a", "b"], breaker=breaker)
    return _report("all providers OPEN -> FALLBACK state", result.state == FALLBACK, result.state)


def test_partial_outage_is_degraded():
    breaker = CircuitBreaker()
    for _ in range(5):
        breaker.record_failure("a")
    tracker = DegradationTracker()
    result = tracker.compute(["a", "b"], breaker=breaker)  # "b" untouched -> still CLOSED
    return _report("one OPEN, one CLOSED -> DEGRADED (not FALLBACK)", result.state == DEGRADED, result.state)


def test_half_open_provider_is_recovery():
    breaker = CircuitBreaker()
    for _ in range(5):
        breaker.record_failure("a")
    rec = breaker._get("a")
    rec.opened_at = time.monotonic() - (rec.cooldown_s + 1)  # simulate cooldown elapsed -> HALF_OPEN
    breaker.get_state("a")
    tracker = DegradationTracker()
    result = tracker.compute(["a"], breaker=breaker)
    return _report("a HALF_OPEN provider mid-trial -> RECOVERY state", result.state == RECOVERY, result.state)


def test_low_quota_headroom_is_degraded():
    breaker = CircuitBreaker()
    tracker_health = ProviderHealthTracker()
    for _ in range(5):
        tracker_health.record_failure("a", "RATE_LIMITED", 100)  # drives quota_headroom down without opening the breaker
    tracker = DegradationTracker()
    result = tracker.compute(["a"], breaker=breaker, tracker=tracker_health)
    return _report("low quota headroom alone triggers DEGRADED even with a CLOSED circuit",
                    result.state == DEGRADED, result.state)


def test_recovery_settles_to_normal_after_sustained_window():
    breaker = CircuitBreaker()
    tracker = DegradationTracker()
    tracker._fully_healthy_since = time.monotonic() - 999  # simulate having been healthy for a long time
    result = tracker.compute(["a", "b"], breaker=breaker)
    return _report("sustained-healthy providers settle to NORMAL, not stuck in RECOVERY forever",
                    result.state == NORMAL, result.state)


# ---------------------------------------------------------------------------
# Chandler Fallback — "never implies a live LLM" (structural check)
# ---------------------------------------------------------------------------

def test_fallback_response_marks_provider_none():
    resp = build_fallback_response("simple_fact", template_index=0)
    ok = resp.provider == "none" and resp.model == "static_fallback"
    return _report("fallback response metadata marks provider=none, model=static_fallback", ok)


def test_fallback_path_never_calls_gateway():
    """The strongest version of this check: patch gateway.generate to raise
    if called at all, force FALLBACK state, and confirm ask() never touches
    it — not just that the returned text happens to look right."""
    import ask as ask_module
    import gateway
    from circuit_breaker import get_breaker
    from degradation import get_degradation_tracker
    from semantic_cache import get_semantic_cache

    def _explode(*a, **kw):
        raise AssertionError("gateway.generate was called during FALLBACK — hard requirement violated")

    original_generate = gateway.generate
    gateway.generate = _explode
    breaker = get_breaker()
    breaker.reset()
    get_degradation_tracker().reset()
    # Response/semantic caches are shared module-level singletons — an
    # earlier test or eval run asking the same question would otherwise
    # short-circuit straight to a cache hit and never reach the FALLBACK
    # branch at all, producing a false pass/fail unrelated to this test.
    ask_module._response_cache.invalidate_all()
    get_semantic_cache().invalidate_all()
    try:
        for _ in range(5):
            breaker.record_failure("gemini")
            breaker.record_failure("groq")

        result = ask_module.ask("Where did Harshith study?", session_id="phase8-fallback-test")
        ok = (
            result.get("degradation_state") == FALLBACK
            and result.get("used_llm") is False
            and result.get("fallback_provider") == "none"
            and result.get("fallback_model") == "static_fallback"
        )
        return _report("ask() in FALLBACK never calls gateway.generate at all", ok,
                        f"degradation_state={result.get('degradation_state')}, used_llm={result.get('used_llm')}")
    finally:
        gateway.generate = original_generate
        breaker.reset()
        get_degradation_tracker().reset()


def test_fallback_selection_deterministic_by_category():
    generic = build_fallback_response("simple_fact", template_index=0)
    chitchat = build_fallback_response("general", template_index=0)
    viral = build_fallback_response("simple_fact", viral=True, template_index=0)
    ok = (generic.template_category == "generic" and chitchat.template_category == "chitchat"
          and viral.template_category == "viral")
    return _report("template category selection is deterministic by query_class/viral flag", ok)


# ---------------------------------------------------------------------------
# Viral Mode state machine (hysteresis)
# ---------------------------------------------------------------------------

def _seed_uniform_requests(tracker, now, span_s, count):
    """Directly seeds the internal timestamp deque, spread uniformly across
    the last `span_s` seconds. Deliberately bypasses record_request()'s own
    incremental pruning (which prunes relative to whatever `now` each call
    receives) — looping record_request() with a rising sequence of past
    `now` values would progressively evict its own earlier entries before
    the loop even finishes, which is a real footgun, not just a test
    convenience issue."""
    step = span_s / count
    tracker._request_timestamps.extend(now - span_s + i * step for i in range(count))


def test_viral_mode_escalates_with_sustained_load():
    tracker = ViralModeTracker()
    now = time.monotonic()
    # ~191 req/60s (~38x baseline) uniformly across both the "now" window
    # and the "one observation-window-ago" window, so the escalation reads
    # as genuinely sustained rather than a recent-only spike.
    _seed_uniform_requests(tracker, now, span_s=REQUEST_WINDOW_S + OBSERVATION_WINDOW_S + 5, count=350)
    status = tracker.compute_state(now=now)
    return _report("sustained heavy load (simulated ~38x traffic) escalates to VIRAL", status.state == VIRAL,
                    status.reason)


def test_viral_mode_does_not_escalate_on_a_single_burst():
    tracker = ViralModeTracker()
    now = time.monotonic()
    _seed_uniform_requests(tracker, now, span_s=1, count=400)  # huge burst, but only just happened — not sustained
    status = tracker.compute_state(now=now)
    return _report("hysteresis: a sudden burst that hasn't been sustained doesn't instantly commit to VIRAL",
                    status.state == VIRAL_NORMAL, status.reason)


def test_viral_mode_recovers_only_after_sustained_quiet():
    tracker = ViralModeTracker()
    now = time.monotonic()
    _seed_uniform_requests(tracker, now, span_s=REQUEST_WINDOW_S + OBSERVATION_WINDOW_S + 5, count=350)
    tracker.compute_state(now=now)  # commit to VIRAL
    # Traffic stops, but only an instant ago — should NOT snap back to NORMAL immediately,
    # since the "one window ago" sample still reflects the recent heavy load.
    status = tracker.compute_state(now=now + 1)
    return _report("VIRAL doesn't instantly drop back to NORMAL on one quiet moment (symmetric hysteresis)",
                    status.state != VIRAL_NORMAL, status.state)


def test_viral_mode_effects_scale_down_with_severity():
    normal_tokens = max_output_tokens_for_state(VIRAL_NORMAL, 1000)
    viral_tokens = max_output_tokens_for_state(VIRAL, 1000)
    normal_rl = rate_limit_tightening_factor(VIRAL_NORMAL)
    viral_rl = rate_limit_tightening_factor(VIRAL)
    ok = viral_tokens < normal_tokens and viral_rl < normal_rl
    return _report("VIRAL trims output tokens and tightens rate limits more than NORMAL", ok,
                    f"tokens {normal_tokens}->{viral_tokens}, rl_factor {normal_rl}->{viral_rl}")


def run():
    tests = [
        test_all_healthy_is_eventually_normal,
        test_total_outage_is_fallback,
        test_partial_outage_is_degraded,
        test_half_open_provider_is_recovery,
        test_low_quota_headroom_is_degraded,
        test_recovery_settles_to_normal_after_sustained_window,
        test_fallback_response_marks_provider_none,
        test_fallback_path_never_calls_gateway,
        test_fallback_selection_deterministic_by_category,
        test_viral_mode_escalates_with_sustained_load,
        test_viral_mode_does_not_escalate_on_a_single_burst,
        test_viral_mode_recovers_only_after_sustained_quiet,
        test_viral_mode_effects_scale_down_with_severity,
    ]
    results = [t() for t in tests]
    passed = sum(results)
    print(f"\nPhase 8 degradation/fallback/viral-mode checks: {passed}/{len(results)} passed")
    return passed == len(results)


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
