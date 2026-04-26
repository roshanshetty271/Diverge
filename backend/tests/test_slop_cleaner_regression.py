"""Regression tests for the _clean_ai_slop post-processor.

After Tier 1.3 the 'navigate' pattern is NO LONGER handled here (it was promoted to the
validator so a full rewrite is forced instead of orphaning a noun). These tests lock that
move in, and also sanity-check that the remaining slop patterns still work.
"""

from __future__ import annotations

from app.orchestrator import _clean_ai_slop


def test_clean_ai_slop_no_longer_touches_navigate_verb():
    """navigate must survive the slop pass unchanged. The validator now forces a rewrite instead."""
    text = "I navigated a series of failures that almost broke me."

    cleaned = _clean_ai_slop(text)

    assert "navigated" in cleaned, (
        f"_clean_ai_slop unexpectedly rewrote 'navigate'. Got: {cleaned!r}"
    )


def test_clean_ai_slop_still_strips_let_that_sink_in():
    text = "The cost is real. Let that sink in. You were warned."

    cleaned = _clean_ai_slop(text)

    assert "let that sink in" not in cleaned.lower()


def test_clean_ai_slop_still_rewrites_lean_into():
    text = "You leaned into the chaos and pretended it was a plan."

    cleaned = _clean_ai_slop(text)

    assert "leaned into" not in cleaned.lower()
    assert "embraced" in cleaned.lower()


def test_clean_ai_slop_still_strips_slop_opener():
    text = "Here's the thing: you already knew what you wanted."

    cleaned = _clean_ai_slop(text)

    assert not cleaned.lower().startswith("here's the thing"), (
        f"Slop opener was not stripped: {cleaned!r}"
    )
