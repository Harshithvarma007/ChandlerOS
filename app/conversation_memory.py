"""Conversation Memory — Section 28 of the blueprint.

Short-term, session-scoped memory only — strictly separate from the
long-term Knowledge Graph/vector store. A recorded turn is the user's own
prior question and this system's own prior (already-validated) answer in
*this* session; it is never merged into TRUSTED_KNOWLEDGE and never treated
as a new fact (Section 28: "do not mix user conversation with trusted
portfolio facts"). Its only two jobs are: (1) let Query Understanding
resolve the obvious ellipsis/pronoun patterns it already detects
(query_understanding.py's CONTEXT_DEPENDENT_PATTERNS) against the entities
actually in play last turn, and (2) give the LLM enough continuity to not
ask "which project?" when the user just said which one.

In-memory, per-process — the same deferral as every other stateful Phase
3+ module here (cache.py, rate_limiter.py, circuit_breaker.py, ...): the
durable version of this is a KV/Durable Object at the edge (Section 28),
not this module's job to build. No conversation summary (Section 28 also
mentions this) — an LLM call to summarize would violate Engineering
Principle 2 ("do not use an LLM unnecessarily") for a session that's at
most a handful of turns; keeping the last few turns verbatim, token-
budget-trimmed, is simpler and sufficient at this scale.
"""
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from token_budget import estimate_tokens

MAX_TURNS_PER_SESSION = 6
SESSION_TTL_S = 1800  # 30 minutes since the session's last turn


@dataclass
class Turn:
    question: str
    answer: str
    resolved_entities: list = field(default_factory=list)
    recorded_at: float = 0.0


class ConversationMemory:
    def __init__(self, max_turns: int = MAX_TURNS_PER_SESSION, ttl_s: float = SESSION_TTL_S):
        self.max_turns = max_turns
        self.ttl_s = ttl_s
        self._sessions = defaultdict(lambda: deque(maxlen=self.max_turns))

    def _prune_expired(self, session_id: str, now: float):
        turns = self._sessions.get(session_id)
        if not turns:
            return
        while turns and (now - turns[0].recorded_at) > self.ttl_s:
            turns.popleft()
        if not turns:
            self._sessions.pop(session_id, None)

    def record_turn(self, session_id: str, question: str, answer: str, resolved_entities=None, now: float = None):
        if not session_id or not question:
            return
        now = now if now is not None else time.monotonic()
        self._prune_expired(session_id, now)
        self._sessions[session_id].append(
            Turn(question=question, answer=answer or "", resolved_entities=list(resolved_entities or []), recorded_at=now)
        )

    def get_recent_turns(self, session_id: str, now: float = None) -> list:
        now = now if now is not None else time.monotonic()
        self._prune_expired(session_id, now)
        return list(self._sessions.get(session_id, ()))

    def most_recent_entities(self, session_id: str, now: float = None) -> list:
        """Entities from the most recent turn that actually resolved any —
        e.g. "Tell me about ChatPDF" / "what about that one" / "which parts
        use Python" should reuse ChatPDF's entities, not whatever turn
        happened to run before ChatPDF was ever mentioned."""
        for turn in reversed(self.get_recent_turns(session_id, now=now)):
            if turn.resolved_entities:
                return turn.resolved_entities
        return []

    def reset(self, session_id: str = None):
        if session_id is None:
            self._sessions.clear()
        else:
            self._sessions.pop(session_id, None)


_default_memory = ConversationMemory()


def get_conversation_memory() -> ConversationMemory:
    return _default_memory


def format_turns_for_prompt(turns: list, max_tokens: int) -> str:
    """Most-recent-first inclusion — a token-budget trim keeps recency over
    completeness (the same "drop whole low-rank items" philosophy
    context_builder.py applies to confidence rank, applied here to
    recency), rendered back out in chronological order for a coherent read."""
    kept = []
    used = 0
    for turn in reversed(turns):
        block = f"Q: {turn.question}\nA: {turn.answer}"
        block_tokens = estimate_tokens(block)
        if used + block_tokens > max_tokens:
            break
        kept.append(block)
        used += block_tokens
    kept.reverse()
    return "\n\n".join(kept)
