"""Output Validation — Section 31 of the blueprint.

Post-generation checks, cheap/deterministic first:
1. Schema check    -> non-empty response
2. Length check     -> too-long truncated deterministically (non-blocking,
                       auto-fixed here); too-short is logged only, not
                       blocking — a short-but-correct factual answer isn't a
                       failure, and a made-up "reformatting pass" for it
                       would do more harm than good
3. Grounding check  -> Section 29's claim verification (blocking)
4. Safety check     -> leaked system-prompt/delimiter content (blocking)
5. Personality consistency -> soft, logged only, never blocking (Section 31:
   "over-blocking on a soft/subjective dimension would hurt availability
   for a low-severity issue")

On failure: schema/grounding/safety failures are `blocking_failures` — the
caller (ask.py) drives the regenerate-then-fallback path (Section 29) for
those. This module makes no LLM calls itself.
"""
from dataclasses import dataclass, field

from grounding import check_grounding

MIN_ANSWER_WORDS = 2  # informational only, never blocks
MAX_ANSWER_WORDS = 500

LEAK_MARKERS = [
    "system_instructions", "trusted_knowledge", "recent_conversation", "user_input",
    "===begin_", "===end_",
]

# Lightweight humor-marker heuristic, NOT another LLM call (Section 31).
HUMOR_MARKERS = ["haha", "lol", "😂", "😉", ";)", "kidding", "!"]


@dataclass
class ValidationResult:
    passed: bool
    schema_ok: bool
    too_short: bool
    too_long: bool
    grounding_result: object
    safety_ok: bool
    leaked_markers: list = field(default_factory=list)
    personality_consistent: bool = True
    blocking_failures: list = field(default_factory=list)


def _schema_ok(answer_text: str) -> bool:
    return bool(answer_text and answer_text.strip())


def _safety_check(answer_text: str, fence_token: str = None):
    lowered = answer_text.lower()
    leaked = [m for m in LEAK_MARKERS if m in lowered]
    if fence_token and fence_token.lower() in lowered:
        leaked.append("fence_token")
    return (len(leaked) == 0, leaked)


def _personality_consistency_check(answer_text: str, policy) -> bool:
    if policy is None or policy.register != "serious":
        return True  # only checking the "supposed to be serious but wasn't" case
    lowered = answer_text.lower()
    return not any(marker in lowered for marker in HUMOR_MARKERS)


def truncate_to_word_limit(answer_text: str, max_words: int = MAX_ANSWER_WORDS) -> str:
    words = answer_text.split()
    if len(words) <= max_words:
        return answer_text
    return " ".join(words[:max_words]) + " ..."


def validate_output(answer_text: str, subgraph_facts, policy=None, fence_token: str = None, conn=None) -> ValidationResult:
    schema_ok = _schema_ok(answer_text)
    if not schema_ok:
        return ValidationResult(
            passed=False, schema_ok=False, too_short=True, too_long=False,
            grounding_result=None, safety_ok=False, blocking_failures=["schema"],
        )

    word_count = len(answer_text.split())
    too_short = word_count < MIN_ANSWER_WORDS
    too_long = word_count > MAX_ANSWER_WORDS

    grounding_result = check_grounding(answer_text, subgraph_facts, conn=conn)
    safety_ok, leaked = _safety_check(answer_text, fence_token=fence_token)
    personality_consistent = _personality_consistency_check(answer_text, policy)

    blocking_failures = []
    if not grounding_result.supported:
        blocking_failures.append("grounding")
    if not safety_ok:
        blocking_failures.append("safety")

    return ValidationResult(
        passed=(len(blocking_failures) == 0),
        schema_ok=True,
        too_short=too_short,
        too_long=too_long,
        grounding_result=grounding_result,
        safety_ok=safety_ok,
        leaked_markers=leaked,
        personality_consistent=personality_consistent,
        blocking_failures=blocking_failures,
    )
