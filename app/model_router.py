"""Model Router — Section 17 of the blueprint.

Scored decision, not a linear fallback chain:

    score(provider, model) =
        w1 * capability_fit(task_complexity_hint, tier)
      + w2 * (1 - normalized_latency(model))
      + w3 * health(provider)
      + w4 * remaining_quota_headroom(provider)
      + w5 * (1 - normalized_cost(model))
      + w6 * historical_quality(model)

Weights and the provider/model/tier table live in router_config.json —
"configuration, not code" (Section 17): swapping which model serves a tier,
re-weighting the score, or changing which providers are active is a JSON
edit, no Python change, no redeploy of this module.
"""
import json
import os

from circuit_breaker import OPEN, get_breaker
from gateway_types import NoProviderAvailable
from provider_health import get_tracker
from providers.registry import get_adapter

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "router_config.json")

LATENCY_CEILING_MS = 6000.0
COST_CEILING_PER_1K = 1.0  # $1/1k tokens as a normalization ceiling; both current providers are 0
HEALTH_HARD_CUTOFF = 0.15  # below this, treat the provider as unavailable, not just low-scored
                            # (approximates a circuit-breaker OPEN state; Phase 4 formalizes this)


def _load_config(path=CONFIG_PATH):
    with open(path) as f:
        return json.load(f)


def get_active_providers(config=None) -> list:
    config = config or _load_config()
    return list(config["active_providers"])


def _capability_fit(task_complexity_hint: str, tier: str) -> float:
    if task_complexity_hint == tier:
        return 1.0
    return 0.5  # usable but mismatched (e.g. a simple query answered by the "complex" model)


def _normalized_latency(observed_ms, static_ms) -> float:
    ms = observed_ms if observed_ms is not None else static_ms
    return min(1.0, ms / LATENCY_CEILING_MS)


def _normalized_cost(cost_per_1k) -> float:
    return min(1.0, cost_per_1k / COST_CEILING_PER_1K)


def _score(provider_name, tier, model, task_complexity_hint, config, tracker):
    adapter = get_adapter(provider_name)
    caps = adapter.capabilities(model)
    weights = config["weights"]

    capability_fit = _capability_fit(task_complexity_hint, tier)
    latency = _normalized_latency(tracker.observed_avg_latency_ms(provider_name), caps.avg_latency_ms)
    health = tracker.health_score(provider_name)
    quota = tracker.quota_headroom(provider_name)
    cost = _normalized_cost(caps.cost_per_1k_tokens)
    quality = config.get("historical_quality", {}).get(model, 0.7)  # neutral default if unrated

    score = (
        weights["capability_fit"] * capability_fit
        + weights["latency"] * (1 - latency)
        + weights["health"] * health
        + weights["quota"] * quota
        + weights["cost"] * (1 - cost)
        + weights["quality"] * quality
    )
    return score, health


def select_candidates(task_complexity_hint: str, config=None, tracker=None, breaker=None,
                       estimated_prompt_tokens: int = None):
    """All viable (score, provider, model) candidates, best first. An OPEN
    circuit is a hard exclusion (Section 20: "not just a penalty, because
    retrying a definitively-down provider is pure waste") — checked before
    the health hard-cutoff, which catches degraded-but-not-yet-tripped
    providers the breaker hasn't formally opened yet. A model whose context
    window can't fit the realized prompt is excluded the same way (Section
    27: "a hard filter in the routing score function, not a runtime
    failure") — every currently-routed model has a huge window, so this
    rarely trips today, but the filter is real, not decorative."""
    config = config or _load_config()
    tracker = tracker or get_tracker()
    breaker = breaker or get_breaker()

    candidates = []
    for provider_name in config["active_providers"]:
        if breaker.get_state(provider_name) == OPEN:
            continue
        tiers = config["providers"].get(provider_name, {})
        for tier, model in tiers.items():
            adapter = get_adapter(provider_name)
            if estimated_prompt_tokens is not None:
                caps = adapter.capabilities(model)
                if estimated_prompt_tokens > caps.context_window:
                    continue
            score, health = _score(provider_name, tier, model, task_complexity_hint, config, tracker)
            if health < HEALTH_HARD_CUTOFF:
                continue  # Section 17: unhealthy provider's score effectively collapses to "excluded"
            candidates.append((score, provider_name, model))

    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates


def select_provider(task_complexity_hint: str, config=None, tracker=None, breaker=None,
                     estimated_prompt_tokens: int = None):
    candidates = select_candidates(task_complexity_hint, config=config, tracker=tracker, breaker=breaker,
                                    estimated_prompt_tokens=estimated_prompt_tokens)
    if not candidates:
        raise NoProviderAvailable(
            f"No provider met the health/circuit/context-window threshold for "
            f"task_complexity_hint={task_complexity_hint!r}"
        )
    _, provider_name, model = candidates[0]
    return provider_name, model
