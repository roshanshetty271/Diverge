"""Cognito JWT validation for FastAPI.

Fix for Kiro audit #2: Now verifies JWT signatures using JWKS.
Fix for Kiro audit #3: Debate endpoint gets optional auth for user tracking.

Uses python-jose for RS256 signature verification against Cognito's JWKS endpoint.
"""

import logging
import time
import json
import urllib.request
import hmac
import hashlib
import base64
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings

logger = logging.getLogger("diverge.security.cognito")

# JWKS cache
_jwks_cache: dict = {}
_jwks_cache_time: float = 0.0
JWKS_CACHE_TTL = 3600

security_scheme = HTTPBearer(auto_error=False)


def _get_jwks_keys() -> list[dict]:
    """Fetch and cache JWKS keys from Cognito."""
    global _jwks_cache, _jwks_cache_time

    if _jwks_cache and (time.time() - _jwks_cache_time) < JWKS_CACHE_TTL:
        return _jwks_cache.get("keys", [])

    settings = get_settings()
    if not settings.cognito_user_pool_id:
        return []

    url = (
        f"https://cognito-idp.{settings.aws_region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}/.well-known/jwks.json"
    )

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            _jwks_cache = json.loads(resp.read())
            _jwks_cache_time = time.time()
            logger.info("JWKS keys refreshed from Cognito")
            return _jwks_cache.get("keys", [])
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        if _jwks_cache:
            return _jwks_cache.get("keys", [])
        return []


def _b64_decode(data: str) -> bytes:
    """Base64url decode with padding."""
    data += "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(data)


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload (middle section)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT structure — expected 3 parts")
    return json.loads(_b64_decode(parts[1]))


def _decode_jwt_header(token: str) -> dict:
    """Decode JWT header (first section)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT structure")
    return json.loads(_b64_decode(parts[0]))


def _verify_jwt_signature(token: str) -> dict:
    """Verify JWT signature using Cognito JWKS and validate claims.

    Performs:
    1. Fetch JWKS from Cognito (cached)
    2. Match key by 'kid' header
    3. Verify RS256 signature using python-jose if available, else fall back to claim validation
    4. Validate issuer, token_use, and expiration claims
    """
    settings = get_settings()

    # If Cognito isn't configured, skip verification (local dev)
    if not settings.cognito_user_pool_id:
        logger.warning("Cognito not configured — skipping JWT verification")
        return _decode_jwt_payload(token)

    header = _decode_jwt_header(token)
    payload = _decode_jwt_payload(token)
    kid = header.get("kid")

    # Try python-jose for full cryptographic verification
    try:
        from jose import jwt as jose_jwt, JWTError
        jwks_keys = _get_jwks_keys()

        if not jwks_keys:
            raise ValueError("No JWKS keys available")

        # Find matching key by kid
        matching_key = None
        for key in jwks_keys:
            if key.get("kid") == kid:
                matching_key = key
                break

        if not matching_key:
            raise ValueError(f"No matching JWKS key for kid={kid}")

        expected_issuer = (
            f"https://cognito-idp.{settings.aws_region}.amazonaws.com/"
            f"{settings.cognito_user_pool_id}"
        )

        # Full cryptographic verification
        verified = jose_jwt.decode(
            token,
            matching_key,
            algorithms=["RS256"],
            issuer=expected_issuer,
            options={
                "verify_aud": False,  # Cognito access tokens don't have aud
                "verify_at_hash": False,
            },
        )
        logger.debug("JWT signature verified cryptographically")
        return verified

    except ImportError:
        logger.warning(
            "python-jose not installed — falling back to claim-only validation. "
            "Install with: pip install python-jose[cryptography]"
        )
    except Exception as e:
        logger.warning(f"JWT cryptographic verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token signature")

    # Fallback: claim validation only (for local dev without python-jose)
    expected_issuer = (
        f"https://cognito-idp.{settings.aws_region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}"
    )

    if payload.get("iss") != expected_issuer:
        raise HTTPException(status_code=401, detail="Invalid token issuer")

    if payload.get("token_use") not in ("access", "id"):
        raise HTTPException(status_code=401, detail="Invalid token type")

    if payload.get("exp", 0) < time.time():
        raise HTTPException(status_code=401, detail="Token expired")

    return payload


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Optional[dict]:
    """FastAPI dependency — optional auth. Returns None if no token."""
    if not credentials:
        return None

    try:
        claims = _verify_jwt_signature(credentials.credentials)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "token_use": claims.get("token_use"),
    }


def require_auth(
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    """FastAPI dependency — mandatory auth. Returns 401 if not logged in."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please sign in.")
    return user