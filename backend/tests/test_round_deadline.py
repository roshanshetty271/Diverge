"""Rounds stop starting retries they can't finish, and OpenAI calls have explicit timeouts."""

import pytest

from app import orchestrator as orch
from app.agents.prompts import get_rounds
from app.config import Settings


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(orch.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(orch.time, "sleep", fake.sleep)
    return fake


@pytest.fixture
def settings(monkeypatch):
    s = Settings(round_deadline_seconds=100.0, min_attempt_seconds=30.0, model_provider="openai")
    monkeypatch.setattr(orch, "get_settings", lambda: s)
    return s


def _ctx():
    return {
        "path_a": "Stay at my job",
        "path_b": "Start the company",
        "debate_id": "d1",
        "_category": "general",
        "constraints": "",
        "financial_context": "",
        "values": "",
        "writing_samples": "",
    }


def test_guardrail_rewrite_is_not_started_past_the_deadline(clock, settings, monkeypatch):
    calls = []

    def slow_invalid_generator(rewrite_instruction):
        calls.append(rewrite_instruction)
        clock.now += 80  # the first attempt eats most of the budget
        return "Here's the thing."  # fails validation, would normally trigger a rewrite

    monkeypatch.setattr(orch, "validate_generated_text", lambda *a, **k: type("R", (), {"is_valid": False, "violations": []})())
    monkeypatch.setattr(orch, "format_violation_report", lambda result: "fix it")

    text = orch._generate_with_guardrails(
        user_ctx=_ctx(),
        transcript=[],
        content_kind="round",
        stage_label="round_1.alpha",
        fallback_text="FALLBACK",
        generator=slow_invalid_generator,
        deadline=clock.now + 100,
    )

    assert text == "FALLBACK"
    assert len(calls) == 1


def test_guardrail_rewrites_still_happen_with_time_left(clock, settings, monkeypatch):
    results = iter([False, True])
    monkeypatch.setattr(
        orch, "validate_generated_text",
        lambda *a, **k: type("R", (), {"is_valid": next(results), "violations": []})(),
    )
    monkeypatch.setattr(orch, "format_violation_report", lambda result: "fix it")

    text = orch._generate_with_guardrails(
        user_ctx=_ctx(),
        transcript=[],
        content_kind="round",
        stage_label="round_1.alpha",
        fallback_text="FALLBACK",
        generator=lambda rewrite: "second try" if rewrite else "first try",
        deadline=clock.now + 100,
    )
    assert text == "second try"


class ThrottledAgent:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, prompt):
        ThrottledAgent.calls += 1
        FakeClockRef.clock.now += 75  # each failing call takes 75 s
        raise RuntimeError("ThrottlingException: slow down")


class FakeClockRef:
    clock = None


def test_round_retry_is_skipped_when_it_cannot_finish(clock, settings, monkeypatch):
    FakeClockRef.clock = clock
    ThrottledAgent.calls = 0
    monkeypatch.setattr(orch, "Agent", ThrottledAgent)
    monkeypatch.setattr(orch, "_make_model", lambda **kwargs: None)

    round_info = get_rounds("general")[0]
    alpha, beta = orch._assign_personas("Stay at my job", "Start the company")
    result = orch._run_round(round_info, _ctx(), None, 0, [], "", [], alpha, beta)

    assert result.status == "partial"
    # One 75 s attempt leaves < 30 s of the 100 s budget, so no backoff or retry.
    assert ThrottledAgent.calls == 1
    assert clock.sleeps == []


def test_split_round_skips_retries_past_the_deadline(clock, settings, monkeypatch):
    FakeClockRef.clock = clock
    ThrottledAgent.calls = 0
    monkeypatch.setattr(orch, "Agent", ThrottledAgent)
    monkeypatch.setattr(orch, "_make_model", lambda **kwargs: None)

    round_info = get_rounds("general")[0]
    alpha, beta = orch._assign_personas("Stay at my job", "Start the company")
    phases = list(orch._run_round_split(round_info, _ctx(), None, 0, [], "", [], alpha, beta))

    result = phases[-1][1]
    assert result.status == "partial"
    assert ThrottledAgent.calls == 1
    assert clock.sleeps == []


def test_openai_clients_get_explicit_timeout():
    s = Settings(openai_api_key="sk-test", model_timeout_seconds=42.0, model_max_retries=1)
    assert s.openai_client_args() == {"api_key": "sk-test", "timeout": 42.0, "max_retries": 1}


def test_debate_model_uses_timeout(monkeypatch):
    s = Settings(openai_api_key="sk-test", model_provider="openai", model_timeout_seconds=42.0)
    monkeypatch.setattr(orch, "get_settings", lambda: s)
    model = orch._make_model()
    assert model.client_args["timeout"] == 42.0
    assert model.client_args["max_retries"] == 1


def test_round_retries_while_time_remains(clock, settings, monkeypatch):
    class OnceThrottledAgent:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, prompt):
            OnceThrottledAgent.calls += 1
            clock.now += 10
            raise RuntimeError("ThrottlingException: slow down")

    monkeypatch.setattr(orch, "Agent", OnceThrottledAgent)
    monkeypatch.setattr(orch, "_make_model", lambda **kwargs: None)
    alpha, beta = orch._assign_personas("Stay at my job", "Start the company")
    orch._run_round(get_rounds("general")[0], _ctx(), None, 0, [], "", [], alpha, beta)

    # With 10 s failures there is time for the normal retries and backoff.
    assert OnceThrottledAgent.calls == orch.MAX_RETRIES
    assert len(clock.sleeps) == orch.MAX_RETRIES - 1
