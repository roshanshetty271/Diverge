"""Regression tests for content_guardrails fixes from the 'Fix debate quality bugs' plan.

Locks down:
- Tier 1.1: scrub_repeated_motifs racing_heart regex absorbs optional 'my' (no 'my my').
- Tier 1.2: coffee motif no longer substitutes bare 'coffee' with 'warm drink'.
- Tier 1.3: navigate verb triggers a validator ContentViolation (rewrite forced).
- Tier 2.1: template_opener triggers a validator ContentViolation on first occurrence.
"""

from __future__ import annotations

from app.content_guardrails import (
    MOTIF_REPLACEMENTS,
    ValidationResult,
    ContentViolation,
    build_grounding_profile,
    scrub_repeated_motifs,
    validate_generated_text,
)


def _base_user_ctx() -> dict:
    return {
        "path_a": "Stay at my current software job",
        "path_b": "Join an early-stage AI startup for equity",
        "constraints": "I have student loans and no safety net.",
        "financial_context": "",
        "values": "growth, financial security, impact",
        "writing_samples": "",
    }


# ── Tier 1.1: 'my my chest' duplication ────────────────────────────

def test_scrub_racing_heart_does_not_double_my():
    """After hitting a racing_heart motif and scrubbing, output must not contain 'my my'."""
    input_text = "Three years in, my heart races as I wait for the numbers to finally add up."

    result = ValidationResult(
        violations=[ContentViolation("repeated_motif", 'Reused overplayed motif "racing_heart".')]
    )
    repaired = scrub_repeated_motifs(input_text, result)

    assert "my my" not in repaired.lower(), f"Got duplicated 'my my' in: {repaired!r}"
    assert "heart races" not in repaired, f"Original phrase survived scrub: {repaired!r}"


def test_scrub_racing_heart_still_works_without_preceding_my():
    """A bare 'heart races' without 'my' should still be replaced (the 'my\\s+' prefix is optional)."""
    input_text = "Her heart races every morning before the deploy."

    result = ValidationResult(
        violations=[ContentViolation("repeated_motif", 'Reused overplayed motif "racing_heart".')]
    )
    repaired = scrub_repeated_motifs(input_text, result)

    assert "heart races" not in repaired
    assert "my chest tightens" in repaired


# ── Tier 1.2: no more 'warm drink' substitution ────────────────────

def test_motif_replacements_no_longer_produce_warm_drink():
    """The bare '\\bcoffee\\b -> warm drink' rule has been deleted. The motif is still watched,
    but its scrubber should never emit 'warm drink' for ANY input."""
    for pattern, replacement in MOTIF_REPLACEMENTS["coffee"]:
        assert replacement != "warm drink", (
            f"Found a coffee motif substitution producing 'warm drink': pattern={pattern.pattern!r}"
        )

    result = ValidationResult(
        violations=[ContentViolation("repeated_motif", 'Reused overplayed motif "coffee".')]
    )
    repaired = scrub_repeated_motifs("I grab coffee before every meeting.", result)
    assert "warm drink" not in repaired.lower(), f"Scrub produced 'warm drink': {repaired!r}"


def test_motif_replacements_still_rewrite_coffee_shop_forms():
    """The coffee-shop / coffeehouse / cafe -> 'quiet corner' rules must still work."""
    result = ValidationResult(
        violations=[ContentViolation("repeated_motif", 'Reused overplayed motif "coffee".')]
    )
    for phrase in ("I sit in a coffee shop every morning.", "At the coffeehouse, I think about it.", "I saw her at a cafe."):
        repaired = scrub_repeated_motifs(phrase, result)
        assert "quiet corner" in repaired.lower(), f"Expected 'quiet corner' after scrub of {phrase!r}, got {repaired!r}"


# ── Tier 1.3: navigate verb promoted to validator ──────────────────

def test_navigate_verb_raises_validation_violation_present_tense():
    profile = build_grounding_profile(_base_user_ctx())
    text = "I navigate every meeting like it's a fresh chess match."

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "banned_verb_navigate" in codes


def test_navigate_verb_raises_validation_violation_past_tense():
    profile = build_grounding_profile(_base_user_ctx())
    text = "Over three years, I navigated a series of failures that almost broke me."

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "banned_verb_navigate" in codes


def test_navigate_verb_raises_validation_violation_gerund():
    profile = build_grounding_profile(_base_user_ctx())
    text = "Navigating the complexity of it all is what the job actually is now."

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "banned_verb_navigate" in codes


def test_navigate_verb_does_not_match_unrelated_words():
    """The pattern should not false-positive on words that merely contain 'navig' as a substring.

    'navigator' and 'navigation' are out of scope of the verb form. Keep them allowed so the guardrail
    forces a rewrite only for the tell-tale verb usage.
    """
    profile = build_grounding_profile(_base_user_ctx())
    text = "The navigator in my old car died but I kept the road atlas in the glovebox."

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "banned_verb_navigate" not in codes


# ── Tier 2.1: template_opener raises validator violation ──────────

def test_template_opener_right_now_im_raises_violation():
    profile = build_grounding_profile(_base_user_ctx())
    text = "Right now, I'm in a studio apartment and the rent is about to go up."

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "template_opener" in codes


def test_template_opener_im_sitting_raises_violation():
    profile = build_grounding_profile(_base_user_ctx())
    text = "I'm sitting in the kitchen, rereading the email I almost sent."

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "template_opener" in codes


def test_template_opener_bare_standing_at_raises_violation():
    profile = build_grounding_profile(_base_user_ctx())
    text = "Standing at the window, I thought about taking the offer anyway."

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "template_opener" in codes


def test_template_opener_bare_sitting_in_kitchen_raises_violation():
    profile = build_grounding_profile(_base_user_ctx())
    text = "Sitting in the kitchen, I felt the shift finally land."

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "template_opener" in codes


def test_non_template_opener_does_not_raise_violation():
    """Sentences that start inside a thought or action should not trigger template_opener."""
    profile = build_grounding_profile(_base_user_ctx())
    text = (
        "My chest tightens when the Slack notification lands. "
        "I still don't know whether to answer yes or put it off another week."
    )

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "template_opener" not in codes


def test_template_opener_fires_on_paragraph_break_not_just_string_start():
    """Regression: the model sometimes starts the SECOND paragraph (not the whole response) with
    a template opener like `...\\n\\nRight now, I'm in a conference room...`. The pattern must
    still flag that, so `^` is applied in MULTILINE mode (after any newline).
    """
    profile = build_grounding_profile(_base_user_ctx())
    text = (
        "The decision looms large, threatening not just your ambition but your very sense of self.\n"
        "\n"
        "Right now, I'm in a conference room at my company, the walls lined with familiar charts."
    )

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "template_opener" in codes, (
        "template_opener must match after a paragraph break, not only at absolute string start."
    )


def test_template_opener_fires_on_paragraph_break_sitting_in():
    profile = build_grounding_profile(_base_user_ctx())
    text = (
        "Years later the picture has shifted.\n"
        "\n"
        "Sitting in the kitchen, I notice the silence has changed shape."
    )

    result = validate_generated_text(text, profile, "round")
    codes = {violation.code for violation in result.violations}

    assert "template_opener" in codes
