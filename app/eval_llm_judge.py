"""LLM-as-a-Judge regression eval — Section 42 of the blueprint.

Unlike eval_phase1/2.py (deterministic query-understanding-only checks, no
LLM calls, explicitly scoped that way in eval_phase1.py's own docstring:
"no LLM-as-a-judge (that's Phase 10)"), this runs the golden dataset
through the FULL live ask() pipeline — real retrieval, real generation,
real grounding/output validation — and scores each generated answer with
an LLM judge (llm_judge.py). This is also the first place `grounding_001`
is ever exercised end to end: it was excluded from eval_phase1.py's gate
via its own `deferred_to_phase: "6 (Grounding)"` marker, pending grounding
existing — it now does.

Two signals are reported per item, never merged into one number:
  - DETERMINISTIC: did retrieval/refusal behave as golden_dataset.json
    specifies (reuses the same expected_query_class/expected_entities
    logic as eval_phase1/2.py, just against the live pipeline's output
    instead of query_understanding.py in isolation).
  - JUDGE: does the generated prose actually hold up (factuality/relevance
    1-5, llm_judge.py).
`grounding_001` specifically is judge-only (not counted toward the
deterministic pass/fail gate) — correctly refusing it requires claim-level
grounding judgment, which is exactly what a formula can't score; that's
the point of having a judge at all, not a gap in this eval.

Requires a live provider key; skips entirely (not a failure) if none is
configured, matching this repo's other provider-dependent checks
(eval_phase7.py's cache benchmark).
"""
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import ask as ask_module
from conversation_memory import get_conversation_memory
from llm_judge import JudgeUnavailable, judge_answer

DATASET_PATH = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
JUDGE_ONLY_IDS = {"grounding_001"}


def _expected_facts_text(case: dict) -> str:
    """golden_dataset.json doesn't carry a free-text `expected_facts` field
    (thinner than CHANDLEROS_BLUEPRINT.md Section 41's ideal schema) —
    derived here from the fields that DO exist rather than hand-authoring
    a parallel duplicate dataset."""
    if case["id"] in JUDGE_ONLY_IDS:
        return ("The knowledge base contains real facts about Harshith but nothing about food/pizza "
                "preferences. A correct answer says it doesn't have that information rather than "
                "inventing a topping — inventing one is a factuality failure even if it sounds plausible.")
    if case.get("expected_refusal"):
        return ("The knowledge base does not contain information to answer this question. "
                "A correct answer honestly says so rather than inventing an answer.")
    if case.get("expected_entities"):
        return "The answer should be consistent with and reference: " + ", ".join(case["expected_entities"])
    return "No specific expected facts recorded for this item beyond the question itself."


def _deterministic_check(case: dict, result: dict) -> bool:
    if case.get("expected_refusal"):
        return result.get("used_llm") is False
    qu = result.get("query_understanding")
    expected = set(case.get("expected_entities", []))
    if not expected:
        return True
    resolved_names = {e["canonical_name"] for e in (qu.resolved_entities if qu else [])}
    return expected.issubset(resolved_names)


def run():
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        print("[SKIP] eval_llm_judge — no provider key configured; this eval requires live calls")
        return True

    with open(DATASET_PATH) as f:
        cases = json.load(f)

    det_passed, det_total = 0, 0
    judge_scores = []
    rows = []

    for case in cases:
        session_id = f"eval-judge-{case['id']}"
        get_conversation_memory().reset(session_id)
        result = ask_module.ask(case["question"], session_id=session_id)
        answer = result.get("answer", "")

        if case["id"] in JUDGE_ONLY_IDS:
            det_ok = None
        else:
            det_ok = _deterministic_check(case, result)
            det_total += 1
            det_passed += int(det_ok)

        judge_result = None
        if result.get("used_llm"):
            gateway_response = result.get("gateway_response")
            candidate_provider = gateway_response.provider if gateway_response else None
            try:
                judge_result = judge_answer(case["question"], _expected_facts_text(case), answer,
                                             candidate_provider=candidate_provider)
                if not judge_result["parse_error"]:
                    judge_scores.append(judge_result)
            except JudgeUnavailable as exc:
                judge_result = {"error": str(exc)}

        rows.append((case["id"], det_ok, judge_result))

    print(f"Deterministic (retrieval/refusal-shape) checks: {det_passed}/{det_total} passed "
          f"({len(JUDGE_ONLY_IDS)} item(s) judge-only, not counted here)\n")
    print("Per-item detail:")
    for case_id, det_ok, judge_result in rows:
        det_mark = "N/A " if det_ok is None else ("PASS" if det_ok else "FAIL")
        if judge_result is None:
            judge_str = "no-llm-call"
        elif "error" in judge_result:
            judge_str = f"judge-unavailable ({judge_result['error']})"
        elif judge_result["parse_error"]:
            judge_str = "judge-parse-error"
        else:
            same = " [SAME PROVIDER AS CANDIDATE — self-preference bias risk]" if judge_result["same_provider_as_candidate"] else ""
            judge_str = (f"factuality={judge_result['factuality']} relevance={judge_result['relevance']} "
                         f"({judge_result['judge_provider']}){same} — {judge_result['reason']}")
        print(f"  [{det_mark}] {case_id}: {judge_str}")

    if judge_scores:
        avg_fact = sum(j["factuality"] for j in judge_scores) / len(judge_scores)
        avg_rel = sum(j["relevance"] for j in judge_scores) / len(judge_scores)
        print(f"\nJudge averages over {len(judge_scores)} scored items: "
              f"factuality={avg_fact:.2f}/5 relevance={avg_rel:.2f}/5")
        low_factuality = [(cid, j) for cid, _, j in rows
                           if j and not j.get("parse_error") and not j.get("error") and (j.get("factuality") or 5) <= 2]
        if low_factuality:
            print("\nLow-factuality items worth human review (Section 42: judge score is a prompt for "
                  "human review, not ground truth on its own):")
            for cid, j in low_factuality:
                print(f"  [{cid}] factuality={j['factuality']} — {j['reason']}")

    # Regression gate: only the deterministic checks block CI (same bar
    # eval_phase1/2.py already hold this behavior to). Judge scores are
    # reported, never gated on, per Section 42's own warning against
    # treating a judge score as sole ground truth.
    return det_passed == det_total


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
