# ChandlerOS Character Specification Dataset — Index

This is an index of the machine-readable artifacts in this directory. It is **not** a narrative biography of Chandler Bing — it explains what each file contains and how the files relate, so an engineer can navigate the specification without reopening `data.parquet`.

Source: 2,535 (context, response) pairs derived from Friends dialogue, where each `response` is treated as a Chandler Bing line (per dataset framing) and `context` is 1–3 preceding lines from other characters. Rows are independent samples, not a continuous script. No verbatim dialogue is reproduced anywhere below this point — see `anti_memorization_spec.json` and `dataset_provenance.json` for the IP-handling policy.

## Start here

| File | What it answers |
|---|---|
| `chandleros_dataset.json` | **The canonical entry point.** A `query_index` mapping the 14 questions a downstream engineer would ask ("how long should responses be?", "when should sarcasm drop?") directly to answers + source files. |
| `chandler_fingerprint.json` | One consolidated digest of every phase's headline numbers, organized by category (lexical/syntax/humor/sarcasm/emotion/social/etc). |
| `chandleros_index.md` | This file. |

## Phase 1 — Dataset forensics

- `dataset_statistics.json` — row/turn counts, length distributions, duplication rates, speaker distributions, encoding checks, independence test.
- `dataset_quality.json` — pass/warn findings on nulls, duplicates, schema uniformity, speaker-attribution confidence, metadata completeness.
- `dataset_provenance.json` — source/IP framing, licensing policy applied in this transformation.

## Phase 2–3 — Lexical & POS

- `lexical_profile.json` — vocabulary size, TTR, hapax rate, top unigrams/bigrams/trigrams, contraction forms.
- `lexical_categories.json` — 27 functional vocabulary categories (interjections, fillers, hedges, discourse markers, etc.) with relative-frequency multipliers vs. a stated baseline, plus breakdowns by response length and by addressee.
- `lexical_statistics.json` — condensed statistical summary of the above.
- `pos_profile.json` — POS-tag distribution, tense distribution, active/passive voice estimate, person-pronoun ratio.

## Phase 4–5 — Syntax, rhythm, punctuation

- `syntax_profile.json` — sentence length, clause count, simple/compound/complex/compound-complex classification, fragment rate.
- `sentence_rhythm.json` — punchline structures, parallelism, repetition, contrast/conditional structures, self-correction, interruption, unfinished thought.
- `punctuation_profile.json` — per-mark rates and their measured functional correlations (emphasis, hesitation, rhetorical use, etc).

## Phase 6, 12, 13 — Discourse, intent, timing

- `discourse_patterns.json` — 23 discourse-structure categories (direct_answer, observation+punchline, setup+punchline, etc.) with frequencies and abstracted structural templates.
- `response_intents.json` — what Chandler is trying to accomplish (entertain/tease/reassure/deflect/etc.), including a distress-context cross-tab.
- `conversation_timing.json` — where humor lands within a response (start/middle/end), punchline-at-end rate, rhetorical-question-opener rate.

## Phase 7 — Humor

- `humor_taxonomy.json` — 22 humor mechanisms, each as an abstract setup→mechanism→payoff structural template (no verbatim jokes).
- `humor_patterns.json` — per-mechanism setup/transition/payoff detail, typical target, position, intensity, explicit-vs-implicit split.
- `humor_statistics.json` — overall humor rate, mechanism ranking, co-occurrence pairs, multi-mechanism stacking stats.

## Phase 8–9 — Sarcasm & self-deprecation

- `sarcasm_profile.json` — sarcasm rate, intensity, markers, target distribution, context-dependency (drops in vulnerable contexts).
- `self_deprecation.json` — self-deprecation rate (rarer than popularly assumed), triggers, placement, function, sarcasm co-occurrence.

## Phase 10–11 — Emotion & social behavior

- `emotional_behavior.json` — a context → behavior matrix across 14 emotional-context categories (humor/sarcasm/warmth/verbosity/directness/empathy/energy).
- `social_behavior.json` — warmth/empathy/teasing/insecurity/dominance rates, including breakdowns by addressee (main-cast vs. minor characters).

## Phase 14–15 — Contextual personality & invariants

- `personality_context_matrix.json` — classifies traits as invariant / context-dependent / intensity-dependent, with a trait × context × intensity table. Includes an explicit note reconciling a cross-worker discrepancy (lexical-marker methods undercount structural humor/sarcasm relative to semantic classification).
- `character_invariants.json` — the 12 most stable, defining characteristics, ranked by statistical strength/frequency/distinctiveness/cross-context stability/confidence.

## Phase 17–22 — Control layer, constraints, structure

- `control_dimensions.json` — 15 tunable dimensions (humor_frequency, sarcasm_frequency, verbosity, etc.) with observed baseline, range, and strongest predictors.
- `negative_constraints.json` — behaviors that should **not** be overproduced (e.g. self-deprecation is rare and never follows praise; sarcasm must drop in vulnerable contexts; parenthetical asides are essentially absent).
- `style_content_separation.json` — classifies every major feature as STYLE / CONTENT / CONTEXT / CHARACTER_BEHAVIOR, with an explicit directive to prioritize HOW over WHAT.
- `pattern_interactions.json` — feature combinations that are disproportionately characteristic (e.g. response length jointly drives discourse structure + intent + humor rate).
- `behavioral_rules.json` — 14 IF/THEN/WITH-STRENGTH/EXCEPTIONS rules synthesized from the above.
- `anti_memorization_spec.json` — explicit statement of what should be learned (structure/statistics/behavior) vs. never reproduced (verbatim quotes/scenes/scripts), plus a self-audit verification pass.

## Phase 23 — Canonical dataset

- `chandleros_dataset.json` — see "Start here" above.

## How the pieces fit together

```
dataset_statistics/quality/provenance   (Phase 1: what IS the data)
        |
lexical / pos / syntax / rhythm / punctuation   (Phase 2-5: HOW words/sentences are built)
        |
discourse / humor / sarcasm / self-deprecation / emotion / social / intent / timing   (Phase 6-13: WHAT Chandler does conversationally, and when)
        |
personality_context_matrix / character_invariants   (Phase 14-15: what's stable vs. situational)
        |
chandler_fingerprint   (Phase 16: one consolidated digest)
        |
control_dimensions / negative_constraints / style_content_separation / pattern_interactions / behavioral_rules / anti_memorization_spec   (Phase 17-22: how to USE it safely and correctly)
        |
chandleros_dataset.json   (Phase 23: the queryable canonical entry point)
```

## Known limitations (see also `chandleros_dataset.json:known_methodological_limitations`)

- No episode/scene/season metadata exists in the source — context is limited to 1–3 preceding lines.
- Semantic-classification phases (discourse/humor/sarcasm/self-deprecation/emotion/social/intent/timing) are based on systematic stratified samples (n=317–508 of 2,535), not full-dataset counts.
- Lexical-marker methods (used in `emotional_behavior.json`, `social_behavior.json`) undercount structural/tonal humor and sarcasm relative to semantic-classification methods — this is documented, not silently ignored.
