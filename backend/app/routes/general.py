"""Templates, Journal, Save, Share, Outcome Tracking, and Health routes."""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from app.schemas import (
    TemplateResponse, SaveDebateRequest, ShareDebateRequest,
    ChoosePathRequest, ReflectionRequest,
)
from app.config import get_settings
from app.db.dynamodb import (
    save_debate, get_user_debates, save_shared_debate, get_shared_debate,
    update_debate_outcome, update_debate_reflection,
)
from app.security.cognito import get_current_user, require_auth

logger = logging.getLogger("diverge.routes.general")
router = APIRouter(prefix="/api", tags=["general"])

TEMPLATES = [
    TemplateResponse(id="career", emoji="💼", title="Career Change", question="Should I stay or take the new offer?", pathA="Stay at my current job", pathB="Take the new opportunity"),
    TemplateResponse(id="city", emoji="🏙️", title="New City", question="Should I move or stay put?", pathA="Stay in my current city", pathB="Move somewhere new"),
    TemplateResponse(id="startup", emoji="🚀", title="Start Something", question="Should I go for it or play it safe?", pathA="Stay employed", pathB="Start my own thing"),
    TemplateResponse(id="education", emoji="🎓", title="Education", question="Should I study or keep working?", pathA="Keep working", pathB="Go back to school"),
]


@router.get("/templates", response_model=list[TemplateResponse])
def get_templates():
    """Return decision templates for the template picker."""
    return TEMPLATES


@router.post("/debate/save")
def save_debate_route(
    body: SaveDebateRequest,
    user: dict = Depends(require_auth),
):
    """Save a completed debate to the Decision Journal.

    Requires authentication. Uses the JWT sub claim as user_id
    (ignores any user_id in the request body for security).
    """
    user_id = user["sub"]  # Always use JWT claim, not request body
    debate_data = body.debate_data

    if not debate_data.get("debate_id"):
        raise HTTPException(status_code=400, detail="Missing debate_id in debate_data")

    try:
        item = save_debate(
            debate_id=debate_data["debate_id"],
            user_id=user_id,
            user_input=debate_data.get("input", {}),
            debate_data=debate_data,
        )
        return {"status": "saved", "debate_id": debate_data["debate_id"]}
    except Exception as e:
        logger.error(f"Save failed for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save debate. Please try again.")


@router.get("/journal")
def get_journal(user: dict = Depends(require_auth), limit: int = 50):
    """Get saved debates for the authenticated user (Decision Journal)."""
    user_id = user["sub"]
    try:
        result = get_user_debates(user_id, limit=min(limit, 100))
        return result
    except Exception as e:
        logger.error(f"Journal fetch failed for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load journal.")


@router.post("/debate/share")
def share_debate(body: ShareDebateRequest):
    """Create a public shareable link for a debate. No auth required."""
    share_id = uuid.uuid4().hex[:10]
    try:
        save_shared_debate(share_id, body.debate_data, body.input_data)
        return {"share_id": share_id, "url": f"/d/{share_id}"}
    except Exception as e:
        logger.error(f"Share failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create shareable link.")


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
    """Health check with dependency verification (Kiro audit #18).

    Returns:
      - status: "healthy" or "degraded"
      - version: app version
      - dependencies: which services are reachable
    """
    deps = {}

    # Check DynamoDB
    try:
        import boto3
        settings = get_settings()
        dynamodb = boto3.client("dynamodb", region_name=settings.aws_region)
        dynamodb.describe_table(TableName=settings.debates_table)
        deps["dynamodb"] = "ok"
    except Exception as e:
        deps["dynamodb"] = f"error: {type(e).__name__}"

    # Check LLM provider
    settings = get_settings()
    if settings.model_provider == "openai":
        deps["llm"] = "openai" if settings.openai_api_key else "error: no API key"
    else:
        try:
            import boto3
            bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)
            deps["llm"] = "bedrock"
        except Exception as e:
            deps["llm"] = f"error: {type(e).__name__}"

    # Check Cognito (if configured)
    settings = get_settings()
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