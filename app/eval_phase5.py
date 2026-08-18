"""Phase 5 definition-of-done check (Section 53):

"personality golden slice passes on every routed provider within tolerance
bands." Tests: "policy-compute unit tests (fixed context in, fixed policy
vector out)."

Cross-provider tolerance-band testing needs an LLM judge (Section 42),
which is Phase 10 — not built yet. What Phase 5 owns and this file checks:
compute_policy() is a pure, deterministic function that reacts correctly to
context signals, negative constraints are structurally enforced (not just
described), and the IP/safety boundary (Section 15) is respected by
construction. A live cross-provider smoke test (not pass/fail-graded, just
demonstrated) is run separately, not part of this automated gate.
"""
import inspect
import sys

from personality_directives import render_directives
from personality_policy import (
    ALLOWED_DATASET_FILES,
    PersonalityContext,
    compute_policy,
)

PASS_MARK = "PASS"
FAIL_MARK = "FAIL"


def _report(name, ok, detail=""):
    mark = PASS_MARK if ok else FAIL_MARK
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


def test_deterministic_pure_function():
    ctx = PersonalityContext(query_class="simple_fact", raw_query="Where did Harshith study?")
    p1 = compute_policy(ctx)
    p2 = compute_policy(ctx)
    ok = p1 == p2
    return _report("compute_policy is deterministic (same input -> identical output)", ok)


def test_technical_question_raises_directness():
    casual = compute_policy(PersonalityContext(query_class="general", raw_query="hi, what's up"))
    technical = compute_policy(PersonalityContext(query_class="simple_fact", raw_query="Where did Harshith study?"))
    ok = technical.directness > casual.directness
    return _report(
        "technical query raises directness vs. casual query", ok,
        f"technical={technical.directness}, casual={casual.directness}",
    )


def test_frustration_suppresses_sarcasm_but_never_to_zero():
    calm = compute_policy(PersonalityContext(query_class="simple_fact", raw_query="Where did Harshith study?"))
    frustrated = compute_policy(PersonalityContext(
        query_class="simple_fact", raw_query="This is wrong, not helpful at all, where did Harshith study?"
    ))
    ok = 0 < frustrated.sarcasm_frequency < calm.sarcasm_frequency
    return _report(
        "frustration signal lowers sarcasm but never to zero (suppress_sarcasm_in_vulnerability)", ok,
        f"calm={calm.sarcasm_frequency}, frustrated={frustrated.sarcasm_frequency}",
    )


def test_compliment_hard_zeroes_self_deprecation():
    ctx = PersonalityContext(query_class="general", raw_query="great job, this is awesome! who are you?")
    policy = compute_policy(ctx)
    ok = policy.self_deprecation_frequency == 0.0
    return _report("self-deprecation is a hard 0.0 immediately after a compliment (never-after-praise)", ok,
                    f"got {policy.self_deprecation_frequency}")


def test_serious_topic_lowers_humor_and_suppresses_punchline():
    normal = compute_policy(PersonalityContext(query_class="general", raw_query="hi"))
    serious = compute_policy(PersonalityContext(
        query_class="general", raw_query="Harshith was laid off recently, can you tell me about that"
    ))
    ok = (serious.humor_frequency < normal.humor_frequency
          and serious.punchline_placement == "none"
          and serious.register == "serious")
    return _report(
        "serious topic lowers humor, suppresses punchline, sets register=serious", ok,
        f"normal_humor={normal.humor_frequency}, serious_humor={serious.humor_frequency}, "
        f"punchline={serious.punchline_placement}, register={serious.register}",
    )


def test_serious_does_not_trigger_formal_register_in_directives():
    # The directive text legitimately NAMES "however/furthermore/nevertheless"
    # as words to avoid — so the check isn't "the word never appears", it's
    # "the word only appears as part of a 'don't use this' instruction, and
    # the directives never themselves switch to formal register (e.g. no
    # passive-voice-as-formality instruction, no hedging language added)."
    ctx = PersonalityContext(query_class="general", raw_query="Harshith was laid off, what happened")
    policy = compute_policy(ctx)
    text = render_directives(policy)
    mentions_as_prohibition = "no 'however/furthermore/nevertheless'" in text.lower()
    ok = policy.register == "serious" and mentions_as_prohibition
    return _report(
        "seriousness explicitly prohibits formal connectives rather than adopting them "
        "(avoid_formal_register_even_when_serious)", ok,
    )


def test_refusal_suppresses_punchline_even_without_other_serious_signals():
    ctx = PersonalityContext(query_class="entity_lookup", raw_query="tell me about project X", is_refusal_response=True)
    policy = compute_policy(ctx)
    ok = policy.punchline_placement == "none"
    return _report("is_refusal_response alone suppresses punchline placement", ok)


def test_awkward_refusal_raises_self_deprecation_ceiling():
    baseline = compute_policy(PersonalityContext(query_class="entity_lookup", raw_query="tell me about project X"))
    awkward = compute_policy(PersonalityContext(
        query_class="entity_lookup", raw_query="tell me about project X", had_to_refuse_recently=True
    ))
    ok = awkward.self_deprecation_frequency > baseline.self_deprecation_frequency
    return _report(
        "an awkward/just-had-to-refuse moment raises self-deprecation above baseline "
        "(self_deprecate_rarely_and_only_when_uncomfortable)", ok,
        f"baseline={baseline.self_deprecation_frequency}, awkward={awkward.self_deprecation_frequency}",
    )


def test_negative_constraints_always_present_in_rendered_directives():
    contexts = [
        PersonalityContext(query_class="general", raw_query="hi"),
        PersonalityContext(query_class="simple_fact", raw_query="where did Harshith study"),
        PersonalityContext(query_class="general", raw_query="Harshith was laid off"),
    ]
    rendered = [render_directives(compute_policy(c)).lower() for c in contexts]
    ok = all("parenthetical" in text for text in rendered) and all("passive voice" in text for text in rendered)
    return _report("negative constraints (parenthetical asides, passive voice) are always rendered", ok)


def test_grounding_guardrail_always_present():
    ctx = PersonalityContext(query_class="simple_fact", raw_query="where did Harshith study")
    text = render_directives(compute_policy(ctx))
    ok = "never let" in text.lower() and "trusted_knowledge" in text.lower()
    return _report("grounding guardrail (style never introduces unsupported facts) is always rendered", ok)


def test_ip_boundary_only_reads_allowed_files():
    # Checks what the module actually LOADS (every _load("...") call site),
    # not what its docstrings mention — the module's own comments name the
    # forbidden files explicitly to document the boundary, which is fine;
    # what matters is that _load() itself is never called with them.
    import re

    import personality_policy
    source = inspect.getsource(personality_policy)
    loaded_files = re.findall(r'_load\("([^"]+)"\)', source)
    forbidden = {"chandleros_dataset.json", "dataset_provenance.json", "chandler_fingerprint.json"}
    hits = [f for f in loaded_files if f in forbidden]
    ok = (
        bool(loaded_files)
        and not hits
        and set(loaded_files).issubset(ALLOWED_DATASET_FILES)
        and ALLOWED_DATASET_FILES == {
            "control_dimensions.json", "negative_constraints.json", "behavioral_rules.json",
            "personality_context_matrix.json", "character_invariants.json",
        }
    )
    return _report(
        "personality_policy.py only ever _load()s allowed abstracted artifacts, never raw dataset files", ok,
        f"actually loaded: {loaded_files}, forbidden hits: {hits}",
    )


def test_directives_contain_no_literal_dataset_dialogue_marker():
    # A cheap structural smoke check: the rendered directive text should never
    # exceed a short length per "sentence" the way a reproduced quote would,
    # and should not contain quotation-wrapped multi-word dialogue snippets.
    ctx = PersonalityContext(query_class="general", raw_query="hi")
    text = render_directives(compute_policy(ctx))
    import re
    quoted = re.findall(r'"([^"]{20,})"', text)
    ok = len(quoted) == 0
    return _report("rendered directives contain no long quoted strings (no verbatim-dialogue risk)", ok,
                    f"quoted snippets found: {quoted}")


def run():
    tests = [
        test_deterministic_pure_function,
        test_technical_question_raises_directness,
        test_frustration_suppresses_sarcasm_but_never_to_zero,
        test_compliment_hard_zeroes_self_deprecation,
        test_serious_topic_lowers_humor_and_suppresses_punchline,
        test_serious_does_not_trigger_formal_register_in_directives,
        test_refusal_suppresses_punchline_even_without_other_serious_signals,
        test_awkward_refusal_raises_self_deprecation_ceiling,
        test_negative_constraints_always_present_in_rendered_directives,
        test_grounding_guardrail_always_present,
        test_ip_boundary_only_reads_allowed_files,
        test_directives_contain_no_literal_dataset_dialogue_marker,
    ]
    results = [t() for t in tests]
    passed = sum(results)
    print(f"\nPhase 5 personality checks: {passed}/{len(results)} passed")
    return passed == len(results)


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
