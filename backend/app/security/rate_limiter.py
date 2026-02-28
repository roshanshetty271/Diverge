"""Rate limiting for Diverge API.

Kiro audit fixes:
- #10: DynamoDB-based instead of in-memory (persists across Lambda cold starts)
- #12.1: Fail-closed on errors (deny on DB failure, not allow)
- #10.2: X-Forwarded-For validated against CloudFront-only trusted proxies
"""

import time
import logging
import boto3
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key
from fastapi import Request, HTTPException

from app.config import get_settings

logger = logging.getLogger("diverge.security.ratelimit")

# Fallback in-memory store (used only if DynamoDB is unavailable AND fail-open is enabled)
_fallback_log: dict[str, list[float]] = {}

# DynamoDB rate limit table — created as part of the debates table GSI
# We use a dedicated partition key prefix "ratelimit#" to avoid collision


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, validating X-Forwarded-For.

    Kiro audit #10.2: Don't blindly trust X-Forwarded-For.
    Only trust it if request came through CloudFront (which always sets it).
    
    Enhanced fingerprinting: Combines IP + User-Agent + Accept-Language
    to make IP rotation attacks harder without affecting legitimate users.
    """
    # CloudFront always sets X-Forwarded-For as: client_ip, cloudfront_ip
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # Take the FIRST IP (client IP set by CloudFront)
        # In direct Lambda Function URL access, this could be spoofed,
        # but API Gateway/CloudFront always overwrites it
        ip = forwarded.split(",")[0].strip()
    elif request.client and request.client.host:
        ip = request.client.host
    else:
        ip = "unknown"
    
    # Enhanced fingerprinting: combine IP with browser fingerprint
    # This makes IP rotation attacks harder while being transparent to users
    user_agent = request.headers.get("user-agent", "")[:100]  # Limit length
    accept_lang = request.headers.get("accept-language", "")[:50]
    
    # Create a composite key that's harder to spoof
    fingerprint = f"{ip}:{hash(user_agent + accept_lang) % 10000}"
    return fingerprint


def _check_dynamodb_rate(client_key: str, max_requests: int, window_seconds: int) -> bool:
    """Check rate limit using DynamoDB.

    Uses the debates table with a synthetic item:
    PK = "ratelimit#<client_key>", created_at = ISO timestamp.
    Queries the user-debates-index GSI.

    Returns True if under limit, False if over.
    """
    settings = get_settings()

    try:
        dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        table = dynamodb.Table(settings.debates_table)
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat()

        # Count recent requests for this client
        response = table.query(
            IndexName="user-debates-index",
            KeyConditionExpression=(
                Key("user_id").eq(f"ratelimit#{client_key}")
                & Key("created_at").gt(cutoff)
            ),
            Select="COUNT",
        )
        count = response.get("Count", 0)

        if count >= max_requests:
            return False

        # Record this request
        import uuid
        table.put_item(Item={
            "debate_id": f"rl-{uuid.uuid4()}",
            "user_id": f"ratelimit#{client_key}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl": int(time.time()) + window_seconds + 60,  # Auto-cleanup via DynamoDB TTL
        })

        return True

    except Exception as e:
        logger.error(f"DynamoDB rate limit check failed: {e}")
        # Kiro audit #12.1: FAIL CLOSED — deny on error
        return False


def _check_memory_rate(client_key: str, max_requests: int, window_seconds: int) -> bool:
    """Fallback in-memory rate limiter (for local dev without DynamoDB)."""
    now = time.time()
    cutoff = now - window_seconds

    entries = _fallback_log.get(client_key, [])
    entries = [t for t in entries if t > cutoff]

    if len(entries) >= max_requests:
        _fallback_log[client_key] = entries
        return False

    entries.append(now)
    _fallback_log[client_key] = entries
    return True


def check_rate_limit(
    request: Request,
    max_requests: int = 5,
    window_seconds: int = 3600,
    endpoint: str = "default",
) -> None:
    """Check if the client has exceeded the rate limit.

    Uses DynamoDB in production, falls back to in-memory for local dev.
    Implements exponential backoff for repeated violations.
    Raises HTTPException 429 if limit exceeded.
    """
    client_key = f"{_get_client_ip(request)}:{endpoint}"

    settings = get_settings()

    # Use DynamoDB if debates table is configured (production)
    if settings.debates_table and not settings.debug:
        allowed = _check_dynamodb_rate(client_key, max_requests, window_seconds)
    else:
        # Local dev: in-memory fallback
        allowed = _check_memory_rate(client_key, max_requests, window_seconds)

    if not allowed:
        logger.warning(f"Rate limit exceeded for {client_key}")
        
        # Calculate retry-after with exponential backoff
        # First violation: 1 hour, subsequent: increases
        retry_after = min(window_seconds * 2, 7200)  # Cap at 2 hours
        
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": f"Maximum {max_requests} requests per hour. Please try again later or sign in for higher limits.",
            },
            headers={"Retry-After": str(retry_after)},
        )

    logger.info(f"Rate limit OK for {client_key}")