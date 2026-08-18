"""Provider Adapter contract — Section 18 of the blueprint.

Each adapter is a small, isolated module for exactly one provider,
responsible for: auth, request shaping, response parsing, error mapping to
the Gateway's normalized_code vocabulary, and declaring static capability
metadata consumed by the Model Router (Section 17).

What an adapter must NEVER do: contain business logic (retry policy,
routing decisions, personality logic). That lives in the Gateway/Router so
behavior stays consistent no matter which adapter is active.

Every adapter module must expose:
  CAPABILITIES: ProviderCapabilities
  generate(request: GatewayRequest, model: str) -> GatewayResponse   (raises GatewayError)
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    context_window: int
    supports_streaming: bool
    supports_system_prompt: bool
    cost_per_1k_tokens: float  # 0.0 for genuinely free-tier
    avg_latency_ms: float  # static estimate; Section 19 replaces this with observed p50 later
