"""Unit tests for the pre-retrieval grounding pipeline.

Covers:
- `_extract_dollar_figures`: positive and negative parsing cases, period
  inference (explicit suffix vs. sentence-level cadence), label inference
  with sentence boundaries.
- `build_grounding_context`: research is always attempted; runway and Monte
  Carlo fire only when the financial_context yields the right shape of
  figures AND the category permits financial modeling. Malformed input never
  raises.
"""

from __future__ import annotations

import pytest

from app.grounding import (
    ExtractedFigure,
    _extract_dollar_figures,
    _infer_label,
    build_grounding_context,
)


# ── _extract_dollar_figures: positive cases ────────────────────────

def test_extract_basic_thousands():
    figs = _extract_dollar_figures("Savings $15K.")
    assert len(figs) == 1
    assert figs[0].amount == 15_000.0
    assert figs[0].label == "savings"


def test_extract_comma_separated_thousands():
    figs = _extract_dollar_figures("Outstanding student debt: $22,400 remaining.")
    assert len(figs) == 1
    assert figs[0].amount == 22_400.0


def test_extract_monthly_suffix_inferred_period():
    figs = _extract_dollar_figures("Rent is $2,400/mo right now.")
    assert len(figs) == 1
    assert figs[0].amount == 2_400.0
    assert figs[0].period == "month"


def test_extract_yearly_suffix_inferred_period():
    figs = _extract_dollar_figures("Current income: $78K/yr.")
    assert len(figs) == 1
    assert figs[0].period == "year"
    assert figs[0].label == "income"


def test_extract_decimal_amount():
    figs = _extract_dollar_figures("Coffee budget: $1,200.50 a year.")
    assert len(figs) == 1
    assert figs[0].amount == 1_200.5


def test_extract_million_multiplier():
    figs = _extract_dollar_figures("Series A round: $2M raised.")
    assert len(figs) == 1
    assert figs[0].amount == 2_000_000.0


def test_extract_multiple_figures_in_realistic_sentence():
    text = "Savings $50K. Day-job income $8K/mo. Startup income $1K/mo. Monthly expenses $4K."
    figs = _extract_dollar_figures(text)
    assert len(figs) == 4
    by_amount = {int(f.amount): f for f in figs}
    assert by_amount[50_000].label == "savings"
    assert by_amount[8_000].label == "income" and by_amount[8_000].period == "month"
    assert by_amount[1_000].label == "income" and by_amount[1_000].period == "month"
    assert by_amount[4_000].label == "expenses" and by_amount[4_000].period == "month"


# ── _extract_dollar_figures: negative cases ────────────────────────

def test_extract_no_dollar_sign_no_match():
    figs = _extract_dollar_figures("about fifteen grand in savings, maybe twenty thousand")
    assert figs == []


def test_extract_zero_dollars_excluded():
    """Zero-dollar entries clutter the dispatch logic; they're filtered out
    so a 'Startup income: $0 for first 6 months' line doesn't pollute the
    Monte Carlo income list."""
    figs = _extract_dollar_figures("Startup income $0 for the first six months.")
    assert figs == []


def test_extract_empty_string():
    assert _extract_dollar_figures("") == []


def test_extract_none_input_does_not_raise():
    assert _extract_dollar_figures(None) == []  # type: ignore[arg-type]


# ── label inference: sentence-bound proximity ──────────────────────

def test_label_does_not_cross_sentence_boundary():
    """Regression: 'Cloud role: $110K/yr but no offer yet. Savings: $15K.'
    must NOT label $110K as savings just because 'Savings' is physically
    close. Sentence boundaries pin the label window."""
    text = "Cloud role: $110K/yr but no offer yet. Savings: $15K."
    figs = _extract_dollar_figures(text)
    by_amount = {int(f.amount): f for f in figs}
    assert by_amount[110_000].label != "savings"
    assert by_amount[15_000].label == "savings"


def test_label_picks_closest_keyword_within_sentence():
    """In a single sentence with multiple labels, distance breaks ties."""
    text = "I have $50K savings, monthly $8K income."
    figs = _extract_dollar_figures(text)
    by_amount = {int(f.amount): f for f in figs}
    assert by_amount[50_000].label == "savings"
    assert by_amount[8_000].label == "income"


def test_label_returns_none_when_no_keyword_in_sentence():
    """Bare numbers in cue-free sentences stay unlabeled rather than being
    forced into a default category — caller decides eligibility."""
    text = "Cloud role: $110K/yr but no offer yet."
    figs = _extract_dollar_figures(text)
    assert figs[0].label is None


# ── period inference: cadence cues ─────────────────────────────────

def test_period_inferred_from_monthly_cadence_word():
    """'Monthly expenses $4K' must parse as a /mo expense even with no suffix."""
    figs = _extract_dollar_figures("Monthly expenses $4K covers rent and food.")
    assert len(figs) == 1
    assert figs[0].period == "month"
    assert figs[0].label == "expenses"


def test_period_inferred_from_annual_cadence_word():
    figs = _extract_dollar_figures("Annual revenue is $200K right now.")
    assert len(figs) == 1
    assert figs[0].period == "year"


def test_explicit_suffix_wins_over_sentence_cadence():
    """If '/yr' is on the figure, sentence-level 'Monthly' shouldn't override it."""
    figs = _extract_dollar_figures("Monthly recurring revenue stat: $200K/yr quoted by sales.")
    assert figs[0].period == "year"


# ── build_grounding_context: research path ─────────────────────────

def _ctx(**overrides) -> dict:
    base = {
        "path_a": "Stay at current job",
        "path_b": "Join AI startup",
        "financial_context": "",
    }
    base.update(overrides)
    return base


def test_research_blurb_set_for_career_category():
    ctx = _ctx()
    build_grounding_context(ctx, category="career")
    assert "_research_blurb" in ctx
    assert ctx["_research_blurb"]


def test_research_blurb_set_for_relationship_category():
    ctx = _ctx(
        path_a="Stay quiet",
        path_b="Confess feelings",
        financial_context="",
    )
    build_grounding_context(ctx, category="relationship")
    assert "_research_blurb" in ctx


def test_research_blurb_does_not_contain_source_prefix():
    """The pre-retrieve helper strips the [Source: ...] header so the prompt
    injection doesn't leak file paths to the model."""
    ctx = _ctx()
    build_grounding_context(ctx, category="career")
    blurb = ctx.get("_research_blurb", "")
    assert blurb
    assert "[Source:" not in blurb


# ── build_grounding_context: financial gating ──────────────────────

def test_no_financial_blurbs_for_relationship_even_with_dollars():
    """Relationship debates never get runway/Monte Carlo even if the user
    pasted a financial sentence — the category gate runs before extraction."""
    ctx = _ctx(
        path_a="Stay quiet",
        path_b="Confess feelings",
        financial_context="Savings $50K. Income $8K/mo. Expenses $4K/mo.",
    )
    build_grounding_context(ctx, category="relationship")
    assert "_runway_blurb" not in ctx
    assert "_monte_carlo_blurb" not in ctx


def test_runway_fires_with_savings_income_expenses_for_career():
    ctx = _ctx(
        financial_context=(
            "Savings $50K. Day-job income $8K/mo. "
            "Monthly expenses $4K covers rent and food."
        ),
    )
    build_grounding_context(ctx, category="career")
    assert "_runway_blurb" in ctx
    assert "$50,000" in ctx["_runway_blurb"] or "50,000" in ctx["_runway_blurb"]


def test_monte_carlo_fires_only_with_two_monthly_incomes_for_startup():
    ctx = _ctx(
        path_a="Stay at the day job",
        path_b="Quit to launch the startup",
        financial_context=(
            "Savings $50K. Day-job income $8K/mo. Startup income $1K/mo. "
            "Monthly expenses $4K."
        ),
    )
    build_grounding_context(ctx, category="startup")
    assert "_monte_carlo_blurb" in ctx
    assert "PATH A" in ctx["_monte_carlo_blurb"]
    assert "PATH B" in ctx["_monte_carlo_blurb"]


def test_monte_carlo_uses_path_mapping_not_income_order():
    """Reversing the text order of the incomes must not flip PATH A / PATH B."""
    ctx = _ctx(
        path_a="Stay at the day job",
        path_b="Quit to launch the startup",
        financial_context=(
            "Savings $50K. Startup income $1K/mo. Day-job income $8K/mo. "
            "Monthly expenses $4K."
        ),
    )
    build_grounding_context(ctx, category="startup")
    assert "_monte_carlo_blurb" in ctx
    assert "PATH A" in ctx["_monte_carlo_blurb"]
    assert "PATH B" in ctx["_monte_carlo_blurb"]
    assert "$8,000/mo income" in ctx["_monte_carlo_blurb"]
    assert "$1,000/mo income" in ctx["_monte_carlo_blurb"]


def test_monte_carlo_skips_when_two_incomes_cannot_be_mapped_to_paths():
    """Comparative math must not guess path ownership from list order."""
    ctx = _ctx(
        financial_context=(
            "Savings $50K. Income $8K/mo. Other income $1K/mo. "
            "Monthly expenses $4K."
        ),
    )
    build_grounding_context(ctx, category="startup")
    assert "_monte_carlo_blurb" not in ctx


def test_runway_labels_paths_when_multiple_incomes_are_path_specific():
    ctx = _ctx(
        path_a="Stay at the day job",
        path_b="Quit to launch the startup",
        financial_context=(
            "Savings $50K. Day-job income $8K/mo. Startup income $1K/mo. "
            "Monthly expenses $4K."
        ),
    )
    build_grounding_context(ctx, category="startup")
    assert "_runway_blurb" in ctx
    assert "Path A:" in ctx["_runway_blurb"]
    assert "Path B:" in ctx["_runway_blurb"]


def test_monte_carlo_does_not_fire_with_only_one_income():
    """One income figure isn't enough to compare two paths."""
    ctx = _ctx(
        financial_context="Savings $50K. Income $8K/mo. Monthly expenses $4K.",
    )
    build_grounding_context(ctx, category="startup")
    assert "_monte_carlo_blurb" not in ctx


def test_runway_does_not_fire_when_expenses_missing():
    """The career test scenario in the harness has yearly salaries, savings,
    and a debt balance — but NO monthly expense flow. Runway must NOT fire,
    because using a balance ($22K student loans) as monthly burn would
    catastrophically distort the runway math."""
    ctx = _ctx(
        financial_context=(
            "Current income: $78K/yr. Cloud role: $110K/yr but no offer yet. "
            "Savings: $15K. Student loans: $22K remaining."
        ),
    )
    build_grounding_context(ctx, category="career")
    assert "_runway_blurb" not in ctx
    assert "_monte_carlo_blurb" not in ctx


def test_runway_does_not_fire_when_under_three_figures():
    """Stay conservative: at least 3 dollar amounts before we attempt models."""
    ctx = _ctx(financial_context="Savings $50K only.")
    build_grounding_context(ctx, category="career")
    assert "_runway_blurb" not in ctx
    assert "_monte_carlo_blurb" not in ctx


# ── build_grounding_context: defensive ─────────────────────────────

def test_build_grounding_context_handles_none_user_context():
    build_grounding_context(None, category="career")  # type: ignore[arg-type]


def test_build_grounding_context_handles_missing_paths():
    ctx = {"financial_context": ""}
    build_grounding_context(ctx, category="career")
    assert "_research_blurb" in ctx or "_research_blurb" not in ctx  # must not raise


def test_build_grounding_context_idempotent():
    """Calling twice should not corrupt state — important if rehydration ever
    re-invokes grounding by mistake."""
    ctx = _ctx()
    build_grounding_context(ctx, category="career")
    snapshot = dict(ctx)
    build_grounding_context(ctx, category="career")
    assert ctx == snapshot


# ── ExtractedFigure dataclass shape ────────────────────────────────

def test_extracted_figure_round_trips_raw():
    figs = _extract_dollar_figures("Savings $42,500 in checking.")
    assert isinstance(figs[0], ExtractedFigure)
    assert "$42,500" in figs[0].raw


# ── persisted-session round-trip ───────────────────────────────────

def test_grounding_blurbs_survive_dynamodb_serialization():
    """Checkpointed sessions persist user_context to DynamoDB and rehydrate
    it on every continue. The grounding blurbs are plain strings — they must
    round-trip through the float-to-Decimal coercion (`_to_dynamodb_compatible`)
    untouched, so subsequent rounds and the verdict prompt see the same
    research/runway/Monte Carlo content the first round saw.
    """
    from app.db.dynamodb import _from_dynamodb_compatible, _to_dynamodb_compatible

    ctx = _ctx(
        path_a="Stay at the day job",
        path_b="Quit to launch the startup",
        financial_context=(
            "Savings $50K. Day-job income $8K/mo. Startup income $1K/mo. "
            "Monthly expenses $4K."
        ),
    )
    build_grounding_context(ctx, category="startup")

    encoded = _to_dynamodb_compatible(ctx)
    decoded = _from_dynamodb_compatible(encoded)

    assert decoded.get("_research_blurb") == ctx["_research_blurb"]
    assert decoded.get("_runway_blurb") == ctx["_runway_blurb"]
    assert decoded.get("_monte_carlo_blurb") == ctx["_monte_carlo_blurb"]
