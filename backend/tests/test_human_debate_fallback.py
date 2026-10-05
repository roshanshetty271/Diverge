from app.content_guardrails import build_grounding_profile, validate_generated_text
from app.orchestrator import _build_round_fallback_text


ROBOTIC_FALLBACK_PHRASES = (
    "right now, living with",
    "this path gives something real",
    "the tradeoff behind this",
    "nothing here is clean",
    "version of life you would have to keep waking up inside",
    "this perspective could not be generated",
)


def _assert_human_safe_fallback(text: str, ctx: dict, category: str) -> None:
    lowered = text.lower()
    for phrase in ROBOTIC_FALLBACK_PHRASES:
        assert phrase not in lowered

    assert 65 <= len(text.split()) <= 120

    profile = build_grounding_profile(ctx, category=category)
    result = validate_generated_text(text, profile, "round")
    assert result.is_valid, [violation.code for violation in result.violations]


def test_startup_round_fallback_sounds_like_future_self_not_template():
    ctx = {
        "path_a": "Stay employed and keep building my idea nights and weekends",
        "path_b": "Quit now and go all-in on the startup",
        "template_id": "startup",
        "user_name": "Ava",
        "age": 29,
        "financial_context": "Current income: $140K/yr. Startup income: $0 for at least 6 months. Savings: $85K. Partner income: $60K/yr.",
        "values": "autonomy, creativity, stability",
        "constraints": "I already have 4 paying customers at $500/mo each.",
    }

    text = _build_round_fallback_text(
        ctx["path_a"],
        "year 2-3",
        "startup",
        user_ctx=ctx,
        other_path=ctx["path_b"],
    )

    _assert_human_safe_fallback(text, ctx, "startup")
    assert text.startswith("Ava, ")
    assert "choosing stay employed" in text.lower()


def test_relationship_round_fallback_handles_interjection_without_robotic_voice():
    ctx = {
        "path_a": "Stay quiet and keep the friendship as it is",
        "path_b": "Tell my best friend I've been in love with her for three years",
        "template_id": "relationship",
        "user_name": "Dev",
        "age": 27,
        "financial_context": "",
        "values": "honesty, connection, self-respect",
        "constraints": "We have been friends since college. She is currently single.",
    }

    text = _build_round_fallback_text(
        ctx["path_b"],
        "year 5",
        "relationship",
        user_ctx=ctx,
        other_path=ctx["path_a"],
        interjection="She just texted me asking to grab dinner alone.",
    )

    _assert_human_safe_fallback(text, ctx, "relationship")
    assert "new detail" in text.lower()


def test_general_family_round_fallback_stays_grounded():
    ctx = {
        "path_a": "Stay home and help run the family restaurant",
        "path_b": "Take the strategy job in Chicago and send money home",
        "template_id": "family",
        "user_name": "Sofia",
        "age": 32,
        "financial_context": "Current income: $42K from family business. New role: $135K/yr. Savings: $14K.",
        "values": "duty, ambition, generational mobility",
        "constraints": "My parents depend on me more than they admit. My younger brother is not ready to step up yet.",
    }

    text = _build_round_fallback_text(
        ctx["path_a"],
        "looking back on all of it",
        "general",
        user_ctx=ctx,
        other_path=ctx["path_b"],
    )

    _assert_human_safe_fallback(text, ctx, "general")
    assert "after all this time" in text.lower()
