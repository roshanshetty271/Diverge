"""Templates, Journal, Save, Share, Outcome Tracking, and Health routes."""

import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import get_settings
from app.data.template_catalog import get_template_catalog
from app.db.dynamodb import (
    get_shared_debate,
    get_user_debates,
    save_debate,
    save_debate_feedback,
    save_shared_debate,
    update_debate_outcome,
    update_debate_reflection,
    upsert_user_profile,
)
from app.schemas import (
    CapabilitiesResponse,
    ChoosePathRequest,
    FeedbackRequest,
    ReflectionRequest,
    SaveDebateRequest,
    ShareDebateRequest,
    TemplateResponse,
)
from app.security.cognito import require_auth
from app.security.llm_security import sanitize_user_input, sanitize_writing_samples
from app.security.rate_limiter import check_rate_limit

logger = logging.getLogger("diverge.routes.general")
router = APIRouter(prefix="/api", tags=["general"])
_capability_probe_cache: dict[str, tuple[float, bool]] = {}
_CAPABILITY_CACHE_TTL = 300


@router.get("/templates", response_model=list[TemplateResponse])
def get_templates(request: Request):
    """Return decision templates for the template picker."""
    check_rate_limit(request, max_requests=60, window_seconds=300, endpoint="templates:burst")
    check_rate_limit(request, max_requests=500, window_seconds=3600, endpoint="templates")
    return [TemplateResponse(**template.to_api_dict()) for template in get_template_catalog()]


def _service_check(service_name: str, settings, call: str | None = None) -> bool:
    """Best-effort AWS service readiness probe."""
    cache_key = f"{service_name}:{call or 'default'}"
    cached = _capability_probe_cache.get(cache_key)
    now = time.time()
    if cached and (now - cached[0]) < _CAPABILITY_CACHE_TTL:
        return cached[1]

    try:
        import boto3
        from botocore.config import Config as BotocoreConfig

        client = boto3.client(
            service_name,
            region_name=settings.aws_region,
            config=BotocoreConfig(
                connect_timeout=2,
                read_timeout=3,
                retries={"max_attempts": 1, "mode": "standard"},
            ),
        )
        if call == "bedrock":
            client.list_foundation_models(byProvider="Amazon")
        elif call == "polly":
            client.describe_voices()
        _capability_probe_cache[cache_key] = (now, True)
        return True
    except Exception as e:
        logger.info("Capability probe failed for %s: %s", service_name, type(e).__name__)
        _capability_probe_cache[cache_key] = (now, False)
        return False


def _sanitize_persisted_input(input_data: dict) -> dict:
    """Normalize and sanitize saved user input before persistence."""
    if not isinstance(input_data, dict):
        return {}

    clean = dict(input_data)
    for field in ("path_a", "path_b", "financial_context", "values", "constraints"):
        value = clean.get(field)
        if isinstance(value, str):
            clean[field] = sanitize_user_input(value)

    writing_samples = clean.get("writing_samples")
    if isinstance(writing_samples, str):
        clean["writing_samples"] = sanitize_writing_samples(writing_samples)

    age = clean.get("age")
    if age in ("", None):
        clean["age"] = None

    return clean


@router.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities(request: Request):
    """Expose truthful runtime capability flags to the frontend."""
    check_rate_limit(request, max_requests=30, window_seconds=300, endpoint="capabilities:burst")
    check_rate_limit(request, max_requests=240, window_seconds=3600, endpoint="capabilities")
    settings = get_settings()
    bedrock_ready = _service_check("bedrock", settings, call="bedrock")
    tts_ready = _service_check("polly", settings, call="polly")

    return {
        "active_provider": settings.model_provider,
        "intended_provider": settings.intended_provider,
        "openai_fallback_active": settings.model_provider == "openai" and settings.intended_provider == "bedrock",
        "bedrock_ready": bedrock_ready,
        "tts": tts_ready,
        "sentiment": settings.comprehend_enabled,
        "email_checkins_ready": bool(
            settings.ses_sender_email
            and settings.checkins_table
            and settings.checkins_scheduler_enabled
        ),
        "knowledge_base": bool(settings.kb_id),
        "agentcore_memory": bool(settings.agentcore_memory_id),
    }


@router.post("/debate/save")
def save_debate_route(
    request: Request,
    body: SaveDebateRequest,
    user: dict = Depends(require_auth),
):
    """Save a completed debate to the Decision Journal."""
    user_id = user["sub"]
    debate_data = body.debate_data

    if not debate_data.get("debate_id"):
        raise HTTPException(status_code=400, detail="Missing debate_id in debate_data")

    check_rate_limit(request, max_requests=100, window_seconds=3600, endpoint="save", identity=f"user:{user_id}")

    try:
        user_input = _sanitize_persisted_input(debate_data.get("input", {}) or {})
        save_debate(
            debate_id=debate_data["debate_id"],
            user_id=user_id,
            user_input=user_input,
            debate_data={**debate_data, "input": user_input},
        )
        if user_input:
            upsert_user_profile(user_id, user_input)
        return {"status": "saved", "debate_id": debate_data["debate_id"]}
    except Exception as e:
        logger.error("Save failed for user %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Failed to save debate. Please try again.") from e


@router.get("/journal")
def get_journal(request: Request, user: dict = Depends(require_auth), limit: int = 50):
    """Get saved debates for the authenticated user (Decision Journal)."""
    user_id = user["sub"]
    check_rate_limit(request, max_requests=120, window_seconds=3600, endpoint="journal", identity=f"user:{user_id}")
    try:
        return get_user_debates(user_id, limit=min(limit, 100))
    except Exception as e:
        logger.error("Journal fetch failed for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Failed to load journal.") from e


@router.post("/debate/share")
def share_debate(body: ShareDebateRequest, request: Request):
    """Create a public shareable link for a debate. No auth required."""
    check_rate_limit(request, max_requests=5, window_seconds=900, endpoint="share:burst")
    check_rate_limit(request, max_requests=25, window_seconds=3600, endpoint="share")
    share_id = uuid.uuid4().hex[:10]
    try:
        save_shared_debate(share_id, body.debate_data, body.input_data)
        return {"share_id": share_id, "url": f"/d/{share_id}"}
    except Exception as e:
        logger.error("Share failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create shareable link.") from e


@router.get("/debate/shared/{share_id}")
def get_shared(share_id: str, request: Request):
    """Retrieve a publicly shared debate. No auth required."""
    check_rate_limit(request, max_requests=60, window_seconds=300, endpoint="shared:burst")
    check_rate_limit(request, max_requests=400, window_seconds=3600, endpoint="shared")
    item = get_shared_debate(share_id)
    if not item:
        raise HTTPException(status_code=404, detail="Shared debate not found or has expired.")
    return item


@router.post("/debate/{debate_id}/choose")
def choose_path(debate_id: str, body: ChoosePathRequest, request: Request, user: dict = Depends(require_auth)):
    """Record which path the user chose for a saved debate."""
    user_id = user["sub"]
    check_rate_limit(request, max_requests=40, window_seconds=3600, endpoint="choose", identity=f"user:{user_id}")
    now = datetime.now(timezone.utc).isoformat()
    ok = update_debate_outcome(debate_id, user_id, body.chosen_path, now)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to record choice.")
    return {"status": "ok"}


@router.post("/debate/{debate_id}/reflect")
def reflect_on_debate(debate_id: str, body: ReflectionRequest, request: Request, user: dict = Depends(require_auth)):
    """Record a reflection on a past decision."""
    user_id = user["sub"]
    check_rate_limit(request, max_requests=20, window_seconds=3600, endpoint="reflect", identity=f"user:{user_id}")
    now = datetime.now(timezone.utc).isoformat()
    ok = update_debate_reflection(debate_id, user_id, body.satisfaction, body.note, now)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save reflection.")
    return {"status": "ok"}


@router.get("/health")
def health_check(request: Request):
    """Health check with dependency verification. Never rate limited."""
    deps: dict[str, str] = {}
    settings = get_settings()

    try:
        import boto3

        dynamodb = boto3.client("dynamodb", region_name=settings.aws_region)
        dynamodb.describe_table(TableName=settings.debates_table)
        deps["dynamodb"] = "ok"
    except Exception as e:
        deps["dynamodb"] = f"error: {type(e).__name__}"

    if settings.model_provider == "openai":
        deps["llm"] = "ok" if settings.openai_api_key else "error: no API key"
    else:
        deps["llm"] = "ok" if _service_check("bedrock", settings, call="bedrock") else "error: unavailable"

    if settings.cognito_user_pool_id:
        try:
            import boto3

            cognito = boto3.client("cognito-idp", region_name=settings.aws_region)
            cognito.describe_user_pool(UserPoolId=settings.cognito_user_pool_id)
            deps["cognito"] = "ok"
        except Exception as e:
            deps["cognito"] = f"error: {type(e).__name__}"
    else:
        deps["cognito"] = "not configured"

    all_ok = all(v == "ok" for v in deps.values() if v != "not configured")

    response = {
        "status": "Sic Mundus Creatus Est" if all_ok else "degraded",
        "version": settings.app_version,
    }
    if settings.debug:
        response["dependencies"] = deps
    return response


@router.post("/debate/{debate_id}/feedback")
def submit_feedback(debate_id: str, req: FeedbackRequest, request: Request):
    """Submit feedback on a debate verdict. Saves to DynamoDB and emails the builder."""
    check_rate_limit(request, max_requests=5, window_seconds=3600, endpoint="feedback")

    now = datetime.now(timezone.utc).isoformat()
    saved = save_debate_feedback(debate_id, req.rating, req.quote, now)

    settings = get_settings()
    if settings.ses_sender_email and settings.feedback_notify_email:
        try:
            from app.routes.email import _send_ses_email

            subject = f"Diverge Feedback: {req.rating}"
            body = (
                f"Debate: {debate_id}\n"
                f"Rating: {req.rating}\n"
                f"Quote: {req.quote or '(none)'}\n"
                f"Time: {now}\n"
            )
            _send_ses_email(settings.feedback_notify_email, subject, body)
        except Exception as e:
            logger.warning("Failed to send feedback notification: %s", e)

    return {"status": "saved" if saved else "logged", "debate_id": debate_id}
