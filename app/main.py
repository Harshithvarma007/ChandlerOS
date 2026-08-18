"""FastAPI HTTP layer for ChandlerOS.

This is a serving layer only — it wraps `ask.py`'s already-complete Phase
0-8 pipeline (`ask()` / `ask_stream()`) and adds the HTTP-facing production
concerns the blueprint calls out that a CLI has no need for: CORS (Section
47), security headers (Section 47), request-id + structured per-request
logging with a theoretical cost estimate (Sections 37/39), body-size limits
(defense-in-depth ahead of Section 24's character cap), and sanitized error
responses. No retrieval/gateway/personality/reliability logic is
duplicated or reimplemented here.
"""
import dataclasses
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import ask as ask_module
import cost_ledger
from abuse_prevention import MAX_INPUT_CHARS
from db import DB_PATH, get_knowledge_version
from degradation import get_degradation_tracker
from model_router import get_active_providers
from prompt import PROMPT_VERSION
from providers.registry import get_adapter
from viral_mode import get_viral_tracker

logger = logging.getLogger("chandleros")
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

MAX_BODY_BYTES = 8 * 1024
SESSION_COOKIE_NAME = "chandleros_session"
SESSION_COOKIE_MAX_AGE_S = 86400

ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://harshithvarma.dev,https://www.harshithvarma.dev,http://localhost:5173",
    ).split(",") if o.strip()
]
# Spoofable unless a reverse proxy in front of this process is trusted to set
# X-Forwarded-For itself and strip any client-supplied copy — off by default.
TRUST_PROXY = os.environ.get("TRUST_PROXY") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.path.exists(DB_PATH):
        logger.error(json.dumps({"event": "startup_error", "detail": f"knowledge.db not found at {DB_PATH}"}))
    else:
        logger.info(json.dumps({
            "event": "startup",
            "knowledge_version": get_knowledge_version(),
            "prompt_version": PROMPT_VERSION,
            "active_providers": get_active_providers(),
            "gemini_key_present": bool(os.environ.get("GEMINI_API_KEY")),
            "groq_key_present": bool(os.environ.get("GROQ_API_KEY")),
        }))
    yield


app = FastAPI(title="ChandlerOS API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
)


@app.middleware("http")
async def body_size_guard(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": f"Request body exceeds {MAX_BODY_BYTES} bytes."})
    return await call_next(request)


@app.middleware("http")
async def request_id_and_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    request.state.log_extra = {}
    start = time.monotonic()

    response = await call_next(request)

    latency_ms = (time.monotonic() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

    log_line = {
        "request_id": request_id, "route": request.url.path, "method": request.method,
        "status": response.status_code, "latency_ms": round(latency_ms, 1),
    }
    log_line.update(request.state.log_extra)
    logger.info(json.dumps(log_line, default=str))
    cost_ledger.record(request_id=request_id, route=request.url.path, status=response.status_code,
                        latency_ms=latency_ms, **request.state.log_extra)
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    logger.exception(json.dumps({"request_id": request_id, "event": "unhandled_exception"}))
    return JSONResponse(status_code=500, content={"detail": "Internal server error.", "request_id": request_id})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_INPUT_CHARS)
    session_id: str | None = None


def _client_ip(request: Request) -> str:
    if TRUST_PROXY:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _resolve_session(payload_session_id: str | None, request: Request) -> tuple[str, bool]:
    if payload_session_id:
        return payload_session_id, False
    cookie_session = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_session:
        return cookie_session, False
    return str(uuid.uuid4()), True


def _estimated_cost_usd(gateway_response) -> float:
    if gateway_response is None:
        return 0.0
    try:
        caps = get_adapter(gateway_response.provider).capabilities(gateway_response.model)
    except (KeyError, ValueError):
        return 0.0
    total_tokens = (gateway_response.tokens_in or 0) + (gateway_response.tokens_out or 0)
    return round(caps.cost_per_1k_tokens * total_tokens / 1000, 6)


def _normalize_response(result: dict, request_id: str) -> dict:
    """Every non-rejected path through ask() ends up here. `structured_response`
    (structured_output.py) is already the intended external contract — used
    directly when present; the refusal/general/fallback short-circuit paths
    in ask.py don't build one, so an equivalent minimal shape is assembled
    here instead of changing ask.py's internals to always build one."""
    structured = result.get("structured_response")
    if structured is not None:
        body = structured.to_dict()
        body["request_id"] = request_id
        return body

    qu = result.get("query_understanding")
    policy = result.get("personality_policy")
    metadata = {
        "query_class": getattr(qu, "query_class", None) if qu else None,
        "retrieval_strategy": result.get("strategy"),
        "used_llm": result.get("used_llm", False),
        "trace_id": request_id,
    }
    if "degradation_state" in result:
        metadata["degradation_state"] = result["degradation_state"]
        metadata["fallback_provider"] = result.get("fallback_provider")
        metadata["fallback_model"] = result.get("fallback_model")

    return {
        "answer": result["answer"],
        "evidence": [],
        "confidence": None,
        "personality_policy_snapshot": dataclasses.asdict(policy) if policy else {},
        "metadata": metadata,
        "validation_status": result.get("validation_status", "n/a"),
        "request_id": request_id,
    }


@app.post("/ask")
async def ask_endpoint(payload: AskRequest, request: Request, response: Response):
    request_id = request.state.request_id
    ip = _client_ip(request)
    session_id, is_new_session = _resolve_session(payload.session_id, request)

    result = ask_module.ask(payload.question, ip=ip, session_id=session_id)

    if "rejected_reason" in result:
        reason = result["rejected_reason"]
        request.state.log_extra.update({"rejected_reason": reason, "used_llm": False})
        if reason.startswith("rate_limited"):
            retry_after = result.get("retry_after_s")
            headers = {"Retry-After": str(int(retry_after) + 1)} if retry_after else {}
            raise HTTPException(status_code=429, detail=result["answer"], headers=headers)
        raise HTTPException(status_code=400, detail=result["answer"])

    if is_new_session:
        response.set_cookie(
            SESSION_COOKIE_NAME, session_id, httponly=True, samesite="lax", max_age=SESSION_COOKIE_MAX_AGE_S,
        )

    gateway_response = result.get("gateway_response")
    request.state.log_extra.update({
        "used_llm": result.get("used_llm", False),
        "provider": getattr(gateway_response, "provider", None),
        "model": getattr(gateway_response, "model", None),
        "tokens_in": getattr(gateway_response, "tokens_in", None),
        "tokens_out": getattr(gateway_response, "tokens_out", None),
        "estimated_cost_usd": _estimated_cost_usd(gateway_response),
        "cache_hit": result.get("cache_hit", False),
        "validation_status": result.get("validation_status"),
        "degradation_state": result.get("degradation_state"),
        "viral_state": get_viral_tracker().compute_state().state,
        "stage_timings_ms": result.get("stage_timings_ms"),
    })

    return _normalize_response(result, request_id)


def _sse_stream(question: str, ip: str, session_id: str, request_id: str, log_extra: dict):
    """Plain (sync) generator — Starlette's StreamingResponse iterates a
    non-async generator in a worker thread automatically, so the blocking
    `requests` calls inside ask_stream()/the provider adapters never stall
    the event loop for other concurrent requests."""
    result_holder = {}
    try:
        for chunk in ask_module.ask_stream(question, ip=ip, session_id=session_id, result_holder=result_holder):
            yield f"data: {json.dumps({'delta': chunk})}\n\n"
    except Exception:
        logger.exception(json.dumps({"request_id": request_id, "event": "stream_error"}))
        yield f"data: {json.dumps({'error': 'stream_failed'})}\n\n"
        result_holder.setdefault("used_llm", False)

    qu = result_holder.get("query_understanding")
    done_payload = {
        "request_id": request_id,
        "query_class": getattr(qu, "query_class", None) if qu else None,
        "strategy": result_holder.get("strategy"),
        "validation_status": result_holder.get("validation_status"),
        "used_llm": result_holder.get("used_llm"),
        "rejected_reason": result_holder.get("rejected_reason"),
    }
    yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    log_extra.update({
        "used_llm": result_holder.get("used_llm", False),
        "validation_status": result_holder.get("validation_status"),
        "rejected_reason": result_holder.get("rejected_reason"),
        "streamed": True,
    })


@app.post("/ask/stream")
async def ask_stream_endpoint(payload: AskRequest, request: Request):
    request_id = request.state.request_id
    ip = _client_ip(request)
    session_id, _ = _resolve_session(payload.session_id, request)

    return StreamingResponse(
        _sse_stream(payload.question, ip, session_id, request_id, request.state.log_extra),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Request-ID": request_id},
    )


@app.get("/health")
async def health():
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=503, detail="knowledge.db not found — run ingestion/build_graph.py")
    try:
        knowledge_version = get_knowledge_version()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"knowledge.db unreadable: {exc}")

    degradation = get_degradation_tracker().compute(get_active_providers())
    return {
        "status": "ok",
        "degradation_state": degradation.state,
        "knowledge_version": knowledge_version,
    }


@app.get("/stats")
async def stats(hours: float = 24.0):
    """Cost Tracking (Section 39) rollup — request/token/cache/latency
    summary from cost_ledger.py's persisted store, not just the stdout log
    line each request already gets. Read-only, no secrets, safe to expose;
    lock this down (auth or remove) before pointing it at real traffic if
    request-volume-by-route ever becomes sensitive."""
    return cost_ledger.summary(since_hours=hours)


@app.get("/version")
async def version():
    return {
        "app_version": app.version,
        "knowledge_version": get_knowledge_version() if os.path.exists(DB_PATH) else None,
        "prompt_version": PROMPT_VERSION,
        "active_providers": get_active_providers(),
    }


@app.get("/")
async def root():
    return {"name": "ChandlerOS API", "docs": "/docs", "health": "/health"}
