"""DynamoDB operations for Diverge.

Kiro security audit fix: replaced table.scan() with GSI query.
"""

import boto3
import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from app.config import get_settings

logger = logging.getLogger(__name__)


class SessionConflictError(Exception):
    """A conditional session write lost to a concurrent request."""


class DebateOwnershipError(Exception):
    """The debate id already belongs to a different user."""


def _is_conditional_failure(exc: Exception) -> bool:
    return (
        isinstance(exc, ClientError)
        and exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"
    )

# GSI name defined in template.yaml
USER_DEBATES_INDEX = "user-debates-index"
CHECKINS_STATUS_INDEX = "status-send-index"
PROFILE_FIELDS = (
    "user_name",
    "age",
    "financial_context",
    "values",
    "risk_level",
    "time_horizon",
    "constraints",
    "writing_samples",
)


def _get_table(table_name: str):
    settings = get_settings()
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    return dynamodb.Table(table_name)


def _to_dynamodb_compatible(value):
    """Recursively coerce floats into Decimal for boto3 DynamoDB writes."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamodb_compatible(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_dynamodb_compatible(item) for key, item in value.items()}
    return value


def _from_dynamodb_compatible(value):
    """Recursively convert DynamoDB Decimal values back into Python numbers."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_from_dynamodb_compatible(item) for item in value]
    if isinstance(value, dict):
        return {key: _from_dynamodb_compatible(item) for key, item in value.items()}
    return value


def save_debate(debate_id: str, user_id: str, user_input: dict, debate_data: dict) -> dict:
    """Save a completed debate to DynamoDB."""
    settings = get_settings()
    table = _get_table(settings.debates_table)

    item = {
        "debate_id": debate_id,
        "user_id": user_id,
        "path_a": user_input.get("path_a", ""),
        "path_b": user_input.get("path_b", ""),
        "input": user_input,
        "verdict": debate_data.get("verdict", ""),
        "transcript": debate_data.get("transcript", []),
        "metrics": debate_data.get("metrics", []),
        "completed_rounds": debate_data.get("completed_rounds", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # The debate id comes from the client: only create it, replace the
        # caller's own item, or claim an anonymous session item.
        table.put_item(
            Item=_to_dynamodb_compatible(item),
            ConditionExpression="attribute_not_exists(debate_id) OR user_id = :uid OR user_id = :anonymous",
            ExpressionAttributeValues={":uid": user_id, ":anonymous": "anonymous"},
        )
        logger.info(f"Saved debate {debate_id} for user {user_id}")
        return item
    except Exception as e:
        if _is_conditional_failure(e):
            logger.warning("Refused to overwrite debate %s owned by another user", debate_id)
            raise DebateOwnershipError(debate_id) from e
        logger.error(f"Failed to save debate {debate_id}: {e}")
        raise


def get_debate_owner(debate_id: str) -> str | None:
    """Return the owner of a stored debate item, "anonymous" if it has none, or None if absent.

    Errors propagate so callers can fail closed.
    """
    settings = get_settings()
    table = _get_table(settings.debates_table)
    response = table.get_item(
        Key={"debate_id": debate_id},
        ProjectionExpression="user_id",
    )
    item = response.get("Item")
    if item is None:
        return None
    return item.get("user_id") or "anonymous"


def get_user_debates(user_id: str, limit: int = 50, last_key: dict | None = None) -> dict:
    """Get debates for a user using the GSI with pagination.

    Returns dict with 'items' and optional 'last_key' for next page.
    """
    settings = get_settings()
    table = _get_table(settings.debates_table)

    try:
        query_params = {
            "IndexName": USER_DEBATES_INDEX,
            "KeyConditionExpression": Key("user_id").eq(user_id),
            "ScanIndexForward": False,
            "Limit": min(limit, 100),
        }
        if last_key:
            query_params["ExclusiveStartKey"] = last_key

        response = table.query(**query_params)
        result = {"items": _from_dynamodb_compatible(response.get("Items", []))}
        if "LastEvaluatedKey" in response:
            result["last_key"] = _from_dynamodb_compatible(response["LastEvaluatedKey"])
        return result
    except Exception as e:
        logger.error(f"Failed to get debates for user {user_id}: {e}")
        return {"items": []}


def get_user_profile(user_id: str) -> dict | None:
    """Get a saved profile context for an authenticated user."""
    settings = get_settings()
    table = _get_table(settings.users_table)

    try:
        response = table.get_item(Key={"user_id": user_id})
        return _from_dynamodb_compatible(response.get("Item"))
    except Exception as e:
        logger.error(f"Failed to get profile for {user_id}: {e}")
        return None


def upsert_user_profile(user_id: str, profile_data: dict) -> dict:
    """Persist profile context for future debates."""
    settings = get_settings()
    table = _get_table(settings.users_table)

    clean_profile = {
        field: value
        for field in PROFILE_FIELDS
        if (value := profile_data.get(field)) not in (None, "")
    }
    now = datetime.now(timezone.utc).isoformat()

    try:
        existing = get_user_profile(user_id) or {"user_id": user_id, "created_at": now}
        item = {
            **existing,
            **clean_profile,
            "user_id": user_id,
            "updated_at": now,
        }
        table.put_item(Item=_to_dynamodb_compatible(item))
        return item
    except Exception as e:
        logger.error(f"Failed to upsert profile for {user_id}: {e}")
        raise


def create_debate_session(debate_id: str, user_id: str, user_input: dict, session_data: dict) -> dict:
    """Create a checkpointed debate session item."""
    settings = get_settings()
    table = _get_table(settings.debates_table)
    now = datetime.now(timezone.utc)

    item = {
        "debate_id": debate_id,
        "user_id": user_id,
        "session_type": "checkpointed",
        "status": session_data.get("status", "paused"),
        "current_round_index": session_data.get("current_round_index", 0),
        "input": user_input,
        "transcript": session_data.get("transcript", []),
        "metrics": session_data.get("metrics", []),
        "debate_summary": session_data.get("debate_summary", ""),
        "prev_beta": session_data.get("prev_beta"),
        "category": session_data.get("category", "general"),
        "alpha_persona_label": session_data.get("alpha_persona_label", ""),
        "beta_persona_label": session_data.get("beta_persona_label", ""),
        "verdict": session_data.get("verdict", ""),
        "resources": session_data.get("resources", []),
        "total_rounds": session_data.get("total_rounds", 5),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "ttl": int((now + timedelta(days=7)).timestamp()),
    }

    try:
        table.put_item(Item=_to_dynamodb_compatible(item))
        return item
    except Exception as e:
        logger.error(f"Failed to create session {debate_id}: {e}")
        raise


def get_debate_session(debate_id: str) -> dict | None:
    """Load a checkpointed debate session."""
    settings = get_settings()
    table = _get_table(settings.debates_table)

    try:
        response = table.get_item(Key={"debate_id": debate_id})
        item = _from_dynamodb_compatible(response.get("Item"))
        if item and item.get("session_type") == "checkpointed":
            return item
        return None
    except Exception as e:
        logger.error(f"Failed to load session {debate_id}: {e}")
        return None


def update_debate_session(
    debate_id: str,
    session_data: dict,
    expected_round_index: int | None = None,
    expected_updated_at: str | None = None,
) -> dict:
    """Update a checkpointed debate session item.

    With `expected_round_index`, the write only succeeds if the stored
    `current_round_index` still equals it; otherwise SessionConflictError is
    raised so a duplicate request cannot overwrite a round that already landed.
    `expected_updated_at` works the same way on the `updated_at` timestamp.
    """
    settings = get_settings()
    table = _get_table(settings.debates_table)
    now = datetime.now(timezone.utc)

    try:
        existing = get_debate_session(debate_id)
        if not existing:
            raise ValueError(f"Checkpointed session {debate_id} not found")

        item = {
            **existing,
            **session_data,
            "debate_id": debate_id,
            "updated_at": now.isoformat(),
            "ttl": int((now + timedelta(days=7)).timestamp()),
        }
        put_kwargs: dict = {"Item": _to_dynamodb_compatible(item)}
        if expected_round_index is not None:
            put_kwargs["ConditionExpression"] = "current_round_index = :expected"
            put_kwargs["ExpressionAttributeValues"] = {":expected": expected_round_index}
        elif expected_updated_at is not None:
            put_kwargs["ConditionExpression"] = "updated_at = :expected_updated_at"
            put_kwargs["ExpressionAttributeValues"] = {":expected_updated_at": expected_updated_at}
        table.put_item(**put_kwargs)
        return item
    except Exception as e:
        if _is_conditional_failure(e):
            logger.info("Conditional update lost for session %s", debate_id)
            raise SessionConflictError(debate_id) from e
        logger.error(f"Failed to update session {debate_id}: {e}")
        raise


def complete_debate_session(
    debate_id: str,
    session_data: dict,
    expected_round_index: int | None = None,
) -> dict:
    """Mark a checkpointed session complete."""
    return update_debate_session(
        debate_id,
        {"status": "complete", **session_data},
        expected_round_index=expected_round_index,
    )


def create_checkin_records(records: list[dict]) -> int:
    """Persist scheduled email check-ins in DynamoDB."""
    settings = get_settings()
    table = _get_table(settings.checkins_table)

    try:
        with table.batch_writer() as batch:
            for record in records:
                batch.put_item(Item=_to_dynamodb_compatible(record))
        return len(records)
    except Exception as e:
        logger.error(f"Failed to create check-in records: {e}")
        raise


def get_due_checkins(limit: int = 25) -> list[dict]:
    """Query pending check-ins whose send time has arrived."""
    settings = get_settings()
    table = _get_table(settings.checkins_table)
    now_ts = int(datetime.now(timezone.utc).timestamp())

    try:
        response = table.query(
            IndexName=CHECKINS_STATUS_INDEX,
            KeyConditionExpression=Key("status").eq("pending") & Key("send_at").lte(now_ts),
            Limit=min(limit, 100),
            ScanIndexForward=True,
        )
        return _from_dynamodb_compatible(response.get("Items", []))
    except Exception as e:
        logger.error(f"Failed to query due check-ins: {e}")
        return []


def update_checkin_record(checkin_id: str, updates: dict) -> dict:
    """Update a scheduled check-in record."""
    settings = get_settings()
    table = _get_table(settings.checkins_table)

    try:
        response = table.get_item(Key={"checkin_id": checkin_id})
        item = _from_dynamodb_compatible(response.get("Item"))
        if not item:
            raise ValueError(f"Check-in {checkin_id} not found")

        item.update(updates)
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        table.put_item(Item=_to_dynamodb_compatible(item))
        return item
    except Exception as e:
        logger.error(f"Failed to update check-in {checkin_id}: {e}")
        raise


def save_shared_debate(share_id: str, debate_data: dict, user_input: dict) -> dict:
    """Save a debate for public sharing (no auth required to view)."""
    settings = get_settings()
    table = _get_table(settings.debates_table)

    item = {
        "debate_id": f"shared#{share_id}",
        "user_id": "public",
        "share_id": share_id,
        "is_public": True,
        "path_a": user_input.get("path_a", ""),
        "path_b": user_input.get("path_b", ""),
        "verdict": debate_data.get("verdict", ""),
        "transcript": debate_data.get("transcript", []),
        "metrics": debate_data.get("metrics", []),
        "resources": debate_data.get("resources", []),
        "completed_rounds": debate_data.get("completed_rounds", 0),
        "total_rounds": debate_data.get("total_rounds", 5),
        "input": user_input,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ttl": int((datetime.now(timezone.utc) + timedelta(days=90)).timestamp()),
    }

    try:
        table.put_item(Item=_to_dynamodb_compatible(item))
        logger.info(f"Saved shared debate {share_id}")
        return item
    except Exception as e:
        logger.error(f"Failed to save shared debate {share_id}: {e}")
        raise


def get_shared_debate(share_id: str) -> dict | None:
    """Retrieve a publicly shared debate."""
    settings = get_settings()
    table = _get_table(settings.debates_table)

    try:
        response = table.get_item(Key={"debate_id": f"shared#{share_id}"})
        item = _from_dynamodb_compatible(response.get("Item"))
        if item and item.get("is_public"):
            return item
        return None
    except Exception as e:
        logger.error(f"Failed to get shared debate {share_id}: {e}")
        return None


def update_debate_outcome(debate_id: str, user_id: str, chosen_path: str, chosen_at: str) -> bool:
    """Record which path the user chose."""
    settings = get_settings()
    table = _get_table(settings.debates_table)

    try:
        table.update_item(
            Key={"debate_id": debate_id},
            UpdateExpression="SET chosen_path = :cp, chosen_at = :ca",
            ConditionExpression="user_id = :uid",
            ExpressionAttributeValues={":cp": chosen_path, ":ca": chosen_at, ":uid": user_id},
        )
        return True
    except Exception as e:
        logger.error(f"Failed to update outcome for {debate_id}: {e}")
        return False


def update_debate_reflection(
    debate_id: str, user_id: str, satisfaction: int, note: str, reflected_at: str
) -> bool:
    """Record a user's reflection on their decision."""
    settings = get_settings()
    table = _get_table(settings.debates_table)

    try:
        table.update_item(
            Key={"debate_id": debate_id},
            UpdateExpression="SET satisfaction_rating = :sr, reflection_note = :rn, reflected_at = :ra",
            ConditionExpression="user_id = :uid",
            ExpressionAttributeValues={
                ":sr": satisfaction, ":rn": note, ":ra": reflected_at, ":uid": user_id,
            },
        )
        return True
    except Exception as e:
        logger.error(f"Failed to update reflection for {debate_id}: {e}")
        return False


def save_debate_feedback(debate_id: str, rating: str, quote: str, submitted_at: str) -> bool:
    """Save user feedback on a debate verdict."""
    settings = get_settings()
    table = _get_table(settings.debates_table)

    try:
        table.update_item(
            Key={"debate_id": debate_id},
            UpdateExpression="SET feedback_rating = :fr, feedback_quote = :fq, feedback_at = :fa",
            ExpressionAttributeValues={
                ":fr": rating, ":fq": quote, ":fa": submitted_at,
            },
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save feedback for {debate_id}: {e}")
        return False
