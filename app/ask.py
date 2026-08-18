"""Phase 6 CLI: question in, grounded answer out — now with grounding,
prompt-injection detection, and output validation (Sections 29-32) wrapped
around the Phase 1-5 pipeline.

USER QUERY -> Abuse/Rate-Limit Check -> Injection Check -> Query
    Understanding -> Retrieval Router -> (Graph | Vector | both) ->
    Context Construction -> Personality -> LLM Generation (Gateway) ->
    Output Validation -> [regenerate once if grounding/safety failed] ->
    [strip unsupported / fallback if still failing] -> Structured Response

Refusal/no-retrieval paths short-circuit before any LLM call whenever
possible (Section 11). Abuse/rate-limit checks run first and reject cheaply
(Section 23). Never implies an LLM processed the request when it didn't
(Section 34's principle, applied early even though full Graceful
Degradation is Phase 8).
"""
import dataclasses
import sys

from abuse_prevention import check_input
from cache import TTLCache
from chandler_fallback import build_fallback_response
from circuit_breaker import get_breaker
from context_builder import build_context
from db import get_knowledge_version
from degradation import FALLBACK as DEGRADATION_FALLBACK
from degradation import get_degradation_tracker
from gateway import GatewayError, GatewayRequest, NoProviderAvailable
from gateway import generate as gateway_generate
from gateway import generate_stream as gateway_generate_stream
from graph_retrieval import Subgraph, retrieve_subgraph
from grounding import guts_the_answer, strip_unsupported
from model_router import get_active_providers
from output_validation import truncate_to_word_limit, validate_output
from personality_directives import render_directives
from personality_policy import PersonalityContext, compute_policy
from prompt import FENCE_TOKEN, SYSTEM_INSTRUCTIONS, build_prompt
from prompt_injection import check_injection
from query_understanding import understand
from rate_limiter import get_limiter
from request_budget import MIN_BUDGET_FOR_LLM_CALL_MS, RequestBudget
from retrieval_router import (
    GRAPH_ONLY,
    GRAPH_PLUS_VECTOR,
    MIN_EVIDENCE_COUNT,
    NONE_STRATEGY,
    VECTOR_ONLY,
    decide_strategy,
)
from semantic_cache import get_semantic_cache
from structured_output import build_structured_response
from token_budget import estimate_prompt_tokens
from vector_retrieval import retrieve_chunks
from viral_mode import VIRAL, get_viral_tracker, max_output_tokens_for_state

# Caching (Section 25) — in-memory TTL caches, same deferral as every other
# Phase 3+ module (Workers KV is a deployment binding, Phase 11). Retrieval
# results are cheap-and-short-TTL (minutes: retrieval is deterministic given
# a fixed knowledge_version, so a hit just saves recomputation); the
# response cache runs longer (medium TTL) since a full answer is more
# expensive to reproduce and personality-signature-gated so a stale
# personality tweak can't serve an old style.
_graph_retrieval_cache = TTLCache(ttl_seconds=300)
_vector_retrieval_cache = TTLCache(ttl_seconds=300)
_response_cache = TTLCache(ttl_seconds=1800)

REFUSAL_UNKNOWN = (
    "I don't have information about that in my knowledge base yet. "
    "(No LLM was called for this response — the question didn't match any known entity or topic.)"
)
REFUSAL_NO_EVIDENCE = (
    "I recognized part of your question but couldn't find supporting facts or content in my "
    "knowledge base to answer it. (No LLM was called for this response.)"
)
REFUSAL_UNGROUNDED = (
    "I generated an answer but couldn't verify it against my knowledge base, even after a second "
    "attempt — so rather than risk giving you something unsupported, I'm not going to answer this one."
)
# Hand-written to spec, not LLM-generated — same reliability principle
# Section 35 (Chandler Fallback, Phase 8) applies to outage fallbacks:
# refusal/identity clarity must never be put at risk by a live personality
# pass (Section 14's own refusal-response note). Section 11 scopes "general/
# chit-chat" as "NONE -> personality layer + a FIXED identity blurb" — fixed
# meaning literally this, hand-authored once in ChandlerOS's voice.
GENERAL_BLURB = (
    "Hey. I'm ChandlerOS — I answer questions about Harshith's portfolio: projects, work history, "
    "education, publications, that sort of thing. Not equipped for anything past that, so please don't "
    "ask me to file your taxes. Try something like \"which projects use Python\" or \"where did Harshith study\"."
)
REFUSAL_OUT_OF_TIME = (
    "This request ran out of its response-time budget before an LLM call could be made. "
    "(No LLM was called — an honest timeout, not a fabricated answer.)"
)

DEFAULT_IP = "local-cli"
DEFAULT_SESSION = "local-cli-session"
DEFAULT_MAX_OUTPUT_TOKENS = 1024  # matches GatewayRequest's own default; named here so viral_mode.py's
                                   # trimming has a base to scale from without importing gateway_types just for this


def _rejected(reason, message, budget):
    return {
        "answer": message, "rejected_reason": reason, "used_llm": False,
        "budget_ms_elapsed": budget.elapsed_ms() if budget else None,
    }


def _fallback_result(message, qu, strategy, context, policy, used_llm=True):
    return {
        "answer": message, "query_understanding": qu, "strategy": strategy, "used_llm": used_llm,
        "context": context, "personality_policy": policy, "validation_status": "fallback",
    }


def _reinforcement_message(unsupported_claims) -> str:
    if unsupported_claims:
        claim_text = unsupported_claims[0].sentence
        detail = f': "{claim_text}"'
    else:
        detail = "."
    return (
        f"Your previous answer included a claim not clearly supported by TRUSTED_KNOWLEDGE{detail} "
        "Regenerate your answer using ONLY facts explicitly present in TRUSTED_KNOWLEDGE above. "
        "If you can't support a claim, omit it or say you don't have enough information for that part."
    )


def ask(question: str, ip: str = DEFAULT_IP, session_id: str = DEFAULT_SESSION) -> dict:
    budget = RequestBudget()

    with budget.stage("abuse_and_rate_limit"):
        abuse_result = check_input(question, session_id)
        if not abuse_result.allowed:
            return _rejected(abuse_result.reason, abuse_result.message, budget)

        rate_result = get_limiter().check(ip, session_id)
        if not rate_result.allowed:
            retry_note = f" Retry in ~{rate_result.retry_after_s:.0f}s." if rate_result.retry_after_s else ""
            return _rejected(
                f"rate_limited:{rate_result.layer}",
                f"Rate limit reached ({rate_result.layer}).{retry_note}",
                budget,
            )

    with get_limiter().in_flight():
        return _ask_inner(question, budget)


def _cache_hit_result(cached, qu, strategy, policy, budget, cache_type: str) -> dict:
    answer_text, structured = cached
    structured = dataclasses.replace(structured, metadata={**structured.metadata, "cache_hit": True})
    return {
        "answer": answer_text, "query_understanding": qu, "strategy": strategy, "used_llm": False,
        "personality_policy": policy, "validation_status": structured.validation_status,
        "structured_response": structured, "cache_hit": True, "cache_type": cache_type,
        "budget_ms_elapsed": budget.elapsed_ms(),
    }


def _ask_inner(question: str, budget: RequestBudget) -> dict:
    get_viral_tracker().record_request()  # Section 36: interpretation of existing traffic, one counter's worth of new instrumentation

    with budget.stage("query_understanding"):
        qu = understand(question)
    strategy = decide_strategy(qu)

    # Injection detection (Section 30) — a signal, not a block. Flagged
    # requests still get answered, but with a tightened personality
    # (personality_policy.py's injection_flagged override) and are logged
    # distinctly here, not silently allowed through.
    injection_result = check_injection(qu.raw_query)
    if injection_result.flagged:
        print(f"[prompt_injection] flagged request (patterns={injection_result.matched}): {qu.raw_query[:120]!r}")

    if strategy == NONE_STRATEGY:
        if qu.query_class == "general":
            return {"answer": GENERAL_BLURB, "query_understanding": qu, "strategy": strategy, "used_llm": False}
        return {"answer": REFUSAL_UNKNOWN, "query_understanding": qu, "strategy": strategy, "used_llm": False}

    # Personality (Sections 14-15): a pure function of context signals, no
    # LLM call, computed independently of retrieval — the policy never sees
    # evidence content, only the query class, raw question text, and the
    # injection-flagged signal. Computed early because it's part of the
    # response-cache key and doesn't need retrieval to exist first.
    personality_ctx = PersonalityContext(
        query_class=qu.query_class, raw_query=qu.raw_query, injection_flagged=injection_result.flagged,
    )
    policy = compute_policy(personality_ctx)

    knowledge_version = get_knowledge_version()
    # Section 25/26: never cache or serve-from-cache a context-dependent or
    # injection-flagged query — a cached answer must never be returned to a
    # query pattern designed to probe or manipulate the system, and "what
    # about that one" means something different every time regardless of
    # literal text match.
    cacheable = not qu.context_dependent and not injection_result.flagged

    with budget.stage("cache_lookup"):
        if cacheable:
            response_key = (qu.normalized, policy.personality_version, knowledge_version)
            cached = _response_cache.get(response_key)
            if cached is not None:
                return _cache_hit_result(cached, qu, strategy, policy, budget, cache_type="exact")

            semantic_hit = get_semantic_cache().lookup(
                qu.raw_query, knowledge_version, policy.personality_version,
                context_dependent=qu.context_dependent, injection_flagged=injection_result.flagged,
            )
            if semantic_hit is not None:
                return _cache_hit_result(semantic_hit, qu, strategy, policy, budget, cache_type="semantic")

    subgraph = None
    chunks = []
    resolved_ids = [e["id"] for e in qu.resolved_entities]

    if strategy in (GRAPH_ONLY, GRAPH_PLUS_VECTOR):
        with budget.stage("graph_retrieval"):
            graph_key = (tuple(sorted(resolved_ids)), qu.query_class, knowledge_version)
            subgraph = _graph_retrieval_cache.get(graph_key)
            if subgraph is None:
                subgraph = retrieve_subgraph(qu)
                _graph_retrieval_cache.set(graph_key, subgraph)

    if strategy == GRAPH_ONLY and (not subgraph.facts) and (not subgraph.entity_notes):
        return {"answer": REFUSAL_NO_EVIDENCE, "query_understanding": qu, "strategy": strategy, "used_llm": False}

    # Escalation (Section 11 point 3): GRAPH_ONLY that came back thin gets one
    # shot at vector retrieval rather than answering off a sparse subgraph.
    escalated = False
    if strategy == GRAPH_ONLY and len(subgraph.facts) < MIN_EVIDENCE_COUNT:
        strategy = GRAPH_PLUS_VECTOR
        escalated = True

    if strategy in (VECTOR_ONLY, GRAPH_PLUS_VECTOR):
        with budget.stage("vector_retrieval"):
            vector_key = (qu.normalized, tuple(sorted(resolved_ids)), knowledge_version)
            chunks = _vector_retrieval_cache.get(vector_key)
            if chunks is None:
                chunks = retrieve_chunks(qu.raw_query, resolved_entity_ids=resolved_ids)
                _vector_retrieval_cache.set(vector_key, chunks)

    if strategy == VECTOR_ONLY and not chunks:
        return {"answer": REFUSAL_NO_EVIDENCE, "query_understanding": qu, "strategy": strategy, "used_llm": False}

    if subgraph is None:
        subgraph = Subgraph(facts=[], entity_notes=[], truncated=False)

    with budget.stage("context_building"):
        context = build_context(subgraph, qu, chunks=chunks)

    if not context.trusted_knowledge_text:
        return {"answer": REFUSAL_NO_EVIDENCE, "query_understanding": qu, "strategy": strategy, "used_llm": False}

    # Graceful Degradation (Section 34): FALLBACK means zero LLM providers
    # reachable. This branch is structurally distinct — it never builds a
    # prompt, never constructs a GatewayRequest, never calls the Gateway at
    # all (the hard requirement from Section 35, enforced by construction,
    # not by a try/except around a failed call). Retrieval already ran
    # (it's cheap and provider-independent), so its evidence is still
    # surfaced even without generated prose.
    active_providers = get_active_providers()
    degradation = get_degradation_tracker().compute(active_providers)
    if degradation.state == DEGRADATION_FALLBACK:
        down_seconds = [s for s in (get_breaker().seconds_since_opened(p) for p in active_providers) if s is not None]
        provider_down_seconds = max(down_seconds) if down_seconds else None
        viral_state = get_viral_tracker().compute_state().state
        fallback = build_fallback_response(
            qu.query_class, provider_down_seconds=provider_down_seconds,
            evidence_lines=context.evidence_refs[:5], viral=(viral_state == VIRAL),
        )
        print(f"[degradation] FALLBACK ({degradation.reason}) — serving static template, no LLM call made")
        return {
            "answer": fallback.text, "query_understanding": qu, "strategy": strategy, "used_llm": False,
            "context": context, "personality_policy": policy, "degradation_state": degradation.state,
            "fallback_provider": fallback.provider, "fallback_model": fallback.model,
        }

    if budget.remaining_ms() < MIN_BUDGET_FOR_LLM_CALL_MS:
        return {
            "answer": REFUSAL_OUT_OF_TIME, "query_understanding": qu, "strategy": strategy,
            "used_llm": False, "context": context,
        }

    style_directives = render_directives(policy)

    prompt_text = build_prompt(context, qu, style_directives=style_directives)

    # task_complexity_hint (Section 17): set deterministically here by the
    # retrieval strategy already decided, never guessed by the Router itself.
    task_complexity_hint = "complex" if (strategy != GRAPH_ONLY or escalated or qu.query_class == "multi_hop") else "simple"

    # Section 27: realized prompt size feeds the Router's hard context-window
    # filter — computed once from the actual assembled prompt, not guessed.
    estimated_prompt_tokens = estimate_prompt_tokens(
        SYSTEM_INSTRUCTIONS, style_directives, context.trusted_knowledge_text, qu.raw_query,
    )

    # Viral Mode (Section 36, HIGH_TRAFFIC/VIRAL row): "output token budget
    # trimmed, shortening max answer length" — protecting provider quota
    # takes priority over answer richness under load.
    viral_state = get_viral_tracker().compute_state().state
    max_tokens = max_output_tokens_for_state(viral_state, DEFAULT_MAX_OUTPUT_TOKENS)

    def _call_llm(messages):
        req = GatewayRequest(messages=messages, task_complexity_hint=task_complexity_hint,
                              deadline_ms=int(budget.remaining_ms()),
                              estimated_prompt_tokens=estimated_prompt_tokens,
                              max_tokens=max_tokens)
        return gateway_generate(req, budget=budget)

    try:
        gateway_response = _call_llm([{"role": "user", "content": prompt_text}])
    except NoProviderAvailable as exc:
        return {
            "answer": f"(No LLM provider is currently available: {exc}. This is an honest failure, not a fabricated answer.)",
            "query_understanding": qu, "strategy": strategy, "used_llm": False,
        }
    except GatewayError as exc:
        return {
            "answer": f"(LLM call failed [{exc.normalized_code}]: {exc})",
            "query_understanding": qu, "strategy": strategy, "used_llm": False,
        }

    with budget.stage("output_validation"):
        validation = validate_output(gateway_response.text, subgraph.facts, policy=policy, fence_token=FENCE_TOKEN)

    final_text = gateway_response.text
    validation_status = "passed"

    if not validation.passed:
        if budget.remaining_ms() < MIN_BUDGET_FOR_LLM_CALL_MS:
            return _fallback_result(REFUSAL_OUT_OF_TIME, qu, strategy, context, policy)

        # Regenerate once (Section 29) — capped at one retry so worst-case
        # latency/cost stays bounded even against a stubborn model.
        reinforcement = _reinforcement_message(
            validation.grounding_result.unsupported_claims if validation.grounding_result else []
        )
        try:
            regenerated = _call_llm([
                {"role": "user", "content": prompt_text},
                {"role": "assistant", "content": gateway_response.text},
                {"role": "user", "content": reinforcement},
            ])
        except (NoProviderAvailable, GatewayError):
            regenerated = None

        if regenerated is None:
            return _fallback_result(REFUSAL_UNGROUNDED, qu, strategy, context, policy)

        with budget.stage("output_validation"):
            revalidation = validate_output(regenerated.text, subgraph.facts, policy=policy, fence_token=FENCE_TOKEN)

        if revalidation.passed:
            gateway_response = regenerated
            final_text = regenerated.text
            validation = revalidation
            validation_status = "regenerated"
        else:
            unsupported = revalidation.grounding_result.unsupported_claims if revalidation.grounding_result else []
            if unsupported and revalidation.safety_ok:
                # Grounding still failing but nothing unsafe leaked — strip
                # the unsupported sentences rather than discard everything.
                stripped = strip_unsupported(regenerated.text, unsupported)
                if not stripped.strip() or guts_the_answer(regenerated.text, stripped):
                    return _fallback_result(REFUSAL_UNGROUNDED, qu, strategy, context, policy)
                gateway_response = regenerated
                final_text = stripped
                validation = revalidation
                validation_status = "fallback"  # had to strip content to make it safe to serve
            else:
                # Safety failure (leaked prompt/delimiter content) survived
                # regeneration — never serve that, fall back outright.
                return _fallback_result(REFUSAL_UNGROUNDED, qu, strategy, context, policy)

    if validation.too_long:
        final_text = truncate_to_word_limit(final_text)

    if not validation.personality_consistent:
        print(f"[output_validation] personality-consistency soft-fail (register={policy.register}, "
              f"query={qu.raw_query[:80]!r}) — logged only, not blocking")

    structured = build_structured_response(
        answer_text=final_text,
        subgraph_facts=subgraph.facts,
        chunks=chunks,
        policy=policy,
        query_class=qu.query_class,
        retrieval_strategy=strategy,
        provider=gateway_response.provider,
        model=gateway_response.model,
        knowledge_version=knowledge_version,
        cache_hit=False,
        context_truncated=context.truncated_by_budget,
        validation_status=validation_status,
    )

    if cacheable:
        with budget.stage("cache_write"):
            _response_cache.set((qu.normalized, policy.personality_version, knowledge_version), (final_text, structured))
            get_semantic_cache().store(
                qu.raw_query, final_text, knowledge_version, policy.personality_version, structured,
                context_dependent=qu.context_dependent, injection_flagged=injection_result.flagged,
            )

    return {
        "answer": final_text,
        "query_understanding": qu,
        "strategy": strategy,
        "escalated": escalated,
        "context": context,
        "used_llm": True,
        "gateway_response": gateway_response,
        "personality_policy": policy,
        "validation_status": validation_status,
        "structured_response": structured,
        "budget_ms_elapsed": budget.elapsed_ms(),
        "stage_timings_ms": budget.stage_timings_ms,
    }


def ask_stream(question: str, ip: str = DEFAULT_IP, session_id: str = DEFAULT_SESSION, result_holder: dict = None):
    """Streaming entry point (Section 33). Yields text chunks as they arrive
    — the caller prints them as they come. `result_holder` (pass a fresh
    `{}`) is populated once the generator is exhausted, for the same
    evidence/metadata footer the non-streaming path prints.

    Reconciliation with Grounding/Output Validation (Section 33): unlike
    `ask()`, there is NO regenerate-then-fallback loop here — tokens are
    already shown to the caller by the time validation runs, so a failure
    gets a short correction line appended to the stream instead of a silent
    second generation pass. This intentionally duplicates ask()/_ask_inner's
    pre-LLM steps rather than sharing code with them — a deliberate,
    contained trade-off so this newer streaming path can't destabilize the
    already-tested non-streaming pipeline.
    """
    result_holder = result_holder if result_holder is not None else {}
    budget = RequestBudget()

    with budget.stage("abuse_and_rate_limit"):
        abuse_result = check_input(question, session_id)
        if not abuse_result.allowed:
            result_holder.update(_rejected(abuse_result.reason, abuse_result.message, budget))
            yield abuse_result.message
            return

        rate_result = get_limiter().check(ip, session_id)
        if not rate_result.allowed:
            msg = f"Rate limit reached ({rate_result.layer})."
            result_holder.update(_rejected(f"rate_limited:{rate_result.layer}", msg, budget))
            yield msg
            return

    with get_limiter().in_flight():
        with budget.stage("query_understanding"):
            qu = understand(question)
        strategy = decide_strategy(qu)

        injection_result = check_injection(qu.raw_query)
        if injection_result.flagged:
            print(f"[prompt_injection] flagged request (patterns={injection_result.matched}): {qu.raw_query[:120]!r}")

        if strategy == NONE_STRATEGY:
            msg = GENERAL_BLURB if qu.query_class == "general" else REFUSAL_UNKNOWN
            result_holder.update({"answer": msg, "query_understanding": qu, "strategy": strategy, "used_llm": False})
            yield msg
            return

        personality_ctx = PersonalityContext(
            query_class=qu.query_class, raw_query=qu.raw_query, injection_flagged=injection_result.flagged,
        )
        policy = compute_policy(personality_ctx)

        subgraph = None
        chunks = []
        resolved_ids = [e["id"] for e in qu.resolved_entities]

        if strategy in (GRAPH_ONLY, GRAPH_PLUS_VECTOR):
            with budget.stage("graph_retrieval"):
                subgraph = retrieve_subgraph(qu)

        if strategy == GRAPH_ONLY and (not subgraph.facts) and (not subgraph.entity_notes):
            result_holder.update({"answer": REFUSAL_NO_EVIDENCE, "query_understanding": qu, "strategy": strategy, "used_llm": False})
            yield REFUSAL_NO_EVIDENCE
            return

        escalated = False
        if strategy == GRAPH_ONLY and len(subgraph.facts) < MIN_EVIDENCE_COUNT:
            strategy = GRAPH_PLUS_VECTOR
            escalated = True

        if strategy in (VECTOR_ONLY, GRAPH_PLUS_VECTOR):
            with budget.stage("vector_retrieval"):
                chunks = retrieve_chunks(qu.raw_query, resolved_entity_ids=resolved_ids)

        if strategy == VECTOR_ONLY and not chunks:
            result_holder.update({"answer": REFUSAL_NO_EVIDENCE, "query_understanding": qu, "strategy": strategy, "used_llm": False})
            yield REFUSAL_NO_EVIDENCE
            return

        if subgraph is None:
            subgraph = Subgraph(facts=[], entity_notes=[], truncated=False)

        with budget.stage("context_building"):
            context = build_context(subgraph, qu, chunks=chunks)

        if not context.trusted_knowledge_text:
            result_holder.update({"answer": REFUSAL_NO_EVIDENCE, "query_understanding": qu, "strategy": strategy, "used_llm": False})
            yield REFUSAL_NO_EVIDENCE
            return

        style_directives = render_directives(policy)
        prompt_text = build_prompt(context, qu, style_directives=style_directives)
        task_complexity_hint = "complex" if (strategy != GRAPH_ONLY or escalated or qu.query_class == "multi_hop") else "simple"
        estimated_prompt_tokens = estimate_prompt_tokens(
            SYSTEM_INSTRUCTIONS, style_directives, context.trusted_knowledge_text, qu.raw_query,
        )

        gateway_request = GatewayRequest(
            messages=[{"role": "user", "content": prompt_text}],
            task_complexity_hint=task_complexity_hint,
            deadline_ms=int(budget.remaining_ms()),
            estimated_prompt_tokens=estimated_prompt_tokens,
            stream=True,
        )

        full_text = ""
        try:
            for chunk in gateway_generate_stream(gateway_request, budget=budget):
                full_text += chunk
                yield chunk
        except NoProviderAvailable as exc:
            msg = f"(No LLM provider is currently available: {exc}.)"
            result_holder.update({"answer": msg, "query_understanding": qu, "strategy": strategy, "used_llm": False})
            yield msg
            return
        except GatewayError as exc:
            msg = f"(LLM call failed [{exc.normalized_code}]: {exc})"
            result_holder.update({"answer": msg, "query_understanding": qu, "strategy": strategy, "used_llm": False})
            yield msg
            return

        with budget.stage("output_validation"):
            validation = validate_output(full_text, subgraph.facts, policy=policy, fence_token=FENCE_TOKEN)

        validation_status = "passed"
        if not validation.passed:
            correction = (
                "\n\n(Quick correction: part of that answer didn't hold up against my knowledge base — "
                "treat it with a grain of salt, or ask again and I'll be more careful.)"
            )
            yield correction
            full_text += correction
            validation_status = "flagged_uncorrected"  # streaming can only flag it, not retroactively fix it

        result_holder.update({
            "answer": full_text, "query_understanding": qu, "strategy": strategy, "escalated": escalated,
            "context": context, "used_llm": True, "personality_policy": policy,
            "validation_status": validation_status, "streamed": True,
            "budget_ms_elapsed": budget.elapsed_ms(),
        })


def main():
    args = sys.argv[1:]
    stream_mode = "--stream" in args
    if stream_mode:
        args = [a for a in args if a != "--stream"]
    question = " ".join(args).strip()
    if not question:
        question = input("Ask a question: ").strip()

    if stream_mode:
        result = {}
        print()
        for chunk in ask_stream(question, result_holder=result):
            print(chunk, end="", flush=True)
        print("\n")
        if result.get("query_understanding"):
            qu = result["query_understanding"]
            print(f"[query_class={qu.query_class} strategy={result.get('strategy')} "
                  f"validation_status={result.get('validation_status')}]")
        if result.get("context") and result["context"].evidence_refs:
            print("Evidence:")
            for ref in result["context"].evidence_refs:
                print(f"  - {ref}")
        return

    result = ask(question)

    if "rejected_reason" in result:
        print(f"\n[rejected: {result['rejected_reason']}]\n{result['answer']}\n")
        return

    qu = result["query_understanding"]
    entity_names = [e["canonical_name"] for e in qu.resolved_entities]
    flags = f" escalated={result['escalated']}" if result.get("escalated") else ""
    print(f"\n[query_class={qu.query_class} strategy={result['strategy']}{flags} entities={entity_names}]")
    if result.get("cache_hit"):
        print(f"[cache_hit={result['cache_type']}]")
    if result.get("context"):
        c = result["context"]
        print(f"[facts_used={c.fact_count} chunks_used={c.chunk_count} truncated={c.truncated_by_budget}]")
    if result.get("gateway_response"):
        gr = result["gateway_response"]
        print(f"[provider={gr.provider} model={gr.model} tokens_in={gr.tokens_in} tokens_out={gr.tokens_out} "
              f"latency_ms={gr.latency_ms:.0f}]")
    if result.get("personality_policy"):
        p = result["personality_policy"]
        print(f"[personality: register={p.register} humor={p.humor_frequency} sarcasm={p.sarcasm_frequency} "
              f"self_deprecation={p.self_deprecation_frequency} signals={p.signals}]")
    if result.get("validation_status"):
        print(f"[validation_status={result['validation_status']}]")
    if result.get("budget_ms_elapsed") is not None:
        print(f"[total_ms={result['budget_ms_elapsed']:.0f}]")

    print(f"\n{result['answer']}\n")

    if result.get("context") and result["context"].evidence_refs:
        print("Evidence:")
        for ref in result["context"].evidence_refs:
            print(f"  - {ref}")


if __name__ == "__main__":
    main()
