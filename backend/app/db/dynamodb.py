"""DynamoDB operations for Diverge.

Kiro security audit fix: replaced table.scan() with GSI query.
"""

import boto3
import logging
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key
from app.config import get_settings

logger = logging.getLogger(__name__)

# GSI name defined in template.yaml
USER_DEBATES_INDEX = "user-debates-index"


def _get_table(table_name: str):
    settings = get_settings()
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    return dynamodb.Table(table_name)


def save_debate(debate_id: str, user_id: str, user_input: dict, debate_data: dict) -> dict:
    """Save a completed debate to DynamoDB."""
    settings = get_settings()
    table = _get_table(settings.debates_table)

    item = {
        "debate_id": debate_id,
        "user_id": user_id,
        "path_a": user_input.get("path_a", ""),
        "path_b": user_input.get("path_b", ""),
        "verdict": debate_data.get("verdict", ""),
        "transcript": debate_data.get("transcript", []),
        "metrics": debate_data.get("metrics", []),
        "completed_rounds": debate_data.get("completed_rounds", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        table.put_item(Item=item)
        logger.info(f"Saved debate {debate_id} for user {user_id}")
        return item
    except Exception as e:
        logger.error(f"Failed to save debate {debate_id}: {e}")
        raise


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
        result = {"items": response.get("Items", [])}
        if "LastEvaluatedKey" in response:
            result["last_key"] = response["LastEvaluatedKey"]
        return result
    except Exception as e:
        logger.error(f"Failed to get debates for user {user_id}: {e}")
        return {"items": []}


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
        table.put_item(Item=item)
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
        item = response.get("Item")
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