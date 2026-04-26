"""Regression tests for prompt-builder fixes from the 'Fix debate quality bugs' plan.

Locks down:
- Tier 2.2: _build_prompt injects a 'NUMERIC ANCHORS YOU MUST REFERENCE' block when
  financial_context contains $-amounts, and omits it otherwise.
- Tier 2.3.D: build_verdict_prompt surfaces `_interjections` in the prompt body with the
  'do not tell them to reach out' consistency rule.
- Tier 2.4: build_verdict_prompt's 'Your next move' block is the new constraint-only
  version (no canonical examples for the model to plagiarize).
"""

from __future__ import annotations

from app.agents.prompts import (
    PERSONA_DEFENDER,
    _build_prompt,
    build_verdict_prompt,
)


def _round_info() -> dict:
    return {
        "name": "The Ledger",
        "title": "Year 2-3: The Ledger",
        "timeline": "year 2-3",
        "focus": "It's been 2-3 years. Go to ONE moment with real emotional weight.",
    }


def _base_ctx(**overrides) -> dict:
    ctx = {
        "path_a": "Stay at current job",
        "path_b": "Join AI startup",
        "financial_context": "",
        "constraints": "Student loans still outstanding.",
        "values": "growth, stability, impact",
        "writing_samples": "",
        "risk_level": "moderate",
        "user_name": "Alex",
        "age": 29,
        "_category": "career",
    }
    ctx.update(overrides)
    return ctx


# ── Tier 2.2: numeric anchors ──────────────────────────────────────

def test_build_prompt_injects_numeric_anchors():
    ctx = _base_ctx(financial_context="Savings $85K. Rent $2,400/mo. Currently earning $115,000/yr.")
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "NUMERIC ANCHORS" in prompt, "Expected anchor block to be injected."
    assert "$85K" in prompt
    assert "$2,400/mo" in prompt
    assert "Weave one exact figure in" in prompt


def test_build_prompt_no_anchor_block_when_no_dollars():
    ctx = _base_ctx(financial_context="Nothing dollar-denominated here, just lifestyle notes.")
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "NUMERIC ANCHORS" not in prompt


def test_build_prompt_no_anchor_block_when_financial_context_empty():
    ctx = _base_ctx(financial_context="")
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "NUMERIC ANCHORS" not in prompt


def test_build_prompt_no_anchor_block_when_financial_context_missing():
    ctx = _base_ctx()
    ctx.pop("financial_context", None)
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "NUMERIC ANCHORS" not in prompt


def test_build_prompt_caps_anchors_at_four():
    """The injection truncates to 4 anchors max so the model doesn't drown in every digit in context."""
    ctx = _base_ctx(
        financial_context="$10K, $20K, $30K, $40K, $50K, $60K, $70K, $80K."
    )
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "NUMERIC ANCHORS" in prompt
    # Only the first four should appear in the anchor block.
    assert "$50K" not in prompt.split("NUMERIC ANCHORS")[1].split("Weave")[0]


# ── Tier 2.3.D: verdict interjection surfacing ─────────────────────

def test_verdict_prompt_includes_interjections_when_present():
    ctx = _base_ctx(_interjections=["She asked me to dinner on Friday."])
    prompt = build_verdict_prompt(ctx, transcript_text="alpha said X; beta said Y.")

    assert "Context the user added mid-debate" in prompt
    assert "She asked me to dinner on Friday." in prompt
    assert "do not tell them to 'reach out'" in prompt


def test_verdict_prompt_includes_all_interjections_in_order():
    ctx = _base_ctx(
        _interjections=[
            "The interview already happened Tuesday.",
            "My partner just lost their job.",
        ]
    )
    prompt = build_verdict_prompt(ctx, transcript_text="transcript body")

    first_idx = prompt.index("The interview already happened Tuesday.")
    second_idx = prompt.index("My partner just lost their job.")
    assert first_idx < second_idx, "Interjections should appear in insertion order."


def test_verdict_prompt_has_no_interjection_block_when_absent():
    ctx = _base_ctx()
    prompt = build_verdict_prompt(ctx, transcript_text="transcript body")

    assert "Context the user added mid-debate" not in prompt


def test_verdict_prompt_has_no_interjection_block_when_list_is_empty():
    ctx = _base_ctx(_interjections=[])
    prompt = build_verdict_prompt(ctx, transcript_text="transcript body")

    assert "Context the user added mid-debate" not in prompt


# ── Grounding injection: BACKGROUND RESEARCH + FINANCIAL MODEL ─────

_RESEARCH_BLURB = "## Career Change Statistics\n67% of career changers report better satisfaction (Keevee 2025)."
_RUNWAY_BLURB = "Cash-flow positive: +$4,000/month net. Projected annual savings: $48,000."
_MC_BLURB = "PATH A median outcome: $268,100. PATH B median outcome: $-153,657."


def test_build_prompt_injects_background_research_when_blurb_present():
    ctx = _base_ctx(_research_blurb=_RESEARCH_BLURB)
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "BACKGROUND RESEARCH" in prompt
    assert "67% of career changers" in prompt
    assert "MUST weave EXACTLY ONE specific statistic or factual finding" in prompt
    assert "do NOT name the source" in prompt.lower() or "do NOT name the source" in prompt


def test_build_prompt_omits_background_research_when_blurb_absent():
    ctx = _base_ctx()
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "BACKGROUND RESEARCH" not in prompt


def test_build_prompt_truncates_long_research_blurb():
    """1200-char ceiling on the research block keeps prompt budget bounded."""
    long_blurb = "Stat. " * 500  # ~3000 chars
    ctx = _base_ctx(_research_blurb=long_blurb)
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    research_section = prompt.split("BACKGROUND RESEARCH")[1].split("You MUST weave EXACTLY ONE")[0]
    assert len(research_section) < 1300


def test_build_prompt_injects_financial_model_when_runway_present():
    ctx = _base_ctx(_runway_blurb=_RUNWAY_BLURB)
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "FINANCIAL MODEL" in prompt
    assert "Runway model:" in prompt
    assert "Cash-flow positive" in prompt
    assert "Reference at most ONE" in prompt


def test_build_prompt_injects_both_runway_and_monte_carlo():
    ctx = _base_ctx(_runway_blurb=_RUNWAY_BLURB, _monte_carlo_blurb=_MC_BLURB)
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "Runway model:" in prompt
    assert "Monte Carlo (60-month outlook):" in prompt
    assert "PATH A median outcome" in prompt


def test_build_prompt_omits_financial_model_when_no_blurbs():
    ctx = _base_ctx()
    prompt = _build_prompt(ctx, _round_info(), "path_a", PERSONA_DEFENDER)

    assert "FINANCIAL MODEL" not in prompt


def test_build_prompt_financial_block_independent_of_research_block():
    """Financial info should render even when research is missing, and vice versa."""
    ctx_only_financial = _base_ctx(_runway_blurb=_RUNWAY_BLURB)
    p1 = _build_prompt(ctx_only_financial, _round_info(), "path_a", PERSONA_DEFENDER)
    assert "FINANCIAL MODEL" in p1
    assert "BACKGROUND RESEARCH" not in p1

    ctx_only_research = _base_ctx(_research_blurb=_RESEARCH_BLURB)
    p2 = _build_prompt(ctx_only_research, _round_info(), "path_a", PERSONA_DEFENDER)
    assert "BACKGROUND RESEARCH" in p2
    assert "FINANCIAL MODEL" not in p2


def test_verdict_prompt_uses_dynamic_research_block_when_blurb_present():
    """When grounding pre-retrieved a chunk, the verdict prompt should swap
    out the generic hardcoded findings for the category-specific block AND
    instruct the model to cite ONE concrete fact in the right section."""
    ctx = _base_ctx(_research_blurb=_RESEARCH_BLURB)
    prompt = build_verdict_prompt(ctx, transcript_text="transcript body")

    assert "BACKGROUND RESEARCH" in prompt
    assert "67% of career changers" in prompt
    assert "you MUST cite EXACTLY ONE concrete fact" in prompt
    # Generic fallback list should be suppressed
    assert "Gilovich & Medvec" not in prompt
    assert "Lally/UCL" not in prompt


def test_verdict_prompt_falls_back_to_hardcoded_research_when_blurb_missing():
    """Without a pre-retrieved chunk, the verdict still has reference findings
    available — the generic curated list. Otherwise the verdict would lose
    research grounding entirely on debates where retrieval misses."""
    ctx = _base_ctx()
    prompt = build_verdict_prompt(ctx, transcript_text="transcript body")

    assert "BACKGROUND RESEARCH" not in prompt
    assert "Gilovich & Medvec" in prompt
    assert "67% of career changers" in prompt  # this lives in the fallback too


def test_verdict_prompt_injects_financial_model_when_blurbs_present():
    ctx = _base_ctx(_runway_blurb=_RUNWAY_BLURB, _monte_carlo_blurb=_MC_BLURB)
    prompt = build_verdict_prompt(ctx, transcript_text="transcript body")

    assert "FINANCIAL MODEL" in prompt
    assert "Runway model:" in prompt
    assert "Monte Carlo (60-month outlook):" in prompt
    assert "Reference at most ONE" in prompt


def test_verdict_prompt_omits_financial_model_when_no_blurbs():
    ctx = _base_ctx()
    prompt = build_verdict_prompt(ctx, transcript_text="transcript body")

    assert "FINANCIAL MODEL" not in prompt


# ── Tier 2.4: next-move is constraint-only (no plagiarism bait) ────

def test_verdict_prompt_next_move_block_has_no_canonical_examples():
    """The previous prompt included literal examples ('update a profile', 'put running shoes by the door',
    'email one person', 'Spend 30 minutes ...') and the model plagiarized them verbatim. They must be gone."""
    ctx = _base_ctx()
    prompt = build_verdict_prompt(ctx, transcript_text="transcript body")

    # Find the "Your next move" section
    next_move_idx = prompt.find("**Your next move:**")
    assert next_move_idx != -1, "Verdict prompt missing 'Your next move' header."
    next_move_section = prompt[next_move_idx:]

    # The constraint-only replacement text should be present.
    assert "take under 10 minutes" in next_move_section
    assert "remove one piece of uncertainty" in next_move_section
    assert "Do not use generic phrasing" in next_move_section

    # The old template examples must NOT be instructions the model sees.
    # We still mention them in the anti-pattern list ("Do not use generic phrasing (...)"),
    # but they must NOT appear as positive prescriptions.
    forbidden_positive_phrases = [
        "put running shoes by the door",
        "throw out one thing",
        "sign up for one class",
        "write down 3 problems",
    ]
    for phrase in forbidden_positive_phrases:
        assert phrase not in next_move_section, (
            f"Old template example survived in next-move section: {phrase!r}"
        )
