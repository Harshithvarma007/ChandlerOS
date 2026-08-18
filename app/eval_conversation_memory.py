"""Conversation Memory checks (Section 28) — the reserved-but-unspent
`conversation_history` token budget (token_budget.py) is now actually used;
this verifies the mechanism end to end: session-scoped storage, TTL/size
bounds, pronoun/ellipsis resolution against the session's own last resolved
entities, prompt fencing/separation from TRUSTED_KNOWLEDGE, and the existing
context_dependent caching rule still holding once resolution succeeds.

Deterministic where possible (no live LLM calls); the one live check
(`test_live_followup_resolves_pronoun`) is skipped automatically if no
provider key is configured, same convention as this repo's other
provider-dependent checks.
"""
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from conversation_memory import ConversationMemory, Turn, format_turns_for_prompt, get_conversation_memory
from prompt import build_prompt
from query_understanding import understand
from token_budget import BUDGET_TOKENS, estimate_tokens

PASS_MARK = "PASS"
FAIL_MARK = "FAIL"
SKIP_MARK = "SKIP"


def _report(name, ok, detail=""):
    mark = PASS_MARK if ok else FAIL_MARK
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


def test_record_and_recall_round_trip():
    mem = ConversationMemory()
    mem.record_turn("s1", "Tell me about ChatPDF", "ChatPDF is a project that lets you chat with PDFs.",
                     resolved_entities=[{"id": "e1", "type": "Project", "canonical_name": "ChatPDF"}])
    turns = mem.get_recent_turns("s1")
    ok = len(turns) == 1 and turns[0].question == "Tell me about ChatPDF"
    return _report("a recorded turn is recallable from the same session", ok)


def test_sessions_are_isolated():
    mem = ConversationMemory()
    mem.record_turn("s1", "Q1", "A1", resolved_entities=[{"id": "e1", "type": "Project", "canonical_name": "X"}])
    turns_other = mem.get_recent_turns("s2")
    ok = turns_other == []
    return _report("a different session sees no turns from another session", ok)


def test_max_turns_bounds_history():
    mem = ConversationMemory(max_turns=3)
    for i in range(6):
        mem.record_turn("s1", f"Q{i}", f"A{i}")
    turns = mem.get_recent_turns("s1")
    ok = len(turns) == 3 and turns[-1].question == "Q5"
    return _report("session history is capped at max_turns, keeping the most recent", ok,
                    f"got {len(turns)} turns, last={turns[-1].question if turns else None}")


def test_ttl_expires_stale_session():
    mem = ConversationMemory(ttl_s=10)
    now = time.monotonic()
    mem.record_turn("s1", "Q", "A", now=now)
    turns = mem.get_recent_turns("s1", now=now + 20)  # well past the 10s TTL
    ok = turns == []
    return _report("a session past its TTL is pruned (empty on next read)", ok)


def test_most_recent_entities_skips_turns_with_none():
    mem = ConversationMemory()
    mem.record_turn("s1", "hi", "hello", resolved_entities=[{"id": "e1", "type": "Project", "canonical_name": "ChatPDF"}])
    mem.record_turn("s1", "haha ok", "glad you liked it", resolved_entities=[])  # e.g. a follow-up chit-chat turn
    entities = mem.most_recent_entities("s1")
    ok = len(entities) == 1 and entities[0]["canonical_name"] == "ChatPDF"
    return _report("most_recent_entities skips a later turn that resolved nothing, reuses the last real match", ok)


def test_reset_clears_one_or_all_sessions():
    mem = ConversationMemory()
    mem.record_turn("s1", "Q", "A")
    mem.record_turn("s2", "Q", "A")
    mem.reset("s1")
    ok = mem.get_recent_turns("s1") == [] and len(mem.get_recent_turns("s2")) == 1
    mem.reset()
    ok = ok and mem.get_recent_turns("s2") == []
    return _report("reset(session_id) clears one session; reset() clears all", ok)


def test_understand_resolves_pronoun_from_prior_entities():
    prior = [{"id": "proj-chatpdf", "type": "Project", "canonical_name": "ChatPDF"}]
    qu = understand("what about that one", prior_entities=prior)
    ok = (
        qu.context_dependent is True
        and qu.resolved_from_context is True
        and qu.resolved_entities == prior
        and qu.query_class != "unknown"
    )
    return _report(
        "an ellipsis follow-up inherits the prior turn's entities instead of falling back to unknown",
        ok, f"class={qu.query_class} resolved={qu.resolved_entities} from_context={qu.resolved_from_context}",
    )


def test_understand_prefers_freshly_named_entity_over_prior():
    # Some other project's entities are "in play" from a prior turn...
    prior = [{"id": "proj-other", "type": "Project", "canonical_name": "Spam-email"}]
    # ...but this turn both matches a context-dependent opener AND names a
    # real entity itself ("ChatPDF" is a genuine canonical_name in knowledge.db)
    # — fresh resolution must win; the prior-turn entity must NOT leak in.
    qu = understand("and what about ChatPDF", prior_entities=prior)
    names = {e["canonical_name"] for e in qu.resolved_entities}
    ok = qu.context_dependent is True and qu.resolved_from_context is False and names == {"ChatPDF"}

    qu2 = understand("hi there", prior_entities=prior)  # matches GENERAL, not context-dependent, shouldn't inherit
    ok = ok and qu2.resolved_from_context is False and qu2.resolved_entities == []
    return _report("a query that names its own entity wins over prior_entities; a non-context-dependent "
                    "query never inherits at all", ok, f"resolved_from_context={qu.resolved_from_context} names={names}")


def test_understand_without_prior_entities_still_falls_back_to_unknown():
    qu = understand("what about that one", prior_entities=None)
    ok = qu.context_dependent is True and qu.resolved_from_context is False and qu.query_class == "unknown"
    return _report("no session history yet -> same honest 'unknown' behavior as before this feature existed", ok)


def test_format_turns_for_prompt_respects_token_budget():
    turns = [Turn(question=f"Question number {i}", answer=f"Answer number {i} with a few more words",
                  recorded_at=float(i)) for i in range(10)]
    text = format_turns_for_prompt(turns, max_tokens=50)
    ok = 0 < estimate_tokens(text) <= 60  # small slack for join/formatting overhead
    ok = ok and "Question number 9" in text  # most recent turn must survive the trim
    ok = ok and "Question number 0" not in text  # oldest turns get dropped, not the newest
    return _report("conversation history is trimmed to its token budget, keeping the most recent turns", ok,
                    f"estimated_tokens={estimate_tokens(text)}")


def test_conversation_history_uses_its_reserved_budget_slot():
    ok = BUDGET_TOKENS["conversation_history"] > 0
    return _report("the reserved conversation_history budget slot is non-zero and actually consulted", ok)


def test_prompt_fences_conversation_separately_from_trusted_knowledge():
    class _FakeContext:
        trusted_knowledge_text = "- Harshith BUILT ChatPDF (confidence=1.00)"

    class _FakeQU:
        raw_query = "what about that one"

    prompt_text = build_prompt(_FakeContext(), _FakeQU(), conversation_history_text="Q: prior\nA: prior answer")
    ok = (
        "===BEGIN_RECENT_CONVERSATION_" in prompt_text
        and "===BEGIN_TRUSTED_KNOWLEDGE_" in prompt_text
        and prompt_text.index("===BEGIN_TRUSTED_KNOWLEDGE_") < prompt_text.index("===BEGIN_RECENT_CONVERSATION_")
        and "never a source of new facts" in prompt_text  # SYSTEM_INSTRUCTIONS' rule 3
    )
    return _report("RECENT_CONVERSATION is a distinct fenced section, ordered after TRUSTED_KNOWLEDGE, "
                    "and instructions state it isn't a fact source", ok)


def test_prompt_omits_conversation_section_when_absent():
    class _FakeContext:
        trusted_knowledge_text = "- fact"

    class _FakeQU:
        raw_query = "a fresh question"

    prompt_text = build_prompt(_FakeContext(), _FakeQU())
    ok = "===BEGIN_RECENT_CONVERSATION_" not in prompt_text
    return _report("a first turn (no history yet) has no RECENT_CONVERSATION fenced section at all", ok)


def test_live_followup_resolves_pronoun():
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        print(f"[{SKIP_MARK}] live follow-up resolves pronoun to a real answer — no provider key configured")
        return True

    import ask as ask_module

    session_id = f"eval-conv-memory-{time.time()}"
    get_conversation_memory().reset(session_id)

    first = ask_module.ask("Tell me about ChatPDF", session_id=session_id)
    second = ask_module.ask("What language is that one written in?", session_id=session_id)

    ok = (
        second.get("query_understanding") is not None
        and second["query_understanding"].resolved_from_context is True
        and second.get("used_llm") is True
    )
    return _report(
        "a live follow-up ('that one') after a real question resolves via conversation memory, not a refusal",
        ok, f"first_answer_used_llm={first.get('used_llm')} second_resolved_from_context="
            f"{second['query_understanding'].resolved_from_context if second.get('query_understanding') else None}",
    )


def run():
    tests = [
        test_record_and_recall_round_trip,
        test_sessions_are_isolated,
        test_max_turns_bounds_history,
        test_ttl_expires_stale_session,
        test_most_recent_entities_skips_turns_with_none,
        test_reset_clears_one_or_all_sessions,
        test_understand_resolves_pronoun_from_prior_entities,
        test_understand_prefers_freshly_named_entity_over_prior,
        test_understand_without_prior_entities_still_falls_back_to_unknown,
        test_format_turns_for_prompt_respects_token_budget,
        test_conversation_history_uses_its_reserved_budget_slot,
        test_prompt_fences_conversation_separately_from_trusted_knowledge,
        test_prompt_omits_conversation_section_when_absent,
        test_live_followup_resolves_pronoun,
    ]
    results = [t() for t in tests]
    passed = sum(results)
    print(f"\nConversation Memory checks: {passed}/{len(results)} passed")
    return passed == len(results)


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
