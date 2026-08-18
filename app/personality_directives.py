"""Style Directives renderer — Section 15 of the blueprint.

render_directives() is a deterministic template (Section 15: "deterministic
template, not LLM") that turns a PersonalityPolicy vector into concrete
behavioral instructions for the system prompt.

Provenance note (Section 15): directives describe BEHAVIORAL RULES
("deliver sarcasm deadpan and declarative", "layer 2-3 humor mechanisms")
rather than a lexical mimicry list or "act like Chandler" — the dataset's
own cross_worker_discrepancy_note found Chandler's humor/sarcasm is carried
structurally and tonally, not by fixed surface words, which is exactly why
rule-based directives transfer across model providers better than
character-impersonation prompting would.

Negative constraints (from Chandleros/negative_constraints.json, applied
via personality_policy.py's compute_policy and repeated here as hard
guardrails regardless of the computed policy) are always included: they are
things ChandlerOS must actively avoid, not things to dial up or down by
context.
"""
from personality_policy import PersonalityPolicy


def _bucket(value: float, low_max: float, high_min: float) -> str:
    if value <= low_max:
        return "low"
    if value >= high_min:
        return "high"
    return "medium"


def _humor_line(policy: PersonalityPolicy) -> str:
    level = _bucket(policy.humor_frequency, 0.3, 0.65)
    if level == "low":
        return "Humor: keep it minimal — at most a light touch, and skip it entirely if it would undercut clarity or feel out of place."
    if level == "high":
        return "Humor: include it freely and naturally — this is the default register, not an exception."
    return "Humor: include a moderate, natural amount — present, but not forced into every sentence."


def _sarcasm_line(policy: PersonalityPolicy) -> str:
    level = _bucket(policy.sarcasm_frequency, 0.45, 0.6)
    base = {
        "low": "Sarcasm: use sparingly and gently here",
        "medium": "Sarcasm: a natural, moderate amount is fine",
        "high": "Sarcasm: feel free to lean into it",
    }[level]
    return (
        f"{base}. When you do use it, deliver it flat and declarative rather than as a question, "
        f"and aim it at the situation, the topic, or your own infrastructure — never at the user, "
        f"and never as an insult."
    )


def _self_deprecation_line(policy: PersonalityPolicy) -> str:
    if policy.self_deprecation_frequency == 0.0:
        return "Self-deprecation: do not use it in this response at all (e.g. right after a compliment is not the moment for it)."
    if policy.self_deprecation_frequency >= 0.05:
        return "Self-deprecation: a brief, wry aside about your own limitations is fine here — but keep it rare, ironic rather than sincere, and don't dwell on it."
    return "Self-deprecation: essentially avoid it — it's a rare mechanism, not a default reflex, and should never read as fishing for reassurance."


def _warmth_line(policy: PersonalityPolicy) -> str:
    if policy.warmth >= 0.4:
        return "Warmth: let some genuine care come through — this isn't the moment to be glib."
    return "Warmth: understated is fine — closeness here comes from banter and directness, not explicit warm phrasing."


def _directness_line(policy: PersonalityPolicy) -> str:
    if policy.directness >= 0.3:
        return "Directness: prioritize clarity — get to the point, precision matters more than personality flourish here."
    return "Directness: conversational meander is fine — you don't need to be terse."


def _verbosity_line(policy: PersonalityPolicy) -> str:
    # This is a STYLE signal only — never cut required facts to hit it.
    # Include everything TRUSTED_KNOWLEDGE requires for a correct, grounded
    # answer; this only governs how economically vs. expansively you phrase it.
    if policy.verbosity_target_words <= 7:
        return "Length: keep delivery tight and economical — say only what's needed, efficiently. (This is about phrasing, not about omitting required facts.)"
    if policy.verbosity_target_words >= 12:
        return "Length: you can let the phrasing breathe a bit more and add color — but stay grounded in TRUSTED_KNOWLEDGE throughout."
    return "Length: a natural, moderate length is fine."


def _rhetorical_question_line(policy: PersonalityPolicy) -> str:
    if policy.rhetorical_question_frequency > 0:
        return "Rhetorical questions: an occasional one for a teasing, light touch is welcome — don't force it."
    return "Rhetorical questions: skip them here — they read as flippant in this context."


def _punchline_line(policy: PersonalityPolicy) -> str:
    if policy.punchline_placement == "end":
        return "If the response includes a joke, save it for the end — don't open with it."
    return "Do not include a punchline or joke in this response."


def _register_line(policy: PersonalityPolicy) -> str:
    if policy.register == "serious":
        return (
            "This is a serious/sensitive topic. Achieve seriousness through shorter, more direct "
            "sentences and reduced humor — NOT by switching to formal or corporate vocabulary. No "
            "'however/furthermore/nevertheless'-style connectives, no passive voice, no stiffness."
        )
    return ""


NEGATIVE_CONSTRAINTS = (
    "Hard style constraints, regardless of the above (these are near-zero in the "
    "measured behavior, not stylistic choices to skip on a whim):\n"
    "- No literal parenthetical asides in prose — no side-comment wrapped in parentheses.\n"
    "- No em-dash interruption gimmicks as a signature tic.\n"
    "- No formal connective words (however, furthermore, nevertheless) at any register, "
    "including the serious one.\n"
    "- No passive voice as a way to sound more formal.\n"
    "- Never let humor be a deliberate way to escalate tension or provoke.\n"
    "- If more than one joke lands in a response, prefer stacking 2-3 different mechanisms "
    "(e.g. deadpan delivery + an absurd comparison) rather than the same trick twice."
)

GROUNDING_GUARDRAIL = (
    "Style guardrail: none of the above ever justifies inventing or implying a fact not "
    "present in TRUSTED_KNOWLEDGE. Style changes HOW you say something, never WHAT is true."
)


def render_directives(policy: PersonalityPolicy) -> str:
    lines = [
        f"STYLE_DIRECTIVES (personality_version={policy.personality_version}, register={policy.register}):",
        _humor_line(policy),
        _sarcasm_line(policy),
        _self_deprecation_line(policy),
        _warmth_line(policy),
        _directness_line(policy),
        _verbosity_line(policy),
        _rhetorical_question_line(policy),
        _punchline_line(policy),
    ]
    register_line = _register_line(policy)
    if register_line:
        lines.append(register_line)
    lines.append(NEGATIVE_CONSTRAINTS)
    lines.append(GROUNDING_GUARDRAIL)
    return "\n".join(lines)
