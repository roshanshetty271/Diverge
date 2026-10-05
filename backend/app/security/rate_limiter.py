"""Rate limiting for Diverge API.

- Counters live in DynamoDB so limits hold across Lambda instances.
- Each (client, endpoint, window) gets one counter item that is incremented
  with a single conditional UpdateItem, so concurrent requests cannot both
  slip under the limit.
- Client keys are HMAC-SHA256 digests: stable across processes and cold
  starts, and raw IPs or user ids never end up in the table.
- Signed-in users are keyed by their Cognito `sub`; anonymous clients by IP.
- If the counter store fails, requests are refused with 503 (fail closed).
"""

import hashlib
import hmac
import logging
import time

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, Request

from app.config import get_settings

logger = logging.getLogger("diverge.security.ratelimit")

# Used only when DIVERGE_RATE_LIMIT_HASH_KEY is not configured.
_FALLBACK_HASH_KEY = "diverge-rate-limit-v1"

# Paths that must never be rate limited (load balancer / uptime probes).
EXEMPT_PATHS = frozenset({"/api/health"})

# In-memory store used for local development (debug mode or no table).
_fallback_log: dict[str, tuple[int, int]] = {}


class RateLimitStoreError(Exception):
    """The rate limit counter store could not be reached."""


def _hash_key() -> bytes:
    return (get_settings().rate_limit_hash_key or _FALLBACK_HASH_KEY).encode("utf-8")


def stable_digest(value: str) -> str:
    """Keyed, process-independent digest used for rate-limit keys and log fields."""
    return hmac.new(_hash_key(), value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _first_forwarded_ip(header_value: str) -> str:
    return header_value.split(",")[0].strip()


def get_client_ip(request: Request) -> str:
    """Return the best available client IP for keying anonymous requests.

    Traffic from the Vercel frontend reaches Lambda through Vercel's rewrite
    proxy, so the TCP peer (`request.client.host`, taken from the Lambda
    request context) is a shared Vercel egress address. Vercel overwrites
    `x-vercel-forwarded-for` with the address it received the request from,
    so a browser cannot spoof it through Vercel. Direct callers of the public
    Function URL can still set that header themselves; closing that gap needs
    the Function URL to be private.

    Requests that did not come through Vercel are keyed by the peer address
    reported by AWS. Generic `X-Forwarded-For` and the user agent are never
    used.
    """
    vercel_forwarded = request.headers.get("x-vercel-forwarded-for", "")
    if vercel_forwarded:
        ip = _first_forwarded_ip(vercel_forwarded)
        if ip:
            return ip

    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def client_ip_hash(request: Request) -> str:
    """Hashed client IP, safe to write to logs."""
    return stable_digest(f"ip:{get_client_ip(request)}")[:16]


def _window_bounds(window_seconds: int, now: float | None = None) -> tuple[int, int]:
    now = time.time() if now is None else now
    window_start = int(now // window_seconds) * window_seconds
    return window_start, window_start + window_seconds


def _get_rate_limit_table():
    settings = get_settings()
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    return dynamodb.Table(settings.debates_table)


def _check_dynamodb_rate(client_key: str, max_requests: int, window_seconds: int) -> bool:
    """Atomically count this request in the current window.

    Returns True if the request is within the limit, False if over it.
    Raises RateLimitStoreError if DynamoDB fails.
    """
    window_start, window_end = _window_bounds(window_seconds)
    try:
        table = _get_rate_limit_table()
        table.update_item(
            Key={"debate_id": f"ratelimit#{client_key}#{window_start}"},
            UpdateExpression="ADD #count :one SET #ttl = :ttl",
            ConditionExpression="attribute_not_exists(#count) OR #count < :limit",
            ExpressionAttributeNames={"#count": "request_count", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":one": 1,
                ":limit": max_requests,
                ":ttl": window_end + 60,  # Auto-cleanup via DynamoDB TTL
            },
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise RateLimitStoreError(type(e).__name__) from e
    except Exception as e:
        raise RateLimitStoreError(type(e).__name__) from e


def _check_memory_rate(client_key: str, max_requests: int, window_seconds: int) -> bool:
    """In-memory fixed-window limiter for local development."""
    window_start, _ = _window_bounds(window_seconds)
    stored_window, count = _fallback_log.get(client_key, (window_start, 0))
    if stored_window != window_start:
        count = 0
    if count >= max_requests:
        return False
    _fallback_log[client_key] = (window_start, count + 1)
    return True


def check_rate_limit(
    request: Request,
    max_requests: int = 5,
    window_seconds: int = 3600,
    endpoint: str = "default",
    identity: str | None = None,
    user: dict | None = None,
) -> None:
    """Raise 429 if the caller is over the limit, 503 if the limit can't be checked.

    `identity` (or the signed-in `user`) keys the limit to an account; otherwise
    the client IP is used.
    """
    settings = get_settings()

    if not settings.rate_limiting_enabled:
        logger.debug("Rate limiting disabled; skipping check for %s", endpoint)
        return

    if request.url.path in EXEMPT_PATHS:
        return

    if not identity and user and user.get("sub"):
        identity = f"user:{user['sub']}"
    subject = identity or f"ip:{get_client_ip(request)}"
    client_key = f"{endpoint}#{stable_digest(subject)}"

    try:
        if settings.debates_table and not settings.debug:
            allowed = _check_dynamodb_rate(client_key, max_requests, window_seconds)
        else:
            allowed = _check_memory_rate(client_key, max_requests, window_seconds)
    except RateLimitStoreError as e:
        logger.error("Rate limit store unavailable for %s: %s", endpoint, e)
        raise HTTPException(
            status_code=503,
            detail="The service is temporarily unavailable. Please try again shortly.",
            headers={"Retry-After": "30"},
        ) from e

    if not allowed:
        _, window_end = _window_bounds(window_seconds)
        retry_after = max(1, window_end - int(time.time()))
        logger.warning("Rate limit exceeded for %s key=%s", endpoint, client_key)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": "Too many requests. Please try again later or sign in for higher limits.",
            },
            headers={"Retry-After": str(retry_after)},
        )
