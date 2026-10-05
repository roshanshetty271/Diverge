"""Cognito token checks, debate ownership on interject/feedback, and safe saves."""

import time

import pytest
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwk, jwt

from app.config import Settings
from app.db import dynamodb
from app.main import create_app
from app.routes import debate as debate_routes
from app.routes import general as general_routes
from app.security import cognito

POOL_ID = "us-east-1_TestPool"
CLIENT_ID = "app-client-123"
ISSUER = f"https://cognito-idp.us-east-1.amazonaws.com/{POOL_ID}"


@pytest.fixture(scope="module")
def signing_key():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    public_jwk = jwk.construct(public_pem, "RS256").to_dict()
    public_jwk["kid"] = "test-kid"
    public_jwk = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in public_jwk.items()}
    return private_pem, public_jwk


@pytest.fixture
def cognito_env(monkeypatch, signing_key):
    _, public_jwk = signing_key
    settings = Settings(cognito_user_pool_id=POOL_ID, cognito_client_id=CLIENT_ID, aws_region="us-east-1")
    monkeypatch.setattr(cognito, "get_settings", lambda: settings)
    monkeypatch.setattr(cognito, "_get_jwks_keys", lambda: [public_jwk])
    return settings


def _token(signing_key, **claims) -> str:
    private_pem, _ = signing_key
    payload = {
        "iss": ISSUER,
        "sub": "user-1",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    payload.update(claims)
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": "test-kid"})


def test_access_token_for_this_client_is_accepted(cognito_env, signing_key):
    claims = cognito._verify_jwt_signature(_token(signing_key, token_use="access", client_id=CLIENT_ID))
    assert claims["sub"] == "user-1"


def test_access_token_for_another_client_is_rejected(cognito_env, signing_key):
    with pytest.raises(HTTPException) as exc:
        cognito._verify_jwt_signature(_token(signing_key, token_use="access", client_id="other-client"))
    assert exc.value.status_code == 401


def test_id_token_checks_audience(cognito_env, signing_key):
    claims = cognito._verify_jwt_signature(_token(signing_key, token_use="id", aud=CLIENT_ID))
    assert claims["token_use"] == "id"
    with pytest.raises(HTTPException) as exc:
        cognito._verify_jwt_signature(_token(signing_key, token_use="id", aud="other-client"))
    assert exc.value.status_code == 401


def test_id_token_cannot_pass_with_client_id_claim_only(cognito_env, signing_key):
    with pytest.raises(HTTPException):
        cognito._verify_jwt_signature(_token(signing_key, token_use="id", client_id=CLIENT_ID))


@pytest.mark.parametrize("token_use", ["refresh", "", None])
def test_other_token_use_is_rejected(cognito_env, signing_key, token_use):
    claims = {"client_id": CLIENT_ID, "aud": CLIENT_ID}
    if token_use is not None:
        claims["token_use"] = token_use
    with pytest.raises(HTTPException) as exc:
        cognito._verify_jwt_signature(_token(signing_key, **claims))
    assert exc.value.status_code == 401


def test_missing_client_id_config_skips_only_the_client_check(monkeypatch, signing_key, caplog):
    _, public_jwk = signing_key
    settings = Settings(cognito_user_pool_id=POOL_ID, cognito_client_id="", aws_region="us-east-1")
    monkeypatch.setattr(cognito, "get_settings", lambda: settings)
    monkeypatch.setattr(cognito, "_get_jwks_keys", lambda: [public_jwk])
    monkeypatch.setattr(cognito, "_missing_client_id_warned", False)

    claims = cognito._verify_jwt_signature(_token(signing_key, token_use="access", client_id="any-client"))
    assert claims["sub"] == "user-1"
    assert "DIVERGE_COGNITO_CLIENT_ID is not set" in caplog.text

    with pytest.raises(HTTPException):
        cognito._verify_jwt_signature(_token(signing_key, token_use="refresh", client_id="any-client"))


def test_wrong_issuer_is_rejected(cognito_env, signing_key):
    with pytest.raises(HTTPException):
        cognito._verify_jwt_signature(
            _token(signing_key, token_use="access", client_id=CLIENT_ID, iss="https://evil.example.com")
        )


# ── Ownership on /interject and /feedback ─────────────────────────────


@pytest.fixture
def client():
    app = create_app()
    yield app, TestClient(app)
    app.dependency_overrides.clear()


def _as_user(app, sub):
    app.dependency_overrides[cognito.get_current_user] = (lambda: {"sub": sub}) if sub else (lambda: None)


def test_interject_on_another_users_debate_is_forbidden(client, monkeypatch):
    app, http = client
    stored = []
    monkeypatch.setattr(debate_routes, "get_debate_owner", lambda debate_id: "owner-sub")
    monkeypatch.setattr(debate_routes, "set_interjection", lambda debate_id, text: stored.append(text))

    _as_user(app, None)
    assert http.post("/api/debate/interject", json={"debate_id": "d1", "text": "What about rent?"}).status_code == 403
    _as_user(app, "someone-else")
    assert http.post("/api/debate/interject", json={"debate_id": "d1", "text": "What about rent?"}).status_code == 403
    _as_user(app, "owner-sub")
    assert http.post("/api/debate/interject", json={"debate_id": "d1", "text": "What about rent?"}).status_code == 200
    assert stored == ["What about rent?"]


def test_interject_on_anonymous_or_unsaved_debate_is_allowed(client, monkeypatch):
    app, http = client
    monkeypatch.setattr(debate_routes, "set_interjection", lambda debate_id, text: None)
    _as_user(app, None)
    for owner in ("anonymous", None):
        monkeypatch.setattr(debate_routes, "get_debate_owner", lambda debate_id, owner=owner: owner)
        assert http.post("/api/debate/interject", json={"debate_id": "d1", "text": "One more thing"}).status_code == 200


def test_interject_owner_lookup_failure_fails_closed(client, monkeypatch):
    app, http = client

    def broken(debate_id):
        raise RuntimeError("dynamodb down")

    monkeypatch.setattr(debate_routes, "get_debate_owner", broken)
    _as_user(app, None)
    assert http.post("/api/debate/interject", json={"debate_id": "d1", "text": "hi"}).status_code == 503


def test_feedback_requires_matching_owner(client, monkeypatch):
    app, http = client
    saved = []
    monkeypatch.setattr(general_routes, "get_debate_owner", lambda debate_id: "owner-sub")
    monkeypatch.setattr(general_routes, "save_debate_feedback", lambda *args: saved.append(args) or True)

    _as_user(app, None)
    assert http.post("/api/debate/d1/feedback", json={"rating": "shifted", "quote": ""}).status_code == 403
    _as_user(app, "intruder")
    assert http.post("/api/debate/d1/feedback", json={"rating": "shifted", "quote": ""}).status_code == 403
    assert saved == []
    _as_user(app, "owner-sub")
    response = http.post("/api/debate/d1/feedback", json={"rating": "shifted", "quote": ""})
    assert response.status_code == 200
    assert len(saved) == 1


def test_feedback_on_anonymous_debate_is_allowed(client, monkeypatch):
    app, http = client
    monkeypatch.setattr(general_routes, "get_debate_owner", lambda debate_id: "anonymous")
    monkeypatch.setattr(general_routes, "save_debate_feedback", lambda *args: True)
    _as_user(app, None)
    assert http.post("/api/debate/d1/feedback", json={"rating": "no", "quote": ""}).status_code == 200


def test_shared_items_cannot_receive_feedback(client, monkeypatch):
    app, http = client
    monkeypatch.setattr(general_routes, "get_debate_owner", lambda debate_id: "public")
    monkeypatch.setattr(general_routes, "save_debate_feedback", lambda *args: True)
    _as_user(app, None)
    assert http.post("/api/debate/shared%23abc/feedback", json={"rating": "no", "quote": ""}).status_code == 403


# ── save_debate is a conditional put ──────────────────────────────────


class RecordingTable:
    def __init__(self, existing_owner=None, exists=False):
        self.existing_owner = existing_owner
        self.exists = exists
        self.put_calls = []

    def put_item(self, **kwargs):
        self.put_calls.append(kwargs)
        values = kwargs["ExpressionAttributeValues"]
        allowed = (not self.exists) or self.existing_owner in (values[":uid"], values[":anonymous"])
        if not allowed:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "no"}}, "PutItem",
            )
        return {}


def test_save_debate_put_is_conditional(monkeypatch):
    table = RecordingTable()
    monkeypatch.setattr(dynamodb, "_get_table", lambda name: table)
    dynamodb.save_debate("d1", "user-1", {"path_a": "a", "path_b": "b"}, {})
    call = table.put_calls[0]
    assert call["ConditionExpression"] == (
        "attribute_not_exists(debate_id) OR user_id = :uid OR user_id = :anonymous"
    )
    assert call["ExpressionAttributeValues"] == {":uid": "user-1", ":anonymous": "anonymous"}


@pytest.mark.parametrize("owner", ["user-1", "anonymous"])
def test_save_debate_can_replace_own_or_anonymous_item(monkeypatch, owner):
    monkeypatch.setattr(dynamodb, "_get_table", lambda name: RecordingTable(existing_owner=owner, exists=True))
    dynamodb.save_debate("d1", "user-1", {}, {})


def test_save_debate_cannot_overwrite_another_users_item(monkeypatch):
    monkeypatch.setattr(dynamodb, "_get_table", lambda name: RecordingTable(existing_owner="victim", exists=True))
    with pytest.raises(dynamodb.DebateOwnershipError):
        dynamodb.save_debate("d1", "attacker", {}, {})


def test_save_route_returns_403_for_another_users_debate(client, monkeypatch):
    app, http = client
    app.dependency_overrides[cognito.require_auth] = lambda: {"sub": "attacker"}

    def refuse(**kwargs):
        raise dynamodb.DebateOwnershipError("d1")

    monkeypatch.setattr(general_routes, "save_debate", refuse)
    response = http.post("/api/debate/save", json={"debate_data": {"debate_id": "d1", "input": {}}})
    assert response.status_code == 403
