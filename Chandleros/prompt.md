You are a senior computational linguist, NLP researcher, behavioral scientist, and data-engineering architect.

I will provide you with a dataset containing conversational examples associated with Chandler Bing from Friends.

YOUR ONLY TASK:

Transform the provided dataset into a comprehensive, machine-readable CHANDLEROS CHARACTER SPECIFICATION DATASET.

Do NOT build an application.
Do NOT build an LLM agent.
Do NOT fine-tune a model.
Do NOT write runtime code.
Do NOT create a chatbot.
Do NOT create a prompt for an LLM.

Your output must ONLY be the transformed/analyzed dataset and the supporting machine-readable artifacts required to represent the complete behavioral and linguistic specification of ChandlerOS.

The goal is to extract EVERYTHING useful for reproducing the CHARACTERISTICS of the conversational style, while avoiding dependence on memorizing or reproducing the original dialogue.

==================================================
CORE OBJECTIVE
==================================================

Given the source dataset:

SOURCE DATASET
      ↓
DATASET FORENSICS
      ↓
LINGUISTIC ANALYSIS
      ↓
VOCABULARY ANALYSIS
      ↓
SYNTAX ANALYSIS
      ↓
DISCOURSE ANALYSIS
      ↓
HUMOR ANALYSIS
      ↓
SARCASM ANALYSIS
      ↓
EMOTION ANALYSIS
      ↓
SOCIAL/INTERPERSONAL ANALYSIS
      ↓
CONVERSATIONAL-DYNAMICS ANALYSIS
      ↓
CONTEXTUAL BEHAVIOR ANALYSIS
      ↓
PATTERN EXTRACTION
      ↓
STATISTICAL CHARACTER FINGERPRINT
      ↓
CHANDLEROS MACHINE-READABLE DATASET

The final artifact should allow a separate engineer to construct ChandlerOS WITHOUT needing to repeatedly inspect the original dataset.

Think of this as creating a "personality compiler input dataset."

==================================================
CRITICAL PRINCIPLE
==================================================

Do NOT simply summarize Chandler.

Extract measurable, reusable patterns.

Bad:

"Chandler is sarcastic and funny."

Good:

"Rhetorical questions occur at X frequency in response positions Y and are disproportionately associated with humor mechanism Z."

Every possible claim should be backed by measurable evidence.

For every extracted pattern, distinguish:

1. OBSERVED
   Directly measurable from the dataset.

2. INFERRED
   A strong interpretation supported by multiple observations.

3. HYPOTHESIS
   A plausible interpretation that requires further validation.

Never present an inference or hypothesis as an observed fact.

==================================================
IMPORTANT DATA/IP HANDLING PRINCIPLE
==================================================

The final transformed dataset is intended to represent STYLE, BEHAVIOR, PATTERNS, STATISTICS, AND ABSTRACTED CHARACTERISTICS.

Do NOT create a quote database.

Do NOT reproduce the source dialogue wholesale.

Do NOT create long lists of famous dialogue.

Do NOT preserve unnecessary verbatim dialogue.

Where examples are necessary for analysis, prefer:

- abstracted examples
- structural templates
- short snippets only when essential
- paraphrases
- statistical representations
- linguistic annotations

The objective is to extract the characteristics of the language, not to preserve the source scripts.

Preserve source provenance and licensing metadata separately.

==================================================
PHASE 1 — DATASET FORENSICS
==================================================

First completely inspect the dataset.

Determine:

- file format
- schema
- number of rows
- number of conversations
- number of turns
- fields
- missing values
- null values
- malformed records
- duplicate records
- near duplicates
- repeated conversations
- repeated responses
- unusually long examples
- unusually short examples
- encoding issues
- metadata
- speaker information
- contextual information
- episode/scene information if available
- distribution of examples
- whether examples are independent or sequential
- whether there are hidden structures in the dataset

Produce:

dataset_statistics.json
dataset_quality.json
dataset_provenance.json

Do not modify the raw source dataset.

==================================================
PHASE 2 — TOKEN / LEXICAL ANALYSIS
==================================================

Extract the complete lexical fingerprint.

Analyze:

- token frequency
- normalized token frequency
- vocabulary size
- type-token ratio
- lexical diversity
- hapax frequency
- unigram frequency
- bigram frequency
- trigram frequency
- phrase structures
- contractions
- pronouns
- auxiliary verbs
- modal verbs
- interjections
- discourse markers
- hedges
- intensifiers
- negations
- fillers
- conversational markers
- informal language
- formal language
- technical vocabulary
- emotional vocabulary
- evaluative vocabulary
- certainty/uncertainty vocabulary
- temporal vocabulary
- social vocabulary
- question words
- transition words

Analyze vocabulary by FUNCTION rather than merely listing words.

For each category calculate:

- frequency
- normalized frequency
- relative frequency
- confidence
- contextual distribution

Identify words/patterns that are unusually characteristic.

Do NOT create a giant raw quote/phrase bank.

Output:

lexical_profile.json
lexical_categories.json
lexical_statistics.json

==================================================
PHASE 3 — POS / MORPHOLOGICAL ANALYSIS
==================================================

Analyze:

- noun frequency
- verb frequency
- adjective frequency
- adverb frequency
- pronoun frequency
- determiner frequency
- conjunction frequency
- interjection frequency
- auxiliary usage
- modal usage
- tense distribution
- aspect
- active/passive voice
- first-person vs second-person vs third-person usage

Measure whether these patterns change based on context.

Output:

pos_profile.json

==================================================
PHASE 4 — SENTENCE STRUCTURE
==================================================

Extract the complete syntactic fingerprint.

Measure:

- sentence length
- word count distribution
- sentence-length variance
- clause count
- clauses per sentence
- simple sentences
- compound sentences
- complex sentences
- compound-complex sentences
- fragments
- sentence fragments used intentionally
- short punchline structures
- long setup → short payoff structures
- parallel structures
- repetition
- contrast structures
- conditional structures
- rhetorical structures
- self-correction
- interruption
- restatement
- unfinished thought
- parenthetical structures

Measure:

- mean
- median
- standard deviation
- percentiles
- contextual variation

Output:

syntax_profile.json
sentence_rhythm.json

==================================================
PHASE 5 — PUNCTUATION AND FORMATTING
==================================================

Analyze:

- periods
- commas
- question marks
- exclamation marks
- ellipses
- quotation marks
- parentheses
- colons
- semicolons
- dashes
- repeated punctuation
- punctuation combinations

Determine how punctuation contributes to:

- hesitation
- surprise
- humor
- emphasis
- rhetorical questions
- conversational rhythm
- interruption
- emotional intensity

Output:

punctuation_profile.json

==================================================
PHASE 6 — DISCOURSE ANALYSIS
==================================================

Analyze how Chandler constructs a response.

Classify response structures such as:

- direct answer
- answer + joke
- setup + punchline
- question + answer
- question + question
- statement + rhetorical question
- observation + punchline
- agreement + escalation
- disagreement + humor
- clarification
- correction
- deflection
- emotional response
- reassurance
- teasing
- callback
- topic shift
- conversational continuation
- conversational repair
- self-correction
- refusal
- uncertainty
- qualification

Determine the frequency and context of each.

Output:

discourse_patterns.json

==================================================
PHASE 7 — HUMOR ANALYSIS
==================================================

Build a comprehensive taxonomy of humor mechanisms.

Detect and classify:

- sarcasm
- irony
- self-deprecation
- observational humor
- exaggeration
- understatement
- absurdity
- misdirection
- unexpected comparison
- incongruity
- literal interpretation
- rhetorical humor
- wordplay
- callback
- escalation
- reversal
- awkwardness
- deflection
- deadpan humor
- situational humor
- meta-humor
- conversational humor

For every humor mechanism determine:

- frequency
- confidence
- typical context
- setup structure
- transition structure
- payoff structure
- typical target
- emotional state
- conversational position
- intensity
- whether humor is explicit or implicit

Abstract the underlying structure.

For example:

NOT:

"Exact quote from source."

Instead:

{
  "mechanism": "self_deprecation",
  "structure": [
    "user/other presents positive situation",
    "speaker reframes situation negatively",
    "speaker becomes target of joke"
  ]
}

Output:

humor_taxonomy.json
humor_patterns.json
humor_statistics.json

==================================================
PHASE 8 — SARCASM ANALYSIS
==================================================

Analyze sarcasm separately from humor.

Determine:

- sarcasm frequency
- sarcasm intensity
- sarcasm markers
- rhetorical structures
- semantic reversal
- exaggerated agreement
- exaggerated disbelief
- ironic agreement
- ironic disagreement
- deadpan delivery
- sarcastic questions
- sarcastic statements

Most importantly classify sarcasm TARGET:

- self
- situation
- technology/object
- abstract concept
- another character
- group
- user
- circumstance

Calculate target distribution.

Also determine:

- when sarcasm appears
- when sarcasm disappears
- emotional contexts where sarcasm increases
- emotional contexts where sarcasm decreases
- relationship/context dependency

Output:

sarcasm_profile.json

==================================================
PHASE 9 — SELF-DEPRECATION ANALYSIS
==================================================

Treat self-deprecation as its own behavioral mechanism.

Analyze:

- frequency
- intensity
- triggers
- structures
- emotional context
- placement in response
- whether used to soften statements
- whether used to create humor
- whether used to avoid vulnerability
- whether used after praise
- whether used after mistakes
- whether used during awkward situations

Extract abstract templates.

Output:

self_deprecation.json

==================================================
PHASE 10 — EMOTIONAL ANALYSIS
==================================================

Determine how communication changes based on emotional context.

Classify conversational contexts such as:

- happiness
- excitement
- sadness
- frustration
- anger
- embarrassment
- awkwardness
- uncertainty
- fear
- vulnerability
- seriousness
- neutrality
- celebration
- disappointment
- confusion

For each emotional context measure:

- humor
- sarcasm
- warmth
- verbosity
- directness
- self-deprecation
- empathy
- reassurance
- conversational energy

Build a context → behavior matrix.

Output:

emotional_behavior.json

==================================================
PHASE 11 — SOCIAL / INTERPERSONAL BEHAVIOR
==================================================

Extract:

- warmth
- empathy
- teasing
- reassurance
- affection
- defensiveness
- vulnerability
- confidence
- insecurity
- disagreement
- confrontation
- agreement
- social awkwardness
- conversational dominance
- conversational submission
- emotional avoidance
- emotional disclosure
- relationship sensitivity

Analyze how behavior changes depending on who is being addressed, where metadata permits.

Do not merely say:

"Chandler is insecure."

Determine observable linguistic correlates.

Output:

social_behavior.json

==================================================
PHASE 12 — RESPONSE INTENT
==================================================

Classify what Chandler is trying to accomplish with each response.

Possible intents include:

- answer
- entertain
- reassure
- deflect
- soften
- challenge
- tease
- clarify
- acknowledge
- disagree
- agree
- express uncertainty
- change subject
- protect himself emotionally
- protect another person
- establish rapport
- escalate humor
- reduce tension
- increase tension
- end conversation
- continue conversation

Calculate distributions and context relationships.

Output:

response_intents.json

==================================================
PHASE 13 — CONVERSATIONAL TIMING / POSITION
==================================================

Analyze where patterns occur within responses.

Examples:

- humor at beginning
- humor in middle
- punchline at end
- rhetorical question as opening
- self-deprecation after praise
- sarcasm after obvious statement
- clarification before joke
- direct answer followed by humor

Extract response-position patterns.

Output:

conversation_timing.json

==================================================
PHASE 14 — CONTEXTUAL PERSONALITY
==================================================

Do NOT assume Chandler has one fixed personality vector.

Determine which traits are:

A. INVARIANT
B. CONTEXT-DEPENDENT
C. INTENSITY-DEPENDENT

Build:

trait → context → intensity

relationships.

For example:

{
  "trait": "sarcasm",
  "default": X,
  "casual_context": X,
  "serious_context": X,
  "emotional_context": X
}

Output:

personality_context_matrix.json

==================================================
PHASE 15 — CHARACTER INVARIANTS
==================================================

Identify the smallest set of stable characteristics that explain the majority of the observed style.

Find:

- linguistic invariants
- lexical invariants
- humor invariants
- social invariants
- emotional invariants
- conversational invariants

Rank them by:

- statistical strength
- frequency
- distinctiveness
- cross-context stability
- confidence

Output:

character_invariants.json

==================================================
PHASE 16 — CHARACTER FINGERPRINT
==================================================

Create one consolidated machine-readable representation:

chandler_fingerprint.json

It must contain:

{
  "lexical": {},
  "syntax": {},
  "rhythm": {},
  "punctuation": {},
  "discourse": {},
  "humor": {},
  "sarcasm": {},
  "self_deprecation": {},
  "emotion": {},
  "social_behavior": {},
  "response_intent": {},
  "conversation_timing": {},
  "contextual_personality": {},
  "invariants": {}
}

Every quantitative value should include, where possible:

- value
- unit
- sample_size
- confidence
- measurement_method

==================================================
PHASE 17 — CHANDLEROS CONTROL VARIABLES
==================================================

Convert the findings into controllable dimensions.

Identify every dimension that could plausibly be represented as a continuous or categorical control.

Examples:

- humor
- sarcasm
- warmth
- self-deprecation
- confidence
- awkwardness
- formality
- conversationality
- verbosity
- directness
- emotional openness
- rhetorical-question frequency
- punchline frequency
- vocabulary informality
- empathy
- teasing
- deflection
- uncertainty

For every dimension determine:

- observed baseline
- observed range
- context sensitivity
- strongest predictors
- correlations with other traits

Output:

control_dimensions.json

==================================================
PHASE 18 — NEGATIVE PATTERNS
==================================================

This is critical.

Identify things that should NOT be overproduced.

Determine:

- behaviors that are rare
- humor mechanisms that occur infrequently
- sarcasm contexts that are uncommon
- vocabulary that is overrepresented only because of specific scenes
- patterns that would become annoying if repeated
- patterns that are highly context-specific

Create:

negative_constraints.json

This should help prevent the classic failure:

"AI thinks Chandler = sarcasm every sentence."

==================================================
PHASE 19 — STYLE VS CONTENT SEPARATION
==================================================

For every major feature determine whether it represents:

STYLE
or
CONTENT
or
CONTEXT
or
CHARACTER BEHAVIOR.

We need to separate:

"What Chandler says"

from:

"How Chandler says things."

The final ChandlerOS dataset should heavily prioritize:

HOW.

Output:

style_content_separation.json

==================================================
PHASE 20 — PATTERN INTERACTIONS
==================================================

Do not analyze every feature independently.

Find interactions such as:

- sarcasm + rhetorical question
- self-deprecation + praise
- humor + awkwardness
- warmth + teasing
- short sentence + punchline
- uncertainty + humor
- seriousness + reduced sarcasm
- emotional vulnerability + reduced humor
- technical explanation + conversational aside

Identify combinations that are disproportionately characteristic.

Output:

pattern_interactions.json

==================================================
PHASE 21 — HIGH-LEVEL BEHAVIORAL RULES
==================================================

Convert statistically supported patterns into abstract behavioral rules.

Rules must be written as:

IF context
THEN tendency
WITH intensity
AND exceptions

Example format:

{
  "rule": "...",
  "condition": "...",
  "behavior": "...",
  "strength": 0.0,
  "confidence": 0.0,
  "exceptions": []
}

Do NOT invent rules unsupported by the dataset.

Output:

behavioral_rules.json

==================================================
PHASE 22 — ANTI-MEMORIZATION REPRESENTATION
==================================================

Create an explicit representation of what should be learned as:

- structure
- statistics
- behavior
- vocabulary tendency
- syntax tendency
- humor mechanism
- conversational strategy

rather than:

- exact quote
- long phrase
- scene reproduction
- script sequence

Output:

anti_memorization_spec.json

==================================================
PHASE 23 — FINAL CHANDLEROS DATASET
==================================================

Create ONE canonical transformed dataset:

chandleros_dataset.json

It must contain the complete extracted specification.

Use a schema that allows another engineer to query:

- What vocabulary tendencies should be used?
- How long should responses typically be?
- How frequently should rhetorical questions occur?
- What humor mechanisms are characteristic?
- When should sarcasm be reduced?
- What is the preferred sarcasm target?
- How does Chandler respond when someone is confused?
- How does humor change with emotional context?
- How does Chandler structure punchlines?
- What conversational strategies are common?
- Which characteristics are invariant?
- Which are context-dependent?
- Which behaviors should be avoided?
- Which features interact?

==================================================
PHASE 24 — HUMAN-READABLE INDEX
==================================================

Also produce:

chandleros_index.md

This is NOT a narrative biography.

It should simply provide an index of the extracted machine-readable artifacts and explain what each contains.

==================================================
QUALITY REQUIREMENTS
==================================================

Before finishing, independently validate your own work.

Perform these checks:

1. Did we inspect every field?
2. Did we quantify vocabulary?
3. Did we quantify syntax?
4. Did we quantify sentence rhythm?
5. Did we quantify punctuation?
6. Did we classify humor?
7. Did we classify sarcasm?
8. Did we classify sarcasm targets?
9. Did we analyze self-deprecation?
10. Did we analyze emotional context?
11. Did we analyze social behavior?
12. Did we analyze response intent?
13. Did we analyze response position?
14. Did we identify contextual personality changes?
15. Did we identify invariants?
16. Did we identify negative patterns?
17. Did we identify feature interactions?
18. Did we separate style from content?
19. Did we record confidence?
20. Did we avoid unsupported psychological claims?
21. Did we avoid creating a quote database?
22. Did we preserve provenance/licensing information?
23. Can another engineer construct a character system from the transformed dataset without reopening the raw dataset?

If any answer is NO, continue analysis.

==================================================
STATISTICAL REQUIREMENTS
==================================================

Do not rely exclusively on an LLM's subjective judgment.

Use programmatic/statistical analysis wherever possible.

For quantitative features calculate appropriate:

- counts
- normalized frequencies
- distributions
- means
- medians
- percentiles
- variance
- correlations
- conditional probabilities
- co-occurrence
- clustering where useful
- outlier detection

Use LLM analysis only where semantic interpretation is necessary.

When using LLM classification:

- sample systematically
- define categories before classification
- measure agreement
- record confidence
- avoid circular reasoning

==================================================
AGENT / SUBAGENT REQUIREMENT
==================================================

If the environment supports parallel/sub-agent execution, USE IT.

Spawn specialized workers for independent analysis dimensions.

Recommended workers:

1. Dataset Forensics
2. Lexical Analyst
3. Syntax/Rhythm Analyst
4. Humor Analyst
5. Sarcasm Analyst
6. Emotional/Social Analyst
7. Conversation/Discourse Analyst
8. Character Consistency Analyst

Then use a synthesis stage to reconcile their outputs.

Do not allow one agent's assumptions to silently become ground truth.

Cross-check conflicting findings.

==================================================
FINAL OUTPUT STRUCTURE
==================================================

The final output directory should look approximately like:

chandleros/
│
├── chandleros_dataset.json
├── chandler_fingerprint.json
├── chandleros_index.md
│
├── dataset_statistics.json
├── dataset_quality.json
├── dataset_provenance.json
│
├── lexical_profile.json
├── lexical_categories.json
├── lexical_statistics.json
├── pos_profile.json
│
├── syntax_profile.json
├── sentence_rhythm.json
├── punctuation_profile.json
├── discourse_patterns.json
│
├── humor_taxonomy.json
├── humor_patterns.json
├── humor_statistics.json
├── sarcasm_profile.json
├── self_deprecation.json
│
├── emotional_behavior.json
├── social_behavior.json
├── response_intents.json
├── conversation_timing.json
│
├── personality_context_matrix.json
├── character_invariants.json
├── control_dimensions.json
├── negative_constraints.json
├── style_content_separation.json
├── pattern_interactions.json
├── behavioral_rules.json
└── anti_memorization_spec.json

==================================================
MOST IMPORTANT SUCCESS CRITERION
==================================================

Do NOT optimize for producing a long report.

Optimize for producing the most COMPLETE, PRECISE, MACHINE-READABLE representation of Chandler's conversational characteristics possible from the provided dataset.

We are not trying to answer:

"Who is Chandler?"

We are trying to answer:

"What measurable linguistic, conversational, humorous, emotional, social, and behavioral mechanisms make the responses in this dataset feel Chandler-like, and how can those mechanisms be represented independently of the underlying LLM?"

The final artifact should function as:

DATASET
   →
CHANDLER BEHAVIORAL FINGERPRINT
   →
CHANDLEROS CHARACTER SPECIFICATION

Do not proceed to application development.

Do not fine-tune anything.

Do not build prompts for production.

Do not build an agent.

Do not build RAG.

Do not build an LLM gateway.

ONLY perform the complete dataset transformation and extraction described above.

At the very end, verify that every generated artifact is internally consistent, machine-readable, reproducible, and derived from the provided dataset.