from app.content_guardrails import build_grounding_profile, validate_generated_text


def _base_user_ctx() -> dict:
    return {
        "path_a": "Stay at my current software job",
        "path_b": "Join an early-stage AI startup for equity",
        "constraints": "I have student loans and no safety net. My family depends on me.",
        "financial_context": "",
        "values": "growth, financial security, impact",
        "writing_samples": "",
    }


def test_guardrails_block_invented_biography_money_location_and_attack_dog_tone():
    profile = build_grounding_profile(_base_user_ctx())
    text = (
        "You think this is safety, but in my sunlit kitchen my daughter laughs while my girlfriend "
        "checks our $95,000 savings in Boston."
    )

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "attack_dog_opener" in codes or "attack_dog_phrase" in codes
    assert "invented_biography" in codes
    assert "invented_money" in codes
    assert "invented_location" in codes


def test_guardrails_allow_grounded_generic_passage():
    profile = build_grounding_profile(_base_user_ctx())
    text = (
        "Three years in, the tradeoff feels real. The path gives me stability, but it also keeps asking "
        "whether I can live with the ceiling that comes with it."
    )

    result = validate_generated_text(text, profile, "round")

    assert result.is_valid


def test_guardrails_block_facade_attack_dog_phrase():
    profile = build_grounding_profile(_base_user_ctx())
    text = "Behind the facade, this choice is still mostly fear dressed up as certainty."

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "attack_dog_opener" in codes or "attack_dog_phrase" in codes


def test_verdict_requires_new_headers_and_rejects_old_sections():
    profile = build_grounding_profile(_base_user_ctx())
    text = (
        "**Where Stay at my current software job wins:**\n- Stable money.\n\n"
        "**Where Join an early-stage AI startup for equity wins:**\n- Higher upside.\n\n"
        "**The question you should actually be asking:**\nWhat kind of life do you want?\n\n"
        "Deathbed: a blurry image.\n"
    )

    result = validate_generated_text(
        text,
        profile,
        "verdict",
        path_a="Stay at my current software job",
        path_b="Join an early-stage AI startup for equity",
    )
    codes = {violation.code for violation in result.violations}

    assert "missing_verdict_header" in codes
    assert "old_verdict_header" in codes
    assert "deathbed_imagery" in codes
