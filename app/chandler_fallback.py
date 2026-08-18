"""Chandler Fallback — Section 35 of the blueprint.

Triggered ONLY in the FALLBACK state (Section 34): zero LLM providers
reachable. Hand-authored, version-controlled static templates — never
generated. Hard requirement enforced by construction (not just asserted):
ask.py's FALLBACK branch calls this module directly and skips the LLM call
entirely — it never constructs a GatewayRequest, never opens a stream.
Response metadata explicitly marks provider="none", model="static_fallback"
so this is auditable in the structured response (Section 32), not just a
claim in a comment.
"""
import random
from dataclasses import dataclass, field

FALLBACK_VERSION = "1.0.0"  # versioned alongside prompts/personality (Section 45)

GENERIC_TEMPLATES = [
    "I'd normally look that up for you properly, but my LLM providers have stepped out{wait_clause}. "
    "Try again in a bit{evidence_clause}",
    "My usual sources for turning facts into sentences are down{wait_clause}. "
    "The raw facts still work fine though{evidence_clause}",
]

CHITCHAT_TEMPLATES = [
    "Hey. Normally I'd have something clever here, but my LLM providers are all down{wait_clause}. "
    "Even I need help sounding like this.",
    "I'm still ChandlerOS, technically. The part of me that generates actual sentences "
    "is on a break{wait_clause}.",
]

VIRAL_TEMPLATES = [
    "Okay, apparently Harshith has gone viral. I would like to formally request that everyone calm down. "
    "My LLM providers already have.",
    "It seems a lot of people want to know about Harshith. Which is flattering. For him. "
    "Less so for my infrastructure, which has currently given up.",
]


def _wait_clause(provider_down_seconds) -> str:
    if provider_down_seconds is None:
        return ""
    if provider_down_seconds < 60:
        return " (down for under a minute — should recover shortly)"
    minutes = int(provider_down_seconds // 60)
    return f" (down for about {minutes} minute{'s' if minutes != 1 else ''})"


def _evidence_clause(evidence_lines) -> str:
    if not evidence_lines:
        return "."
    return ", or here's what I found without the commentary:\n" + "\n".join(f"- {e}" for e in evidence_lines)


@dataclass
class FallbackResponse:
    text: str
    provider: str = "none"
    model: str = "static_fallback"
    fallback_version: str = FALLBACK_VERSION
    template_category: str = "generic"


def build_fallback_response(query_class: str, provider_down_seconds: float = None, evidence_lines: list = None,
                             viral: bool = False, template_index: int = None) -> FallbackResponse:
    """template_index bypasses the random pick-within-category (kept for
    variety in normal operation) — pass an explicit index for deterministic
    testing (eval_phase8.py)."""
    evidence_lines = evidence_lines or []

    def pick(templates):
        return templates[template_index % len(templates)] if template_index is not None else random.choice(templates)

    if viral:
        return FallbackResponse(text=pick(VIRAL_TEMPLATES), template_category="viral")

    if query_class == "general":
        text = pick(CHITCHAT_TEMPLATES).format(wait_clause=_wait_clause(provider_down_seconds))
        return FallbackResponse(text=text, template_category="chitchat")

    text = pick(GENERIC_TEMPLATES).format(
        wait_clause=_wait_clause(provider_down_seconds), evidence_clause=_evidence_clause(evidence_lines),
    )
    return FallbackResponse(text=text, template_category="generic")
