"""Cloudflare Turnstile verification for anonymous debate starts."""

import json
import logging
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import HTTPException, Request

from app.config import get_settings

logger = logging.getLogger("diverge.security.turnstile")

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _remote_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return ""


def turnstile_enabled() -> bool:
    return bool(get_settings().turnstile_secret_key)


def verify_turnstile_token(token: str, remote_ip: str = "") -> tuple[bool, str]:
    """Verify a Turnstile token with Cloudflare."""
    settings = get_settings()
    if not settings.turnstile_secret_key:
        return True, ""

    if not token:
        return False, "Please verify you're human before starting the debate."

    payload = {
        "secret": settings.turnstile_secret_key,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        encoded = urlencode(payload).encode("utf-8")
        req = UrlRequest(
            TURNSTILE_VERIFY_URL,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(req, timeout=5) as res:
            body = json.loads(res.read().decode("utf-8"))
    except Exception as e:
        logger.error("Turnstile verification request failed: %s", type(e).__name__)
        return False, "Couldn't verify you're human right now. Please try again."

    if body.get("success") is True:
        return True, ""

    error_codes = body.get("error-codes") or []
    logger.warning("Turnstile verification failed: %s", error_codes)
    return False, "Please verify you're human and try again."


def require_turnstile_for_anonymous_start(request: Request, user: dict | None) -> None:
    """Require a valid Turnstile token only for anonymous starts."""
    if user or not turnstile_enabled():
        return

    token = request.headers.get("x-captcha-token", "").strip()
    ok, message = verify_turnstile_token(token, _remote_ip(request))
    if not ok:
        raise HTTPException(status_code=400, detail=message)
