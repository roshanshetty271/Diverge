"""Templates, Journal, Save, Share, Outcome Tracking, and Health routes."""

import logging
import uuid
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.db.dynamodb import (
    get_shared_debate,
    get_user_debates,
    save_debate,
    save_shared_debate,
    upsert_user_profile,
    update_debate_outcome,
    update_debate_reflection,
)
from app.schemas import (
    CapabilitiesResponse,
    ChoosePathRequest,
    ReflectionRequest,
    SaveDebateRequest,
    ShareDebateRequest,
    TemplateResponse,
)
from app.security.cognito import require_auth
from app.security.llm_security import sanitize_user_input, sanitize_writing_samples

logger = logging.getLogger("diverge.routes.general")
router = APIRouter(prefix="/api", tags=["general"])
_capability_probe_cache: dict[str, tuple[float, bool]] = {}
_CAPABILITY_CACHE_TTL = 300

TEMPLATES = [
    TemplateResponse(id="career", emoji="💼", title="Career Change", question="Should I stay or take the new offer?", pathA="Stay at my current job", pathB="Take the new opportunity"),
    TemplateResponse(id="city", emoji="🏙️", title="New City", question="Should I move or stay put?", pathA="Stay in my current city", pathB="Move somewhere new"),
    TemplateResponse(id="startup", emoji="🚀", title="Start Something", question="Should I go for it or play it safe?", pathA="Stay employed", pathB="Start my own thing"),
    TemplateResponse(id="education", emoji="🎓", title="Education", question="Should I study or keep working?", pathA="Keep working", pathB="Go back to school"),
    TemplateResponse(id="relationship", emoji="❤️", title="Relationship", question="Should I say something or let it go?", pathA="Say what I feel", pathB="Keep it to myself"),
    TemplateResponse(id="lifestyle", emoji="🌿", title="Lifestyle Change", question="Should I make the change or stay comfortable?", pathA="Commit to the change", pathB="Keep things as they are"),
]


@router.get("/templates", response_model=list[TemplateResponse])
def get_templates():
    """Return decision templates for the template picker."""
    return TEMPLATES


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
def get_capabilities():
    """Expose truthful runtime capability flags to the frontend."""
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
    body: SaveDebateRequest,
    user: dict = Depends(require_auth),
):
    """Save a completed debate to the Decision Journal."""
    user_id = user["sub"]
    debate_data = body.debate_data

    if not debate_data.get("debate_id"):
        raise HTTPException(status_code=400, detail="Missing debate_id in debate_data")

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
def get_journal(user: dict = Depends(require_auth), limit: int = 50):
    """Get saved debates for the authenticated user (Decision Journal)."""
    user_id = user["sub"]
    try:
        return get_user_debates(user_id, limit=min(limit, 100))
    except Exception as e:
        logger.error("Journal fetch failed for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Failed to load journal.") from e


@router.post("/debate/share")
def share_debate(body: ShareDebateRequest):
    """Create a public shareable link for a debate. No auth required."""
    share_id = uuid.uuid4().hex[:10]
    try:
        save_shared_debate(share_id, body.debate_data, body.input_data)
        return {"share_id": share_id, "url": f"/d/{share_id}"}
    except Exception as e:
        logger.error("Share failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create shareable link.") from e


@router.get("/debate/shared/{share_id}")
def get_shared(share_id: str):
    """Retrieve a publicly shared debate. No auth required."""
    item = get_shared_debate(share_id)
    if not item:
        raise HTTPException(status_code=404, detail="Shared debate not found or has expired.")
    return item


@router.post("/debate/{debate_id}/choose")
def choose_path(debate_id: str, body: ChoosePathRequest, user: dict = Depends(require_auth)):
    """Record which path the user chose for a saved debate."""
    user_id = user["sub"]
    now = datetime.now(timezone.utc).isoformat()
    ok = update_debate_outcome(debate_id, user_id, body.chosen_path, now)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to record choice.")
    return {"status": "ok"}


@router.post("/debate/{debate_id}/reflect")
def reflect_on_debate(debate_id: str, body: ReflectionRequest, user: dict = Depends(require_auth)):
    """Record a reflection on a past decision."""
    user_id = user["sub"]
    now = datetime.now(timezone.utc).isoformat()
    ok = update_debate_reflection(debate_id, user_id, body.satisfaction, body.note, now)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save reflection.")
    return {"status": "ok"}


@router.get("/health")
def health_check():
    """Health check with dependency verification."""
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
        deps["llm"] = "openai" if settings.openai_api_key else "error: no API key"
    else:
        deps["llm"] = "bedrock" if _service_check("bedrock", settings, call="bedrock") else "error: unavailable"

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

    return {
        "status": "Sic Mundus Creatus Est" if all_ok else "degraded",
        "version": settings.app_version,
        "dependencies": deps,
    }
