"""LLM-as-a-Judge — Section 42 of the blueprint.

Used ONLY by offline evaluation scripts (eval_*.py) against
golden_dataset.json — never inline in the live request path (ask.py never
imports this module; judging a live user request would double per-request
LLM calls for no user-facing benefit, violating Engineering Principle 2).

Section 42 is explicit an LLM judge must not be the only evaluation
signal. It's combined with, not a replacement for: query_understanding's
deterministic expected_query_class/expected_entities checks (eval_phase1/2),
grounding.py's own deterministic claim verification (used live, in
ask.py, on every real request), and the eval report format below, which
always shows the judge's verdict alongside those deterministic results
rather than letting it override them silently.

Bias mitigation (Section 42: "explain judge bias and how to reduce it"):
 - Judge provider is deliberately different from whichever provider
   generated the candidate answer, when more than one is configured — a
   model grading its own output is a well-documented self-preference bias
   in the LLM-as-judge literature. `_pick_judge_provider` enforces this;
   `judge_provider != candidate_provider` is asserted in the result so a
   report can flag the (today, unavoidable with one configured provider)
   same-provider case rather than hiding it.
 - Grading is scoped to the golden dataset's own curated `expected_facts`
   string, not "is this correct" in some open-ended sense — the judge
   can't reward a plausible-sounding fabrication just because it sounds
   right; it can only check consistency with the given expectation.
 - Output is a small integer 1-5 scale plus one short reason, not free
   prose — reduces the well-known verbosity/length bias (longer answers
   scoring higher independent of quality) and keeps grading cheap.
 - Uses gateway.generate() (Section 16) rather than calling a provider
   adapter directly, so the judge call gets the same retry/circuit-breaker/
   health-tracking treatment as any other Gateway call — no separate
   reliability mechanism invented just for this.
"""
import copy
import re

from gateway import GatewayError, NoProviderAvailable
from gateway import generate as gateway_generate
from gateway_types import GatewayRequest
from model_router import _load_config
from providers.registry import get_adapter

JUDGE_PROVIDER_PREFERENCE = ["gemini", "groq"]  # tried in order, skipping the candidate's own provider

JUDGE_PROMPT_TEMPLATE = """You are grading one answer from a portfolio Q&A assistant called ChandlerOS. Judge ONLY against the EXPECTED_FACTS given below — do not use outside knowledge, and do not reward a fluent-sounding answer that isn't actually supported by EXPECTED_FACTS.

QUESTION:
{question}

EXPECTED_FACTS (the only ground truth for this grading):
{expected_facts}

CANDIDATE_ANSWER:
{answer}

Score the CANDIDATE_ANSWER on two 1-5 integer scales:
- factuality: 5 = fully consistent with EXPECTED_FACTS and adds nothing unsupported, 1 = contradicts or fabricates.
- relevance: 5 = directly and completely answers QUESTION, 1 = off-topic or non-answer.

Respond with EXACTLY one line in this format, nothing else, no other commentary:
SCORE: factuality=<1-5> relevance=<1-5> reason=<one short sentence>
"""

SCORE_LINE_RE = re.compile(
    r"factuality\s*=\s*(?P<factuality>[1-5]).*?relevance\s*=\s*(?P<relevance>[1-5]).*?reason\s*=\s*(?P<reason>.+)",
    re.IGNORECASE | re.DOTALL,
)


class JudgeUnavailable(RuntimeError):
    pass


def _pick_judge_provider(candidate_provider: str = None) -> str:
    config = _load_config()
    active = config["active_providers"]
    for name in JUDGE_PROVIDER_PREFERENCE:
        if name in active and name != candidate_provider:
            return name
    # Only one provider configured, or it's the only one that also generated
    # the candidate — fall back to whatever's active rather than refuse to
    # judge at all; the same-provider case is surfaced in the result below.
    for name in active:
        return name
    raise JudgeUnavailable("no provider configured to judge with")


def _judge_only_config(judge_provider: str) -> dict:
    config = copy.deepcopy(_load_config())
    config["active_providers"] = [judge_provider]
    return config


def judge_answer(question: str, expected_facts: str, answer: str, candidate_provider: str = None) -> dict:
    """Returns a dict: {factuality, relevance, reason, judge_provider,
    judge_model, same_provider_as_candidate, parse_error}. Raises
    JudgeUnavailable if no provider could be reached at all (caller should
    treat that as "skip this item's judge score", not a test failure —
    it's an infrastructure gap, not a quality signal)."""
    judge_provider = _pick_judge_provider(candidate_provider)
    prompt = JUDGE_PROMPT_TEMPLATE.format(question=question, expected_facts=expected_facts, answer=answer)
    request = GatewayRequest(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100, temperature=0.0, task_complexity_hint="simple", deadline_ms=15000,
    )

    try:
        response = gateway_generate(request, config=_judge_only_config(judge_provider))
    except (GatewayError, NoProviderAvailable) as exc:
        raise JudgeUnavailable(f"judge provider {judge_provider!r} unavailable: {exc}") from exc

    match = SCORE_LINE_RE.search(response.text)
    if not match:
        return {
            "factuality": None, "relevance": None, "reason": None,
            "judge_provider": judge_provider, "judge_model": response.model,
            "same_provider_as_candidate": judge_provider == candidate_provider,
            "parse_error": True, "raw_response": response.text[:300],
        }

    return {
        "factuality": int(match.group("factuality")),
        "relevance": int(match.group("relevance")),
        "reason": match.group("reason").strip(),
        "judge_provider": judge_provider,
        "judge_model": response.model,
        "same_provider_as_candidate": judge_provider == candidate_provider,
        "parse_error": False,
    }
