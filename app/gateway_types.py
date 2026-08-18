"""Gateway interface types — Section 16 of the blueprint.

Split out from gateway.py so provider adapters (providers/*.py) can import
these without a circular dependency: gateway.py orchestrates and needs to
import the provider registry, while adapters need these types but must
never import gateway.py itself (an adapter is a leaf module — Section 18:
"what an adapter must never do" includes knowing about routing/orchestration).
"""
from dataclasses import dataclass


@dataclass
class GatewayRequest:
    messages: list  # [{role, content}]
    max_tokens: int = 1024
    temperature: float = 0.3
    stream: bool = False  # Section 33 — when True, adapter.generate_stream() is used instead of adapter.generate()
    task_complexity_hint: str = "simple"  # "simple" | "complex"
    deadline_ms: int = 40000
    estimated_prompt_tokens: int = None  # Section 27: router hard-filters models whose window can't fit this


@dataclass
class GatewayResponse:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    finish_reason: str = "stop"


# Normalized error vocabulary — every adapter maps its provider's distinct
# error shapes to one of these, so routing/observability code never needs to
# know a specific provider's error format.
TIMEOUT = "TIMEOUT"
RATE_LIMITED = "RATE_LIMITED"
PROVIDER_ERROR = "PROVIDER_ERROR"
CONTEXT_TOO_LONG = "CONTEXT_TOO_LONG"
UNKNOWN = "UNKNOWN"

RETRIABLE_CODES = {TIMEOUT, RATE_LIMITED, PROVIDER_ERROR}


class GatewayError(RuntimeError):
    def __init__(self, normalized_code: str, message: str, raw=None, retriable: bool = None):
        super().__init__(message)
        self.normalized_code = normalized_code
        self.raw = raw
        self.retriable = retriable if retriable is not None else (normalized_code in RETRIABLE_CODES)


class NoProviderAvailable(RuntimeError):
    """Every configured provider is unhealthy or missing. Section 17: this is
    the trigger for Graceful Degradation (Section 34, Phase 8) — Phase 3 just
    surfaces it honestly rather than pretending a call happened."""
