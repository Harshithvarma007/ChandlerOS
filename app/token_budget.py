"""Token Optimization — Section 27 of the blueprint.

No real tokenizer library available offline, so token counts are a
word-count-based approximation (~0.75 tokens/word for English prose) — the
same heuristic already used ad hoc in the provider adapters' fallback usage
estimate (Section 16 prefers provider-reported usage when available; this
is what budgeting decisions use *before* a call, when no usage exists yet).
Centralized here as the one place that heuristic lives, rather than
duplicated per adapter.

Budget table (Section 27), with one documented deviation: the blueprint's
illustrative trusted_knowledge line (~2000 tokens) undersizes the evidence
Phase 2's chunker actually produces (300-500 tokens/chunk, Section 10) — a
single semantic-RAG answer routinely wants 4-6 chunks, which alone exceeds
2000 tokens before graph facts are even added. Using 4000 tokens for
trusted_knowledge instead (empirically what Phase 2 already needed to
produce its best live results) — still comfortably within even the
smallest currently-routed model's context window (131,072, Groq's
gpt-oss models), and Section 27's own rule is "tuned to the smallest
context window among actively-routed models," not a hardcoded constant.
"""
WORDS_TO_TOKENS_RATIO = 0.75  # tokens per word, rough English-prose average

BUDGET_TOKENS = {
    "system_prompt": 400,
    "personality_directives": 150,
    "conversation_history": 500,  # Conversation Memory (conversation_memory.py) — trimmed to fit, most-recent-first
    "trusted_knowledge": 4000,  # see module docstring for the deviation from the illustrative 2000
    "user_query": 100,
    "output_reserve": 800,
}
TOTAL_BUDGET_TOKENS = sum(BUDGET_TOKENS.values())

# How trusted_knowledge splits between the two evidence sources — graph
# facts are terse and high-priority (Section 13: "graph facts preferred for
# the same claim"), vector chunks are large but add nuance.
GRAPH_SHARE = 0.4
VECTOR_SHARE = 0.6


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text.split()) / WORDS_TO_TOKENS_RATIO))


def estimate_prompt_tokens(
    system_prompt: str, style_directives: str, trusted_knowledge: str, user_query: str,
    conversation_history: str = "",
) -> int:
    """Realized total for a specific assembled prompt — used by the Model
    Router's hard context-window filter (Section 27: 'will not route a
    request whose realized prompt exceeds a model's window'). Defaults
    conversation_history to "" so existing call sites without a session
    history behave exactly as before."""
    return (
        estimate_tokens(system_prompt)
        + estimate_tokens(style_directives)
        + estimate_tokens(trusted_knowledge)
        + estimate_tokens(conversation_history)
        + estimate_tokens(user_query)
        + BUDGET_TOKENS["output_reserve"]  # reserve room for the response too, not just the input
    )
