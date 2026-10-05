"""Debate API routes.

Security measures:
- Rate limiting: 5/hr per IP (anonymous), 10/hr per user (authenticated)
- Optional auth: tracks user_id if logged in (Kiro audit #3)
- Input sanitization: prompt injection defense
- Output validation: system prompt leak detection
- Error sanitization: no stack traces in responses
"""

import json
import asyncio
import logging
import queue
import threading
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from app.schemas import (
    CheckpointedDebateResponse,
    DebateResponse,
    DebateSessionContinueRequest,
    DecisionInput,
    InterjectionRequest,
)
from app.db.dynamodb import get_debate_owner, get_debate_session, get_user_profile
from app.orchestrator_checkpointed import (
    continue_checkpointed_debate,
    continue_checkpointed_streaming,
    _session_to_response,
    start_checkpointed_debate,
    start_checkpointed_streaming,
)
from app.orchestrator import run_debate, run_debate_streaming, run_debate_token_streaming, set_interjection
from app.security.rate_limiter import check_rate_limit, client_ip_hash
from app.security.llm_security import (
    detect_injection,
    sanitize_context_field,
    sanitize_user_input,
    sanitize_writing_samples,
)
from app.security.safety import detect_crisis, detect_blocked_topic, CRISIS_RESOURCES
from app.security.cognito import ensure_debate_access, get_current_user
from app.security.turnstile import require_turnstile_for_anonymous_start
from app.config import get_settings

logger = logging.getLogger("diverge.routes.debate")
router = APIRouter(prefix="/api", tags=["debate"])
# Stream error events never carry exception text; details go to the server log.
STREAM_START_ERROR = "The debate could not be completed. Please try again."
STREAM_CONTINUE_ERROR = "The debate could not continue. Please try again."
# Only hydrate lightweight profile fields automatically. Narrative fields like
# constraints or writing samples should never silently bleed into a new debate.
PROFILE_FIELDS = (
    "user_name",
    "age",
    "risk_level",
    "time_horizon",
)


def _log_debug_debate_input(label: str, user_context: dict):
    """Emit a concise debate input trace only in local/debug mode."""
    settings = get_settings()
    if not settings.debug:
        return

    logger.info(
        "[debug-trace] %s | name=%r age=%r path_a=%r path_b=%r constraints=%r financial=%r values=%r writing_samples_len=%s",
        label,
        user_context.get("user_name"),
        user_context.get("age"),
        user_context.get("path_a"),
        user_context.get("path_b"),
        user_context.get("constraints"),
        user_context.get("financial_context"),
        user_context.get("values"),
        len(user_context.get("writing_samples") or ""),
    )


def _sanitize_context_fields(user_context: dict) -> dict:
    """Screen every free-text field that reaches the prompts, in place."""
    user_context["writing_samples"] = sanitize_writing_samples(user_context.get("writing_samples") or "")
    user_context["financial_context"] = sanitize_context_field(user_context.get("financial_context") or "", 500)
    user_context["constraints"] = sanitize_context_field(user_context.get("constraints") or "", 500)
    user_context["values"] = sanitize_context_field(user_context.get("values") or "", 200)
    return user_context


def _hydrate_from_profile(user_context: dict, user: Optional[dict]) -> dict:
    """Backfill missing authenticated user context from saved profile data."""
    if not user:
        return user_context

    profile = get_user_profile(user["sub"])
    if not profile:
        return user_context

    hydrated = dict(user_context)
    for field in PROFILE_FIELDS:
        current = hydrated.get(field)
        if current not in (None, ""):
            continue
        profile_value = profile.get(field)
        if profile_value not in (None, ""):
            hydrated[field] = profile_value
    return hydrated


def _verify_origin(request: Request):
    """Reject requests that bypass the intended public entrypoint."""
    settings = get_settings()
    if settings.origin_verify_header and settings.origin_verify_secret:
        origin_header = request.headers.get(settings.origin_verify_header, "")
        if origin_header != settings.origin_verify_secret:
            logger.warning("Origin verification failed client=%s", client_ip_hash(request))
            raise HTTPException(status_code=403, detail="Access denied.")


@router.post("/debate/start", response_model=DebateResponse)
def start_debate(
    decision: DecisionInput,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Start a new 5-round debate.

    Public endpoint (no auth required to start a debate), but:
    - Anonymous: 5 debates/hour per client IP
    - Authenticated: 10 debates/hour per user (can't bypass with VPN)
    """
    # 0. Origin verification — enabled only when a trusted edge proxy is available
    _verify_origin(request)
    require_turnstile_for_anonymous_start(request, user)

    # 0b. Content safety — runs BEFORE rate limiting so blocked requests don't count
    all_text = f"{decision.path_a} {decision.path_b} {decision.constraints or ''}"
    is_crisis, crisis_cat = detect_crisis(all_text)
    if is_crisis:
        logger.warning("Crisis signal detected (category=%s) client=%s", crisis_cat, client_ip_hash(request))
        return JSONResponse({"type": "crisis", "category": crisis_cat, "resources": CRISIS_RESOURCES})

    is_blocked, block_reason = detect_blocked_topic(decision.path_a, decision.path_b, decision.constraints or "")
    if is_blocked:
        raise HTTPException(status_code=400, detail=block_reason)

    # 1. Rate limiting — tighter for anonymous, generous for authenticated
    if user:
        check_rate_limit(request, max_requests=4, window_seconds=600, endpoint="debate:burst", identity=f"user:{user['sub']}")
        check_rate_limit(request, max_requests=10, window_seconds=3600, endpoint="debate", identity=f"user:{user['sub']}")
    else:
        check_rate_limit(request, max_requests=2, window_seconds=600, endpoint="debate:burst")
        check_rate_limit(request, max_requests=5, window_seconds=3600, endpoint="debate")

    # 2. Check decision paths for injection
    for field_name, field_value in [("path_a", decision.path_a), ("path_b", decision.path_b)]:
        is_suspicious, pattern = detect_injection(field_value)
        if is_suspicious:
            logger.warning("Injection detected in %s: %r client=%s", field_name, pattern, client_ip_hash(request))
            raise HTTPException(
                status_code=400,
                detail="Your input contains patterns that can't be processed. Please rephrase.",
            )

    # 3. Sanitize all text fields
    user_context = _hydrate_from_profile(decision.model_dump(), user)
    _sanitize_context_fields(user_context)
    _log_debug_debate_input("debate.stream.start", user_context)
    _log_debug_debate_input("debate.start", user_context)

    # Track who started this debate
    user_id = user["sub"] if user else "anonymous"
    logger.info("Starting debate by %s (path lengths %d/%d)", user_id, len(decision.path_a), len(decision.path_b))

    try:
        result = run_debate(user_context)
        logger.info(f"Debate {result.debate_id} completed ({result.completed_rounds}/{result.total_rounds} rounds) by {user_id}")
        return result
    except Exception as e:
        logger.error(f"Debate failed for {user_id}: {type(e).__name__}", exc_info=False)
        raise HTTPException(status_code=500, detail="The debate could not be completed. Please try again.")


@router.post("/debate/session/start", response_model=CheckpointedDebateResponse)
def start_checkpointed_debate_route(
    decision: DecisionInput,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Start a checkpointed debate that pauses after each round."""
    _verify_origin(request)
    require_turnstile_for_anonymous_start(request, user)

    all_text = f"{decision.path_a} {decision.path_b} {decision.constraints or ''}"
    is_crisis, crisis_cat = detect_crisis(all_text)
    if is_crisis:
        logger.warning("Crisis signal detected (category=%s) client=%s", crisis_cat, client_ip_hash(request))
        return JSONResponse({"type": "crisis", "category": crisis_cat, "resources": CRISIS_RESOURCES})

    is_blocked, block_reason = detect_blocked_topic(
        decision.path_a,
        decision.path_b,
        decision.constraints or "",
    )
    if is_blocked:
        raise HTTPException(status_code=400, detail=block_reason)

    if user:
        check_rate_limit(request, max_requests=4, window_seconds=600, endpoint="debate-session:burst", identity=f"user:{user['sub']}")
        check_rate_limit(request, max_requests=10, window_seconds=3600, endpoint="debate-session", identity=f"user:{user['sub']}")
    else:
        check_rate_limit(request, max_requests=2, window_seconds=600, endpoint="debate-session:burst")
        check_rate_limit(request, max_requests=5, window_seconds=3600, endpoint="debate-session")

    for field_name, field_value in [("path_a", decision.path_a), ("path_b", decision.path_b)]:
        is_suspicious, pattern = detect_injection(field_value)
        if is_suspicious:
            logger.warning("Injection detected in %s: %r client=%s", field_name, pattern, client_ip_hash(request))
            raise HTTPException(
                status_code=400,
                detail="Your input contains patterns that can't be processed. Please rephrase.",
            )

    user_context = _hydrate_from_profile(decision.model_dump(), user)
    _sanitize_context_fields(user_context)
    _log_debug_debate_input("debate.session.start", user_context)

    user_id = user["sub"] if user else "anonymous"
    logger.info(
        "Starting checkpointed debate by %s (path lengths %d/%d)",
        user_id,
        len(decision.path_a),
        len(decision.path_b),
    )

    try:
        return start_checkpointed_debate(user_context, user_id=user_id)
    except Exception as e:
        logger.error(f"Checkpointed debate failed for {user_id}: {type(e).__name__}", exc_info=False)
        raise HTTPException(status_code=500, detail="The debate could not be completed. Please try again.")


@router.post("/debate/session/{debate_id}/continue", response_model=CheckpointedDebateResponse)
def continue_checkpointed_debate_route(
    debate_id: str,
    body: DebateSessionContinueRequest,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Resume a paused debate for exactly one more round."""
    _verify_origin(request)

    if user:
        check_rate_limit(request, max_requests=30, window_seconds=3600, endpoint="debate-continue", identity=f"user:{user['sub']}")
    else:
        check_rate_limit(request, max_requests=15, window_seconds=3600, endpoint="debate-continue")

    session = get_debate_session(debate_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found.")

    ensure_debate_access(session.get("user_id", "anonymous"), user)

    interjection = (body.interjection or "").strip()
    if interjection:
        is_suspicious, _ = detect_injection(interjection)
        if is_suspicious:
            raise HTTPException(
                status_code=400,
                detail="Your input contains patterns that can't be processed.",
            )
        interjection = sanitize_user_input(interjection)
        if get_settings().debug:
            logger.info("[debug-trace] debate.session.continue | debate_id=%s interjection=%r", debate_id, interjection)

    try:
        return continue_checkpointed_debate(debate_id, interjection or None, body.round_number)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        logger.error("Checkpointed continue failed for %s", debate_id, exc_info=False)
        raise HTTPException(status_code=500, detail="The debate could not continue. Please try again.")


@router.get("/debate/session/{debate_id}", response_model=CheckpointedDebateResponse)
def get_checkpointed_debate_session_route(
    debate_id: str,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Fetch the latest checkpointed debate session state."""
    _verify_origin(request)

    if user:
        check_rate_limit(request, max_requests=120, window_seconds=600, endpoint="debate-status", identity=f"user:{user['sub']}")
    else:
        check_rate_limit(request, max_requests=60, window_seconds=600, endpoint="debate-status")

    session = get_debate_session(debate_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found.")

    ensure_debate_access(session.get("user_id", "anonymous"), user)

    return _session_to_response(debate_id, session)


@router.post("/debate/session/start-stream")
async def start_checkpointed_stream_route(
    decision: DecisionInput,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Stream the first round of a checkpointed debate via SSE."""
    _verify_origin(request)
    require_turnstile_for_anonymous_start(request, user)

    all_text = f"{decision.path_a} {decision.path_b} {decision.constraints or ''}"
    is_crisis, crisis_cat = detect_crisis(all_text)
    if is_crisis:
        logger.warning(
            "Crisis signal detected in checkpointed stream (category=%s) client=%s",
            crisis_cat,
            client_ip_hash(request),
        )
        return JSONResponse({"type": "crisis", "category": crisis_cat, "resources": CRISIS_RESOURCES})

    is_blocked, block_reason = detect_blocked_topic(
        decision.path_a,
        decision.path_b,
        decision.constraints or "",
    )
    if is_blocked:
        raise HTTPException(status_code=400, detail=block_reason)

    if user:
        check_rate_limit(request, max_requests=4, window_seconds=600, endpoint="debate-session:burst", identity=f"user:{user['sub']}")
        check_rate_limit(request, max_requests=10, window_seconds=3600, endpoint="debate-session", identity=f"user:{user['sub']}")
    else:
        check_rate_limit(request, max_requests=2, window_seconds=600, endpoint="debate-session:burst")
        check_rate_limit(request, max_requests=5, window_seconds=3600, endpoint="debate-session")

    for field_name, field_value in [("path_a", decision.path_a), ("path_b", decision.path_b)]:
        is_suspicious, pattern = detect_injection(field_value)
        if is_suspicious:
            logger.warning("Injection detected in %s: %r client=%s", field_name, pattern, client_ip_hash(request))
            raise HTTPException(
                status_code=400,
                detail="Your input contains patterns that can't be processed. Please rephrase.",
            )

    user_context = _hydrate_from_profile(decision.model_dump(), user)
    _sanitize_context_fields(user_context)
    _log_debug_debate_input("debate.session.start-stream", user_context)

    user_id = user["sub"] if user else "anonymous"
    logger.info(
        "Starting checkpointed stream debate by %s (path lengths %d/%d)",
        user_id,
        len(decision.path_a),
        len(decision.path_b),
    )

    async def event_generator():
        q: queue.Queue = queue.Queue()

        def worker():
            try:
                for event in start_checkpointed_streaming(user_context, user_id=user_id):
                    q.put(event)
            except Exception:
                logger.exception("Checkpointed start stream failed for %s", user_id)
                q.put({"type": "error", "message": STREAM_START_ERROR})
            q.put(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            event = await asyncio.to_thread(q.get)
            if event is None:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/debate/session/{debate_id}/continue-stream")
async def continue_checkpointed_stream_route(
    debate_id: str,
    body: DebateSessionContinueRequest,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Stream one round of a checkpointed debate via SSE."""
    _verify_origin(request)

    # Same rate-limit bucket as sync /continue
    if user:
        check_rate_limit(request, max_requests=30, window_seconds=3600, endpoint="debate-continue", identity=f"user:{user['sub']}")
    else:
        check_rate_limit(request, max_requests=15, window_seconds=3600, endpoint="debate-continue")

    session = get_debate_session(debate_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found.")

    ensure_debate_access(session.get("user_id", "anonymous"), user)

    interjection = (body.interjection or "").strip()
    if interjection:
        is_suspicious, _ = detect_injection(interjection)
        if is_suspicious:
            raise HTTPException(
                status_code=400,
                detail="Your input contains patterns that can't be processed.",
            )
        interjection = sanitize_user_input(interjection)

    async def event_generator():
        q: queue.Queue = queue.Queue()

        def worker():
            try:
                for event in continue_checkpointed_streaming(debate_id, interjection or None, body.round_number):
                    q.put(event)
            except Exception:
                logger.exception("Checkpointed continue stream failed for %s", debate_id)
                q.put({"type": "error", "message": STREAM_CONTINUE_ERROR})
            q.put(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            event = await asyncio.to_thread(q.get)
            if event is None:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/debate/stream")
async def stream_debate(
    decision: DecisionInput,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Stream debate rounds via SSE as each round completes."""
    _verify_origin(request)
    require_turnstile_for_anonymous_start(request, user)

    # Content safety — before rate limiting
    all_text = f"{decision.path_a} {decision.path_b} {decision.constraints or ''}"
    is_crisis, crisis_cat = detect_crisis(all_text)
    if is_crisis:
        logger.warning(f"Crisis signal detected in stream (category={crisis_cat})")
        return JSONResponse({"type": "crisis", "category": crisis_cat, "resources": CRISIS_RESOURCES})

    is_blocked, block_reason = detect_blocked_topic(decision.path_a, decision.path_b, decision.constraints or "")
    if is_blocked:
        raise HTTPException(status_code=400, detail=block_reason)

    if user:
        check_rate_limit(request, max_requests=4, window_seconds=600, endpoint="debate-stream:burst", identity=f"user:{user['sub']}")
        check_rate_limit(request, max_requests=10, window_seconds=3600, endpoint="debate-stream", identity=f"user:{user['sub']}")
    else:
        check_rate_limit(request, max_requests=2, window_seconds=600, endpoint="debate-stream:burst")
        check_rate_limit(request, max_requests=5, window_seconds=3600, endpoint="debate-stream")

    for field_name, field_value in [("path_a", decision.path_a), ("path_b", decision.path_b)]:
        is_suspicious, pattern = detect_injection(field_value)
        if is_suspicious:
            logger.warning("Injection detected in %s: %r client=%s", field_name, pattern, client_ip_hash(request))
            raise HTTPException(status_code=400, detail="Your input contains patterns that can't be processed.")

    user_context = _hydrate_from_profile(decision.model_dump(), user)
    _sanitize_context_fields(user_context)

    user_id = user["sub"] if user else "anonymous"
    logger.info("Starting streaming debate by %s (path lengths %d/%d)", user_id, len(decision.path_a), len(decision.path_b))

    async def event_generator():
        q: queue.Queue = queue.Queue()

        def worker():
            try:
                for event in run_debate_streaming(user_context):
                    q.put(event)
            except Exception:
                logger.exception("Debate stream failed for %s", user_id)
                q.put({"type": "error", "message": STREAM_START_ERROR})
            q.put(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            event = await asyncio.to_thread(q.get)
            if event is None:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/debate/interject")
def interject_debate(
    req: InterjectionRequest,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Submit a user interjection to be included in the next debate round.

    The interjection is picked up by the streaming orchestrator between rounds,
    influencing both agents' arguments in the following round.
    """
    _verify_origin(request)
    check_rate_limit(request, max_requests=10, window_seconds=300, endpoint="interject:burst", user=user)
    check_rate_limit(request, max_requests=60, window_seconds=3600, endpoint="interject", user=user)

    # Debates that were saved by a signed-in user only accept that user's input.
    try:
        owner_id = get_debate_owner(req.debate_id)
    except Exception:
        logger.error("Owner lookup failed for interjection on %s", req.debate_id)
        raise HTTPException(status_code=503, detail="The service is temporarily unavailable. Please try again.")
    ensure_debate_access(owner_id, user)

    is_suspicious, pattern = detect_injection(req.text)
    if is_suspicious:
        raise HTTPException(status_code=400, detail="Your input contains patterns that can't be processed.")

    sanitized = sanitize_user_input(req.text)
    set_interjection(req.debate_id, sanitized)
    logger.info("Interjection stored for debate %s (%d chars)", req.debate_id, len(sanitized))
    if get_settings().debug:
        logger.info("[debug-trace] debate.interject | debate_id=%s text=%r", req.debate_id, sanitized)
    return {"status": "ok"}


@router.post("/debate/stream-tokens")
async def stream_debate_tokens(
    decision: DecisionInput,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Stream debate with token-level granularity via SSE.

    Yields individual tokens as agents generate them, enabling
    real-time typewriter effect in the UI.
    """
    _verify_origin(request)
    require_turnstile_for_anonymous_start(request, user)

    all_text = f"{decision.path_a} {decision.path_b} {decision.constraints or ''}"
    is_crisis, crisis_cat = detect_crisis(all_text)
    if is_crisis:
        logger.warning(f"Crisis signal detected in token-stream (category={crisis_cat})")
        return JSONResponse({"type": "crisis", "category": crisis_cat, "resources": CRISIS_RESOURCES})

    is_blocked, block_reason = detect_blocked_topic(decision.path_a, decision.path_b, decision.constraints or "")
    if is_blocked:
        raise HTTPException(status_code=400, detail=block_reason)

    if user:
        check_rate_limit(request, max_requests=4, window_seconds=600, endpoint="debate-token-stream:burst", identity=f"user:{user['sub']}")
        check_rate_limit(request, max_requests=10, window_seconds=3600, endpoint="debate-token-stream", identity=f"user:{user['sub']}")
    else:
        check_rate_limit(request, max_requests=2, window_seconds=600, endpoint="debate-token-stream:burst")
        check_rate_limit(request, max_requests=5, window_seconds=3600, endpoint="debate-token-stream")

    for field_name, field_value in [("path_a", decision.path_a), ("path_b", decision.path_b)]:
        is_suspicious, pattern = detect_injection(field_value)
        if is_suspicious:
            logger.warning("Injection detected in %s: %r client=%s", field_name, pattern, client_ip_hash(request))
            raise HTTPException(status_code=400, detail="Your input contains patterns that can't be processed.")

    user_context = _hydrate_from_profile(decision.model_dump(), user)
    _sanitize_context_fields(user_context)
    _log_debug_debate_input("debate.stream_tokens.start", user_context)

    user_id = user["sub"] if user else "anonymous"
    logger.info("Starting token-streaming debate by %s (path lengths %d/%d)", user_id, len(decision.path_a), len(decision.path_b))

    async def event_generator():
        q: queue.Queue = queue.Queue()

        def worker():
            try:
                for event in run_debate_token_streaming(user_context):
                    q.put(event)
            except Exception:
                logger.exception("Token stream failed for %s", user_id)
                q.put({"type": "error", "message": STREAM_START_ERROR})
            q.put(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            event = await asyncio.to_thread(q.get)
            if event is None:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
