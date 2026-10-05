"""Public shares store and serve only what the shared page renders."""

from fastapi.testclient import TestClient

from app.db import dynamodb
from app.main import create_app

PRIVATE_INPUT = {
    "path_a": "Stay in Boston",
    "path_b": "Move to Austin",
    "user_name": "Maya",
    "age": 31,
    "financial_context": "Savings: $42K, debt: $18K",
    "values": "family, growth",
    "constraints": "My mother is ill",
    "writing_samples": "hey it's me, private texts",
}

ROUND = {
    "round_number": 1,
    "round_name": "The Ripple",
    "round_title": "Year 1: The Ripple",
    "alpha": "Alpha text",
    "beta": "Beta text",
    "status": "completed",
    "sentiment": {"path_a": {"positive": 0.5}},
    "metrics": {"path_a": {"happiness_estimate": 6}, "path_b": {"happiness_estimate": 7}},
}

METRICS = [{"path_a": {"happiness_estimate": 6, "key_insight": "x"}, "path_b": {"happiness_estimate": 7, "key_insight": "y"}}]

PRIVATE_STRINGS = ("Maya", "Savings", "My mother is ill", "private texts", "family, growth")


class FakeTable:
    def __init__(self, items=None):
        self.items = dict(items or {})

    def put_item(self, Item, **kwargs):
        self.items[Item["debate_id"]] = Item
        return {}

    def get_item(self, Key):
        item = self.items.get(Key["debate_id"])
        return {"Item": item} if item else {}


def _assert_public_only(payload: dict):
    flat = repr(payload)
    for private in PRIVATE_STRINGS:
        assert private not in flat
    assert "input" not in payload
    assert "writing_samples" not in flat


def test_new_share_stores_only_public_fields(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(dynamodb, "_get_table", lambda name: table)

    dynamodb.save_shared_debate(
        "abc123",
        {"verdict": "Go.", "transcript": [ROUND], "metrics": METRICS, "completed_rounds": 1, "total_rounds": 5, "resources": [{"title": "Book"}]},
        PRIVATE_INPUT,
    )

    stored = table.items["shared#abc123"]
    _assert_public_only(stored)
    assert stored["path_a"] == "Stay in Boston"
    assert stored["transcript"][0] == {k: ROUND[k] for k in ("round_number", "round_name", "round_title", "alpha", "beta", "status")}
    assert stored["is_public"] is True
    assert "resources" not in stored


def test_old_share_with_full_input_still_renders_without_it(monkeypatch):
    legacy_item = {
        "debate_id": "shared#old1",
        "user_id": "public",
        "share_id": "old1",
        "is_public": True,
        "path_a": "Stay in Boston",
        "path_b": "Move to Austin",
        "verdict": "Go.",
        "transcript": [ROUND],
        "metrics": METRICS,
        "resources": [],
        "completed_rounds": 1,
        "total_rounds": 5,
        "input": PRIVATE_INPUT,
        "created_at": "2026-05-01T00:00:00+00:00",
    }
    monkeypatch.setattr(dynamodb, "_get_table", lambda name: FakeTable({"shared#old1": legacy_item}))

    response = TestClient(create_app()).get("/api/debate/shared/old1")

    assert response.status_code == 200
    body = response.json()
    _assert_public_only(body)
    assert body["path_a"] == "Stay in Boston"
    assert body["path_b"] == "Move to Austin"
    assert body["transcript"][0]["alpha"] == "Alpha text"
    assert body["metrics"][0]["path_b"]["happiness_estimate"] == 7
    assert body["verdict"] == "Go."


def test_old_share_without_top_level_paths_falls_back_to_input(monkeypatch):
    legacy_item = {"debate_id": "shared#old2", "share_id": "old2", "is_public": True, "input": PRIVATE_INPUT, "transcript": []}
    monkeypatch.setattr(dynamodb, "_get_table", lambda name: FakeTable({"shared#old2": legacy_item}))

    body = dynamodb.get_shared_debate("old2")

    assert body["path_a"] == "Stay in Boston"
    _assert_public_only(body)


def test_share_route_round_trip(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(dynamodb, "_get_table", lambda name: table)
    http = TestClient(create_app())

    created = http.post("/api/debate/share", json={
        "debate_data": {"verdict": "Go.", "transcript": [ROUND], "metrics": METRICS},
        "input_data": {"path_a": "Stay in Boston", "path_b": "Move to Austin"},
    })
    assert created.status_code == 200
    share_id = created.json()["share_id"]

    body = http.get(f"/api/debate/shared/{share_id}").json()
    assert body["transcript"][0]["beta"] == "Beta text"
    assert body["path_b"] == "Move to Austin"
