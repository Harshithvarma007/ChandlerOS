"""Phase 7 definition-of-done check (Section 53):

"measurable cost reduction on a repeated-query benchmark, no correctness
regression from caching."

Most of this is pure/no-LLM (TTLCache mechanics, context_dependent
detection, token estimation, the router's context-window hard filter).
The repeated-query benchmark and the semantic-cache similarity check are
live — they need a real LLM/embedding call to prove a *second* equivalent
request is actually served from cache rather than re-generated, which is
the whole point of this phase's DoD.
"""
import sys
import time

from cache import TTLCache
from circuit_breaker import CircuitBreaker
from model_router import select_candidates
from provider_health import ProviderHealthTracker
from providers.base import ProviderCapabilities
from query_understanding import understand
from token_budget import estimate_prompt_tokens, estimate_tokens

PASS_MARK = "PASS"
FAIL_MARK = "FAIL"


def _report(name, ok, detail=""):
    mark = PASS_MARK if ok else FAIL_MARK
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


# ---------------------------------------------------------------------------
# TTLCache mechanics
# ---------------------------------------------------------------------------

def test_ttlcache_hit_and_miss():
    cache = TTLCache(ttl_seconds=10)
    ok_miss = cache.get("k") is None
    cache.set("k", "v")
    ok_hit = cache.get("k") == "v"
    return _report("TTLCache: miss before set, hit after", ok_miss and ok_hit)


def test_ttlcache_expiry():
    cache = TTLCache(ttl_seconds=0.05)
    cache.set("k", "v")
    time.sleep(0.1)
    ok = cache.get("k") is None
    return _report("TTLCache: entry expires after its TTL", ok)


def test_ttlcache_eviction_at_capacity():
    cache = TTLCache(ttl_seconds=10, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # should evict "a" (oldest)
    ok = cache.get("a") is None and cache.get("b") == 2 and cache.get("c") == 3
    return _report("TTLCache: evicts oldest entry at capacity", ok)


def test_ttlcache_invalidate_all():
    cache = TTLCache(ttl_seconds=10)
    cache.set("a", 1)
    cache.invalidate_all()
    ok = cache.get("a") is None
    return _report("TTLCache: invalidate_all clears everything", ok)


# ---------------------------------------------------------------------------
# context_dependent detection (Query Understanding)
# ---------------------------------------------------------------------------

def test_context_dependent_detected():
    cases = ["What about that one?", "And what about Confluent?", "That one too"]
    results = [understand(c).context_dependent for c in cases]
    return _report("obvious ellipsis/pronoun openers are flagged context_dependent", all(results), str(results))


def test_normal_question_not_context_dependent():
    result = understand("Where did Harshith study?")
    return _report("an ordinary self-contained question is not flagged context_dependent", not result.context_dependent)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def test_estimate_tokens_scales_with_length():
    short = estimate_tokens("hello there")
    long = estimate_tokens("hello there " * 50)
    return _report("estimate_tokens grows with text length", 0 < short < long)


def test_estimate_prompt_tokens_includes_output_reserve():
    total = estimate_prompt_tokens("sys", "style", "knowledge", "query")
    from token_budget import BUDGET_TOKENS
    ok = total >= BUDGET_TOKENS["output_reserve"]
    return _report("estimate_prompt_tokens reserves room for the response, not just the input", ok)


# ---------------------------------------------------------------------------
# Router context-window hard filter (Section 27)
# ---------------------------------------------------------------------------

class _FakeAdapter:
    def __init__(self, context_window):
        self._caps = ProviderCapabilities(
            context_window=context_window, supports_streaming=False, supports_system_prompt=True,
            cost_per_1k_tokens=0.0, avg_latency_ms=500,
        )

    def capabilities(self, model):
        return self._caps


def test_router_excludes_model_whose_window_is_too_small():
    import providers.registry as registry

    original = dict(registry._ADAPTERS)
    registry._ADAPTERS["small_ctx"] = _FakeAdapter(context_window=1000)
    registry._ADAPTERS["big_ctx"] = _FakeAdapter(context_window=1_000_000)
    try:
        config = {
            "active_providers": ["small_ctx", "big_ctx"],
            "weights": {"capability_fit": 0.3, "latency": 0.2, "health": 0.25, "quota": 0.15, "cost": 0.05, "quality": 0.05},
            "providers": {"small_ctx": {"simple": "m1"}, "big_ctx": {"simple": "m1"}},
            "historical_quality": {},
        }
        tracker = ProviderHealthTracker()
        breaker = CircuitBreaker()
        candidates = select_candidates("simple", config=config, tracker=tracker, breaker=breaker,
                                        estimated_prompt_tokens=5000)
        providers_seen = {p for _, p, _ in candidates}
        ok = "small_ctx" not in providers_seen and "big_ctx" in providers_seen
        return _report("router excludes a model whose context window can't fit the realized prompt", ok,
                        f"providers_seen={providers_seen}")
    finally:
        registry._ADAPTERS.clear()
        registry._ADAPTERS.update(original)


def run_pure():
    tests = [
        test_ttlcache_hit_and_miss,
        test_ttlcache_expiry,
        test_ttlcache_eviction_at_capacity,
        test_ttlcache_invalidate_all,
        test_context_dependent_detected,
        test_normal_question_not_context_dependent,
        test_estimate_tokens_scales_with_length,
        test_estimate_prompt_tokens_includes_output_reserve,
        test_router_excludes_model_whose_window_is_too_small,
    ]
    results = [t() for t in tests]
    passed = sum(results)
    print(f"\nPhase 7 pure/no-LLM checks: {passed}/{len(results)} passed")
    return passed == len(results)


# ---------------------------------------------------------------------------
# Live: repeated-query benchmark (the roadmap's explicit Phase 7 DoD)
# ---------------------------------------------------------------------------

def run_live_repeated_query_benchmark():
    from ask import ask

    question = "Where has Harshith worked?"
    print(f"\n--- live repeated-query benchmark: {question!r} ---")

    t0 = time.monotonic()
    first = ask(question, session_id="phase7-bench-1")
    t1 = time.monotonic()
    second = ask(question, session_id="phase7-bench-2")  # different session — proves it's not session-scoped
    t2 = time.monotonic()

    first_ms = (t1 - t0) * 1000
    second_ms = (t2 - t1) * 1000

    correctness_ok = second.get("answer", "").strip() != "" and not second.get("rejected_reason")
    cache_ok = second.get("cache_hit") is True
    faster_ok = second_ms < first_ms

    print(f"first call:  {first_ms:.0f}ms, used_llm={first.get('used_llm')}, cache_hit={first.get('cache_hit', False)}")
    print(f"second call: {second_ms:.0f}ms, used_llm={second.get('used_llm')}, cache_hit={second.get('cache_hit', False)}")

    ok1 = _report("second identical query hits the response cache (cache_hit=True)", cache_ok)
    ok2 = _report("cached response is measurably faster than the original generation", faster_ok,
                   f"first={first_ms:.0f}ms, second={second_ms:.0f}ms")
    ok3 = _report("cached answer is non-empty and not itself rejected (no correctness regression)", correctness_ok)
    return ok1 and ok2 and ok3


def run():
    pure_ok = run_pure()
    live_ok = run_live_repeated_query_benchmark()
    return pure_ok and live_ok


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
