"""Rate limiter: stable keys, atomic counting, fail-closed with 503, health exempt."""

import hashlib
import hmac

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import Settings
from app.security import rate_limiter as rl


def _settings(**overrides) -> Settings:
    values = {
        "rate_limiting_enabled": True,
        "debates_table": "diverge-debates",
        "debug": False,
        "rate_limit_hash_key": "test-key",
    }
    values.update(overrides)
    return Settings(**values)


def _request(path="/api/debate/start", client_ip="203.0.113.10", headers=None) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({
        "type": "http",
        "method": "POST",
        "path": path,
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_ip, 443),
    })


class FakeTable:
    """Minimal DynamoDB table honouring the limiter's conditional ADD."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.calls: list[dict] = []

    def update_item(self, **kwargs):
        self.calls.append(kwargs)
        key = kwargs["Key"]["debate_id"]
        limit = kwargs["ExpressionAttributeValues"][":limit"]
        item = self.items.setdefault(key, {})
        count = item.get("request_count")
        if count is not None and not count < limit:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "failed"}},
                "UpdateItem",
            )
        item["request_count"] = (count or 0) + 1
        item["ttl"] = kwargs["ExpressionAttributeValues"][":ttl"]
        return {}


@pytest.fixture
def fake_table(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(rl, "get_settings", lambda: _settings())
    monkeypatch.setattr(rl, "_get_rate_limit_table", lambda: table)
    return table


def test_digest_is_stable_keyed_hmac(monkeypatch):
    monkeypatch.setattr(rl, "get_settings", lambda: _settings())
    expected = hmac.new(b"test-key", b"ip:1.2.3.4", hashlib.sha256).hexdigest()[:32]
    assert rl.stable_digest("ip:1.2.3.4") == expected
    assert rl.stable_digest("ip:1.2.3.4") == rl.stable_digest("ip:1.2.3.4")


def test_digest_falls_back_to_constant_key(monkeypatch):
    monkeypatch.setattr(rl, "get_settings", lambda: _settings(rate_limit_hash_key=""))
    expected = hmac.new(b"diverge-rate-limit-v1", b"x", hashlib.sha256).hexdigest()[:32]
    assert rl.stable_digest("x") == expected


def test_client_ip_prefers_vercel_header_and_ignores_xff():
    request = _request(
        client_ip="76.76.21.21",
        headers={
            "x-vercel-forwarded-for": "198.51.100.7, 76.76.21.21",
            "x-forwarded-for": "10.9.9.9",
        },
    )
    assert rl.get_client_ip(request) == "198.51.100.7"


def test_client_ip_uses_peer_without_vercel_header():
    request = _request(client_ip="198.51.100.8", headers={"x-forwarded-for": "10.9.9.9"})
    assert rl.get_client_ip(request) == "198.51.100.8"


def test_user_agent_rotation_does_not_reset_the_limit(fake_table):
    for i in range(2):
        rl.check_rate_limit(_request(headers={"user-agent": f"agent-{i}"}), max_requests=2, window_seconds=600, endpoint="debate")
    with pytest.raises(HTTPException) as exc:
        rl.check_rate_limit(_request(headers={"user-agent": "agent-new"}), max_requests=2, window_seconds=600, endpoint="debate")
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) >= 1


def test_signed_in_users_are_keyed_by_sub(fake_table):
    user = {"sub": "user-123"}
    rl.check_rate_limit(_request(client_ip="198.51.100.1"), max_requests=2, window_seconds=600, endpoint="feedback", user=user)
    rl.check_rate_limit(_request(client_ip="198.51.100.2"), max_requests=2, window_seconds=600, endpoint="feedback", user=user)
    with pytest.raises(HTTPException) as exc:
        rl.check_rate_limit(_request(client_ip="198.51.100.3"), max_requests=2, window_seconds=600, endpoint="feedback", user=user)
    assert exc.value.status_code == 429

    # A different account behind the same IP has its own budget.
    rl.check_rate_limit(_request(client_ip="198.51.100.3"), max_requests=2, window_seconds=600, endpoint="feedback", user={"sub": "user-456"})


def test_counter_keys_never_contain_raw_ip_or_sub(fake_table):
    rl.check_rate_limit(_request(client_ip="198.51.100.77"), max_requests=5, endpoint="debate")
    rl.check_rate_limit(_request(), max_requests=5, endpoint="debate", identity="user:abc-sub")
    for key in fake_table.items:
        assert "198.51.100.77" not in key
        assert "abc-sub" not in key
        assert key.startswith("ratelimit#debate#")


def test_update_item_is_one_atomic_conditional_write(monkeypatch):
    monkeypatch.setattr(rl, "get_settings", lambda: _settings())
    monkeypatch.setattr(rl, "_window_bounds", lambda window_seconds, now=None: (7200, 7800))
    table = boto3.resource(
        "dynamodb", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x",
    ).Table("diverge-debates")
    monkeypatch.setattr(rl, "_get_rate_limit_table", lambda: table)
    subject_key = f"debate#{rl.stable_digest('ip:203.0.113.10')}"

    with Stubber(table.meta.client) as stubber:
        stubber.add_response(
            "update_item",
            {},
            {
                "TableName": "diverge-debates",
                "Key": {"debate_id": f"ratelimit#{subject_key}#7200"},
                "UpdateExpression": "ADD #count :one SET #ttl = :ttl",
                "ConditionExpression": "attribute_not_exists(#count) OR #count < :limit",
                "ExpressionAttributeNames": {"#count": "request_count", "#ttl": "ttl"},
                "ExpressionAttributeValues": {":one": 1, ":limit": 2, ":ttl": 7860},
            },
        )
        stubber.add_client_error("update_item", service_error_code="ConditionalCheckFailedException")

        rl.check_rate_limit(_request(), max_requests=2, window_seconds=600, endpoint="debate")
        with pytest.raises(HTTPException) as exc:
            rl.check_rate_limit(_request(), max_requests=2, window_seconds=600, endpoint="debate")
        assert exc.value.status_code == 429
        stubber.assert_no_pending_responses()


def test_store_error_returns_503_not_429(monkeypatch):
    monkeypatch.setattr(rl, "get_settings", lambda: _settings())
    table = boto3.resource(
        "dynamodb", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x",
    ).Table("diverge-debates")
    monkeypatch.setattr(rl, "_get_rate_limit_table", lambda: table)

    with Stubber(table.meta.client) as stubber:
        stubber.add_client_error("update_item", service_error_code="ProvisionedThroughputExceededException")
        with pytest.raises(HTTPException) as exc:
            rl.check_rate_limit(_request(), max_requests=2, endpoint="debate")
    assert exc.value.status_code == 503


def test_unexpected_store_failure_returns_503(monkeypatch):
    monkeypatch.setattr(rl, "get_settings", lambda: _settings())

    def broken_table():
        raise RuntimeError("no credentials")

    monkeypatch.setattr(rl, "_get_rate_limit_table", broken_table)
    with pytest.raises(HTTPException) as exc:
        rl.check_rate_limit(_request(), max_requests=2, endpoint="debate")
    assert exc.value.status_code == 503


def test_health_path_is_never_limited(monkeypatch):
    monkeypatch.setattr(rl, "get_settings", lambda: _settings())

    def broken_table():
        raise AssertionError("health must not touch the limiter store")

    monkeypatch.setattr(rl, "_get_rate_limit_table", broken_table)
    for _ in range(5):
        rl.check_rate_limit(_request(path="/api/health"), max_requests=1, endpoint="health")


def test_health_route_does_not_call_rate_limiter(monkeypatch):
    from app.main import create_app
    from app.routes import general

    def fail(*args, **kwargs):
        raise AssertionError("health route must not be rate limited")

    class FakeClient:
        def describe_table(self, **kwargs):
            return {}

    monkeypatch.setattr(general, "check_rate_limit", fail)
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: FakeClient())
    response = TestClient(create_app()).get("/api/health")
    assert response.status_code == 200


def test_memory_limiter_resets_each_window(monkeypatch):
    monkeypatch.setattr(rl, "get_settings", lambda: _settings(debug=True))
    rl._fallback_log.clear()
    monkeypatch.setattr(rl, "_window_bounds", lambda window_seconds, now=None: (0, 600))
    rl.check_rate_limit(_request(), max_requests=1, window_seconds=600, endpoint="local")
    with pytest.raises(HTTPException):
        rl.check_rate_limit(_request(), max_requests=1, window_seconds=600, endpoint="local")
    monkeypatch.setattr(rl, "_window_bounds", lambda window_seconds, now=None: (600, 1200))
    rl.check_rate_limit(_request(), max_requests=1, window_seconds=600, endpoint="local")
