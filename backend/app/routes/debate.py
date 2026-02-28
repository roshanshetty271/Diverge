"""Debate API routes.

Security measures:
- Rate limiting: 5/hr per IP (anonymous), 10/hr per user (authenticated)
- Optional auth: tracks user_id if logged in (Kiro audit #3)
- Input sanitization: prompt injection defense
- Output validation: system prompt leak detection
- Error sanitization: no stack traces in responses
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from app.schemas import DecisionInput, DebateResponse
from app.orchestrator import run_debate
from app.security.rate_limiter import check_rate_limit
from app.security.llm_security import sanitize_writing_samples, sanitize_user_input, detect_injection
from app.security.cognito import get_current_user
from app.config import get_settings

logger = logging.getLogger("diverge.routes.debate")
router = APIRouter(prefix="/api", tags=["debate"])


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
    # 0. Origin verification — reject requests that didn't come through CloudFront
    settings = get_settings()
    if settings.origin_verify_header and settings.origin_verify_secret:
        origin_header = request.headers.get(settings.origin_verify_header, "")
        if origin_header != settings.origin_verify_secret:
            logger.warning(f"Origin verification failed from {request.client.host if request.client else 'unknown'}")
            raise HTTPException(status_code=403, detail="Access denied.")

    # 1. Rate limiting — tighter for anonymous, generous for authenticated
    if user:
        # Authenticated: rate limit by user sub (can't bypass with VPN)
        check_rate_limit(request, max_requests=10, window_seconds=3600, endpoint=f"user:{user['sub']}")
    else:
        # Anonymous: rate limit by IP+fingerprint (enhanced tracking)
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
    user_context = decision.model_dump()
    user_context["writing_samples"] = sanitize_writing_samples(user_context.get("writing_samples") or "")
    user_context["financial_context"] = sanitize_user_input(user_context.get("financial_context") or "")
    user_context["constraints"] = sanitize_user_input(user_context.get("constraints") or "")

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