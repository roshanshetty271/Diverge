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
from app.db.dynamodb import get_debate_session, get_user_profile
from app.orchestrator_checkpointed import (
    continue_checkpointed_debate,
    start_checkpointed_debate,
)
from app.orchestrator import run_debate, run_debate_streaming, run_debate_token_streaming, set_interjection
from app.security.rate_limiter import check_rate_limit
from app.security.llm_security import sanitize_writing_samples, sanitize_user_input, detect_injection
from app.security.safety import detect_crisis, detect_blocked_topic, CRISIS_RESOURCES
from app.security.cognito import get_current_user
from app.config import get_settings

logger = logging.getLogger("diverge.routes.debate")
router = APIRouter(prefix="/api", tags=["debate"])
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
            logger.warning(
                "Origin verification failed from %s",
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(status_code=403, detail="Access denied.")


@router.post("/debate/start", response_model=DebateResponse)
def start_debate(
    decision: DecisionInput,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Start a new 5-round debate.

    Public endpoint (no auth required to start a debate), but:
    - Anonymous: 5 debates/hour per IP+fingerprint (enhanced tracking)
    - Authenticated: 10 debates/hour per user (can't bypass with VPN)
    
    Security: Enhanced fingerprinting combines IP + User-Agent + Accept-Language
    to make abuse harder while maintaining seamless UX for legitimate users.
    """
    # 0. Origin verification — enabled only when a trusted edge proxy is available
    _verify_origin(request)

    # 0b. Content safety — runs BEFORE rate limiting so blocked requests don't count
    all_text = f"{decision.path_a} {decision.path_b} {decision.constraints or ''}"
    is_crisis, crisis_cat = detect_crisis(all_text)
    if is_crisis:
        logger.warning(f"Crisis signal detected (category={crisis_cat}) from {request.client.host if request.client else 'unknown'}")
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
            logger.warning(f"Injection detected in {field_name}: '{pattern}' from {request.client.host}")
            raise HTTPException(
                status_code=400,
                detail="Your input contains patterns that can't be processed. Please rephrase.",
            )

    # 3. Sanitize all text fields
    user_context = _hydrate_from_profile(decision.model_dump(), user)
    user_context["writing_samples"] = sanitize_writing_samples(user_context.get("writing_samples") or "")
    user_context["financial_context"] = sanitize_user_input(user_context.get("financial_context") or "")
    user_context["constraints"] = sanitize_user_input(user_context.get("constraints") or "")
    _log_debug_debate_input("debate.stream.start", user_context)
    _log_debug_debate_input("debate.start", user_context)

    # Track who started this debate
    user_id = user["sub"] if user else "anonymous"
    logger.info(f"Starting debate: '{decision.path_a}' vs '{decision.path_b}' by {user_id}")

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

    all_text = f"{decision.path_a} {decision.path_b} {decision.constraints or ''}"
    is_crisis, crisis_cat = detect_crisis(all_text)
    if is_crisis:
        logger.warning(
            "Crisis signal detected (category=%s) from %s",
            crisis_cat,
            request.client.host if request.client else "unknown",
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
            logger.warning(f"Injection detected in {field_name}: '{pattern}' from {request.client.host}")
            raise HTTPException(
                status_code=400,
                detail="Your input contains patterns that can't be processed. Please rephrase.",
            )

    user_context = _hydrate_from_profile(decision.model_dump(), user)
    user_context["writing_samples"] = sanitize_writing_samples(user_context.get("writing_samples") or "")
    user_context["financial_context"] = sanitize_user_input(user_context.get("financial_context") or "")
    user_context["constraints"] = sanitize_user_input(user_context.get("constraints") or "")
    _log_debug_debate_input("debate.session.start", user_context)

    user_id = user["sub"] if user else "anonymous"
    logger.info(
        "Starting checkpointed debate: '%s' vs '%s' by %s",
        decision.path_a,
        decision.path_b,
        user_id,
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

    session_user_id = session.get("user_id", "anonymous")
    if session_user_id != "anonymous" and (not user or user.get("sub") != session_user_id):
        raise HTTPException(status_code=403, detail="You don't have access to this debate session.")

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
        return continue_checkpointed_debate(debate_id, interjection or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        logger.error("Checkpointed continue failed for %s", debate_id, exc_info=False)
        raise HTTPException(status_code=500, detail="The debate could not continue. Please try again.")


@router.post("/debate/stream")
async def stream_debate(
    decision: DecisionInput,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """Stream debate rounds via SSE as each round completes."""
    _verify_origin(request)

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
            logger.warning(f"Injection detected in {field_name}: '{pattern}'")
            raise HTTPException(status_code=400, detail="Your input contains patterns that can't be processed.")

    user_context = _hydrate_from_profile(decision.model_dump(), user)
    user_context["writing_samples"] = sanitize_writing_samples(user_context.get("writing_samples") or "")
    user_context["financial_context"] = sanitize_user_input(user_context.get("financial_context") or "")
    user_context["constraints"] = sanitize_user_input(user_context.get("constraints") or "")

    user_id = user["sub"] if user else "anonymous"
    logger.info(f"Starting streaming debate: '{decision.path_a}' vs '{decision.path_b}' by {user_id}")

    async def event_generator():
        q: queue.Queue = queue.Queue()

        def worker():
            try:
                for event in run_debate_streaming(user_context):
                    q.put(event)
            except Exception as e:
                q.put({"type": "error", "message": str(e)})
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
def interject_debate(req: InterjectionRequest, request: Request):
    """Submit a user interjection to be included in the next debate round.

    The interjection is picked up by the streaming orchestrator between rounds,
    influencing both agents' arguments in the following round.
    """
    _verify_origin(request)
    check_rate_limit(request, max_requests=10, window_seconds=300, endpoint="interject:burst")
    check_rate_limit(request, max_requests=60, window_seconds=3600, endpoint="interject")

    is_suspicious, pattern = detect_injection(req.text)
    if is_suspicious:
        raise HTTPException(status_code=400, detail="Your input contains patterns that can't be processed.")

    sanitized = sanitize_user_input(req.text)
    set_interjection(req.debate_id, sanitized)
    logger.info(f"Interjection stored for debate {req.debate_id}: '{sanitized[:50]}...'")
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
            logger.warning(f"Injection detected in {field_name}: '{pattern}'")
            raise HTTPException(status_code=400, detail="Your input contains patterns that can't be processed.")

    user_context = _hydrate_from_profile(decision.model_dump(), user)
    user_context["writing_samples"] = sanitize_writing_samples(user_context.get("writing_samples") or "")
    user_context["financial_context"] = sanitize_user_input(user_context.get("financial_context") or "")
    user_context["constraints"] = sanitize_user_input(user_context.get("constraints") or "")
    _log_debug_debate_input("debate.stream_tokens.start", user_context)

    user_id = user["sub"] if user else "anonymous"
    logger.info(f"Starting token-streaming debate: '{decision.path_a}' vs '{decision.path_b}' by {user_id}")

    async def event_generator():
        q: queue.Queue = queue.Queue()

        def worker():
            try:
                for event in run_debate_token_streaming(user_context):
                    q.put(event)
            except Exception as e:
                q.put({"type": "error", "message": str(e)})
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
