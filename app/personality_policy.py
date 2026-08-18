"""Personality Policy — Sections 14-15 of the blueprint.

compute_policy() is a pure function: fixed context signals in, a fixed
PersonalityPolicy vector out. No LLM call, fully unit-testable.

Baselines are loaded directly from the Chandleros/ dataset's abstracted
artifacts (control_dimensions.json, negative_constraints.json,
behavioral_rules.json) rather than hand-copied into Python — this keeps the
dataset as the single source of truth and means a future dataset refinement
(Section 15: "re-deriving control_dimensions.json from a larger sample")
takes effect here with zero code changes.

IP/safety boundary (Section 15): this module and personality_directives.py
are the ONLY code allowed to read from Chandleros/, and they read ONLY the
abstracted rule/policy files listed in ALLOWED_DATASET_FILES below — never
chandleros_dataset.json (the raw transformed corpus) or dataset_provenance.json.
Those files contain no runtime-relevant content anyway (Section 15: "the
personality layer's only inputs are the policy tables ... which contain no
verbatim dialogue"), but the restriction is enforced here by construction,
not just by convention, so a future edit can't accidentally reach for them.
"""
import json
import os
from dataclasses import dataclass, field

CHANDLEROS_DIR = os.path.join(os.path.dirname(__file__), "..", "Chandleros")

ALLOWED_DATASET_FILES = {
    "control_dimensions.json",
    "negative_constraints.json",
    "behavioral_rules.json",
    "personality_context_matrix.json",
    "character_invariants.json",
}

PERSONALITY_VERSION = "chandleros-2026.08.0"


def _load(filename: str) -> dict:
    assert filename in ALLOWED_DATASET_FILES, (
        f"{filename} is not in ALLOWED_DATASET_FILES — the IP/safety boundary (Section 15) "
        f"only permits reading abstracted rule/policy artifacts, never the raw dataset."
    )
    with open(os.path.join(CHANDLEROS_DIR, filename)) as f:
        return json.load(f)


def _dimension_baselines():
    data = _load("control_dimensions.json")
    return {d["dimension"]: d["observed_baseline"] for d in data["dimensions"]}


_BASELINES = _dimension_baselines()

HUMOR_FREQUENCY_BASELINE = _BASELINES["humor_frequency"]  # 0.8
SARCASM_FREQUENCY_BASELINE = _BASELINES["sarcasm_frequency"]  # 0.592
SARCASM_FREQUENCY_VULNERABLE_FLOOR = 0.491  # sarcasm_profile.json observed floor; never goes below this
SARCASM_TARGET_BIAS_BASELINE = _BASELINES["sarcasm_target_bias"]  # {other_character, situation, self, other}
SELF_DEPRECATION_FREQUENCY_BASELINE = _BASELINES["self_deprecation_frequency"]  # 0.025
SELF_DEPRECATION_FREQUENCY_AWKWARD_CEILING = 0.06  # observed_range upper bound
WARMTH_BASELINE = _BASELINES["warmth"]  # 0.01 (floor estimate, lexical-marker undercounts — see dataset caveat)
DIRECTNESS_BASELINE = _BASELINES["directness"]  # 0.062
VERBOSITY_BASELINE_WORDS = _BASELINES["verbosity"]  # 9.38 — see PersonalityPolicy.verbosity_target_words note
RHETORICAL_QUESTION_FREQUENCY_BASELINE = _BASELINES["rhetorical_question_frequency"]  # 0.054

TECHNICAL_QUERY_CLASSES = {"simple_fact", "entity_lookup", "relationship", "multi_hop"}
CASUAL_QUERY_CLASSES = {"general", "semantic"}

FRUSTRATION_MARKERS = [
    "this is wrong", "not helpful", "useless", "doesn't work", "frustrat",
    "annoyed", "annoying", "come on", "seriously?", "ugh", "!!",
]
COMPLIMENT_MARKERS = [
    "great job", "awesome", "nice work", "impressive", "well done", "love this",
    "you're the best", "amazing work", "good bot", "well played",
]
SERIOUS_TOPIC_MARKERS = [
    "layoff", "laid off", "fired", "failure", "failed", "died", "passed away",
    "difficult time", "tragedy", "loss of", "grieving",
]


@dataclass
class PersonalityContext:
    query_class: str = "general"
    raw_query: str = ""
    is_refusal_response: bool = False  # gates humor/punchline suppression; only meaningful if this path DOES reach the LLM
    had_to_refuse_recently: bool = False  # "awkward moment" trigger for self-deprecation
    injection_flagged: bool = False  # Section 30: forces the tightened/low-creative-freedom variant
    provider: str = "unknown"
    traffic_state: str = "normal"  # Viral Mode input — structural placeholder, Phase 8


@dataclass
class PersonalityPolicy:
    personality_version: str
    humor_frequency: float
    sarcasm_frequency: float
    sarcasm_target_bias: dict
    self_deprecation_frequency: float
    warmth: float
    directness: float
    verbosity_target_words: float  # relative style signal, NOT a hard cap on grounded factual content — see render_directives
    rhetorical_question_frequency: float
    punchline_placement: str  # "end" | "none"
    register: str  # "normal" | "serious"
    signals: dict = field(default_factory=dict)  # detected context signals, for observability/debugging


def detect_frustration(raw_query: str) -> bool:
    text = raw_query.lower()
    return any(marker in text for marker in FRUSTRATION_MARKERS)


def detect_compliment(raw_query: str) -> bool:
    text = raw_query.lower()
    return any(marker in text for marker in COMPLIMENT_MARKERS)


def detect_serious_topic(raw_query: str) -> bool:
    text = raw_query.lower()
    return any(marker in text for marker in SERIOUS_TOPIC_MARKERS)


def _register_for(query_class: str) -> str:
    return "technical" if query_class in TECHNICAL_QUERY_CLASSES else "casual"


def compute_policy(ctx: PersonalityContext) -> PersonalityPolicy:
    frustrated = detect_frustration(ctx.raw_query)
    complimented = detect_compliment(ctx.raw_query)
    serious = detect_serious_topic(ctx.raw_query) or ctx.is_refusal_response
    question_register = _register_for(ctx.query_class)

    # --- humor_frequency ---
    # Context-dependent presets (Section 14) intentionally override the raw
    # dataset's own "humor is invariant even under distress" finding
    # (character_invariants.json rank 1) — that finding describes a sitcom
    # character in a scene, not a portfolio Q&A assistant being asked about
    # someone's layoff. Section 14 makes this override explicit ("Serious
    # topic -> humor way down"); this is a deliberate design choice on top
    # of the measured baseline, not a data-fidelity gap.
    humor_frequency = HUMOR_FREQUENCY_BASELINE
    if serious:
        humor_frequency = 0.15
    elif question_register == "technical":
        humor_frequency = HUMOR_FREQUENCY_BASELINE - 0.15
    elif question_register == "casual":
        humor_frequency = min(0.942, HUMOR_FREQUENCY_BASELINE + 0.05)  # observed range upper bound

    # --- sarcasm_frequency --- (suppress_sarcasm_in_vulnerability rule)
    sarcasm_frequency = SARCASM_FREQUENCY_BASELINE
    if frustrated or serious:
        sarcasm_frequency = max(SARCASM_FREQUENCY_VULNERABLE_FLOOR, SARCASM_FREQUENCY_BASELINE * 0.78)

    # --- sarcasm_target_bias --- (target_sarcasm_outward_by_default, shifted toward self when awkward)
    sarcasm_target_bias = dict(SARCASM_TARGET_BIAS_BASELINE)
    if ctx.had_to_refuse_recently:
        shift = 0.1
        sarcasm_target_bias["self"] = min(1.0, sarcasm_target_bias["self"] + shift)
        sarcasm_target_bias["other_character"] = max(0.0, sarcasm_target_bias["other_character"] - shift)

    # --- self_deprecation_frequency --- (never after praise — hard override, not a dial)
    if complimented:
        self_deprecation_frequency = 0.0
    elif ctx.had_to_refuse_recently:
        self_deprecation_frequency = SELF_DEPRECATION_FREQUENCY_AWKWARD_CEILING
    else:
        self_deprecation_frequency = SELF_DEPRECATION_FREQUENCY_BASELINE

    # --- warmth ---
    warmth = WARMTH_BASELINE
    if frustrated or serious:
        warmth = 0.6  # deliberately far above the lexical-marker floor (Section 14: "Raised when user
                       # expresses frustration or asks a personal/serious question"); the dataset's own
                       # caveat says its 0.01 figure undercounts warmth conveyed structurally, so scaling
                       # it up here rather than treating 0.01 as a hard ceiling is consistent with that note.

    # --- directness ---
    directness = DIRECTNESS_BASELINE
    if question_register == "technical":
        directness = 0.5

    # --- verbosity_target_words ---
    verbosity_target_words = VERBOSITY_BASELINE_WORDS
    if serious:
        verbosity_target_words = 6.2  # shrink_verbosity_in_sadness rule
    elif question_register == "technical":
        verbosity_target_words = 14.0  # observed range upper bound — precision needs room

    # --- rhetorical_question_frequency --- (concentrated in teasing/light moments, not technical/serious)
    rhetorical_question_frequency = RHETORICAL_QUESTION_FREQUENCY_BASELINE
    if question_register == "casual" and not serious:
        rhetorical_question_frequency = 0.15
    elif question_register == "technical" or serious:
        rhetorical_question_frequency = 0.0

    # --- punchline_placement ---
    punchline_placement = "none" if (serious or ctx.is_refusal_response) else "end"

    register = "serious" if serious else "normal"

    # Injection-flagged override (Section 30) — takes priority over every
    # other signal above: a tightened, low-creative-freedom variant. This
    # doesn't change what the model is ALLOWED to say (the fenced delimiters
    # and instruction hierarchy in prompt.py do that job); it reduces the
    # stylistic surface area (jokes, rhetorical questions, asides) an
    # injection attempt could try to hijack or hide inside.
    if ctx.injection_flagged:
        humor_frequency = 0.0
        sarcasm_frequency = 0.0
        self_deprecation_frequency = 0.0
        directness = 0.9
        rhetorical_question_frequency = 0.0
        punchline_placement = "none"
        register = "serious"

    return PersonalityPolicy(
        personality_version=PERSONALITY_VERSION,
        humor_frequency=round(humor_frequency, 3),
        sarcasm_frequency=round(sarcasm_frequency, 3),
        sarcasm_target_bias=sarcasm_target_bias,
        self_deprecation_frequency=round(self_deprecation_frequency, 3),
        warmth=round(warmth, 3),
        directness=round(directness, 3),
        verbosity_target_words=round(verbosity_target_words, 1),
        rhetorical_question_frequency=round(rhetorical_question_frequency, 3),
        punchline_placement=punchline_placement,
        register=register,
        signals={
            "frustrated": frustrated, "complimented": complimented, "serious": serious,
            "question_register": question_register, "injection_flagged": ctx.injection_flagged,
        },
    )
