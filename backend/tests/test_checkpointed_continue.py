"""Checkpointed continue: duplicate requests must not run or overwrite a round twice."""

import copy

import pytest
from botocore.exceptions import ClientError

from app import orchestrator_checkpointed as oc
from app.db import dynamodb
from app.schemas import RoundResult

DEBATE_ID = "debate-1"


class FakeSessionTable:
    """In-memory table supporting the conditional put used for sessions."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.puts = 0

    def get_item(self, Key):
        item = self.items.get(Key["debate_id"])
        return {"Item": copy.deepcopy(item)} if item else {}

    def put_item(self, Item, ConditionExpression=None, ExpressionAttributeValues=None):
        existing = self.items.get(Item["debate_id"])
        if ConditionExpression == "current_round_index = :expected":
            expected = ExpressionAttributeValues[":expected"]
            if not existing or existing.get("current_round_index") != expected:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "conflict"}},
                    "PutItem",
                )
        elif ConditionExpression is not None:
            raise AssertionError(f"unexpected condition {ConditionExpression}")
        self.puts += 1
        self.items[Item["debate_id"]] = copy.deepcopy(Item)
        return {}


def _round(number: int, text: str) -> RoundResult:
    return RoundResult(
        round_number=number,
        round_name=f"Round {number}",
        round_title=f"Title {number}",
        alpha=f"alpha {text}",
        beta=f"beta {text}",
        status="completed",
    )


def _session(current_round_index: int, status: str = "paused") -> dict:
    return {
        "debate_id": DEBATE_ID,
        "user_id": "anonymous",
        "session_type": "checkpointed",
        "status": status,
        "current_round_index": current_round_index,
        "input": {"path_a": "Stay at my job", "path_b": "Start the company", "debate_id": DEBATE_ID},
        "transcript": [_round(i + 1, f"stored {i + 1}").model_dump() for i in range(current_round_index)],
        "metrics": [None] * current_round_index,
        "debate_summary": "",
        "prev_beta": None,
        "category": "general",
        "total_rounds": 5,
    }


@pytest.fixture
def table(monkeypatch):
    fake = FakeSessionTable()
    monkeypatch.setattr(dynamodb, "_get_table", lambda name: fake)
    monkeypatch.setattr(oc, "_persist_to_agentcore_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(oc, "_build_partial_verdict", lambda *args, **kwargs: "The verdict.")
    monkeypatch.setattr(oc, "_get_resources", lambda ctx: [])
    monkeypatch.setattr(oc, "_generate_structured_timeline", lambda *args, **kwargs: None)
    return fake


def _install_round(monkeypatch, texts: list[str], on_first=None):
    """Fake _run_round / _stream_single_round that hand out `texts` in call order."""
    calls = {"count": 0}

    def next_result(round_num: int) -> RoundResult:
        index = calls["count"]
        calls["count"] += 1
        if index == 0 and on_first:
            on_first()
        return _round(round_num + 1, texts[index])

    def fake_run_round(round_info, user_ctx, prev_beta, round_num, *args, **kwargs):
        return next_result(round_num)

    def fake_stream_single_round(*, round_index, round_info, debate_summary, **kwargs):
        yield {"type": "round_start", "round": round_index + 1}
        result = next_result(round_index)
        yield {"type": "round_complete", "round": round_index + 1, "data": result.model_dump()}
        return result, debate_summary

    monkeypatch.setattr(oc, "_run_round", fake_run_round)
    monkeypatch.setattr(oc, "_stream_single_round", fake_stream_single_round)
    return calls


def test_concurrent_duplicate_continue_returns_the_round_that_won(monkeypatch, table):
    table.items[DEBATE_ID] = _session(1)
    nested = {}

    def duplicate_click_lands_first():
        nested["response"] = oc.continue_checkpointed_debate(DEBATE_ID)

    _install_round(monkeypatch, ["slow request", "fast duplicate"], on_first=duplicate_click_lands_first)

    response = oc.continue_checkpointed_debate(DEBATE_ID)

    stored = table.items[DEBATE_ID]
    assert stored["current_round_index"] == 2
    assert stored["transcript"][1]["alpha"] == "alpha fast duplicate"
    # The slower request did not overwrite the stored round and reports the winner.
    assert response.transcript[1].alpha == "alpha fast duplicate"
    assert nested["response"].transcript[1].alpha == "alpha fast duplicate"
    assert len(response.transcript) == 2


def test_repeat_with_same_round_number_does_not_run_a_new_round(monkeypatch, table):
    table.items[DEBATE_ID] = _session(2)
    calls = _install_round(monkeypatch, ["should not run"])

    response = oc.continue_checkpointed_debate(DEBATE_ID, round_number=2)

    assert calls["count"] == 0
    assert response.transcript[1].alpha == "alpha stored 2"
    assert response.next_round_number == 3
    assert table.puts == 0


def test_round_number_ahead_of_session_is_rejected(monkeypatch, table):
    table.items[DEBATE_ID] = _session(1)
    _install_round(monkeypatch, ["x"])
    with pytest.raises(ValueError):
        oc.continue_checkpointed_debate(DEBATE_ID, round_number=4)


def test_streaming_duplicate_replays_the_stored_round(monkeypatch, table):
    table.items[DEBATE_ID] = _session(1)
    nested = {}

    def duplicate_click_lands_first():
        nested["events"] = list(oc.continue_checkpointed_streaming(DEBATE_ID))

    _install_round(monkeypatch, ["slow stream", "fast stream"], on_first=duplicate_click_lands_first)

    events = list(oc.continue_checkpointed_streaming(DEBATE_ID))

    completes = [e for e in events if e["type"] == "round_complete"]
    assert len(completes) == 1
    assert completes[0]["data"]["alpha"] == "alpha fast stream"
    assert table.items[DEBATE_ID]["transcript"][1]["alpha"] == "alpha fast stream"
    updates = [e for e in events if e["type"] == "session_update"]
    assert updates[-1]["status"] == "paused"
    assert updates[-1]["next_round_number"] == 3


def test_streaming_round_complete_is_sent_only_after_the_save(monkeypatch, table):
    table.items[DEBATE_ID] = _session(1)
    _install_round(monkeypatch, ["only"])
    seen_index_at_complete = []

    for event in oc.continue_checkpointed_streaming(DEBATE_ID):
        if event["type"] == "round_complete":
            seen_index_at_complete.append(table.items[DEBATE_ID]["current_round_index"])

    assert seen_index_at_complete == [2]


def test_streaming_repeat_with_round_number_replays_without_running(monkeypatch, table):
    table.items[DEBATE_ID] = _session(3)
    calls = _install_round(monkeypatch, ["should not run"])

    events = list(oc.continue_checkpointed_streaming(DEBATE_ID, round_number=3))

    assert calls["count"] == 0
    assert [e["type"] for e in events] == ["round_complete", "session_update"]
    assert events[0]["data"]["alpha"] == "alpha stored 3"


def test_streaming_on_completed_session_replays_instead_of_erroring(monkeypatch, table):
    session = _session(5, status="complete")
    session["verdict"] = "Done."
    table.items[DEBATE_ID] = session
    _install_round(monkeypatch, ["should not run"])

    events = list(oc.continue_checkpointed_streaming(DEBATE_ID, round_number=5))

    assert [e["type"] for e in events] == ["round_complete", "session_update", "complete"]
    assert events[-1]["verdict"] == "Done."
