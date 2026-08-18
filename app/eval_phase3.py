"""Phase 3 definition-of-done check (Section 53):

"swapping the active provider via config only (no code change) demonstrably
works; routing picks sensibly under a simulated unhealthy-provider test."

No live LLM calls here — this exercises model_router.select_provider()
directly with controlled config/health-tracker state, which is exactly what
Section 18's "adapter test contract" argues for: routing correctness
shouldn't depend on hitting live rate limits or real provider latency to
verify.
"""
import copy
import json
import sys

from gateway_types import NoProviderAvailable
from model_router import CONFIG_PATH, HEALTH_HARD_CUTOFF, _load_config, select_provider
from provider_health import ProviderHealthTracker

PASS_MARK = "PASS"
FAIL_MARK = "FAIL"


def _report(name, ok, detail=""):
    mark = PASS_MARK if ok else FAIL_MARK
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


def test_config_driven_swap():
    """Edit only router_config.json (in memory — the real file on disk is
    never touched by this test) and confirm the router's pick changes
    accordingly. Proves the router reads from config, nothing is hardcoded."""
    config = _load_config(CONFIG_PATH)
    tracker = ProviderHealthTracker()  # fresh, no history — isolates this test from eval run order

    provider_a, model_a = select_provider("simple", config=config, tracker=tracker)

    # Swap what model_a's provider serves the "simple" tier, in memory only.
    swapped_config = copy.deepcopy(config)
    swapped_config["providers"][provider_a]["simple"] = "swapped-test-model-xyz"

    provider_b, model_b = select_provider("simple", config=swapped_config, tracker=tracker)

    ok = provider_b == provider_a and model_b == "swapped-test-model-xyz"
    return _report(
        "config-driven swap changes router output with zero code change",
        ok,
        f"before={provider_a}/{model_a}, after={provider_b}/{model_b}",
    )


def test_unhealthy_provider_is_routed_around():
    """Force one provider's health below the hard cutoff and confirm the
    router picks the other one instead, even though nothing else changed."""
    config = _load_config(CONFIG_PATH)
    tracker = ProviderHealthTracker()

    providers = config["active_providers"]
    if len(providers) < 2:
        return _report("unhealthy provider routed around", False, "need 2+ active providers configured")

    unhealthy, healthy = providers[0], providers[1]
    tracker.force_unhealthy(unhealthy)

    chosen_provider, _ = select_provider("simple", config=config, tracker=tracker)
    ok = chosen_provider == healthy
    return _report(
        f"router avoids '{unhealthy}' once its health drops below {HEALTH_HARD_CUTOFF}",
        ok,
        f"expected {healthy}, got {chosen_provider}",
    )


def test_all_unhealthy_raises_no_provider_available():
    config = _load_config(CONFIG_PATH)
    tracker = ProviderHealthTracker()
    for provider in config["active_providers"]:
        tracker.force_unhealthy(provider)

    try:
        select_provider("simple", config=config, tracker=tracker)
        return _report("all-unhealthy raises NoProviderAvailable", False, "no exception raised")
    except NoProviderAvailable:
        return _report("all-unhealthy raises NoProviderAvailable", True)


def test_config_file_is_well_formed():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    required_keys = {"active_providers", "weights", "providers"}
    ok = required_keys.issubset(config.keys()) and len(config["active_providers"]) >= 1
    return _report("router_config.json has required structure", ok)


def run():
    results = [
        test_config_file_is_well_formed(),
        test_config_driven_swap(),
        test_unhealthy_provider_is_routed_around(),
        test_all_unhealthy_raises_no_provider_available(),
    ]
    passed = sum(results)
    print(f"\nPhase 3 router checks: {passed}/{len(results)} passed")
    return passed == len(results)


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
