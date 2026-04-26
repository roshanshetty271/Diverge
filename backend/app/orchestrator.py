"""Debate orchestrator — runs the 5-round structured debate.

Edge cases handled:
- Model throttling → longer backoff + jitter
- Model timeout → retry
- Validation errors → no retry (same input will fail again)
- Agent returning empty/None → explicit fallback text
- Verdict output validated for prompt leakage

Supports both OpenAI and Bedrock via DIVERGE_MODEL_PROVIDER setting.
Streaming routes emit already-validated text in chunks.
"""

import re
import uuid
import time
import random
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable
from strands import Agent

from app.config import get_settings
from app.agents.prompts import (
    get_rounds, detect_decision_category,
    build_alpha_prompt, build_beta_prompt, build_verdict_prompt, build_timeline_simulator_prompt,
    PERSONA_CHALLENGER, PERSONA_DEFENDER, PERSONA_EQUAL,
)
from app.agents.metrics import extract_metrics
from app.content_guardrails import (
    ValidationResult,
    build_grounding_profile,
    format_violation_report,
    log_validation_failure,
    scrub_repeated_motifs,
    strict_grounding_rewrite_brief,
    validate_generated_text,
)
from app.schemas import (
    DebateResponse,
    Resource,
    RoundMetrics,
    RoundResult,
    StructuredTimeline,
    StructuredTimelineCore,
    TimelineExploreItem,
)
from app.tools.monte_carlo import monte_carlo_financial
from app.tools.data_tools import get_salary_data, compare_cost_of_living, calculate_runway
from app.tools.knowledge import research_insight
from app.grounding import build_grounding_context
from app.security.llm_security import validate_agent_output, validate_safe_content
from app.tools.comprehend import analyze_round_sentiment

logger = logging.getLogger(__name__)

# --------------- AI Slop Cleaner ---------------
_SLOP_OPENERS = re.compile(
    r"^\s*(?:"
    r"Here'?s the thing[:\s—–-]*"
    r"|The (?:uncomfortable |honest |real )?truth is[,:\s—–-]*"
    r"|Let me be (?:clear|honest|real)[.:\s—–-]*"
    r"|I'll be honest[,:\s—–-]*"
    r"|I'm going to be honest[,:\s—–-]*"
    r"|Can we talk about[:\s]*"
    r"|Make no mistake[,:\s—–-]*"
    r"|Picture this[.:\s—–-]*"
    r"|Imagine this[.:\s—–-]*"
    r"|Let me paint you a picture[.:\s—–-]*"
    r"|Here's what I find interesting[.:\s—–-]*"
    r"|Here's the (?:problem|deal)[.:\s—–-]*"
    r"|Look[,:\s]+"
    r"|Listen[,:\s]+"
    r")",
    re.IGNORECASE,
)

_SLOP_PHRASES = [
    (re.compile(r"\bLet that sink in\.?", re.I), ""),
    (re.compile(r"\bFull stop\.?", re.I), ""),
    (re.compile(r"\bPeriod\.(?!\d)", re.I), ""),
    (re.compile(r"\bGame[- ]?changer", re.I), "significant shift"),
    (re.compile(r"\bDeep dive", re.I), "close look"),
    (re.compile(r"\bAt the end of the day[,]?\s*", re.I), ""),
    (re.compile(r"\bIt's worth noting\s*(?:that)?\s*", re.I), ""),
    (re.compile(r"\bInterestingly,?\s*", re.I), ""),
    (re.compile(r"\bCrucially,?\s*", re.I), ""),
    (re.compile(r"\bImportantly,?\s*", re.I), ""),
    (re.compile(r"\bunpack\s+(?:this|that|it)", re.I), "explain it"),
    (re.compile(r"\blean(?:ed|ing|s)?\s+into\b", re.I), "embraced"),
    (re.compile(r"\bdouble(?:d|s)?\s+down\s+on\b", re.I), "committed to"),
]

_DOUBLE_HYPHEN = re.compile(r"(?<!\w)--(?!\w)")
_MULTI_SPACE = re.compile(r" {2,}")
_LEADING_SPACE_LINE = re.compile(r"^ +", re.MULTILINE)


def _clean_ai_slop(text: str) -> str:
    """Strip common AI-tell patterns from agent output."""
    if not text:
        return text
    text = _SLOP_OPENERS.sub("", text, count=1)
    for pattern, replacement in _SLOP_PHRASES:
        text = pattern.sub(replacement, text)
    text = _DOUBLE_HYPHEN.sub(" - ", text)
    text = text.replace("\u2014", " - ")   # em dash
    text = text.replace("\u2013", " - ")   # en dash
    text = _MULTI_SPACE.sub(" ", text)
    text = _LEADING_SPACE_LINE.sub("", text)
    return text.strip()


def _guardrail_stats(user_ctx: dict) -> dict[str, int]:
    stats = user_ctx.setdefault(
        "_content_guardrail_stats",
        {
            "biography_violations": 0,
            "style_violations": 0,
            "resource_selector_fallbacks": 0,
            "fallback_count": 0,
        },
    )
    return stats


def _record_guardrail_failures(user_ctx: dict, result) -> None:
    stats = _guardrail_stats(user_ctx)
    for violation in result.violations:
        if violation.code.startswith("invented_") or "biography" in violation.code:
            stats["biography_violations"] += 1
        else:
            stats["style_violations"] += 1


def _validated_transcript_texts(transcript: list[RoundResult] | None) -> list[str]:
    texts: list[str] = []
    for round_result in transcript or []:
        if round_result.status != "completed":
            continue
        texts.extend([round_result.alpha, round_result.beta])
    return texts


def _append_rewrite_instruction(base_input: str, rewrite_instruction: str) -> str:
    if not rewrite_instruction:
        return base_input
    return f"{base_input}\n\nREWRITE REQUIREMENTS:\n{rewrite_instruction}"


def _iter_stream_events_for_text(
    text: str,
    *,
    event_type: str,
    agent: str | None = None,
    round_num: int | None = None,
    chunk_words: int = 14,
):
    words = re.findall(r"\S+\s*", text)
    if not words and text:
        words = [text]

    for index in range(0, len(words), chunk_words):
        payload = {
            "type": event_type,
            "text": "".join(words[index:index + chunk_words]),
        }
        if agent is not None:
            payload["agent"] = agent
        if round_num is not None:
            payload["round"] = round_num
        yield payload


def _generate_with_guardrails(
    *,
    user_ctx: dict,
    transcript: list[RoundResult] | None,
    extra_prior_texts: list[str] | None = None,
    content_kind: str,
    stage_label: str,
    fallback_text: str,
    generator: Callable[[str], str],
    path_a: str | None = None,
    path_b: str | None = None,
) -> str:
    """Run generation with validation, corrective rewrite, and strict fallback."""
    prior_texts = _validated_transcript_texts(transcript)
    if extra_prior_texts:
        prior_texts.extend(extra_prior_texts)
    rewrite_instruction = ""
    debate_id = user_ctx.get("debate_id")

    for attempt in range(3):
        text = generator(rewrite_instruction).strip()
        if not text:
            rewrite_instruction = strict_grounding_rewrite_brief()
            continue

        profile = build_grounding_profile(user_ctx, prior_texts, category=user_ctx.get("_category", ""))
        result = validate_generated_text(
            text,
            profile,
            content_kind,
            path_a=path_a,
            path_b=path_b,
        )
        if result.is_valid:
            return text

        log_validation_failure(debate_id, stage_label, result)
        _record_guardrail_failures(user_ctx, result)
        # Run the motif scrub whenever we have motif violations — even if other
        # violations coexist. If the scrub clears every outstanding violation, use it;
        # otherwise continue into the rewrite loop with the remaining issues only.
        has_motif_violation = any(v.code == "repeated_motif" for v in result.violations)
        if has_motif_violation:
            scrubbed_text = scrub_repeated_motifs(text, result)
            if scrubbed_text and scrubbed_text != text:
                scrubbed_result = validate_generated_text(
                    scrubbed_text,
                    profile,
                    content_kind,
                    path_a=path_a,
                    path_b=path_b,
                )
                if scrubbed_result.is_valid:
                    logger.info("Motif scrub rescued stage=%s debate_id=%s", stage_label, debate_id)
                    return scrubbed_text
                # Scrub didn't fully rescue; keep going with the remaining violations
                # so the rewrite brief isn't dominated by motif noise that's already fixed.
                text = scrubbed_text
                result = scrubbed_result
        rewrite_instruction = format_violation_report(result) if attempt == 0 else strict_grounding_rewrite_brief()

    logger.warning("Guardrail exhaustion: returning fallback for stage=%s debate_id=%s", stage_label, debate_id)
    _guardrail_stats(user_ctx)["fallback_count"] = _guardrail_stats(user_ctx).get("fallback_count", 0) + 1
    return fallback_text


_CATEGORY_FALLBACK_FLAVOR: dict[str, tuple[str, str]] = {
    "career": ("professional routine", "career path"),
    "startup": ("founder reality", "entrepreneurial bet"),
    "relationship": ("emotional landscape", "relationship dynamic"),
    "health": ("daily habits", "lifestyle shift"),
    "education": ("learning commitment", "educational investment"),
    "financial": ("financial rhythm", "money decision"),
}


def _build_round_fallback_text(path: str, timeline: str, category: str = "") -> str:
    flavor = _CATEGORY_FALLBACK_FLAVOR.get(category, ("daily reality", "life choice"))
    return (
        f"Right now, living with {path.lower()} in {timeline} shows up in your {flavor[0]}. "
        f"This path gives something real, but it asks something real back.\n\n"
        f"The tradeoff behind this {flavor[1]} surfaces in pressure, relief, and responsibility. "
        "Nothing here is clean. It is simply the version of life you would have to keep waking up inside."
    )


def _build_verdict_fallback_text(user_ctx: dict) -> str:
    path_a = user_ctx["path_a"]
    path_b = user_ctx["path_b"]
    return (
        f"**Where {path_a} wins:**\n"
        "- It preserves something tangible that matters in the context you gave.\n"
        "- It carries a downside, but that downside is legible.\n\n"
        f"**Where {path_b} wins:**\n"
        "- It opens a form of upside the safer path cannot create.\n"
        "- It may fit if the hidden cost of staying still is bigger than the visible risk.\n\n"
        "**What this decision is really about:**\n"
        "This is not just about preference. It is about which form of uncertainty you are more willing to live with once the adrenaline wears off.\n\n"
        "**The bottleneck:**\n"
        "The main blocker looks like overprotection against the wrong kind of pain rather than lack of information.\n\n"
        "**Your next move:**\n"
        "Right now, do this: write one sentence for what each path protects, and one sentence for what each path delays."
    )


MAX_RETRIES = 3
FINANCIAL_TOOLS = [monte_carlo_financial, get_salary_data, compare_cost_of_living, calculate_runway]

TOOL_MAP: dict[str, list] = {
    "career":       [research_insight, get_salary_data, compare_cost_of_living],
    "startup":      [research_insight, monte_carlo_financial, calculate_runway],
    "financial":    [research_insight] + FINANCIAL_TOOLS,
    "education":    [research_insight, get_salary_data],
    "relationship": [research_insight],
    "health":       [research_insight],
    "general":      [research_insight],
}

NON_RETRYABLE = ("ValidationException", "AccessDeniedException", "ResourceNotFoundException")

# In-memory interjection store: debate_id → list of interjection texts (one per round gap)
_interjection_store: dict[str, list[str]] = {}


def _log_debug_round_trace(round_num: int, round_name: str, alpha_response: str, beta_response: str):
    """Emit full round outputs only in debug mode for local prompt testing."""
    if not get_settings().debug:
        return

    logger.info(
        "[debug-trace] round %s (%s) | alpha=%r | beta=%r",
        round_num,
        round_name,
        alpha_response,
        beta_response,
    )


def set_interjection(debate_id: str, text: str):
    """Store a user interjection to be picked up by the next round."""
    _interjection_store.setdefault(debate_id, []).append(text)


def _pop_interjection(debate_id: str) -> str | None:
    """Pop and return the next interjection for a debate, if any."""
    interjections = _interjection_store.get(debate_id, [])
    if interjections:
        return interjections.pop(0)
    return None


def _make_model(
    max_tokens: int | None = None,
    temperature: float | None = None,
    persona_label: str | None = None,
):
    """Create a model instance based on the configured provider (openai or bedrock).

    If `temperature` is not provided, a persona-aware temperature is used:
      challenger => 0.9 (more variety, punchier fragments)
      defender   => 0.55 (more measured, patient sentences)
    Falling back to the global debate_temperature for helpers with no persona.
    """
    s = get_settings()
    tokens = max_tokens or s.debate_max_tokens
    if temperature is not None:
        temp = temperature
    elif persona_label == "challenger":
        temp = 0.9
    elif persona_label == "defender":
        temp = 0.55
    else:
        temp = s.debate_temperature

    if s.model_provider == "openai":
        from strands.models.openai import OpenAIModel
        return OpenAIModel(
            client_args={"api_key": s.openai_api_key},
            model_id=s.debate_model_id,
            params={"max_tokens": tokens, "temperature": temp},
        )
    else:
        from botocore.config import Config as BotocoreConfig
        from strands.models import BedrockModel
        boto_config = BotocoreConfig(
            retries={"max_attempts": 2, "mode": "adaptive"},
            read_timeout=120,
            connect_timeout=10,
        )
        kwargs: dict = {
            "model_id": s.debate_model_id,
            "region_name": s.aws_region,
            "max_tokens": tokens,
            "temperature": temp,
            "boto_client_config": boto_config,
        }
        if s.guardrail_id:
            kwargs["guardrail_config"] = {
                "guardrailIdentifier": s.guardrail_id,
                "guardrailVersion": s.guardrail_version,
            }
        return BedrockModel(**kwargs)


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is worth retrying."""
    exc_name = type(exc).__name__
    exc_str = str(exc)
    for pattern in NON_RETRYABLE:
        if pattern in exc_name or pattern in exc_str:
            return False
    return True


def _backoff_with_jitter(attempt: int) -> float:
    """Exponential backoff with jitter to prevent thundering herd."""
    base = 2 ** attempt
    jitter = random.uniform(0, base * 0.5)
    return base + jitter


def _safe_agent_output(result) -> str:
    """Safely convert agent output to string, handling None/empty, then strip AI slop."""
    text = str(result) if result is not None else ""
    if text in ("None", "null", ""):
        return ""
    return _clean_ai_slop(text)


def _format_transcript_for_llm(transcript: list[RoundResult], user_ctx: dict) -> str:
    """Format completed rounds into a compact transcript for downstream LLM steps."""
    full_text = ""
    for r in transcript:
        if r.status == "completed":
            full_text += f"\n--- Round {r.round_number}: {r.round_title} ---\n"
            full_text += f"Path A ({user_ctx['path_a']}): {r.alpha}\n"
            full_text += f"Path B ({user_ctx['path_b']}): {r.beta}\n"
    return full_text.strip()


def _strip_json_fences(text: str) -> str:
    """Remove optional markdown fences around JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _get_round_time_jump(round_num: int) -> tuple[str, int | None]:
    """Return the forced time jump label and years elapsed for a debate round."""
    jumps: dict[int, tuple[str, int | None]] = {
        0: ("EXACTLY 1 YEAR AFTER THE ORIGINAL DECISION", 1),
        1: ("AT THE 3-YEAR MARK AFTER THE ORIGINAL DECISION", 3),
        2: ("EXACTLY 5 YEARS AFTER THE ORIGINAL DECISION", 5),
        3: ("EXACTLY 10 YEARS AFTER THE ORIGINAL DECISION", 10),
        4: ("AT THE FINAL LOOK-BACK AFTER LIVING THE FULL CONSEQUENCES OF THIS PATH", None),
    }
    return jumps.get(round_num, (f"AT {round_num + 1} STAGES LATER IN THIS LIFE", None))


def _build_chronology_guardrail(user_ctx: dict, round_info: dict, round_num: int) -> str:
    """Force the model to honor time jumps, setting evolution, and detail decay."""
    jump_label, years_elapsed = _get_round_time_jump(round_num)
    age = user_ctx.get("age")
    timeline = round_info.get("timeline", f"round {round_num + 1}")

    if years_elapsed is not None:
        if age is not None:
            age_line = (
                f"- The user was {age} at the original decision. In this round they are {age + years_elapsed}. "
                f"They are exactly {years_elapsed} years older."
            )
        else:
            age_line = f"- The user is exactly {years_elapsed} years older in this round."
    else:
        if age is not None:
            age_line = (
                f"- The user was {age} at the original decision. This round is the final look-back from a meaningfully older life stage."
            )
        else:
            age_line = "- This round is the final look-back from a meaningfully older life stage."

    setting_line = (
        "- You are FORBIDDEN from keeping the character in the same physical setting as a previous round. "
        "Do not leave them in the same room, same cafe, same office, same shower, same car, same kitchen, "
        "same bed, or same conversation."
        if round_num > 0
        else "- This Year 1 scene is not a permanent set for the rest of the timeline. Do not lock future rounds into this exact room, outfit, or minute."
    )
    final_round_line = (
        "- FINAL WORDS RULE: This is the closing reckoning after living the consequences. Do NOT call it 'five years in', 'ten years in', 'year 5', or 'year 10'. "
        "Speak from accumulated consequence, not a numbered milestone."
        if round_num == 4
        else ""
    )

    return (
        "CHRONOLOGY ENFORCEMENT - FOLLOW THIS EXACTLY:\n"
        f"- This round takes place {jump_label}. Treat the lived moment as {timeline}.\n"
        f"{age_line}\n"
        f"{setting_line}\n"
        f"{final_round_line}\n"
        "- The environment MUST evolve to reflect the passage of time. Use a new scene, new objects, and new stakes that make the years feel real.\n"
        "- If you revisit a familiar place, it must be obviously transformed by time and compounding consequences.\n"
        "- Drop trivial carryover details from Year 1 and earlier rounds: exact clothes, exact chair, exact wall color, exact cup, exact sentence, exact weather, exact body posture.\n"
        "- Carry forward only what compounds: money, health, leverage, intimacy, status, habit debt, regret, relief, freedom, isolation, confidence, exhaustion.\n"
        "- This round must feel like a NEW chapter in the same life, not the same room frozen in time."
    )


def _get_chronological_awareness_window(round_num: int) -> str:
    """Return the round-aware elapsed-time wording for system-prompt timeline references."""
    windows = {
        0: "1 year",
        1: "3 years",
        2: "5 years",
        3: "10 years",
        4: "all these years",
    }
    return windows.get(round_num, f"{round_num + 1} stages")


def _build_chronological_awareness_rule(agent_name: str, round_num: int) -> str:
    """Force the agent to acknowledge the widening timeline gap explicitly."""
    elapsed_window = _get_chronological_awareness_window(round_num)

    if agent_name.lower() == "alpha":
        agent_specific_rule = (
            f"- If you are Alpha, contrast your long-term reality over the last {elapsed_window} "
            "with what the other path would likely cost or preserve."
        )
    else:
        agent_specific_rule = (
            f"- If you are Beta, explain your long-term reality based on the time passed, and name what the other path would likely cost or preserve over the last {elapsed_window}."
        )

    return (
        "CHRONOLOGICAL AWARENESS:\n"
        "You must actively acknowledge the passage of time in your argument. Do not just describe your current state; "
        "you must explicitly reference how much time has passed since the decision was made.\n"
        f"{agent_specific_rule}\n"
        f"{'- For the final round, talk like someone summing up the whole cost of a life, not someone narrating another five-year checkpoint.\n' if round_num == 4 else ''}"
        "- You MUST reference the timeline directly to show the widening gap between the two paths."
    )


def _build_round_system_prompt(
    base_prompt: str,
    user_ctx: dict,
    round_info: dict,
    round_num: int,
    agent_name: str,
) -> str:
    """Append chronology guardrails and timeline-awareness directives to the round system prompt."""
    chronology_guardrail = _build_chronology_guardrail(user_ctx, round_info, round_num)
    chronological_awareness = _build_chronological_awareness_rule(agent_name, round_num)
    return f"{base_prompt}\n\n{chronology_guardrail}\n\n{chronological_awareness}"


def _build_runtime_wrapper_prompt(
    debate_summary: str,
    interjection: str | None,
    path: str,
    timeline: str,
    prev_response: str,
    chronology_guardrail: str,
) -> str:
    """Build the per-turn runtime wrapper that keeps agents grounded in the live exchange."""
    summary_prefix = f"THE RECKONING SO FAR:\n{debate_summary}\n\n" if debate_summary else ""
    interjection_prefix = (
        "IMPORTANT USER CONTEXT FOR THIS ROUND:\n"
        f'- The user just added this: "{interjection}" (Account for this explicitly in your reality).\n\n'
        if interjection
        else ""
    )

    return (
        f"{chronology_guardrail}\n\n"
        f"{summary_prefix}"
        f"{interjection_prefix}"
        f'You chose "{path}". You are living in {timeline}.\n\n'
        "The version of you who chose the other path just described their reality:\n\n"
        f"\"{prev_response}\"\n\n"
        "YOUR TURN:\n"
        "1. Start by directly addressing the exact scene or feeling they just described. "
        "Name the tradeoff or blind spot they are minimizing in that specific moment without mocking them.\n"
        f"2. Then, pivot to YOUR reality right now at {timeline}.\n"
        f'3. CRITICAL TIME RULE: Do NOT use the phrase "I remember" or tell a story in the past tense. '
        f"You are living this moment RIGHT NOW in {timeline}. Make it visceral. "
        "What are you looking at? What do you feel in your body?\n"
        "4. CRITICAL SETTING RULE: You may not remain in the exact physical setting from a previous round. "
        "Change the environment to prove time has passed.\n"
        "5. CRITICAL DETAIL RULE: Drop trivial old details like clothes or exact rooms from earlier rounds. "
        "Focus on the long-term compounding consequences.\n"
        "6. DO NOT use attack-dog openers like 'You think...', 'It's an illusion', or 'Let's be real'."
    )


def _assign_personas(path_a: str, path_b: str) -> tuple[dict, dict]:
    """Dynamically assign personas based on which path requires courage."""
    from app.agents.prompts import detect_brave_path

    brave_path = detect_brave_path(path_a, path_b)

    if brave_path == "a":
        return PERSONA_CHALLENGER, PERSONA_DEFENDER
    elif brave_path == "b":
        return PERSONA_DEFENDER, PERSONA_CHALLENGER
    else:
        return PERSONA_EQUAL, PERSONA_EQUAL


def _build_stage06_fallback(user_ctx: dict) -> list[TimelineExploreItem]:
    """Create deterministic fallback recommendations when stage-06 output is missing or invalid."""
    fallback_resources = _get_resources(user_ctx)
    return [
        TimelineExploreItem(
            type=resource.type,
            title=resource.title,
            author=resource.author,
            why_it_helps=resource.why,
            url=resource.url or "",
        )
        for resource in fallback_resources
        if resource.url
    ]


def _build_stage06_items(user_ctx: dict) -> list[TimelineExploreItem]:
    """Select deterministic stage-06 resources server-side."""
    try:
        from app.data.resources import select_timeline_resources

        items, _ = select_timeline_resources(
            user_ctx.get("path_a", ""),
            user_ctx.get("path_b", ""),
            user_ctx.get("constraints"),
            writing_samples=user_ctx.get("writing_samples"),
            decision_category=user_ctx.get("_category"),
        )
        return [TimelineExploreItem(**item) for item in items]
    except Exception as e:
        logger.warning("Failed to build stage-06 resources: %s", e)
        _guardrail_stats(user_ctx)["resource_selector_fallbacks"] += 1
        return _build_stage06_fallback(user_ctx)


def _validate_timeline_core(
    timeline: StructuredTimelineCore,
    transcript: list[RoundResult],
    user_ctx: dict,
) -> ValidationResult:
    """Validate each timeline passage against grounding/style guardrails."""
    profile = build_grounding_profile(user_ctx, _validated_transcript_texts(transcript), category=user_ctx.get("_category", ""))
    all_violations = []
    fields = [
        ("timeline.stage_01.path_a", timeline.stage_01_the_ripple_year_1.path_a_safe),
        ("timeline.stage_01.path_b", timeline.stage_01_the_ripple_year_1.path_b_bet),
        ("timeline.stage_02.path_a", timeline.stage_02_the_ledger_year_3.path_a_safe),
        ("timeline.stage_02.path_b", timeline.stage_02_the_ledger_year_3.path_b_bet),
        ("timeline.stage_03.path_a", timeline.stage_03_the_mirror_year_5.path_a_safe),
        ("timeline.stage_03.path_b", timeline.stage_03_the_mirror_year_5.path_b_bet),
        ("timeline.stage_04.path_a", timeline.stage_04_the_ghost_year_10.path_a_safe),
        ("timeline.stage_04.path_b", timeline.stage_04_the_ghost_year_10.path_b_bet),
        ("timeline.stage_05.path_a", timeline.stage_05_the_knot_final_words.path_a_safe),
        ("timeline.stage_05.path_b", timeline.stage_05_the_knot_final_words.path_b_bet),
    ]
    for stage_label, passage in fields:
        result = validate_generated_text(passage, profile, "timeline_stage")
        if not result.is_valid:
            log_validation_failure(user_ctx.get("debate_id"), stage_label, result)
            all_violations.extend(result.violations)
    return ValidationResult(violations=all_violations)


def _build_structured_timeline_fallback(user_ctx: dict) -> StructuredTimeline:
    """Create a grounded generic structured timeline fallback."""
    path_a = user_ctx["path_a"]
    path_b = user_ctx["path_b"]
    stage06 = _build_stage06_items(user_ctx)
    return StructuredTimeline(
        stage_01_the_ripple_year_1={
            "path_a_safe": f"One year in, {path_a.lower()} has settled into a familiar rhythm — the stability is real, but so is the quiet cost of staying.",
            "path_b_bet": f"One year in, {path_b.lower()} still feels uncertain — the discomfort is real, but so is the energy that comes from having moved.",
        },
        stage_02_the_ledger_year_3={
            "path_a_safe": f"Three years in, {path_a.lower()} has compounded into predictable routines and protections that feel harder to walk away from.",
            "path_b_bet": f"Three years in, {path_b.lower()} has compounded into new skills and connections that did not exist before the leap.",
        },
        stage_03_the_mirror_year_5={
            "path_a_safe": f"Five years in, {path_a.lower()} has shaped who you are — the comfort is earned, but the unlived possibilities still surface.",
            "path_b_bet": f"Five years in, {path_b.lower()} has shaped who you are — the growth is earned, but the costs and sacrifices still surface.",
        },
        stage_04_the_ghost_year_10={
            "path_a_safe": f"Ten years in, {path_a.lower()} carries a long tail of security and regret that can no longer be separated.",
            "path_b_bet": f"Ten years in, {path_b.lower()} carries a long tail of growth and tradeoffs that can no longer be abstracted away.",
        },
        stage_05_the_knot_final_words={
            "path_a_safe": f"{path_a} protects something important, but it asks for a real cost in unlived possibility.",
            "path_b_bet": f"{path_b} opens something meaningful, but it asks for a real cost in comfort and certainty.",
            "verdict_path_of_least_regret": "The path of least regret depends on which form of uncertainty this person is actually willing to carry.",
        },
        stage_06_what_to_explore_next=stage06,
    )


def _generate_structured_timeline(transcript: list[RoundResult], user_ctx: dict) -> StructuredTimeline | None:
    """Generate the strict timeline JSON used by the verdict timeline UI."""
    full_text = _format_transcript_for_llm(transcript, user_ctx)
    if not full_text:
        return None

    prompt = build_timeline_simulator_prompt(user_ctx, full_text)
    settings = get_settings()
    rewrite_instruction = ""

    for attempt in range(3):
        try:
            user_message = "Generate the structured timeline JSON now."
            if rewrite_instruction:
                user_message = f"{user_message}\n\n{rewrite_instruction}"
            if settings.model_provider == "openai":
                from openai import OpenAI

                client = OpenAI(api_key=settings.openai_api_key)
                completion = client.beta.chat.completions.parse(
                    model=settings.debate_model_id,
                    temperature=0.4,
                    max_completion_tokens=3500,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_message},
                    ],
                    response_format=StructuredTimelineCore,
                )
                parsed = completion.choices[0].message.parsed
                if parsed:
                    validation = _validate_timeline_core(parsed, transcript, user_ctx)
                    if validation.is_valid:
                        return StructuredTimeline(
                            **parsed.model_dump(),
                            stage_06_what_to_explore_next=_build_stage06_items(user_ctx),
                        )
                    _record_guardrail_failures(user_ctx, validation)
                    rewrite_instruction = format_violation_report(validation) if attempt == 0 else strict_grounding_rewrite_brief()
            else:
                timeline_agent = Agent(
                    model=_make_model(max_tokens=3500, temperature=0.4),
                    system_prompt=prompt,
                )
                raw = timeline_agent(user_message)
                parsed = StructuredTimelineCore.model_validate_json(_strip_json_fences(str(raw)))
                validation = _validate_timeline_core(parsed, transcript, user_ctx)
                if validation.is_valid:
                    return StructuredTimeline(
                        **parsed.model_dump(),
                        stage_06_what_to_explore_next=_build_stage06_items(user_ctx),
                    )
                _record_guardrail_failures(user_ctx, validation)
                rewrite_instruction = format_violation_report(validation) if attempt == 0 else strict_grounding_rewrite_brief()
        except Exception as e:
            logger.error("Structured timeline generation attempt %s failed: %s", attempt + 1, e)
            rewrite_instruction = strict_grounding_rewrite_brief()
            if attempt < 2:
                time.sleep(1.5)

    _guardrail_stats(user_ctx)["resource_selector_fallbacks"] += 1
    return _build_structured_timeline_fallback(user_ctx)


def _run_round(
    round_info: dict,
    user_ctx: dict,
    prev_beta: str | None,
    round_num: int,
    transcript: list[RoundResult] | None,
    debate_summary: str,
    tools: list,
    alpha_persona: dict,
    beta_persona: dict,
    interjection: str | None = None,
) -> RoundResult:
    """Execute one debate round with smart retry logic."""
    alpha_response = ""
    beta_response = ""

    for attempt in range(MAX_RETRIES):
        try:
            chronology_guardrail = _build_chronology_guardrail(user_ctx, round_info, round_num)
            alpha_system_prompt = _build_round_system_prompt(
                build_alpha_prompt(user_ctx, round_info, alpha_persona),
                user_ctx,
                round_info,
                round_num,
                "Alpha",
            )
            path_a = user_ctx["path_a"]
            path_b = user_ctx["path_b"]
            timeline = round_info.get("timeline", f"round {round_num + 1}")

            if round_num == 0:
                alpha_input = (
                    f"{chronology_guardrail}\n\n"
                    f"You chose \"{path_a}\". You are living in {timeline} right now. "
                    f"Do NOT use the phrase \"I remember\" or tell this in the past tense. "
                    f"Speak from one emotionally loaded moment that makes this reality feel current, physical, and concrete. "
                    f"Do not trap the rest of the timeline inside this exact room or trivial detail."
                )
            else:
                alpha_input = _build_runtime_wrapper_prompt(
                    debate_summary=debate_summary,
                    interjection=interjection,
                    path=path_a,
                    timeline=timeline,
                    prev_response=prev_beta or "",
                    chronology_guardrail=chronology_guardrail,
                )
            alpha_response = _generate_with_guardrails(
                user_ctx=user_ctx,
                transcript=transcript,
                content_kind="round",
                stage_label=f"round_{round_num + 1}.alpha",
                fallback_text=_build_round_fallback_text(path_a, timeline, user_ctx.get("_category", "")),
                generator=lambda rewrite_instruction: validate_safe_content(
                    validate_agent_output(
                        _safe_agent_output(
                            Agent(
                                model=_make_model(persona_label=alpha_persona["label"]),
                                system_prompt=alpha_system_prompt,
                                tools=tools,
                            )(_append_rewrite_instruction(alpha_input, rewrite_instruction))
                        )
                    )
                ),
            )

            if not alpha_response:
                raise ValueError("Alpha agent returned empty response")

            beta_system_prompt = _build_round_system_prompt(
                build_beta_prompt(user_ctx, round_info, beta_persona),
                user_ctx,
                round_info,
                round_num,
                "Beta",
            )
            beta_input = _build_runtime_wrapper_prompt(
                    debate_summary=debate_summary,
                    interjection=interjection,
                    path=path_b,
                    timeline=timeline,
                    prev_response=alpha_response,
                    chronology_guardrail=chronology_guardrail,
                )
            beta_response = _generate_with_guardrails(
                user_ctx=user_ctx,
                transcript=transcript,
                extra_prior_texts=[alpha_response],
                content_kind="round",
                stage_label=f"round_{round_num + 1}.beta",
                fallback_text=_build_round_fallback_text(path_b, timeline, user_ctx.get("_category", "")),
                generator=lambda rewrite_instruction: validate_safe_content(
                    validate_agent_output(
                        _safe_agent_output(
                            Agent(
                                model=_make_model(persona_label=beta_persona["label"]),
                                system_prompt=beta_system_prompt,
                                tools=tools,
                            )(_append_rewrite_instruction(beta_input, rewrite_instruction))
                        )
                    )
                ),
            )

            if not beta_response:
                raise ValueError("Beta agent returned empty response")

            debate_text = f"Path A argued:\n{alpha_response}\n\nPath B argued:\n{beta_response}"
            with ThreadPoolExecutor(max_workers=2) as pool:
                metrics_future = pool.submit(extract_metrics, debate_text)
                sentiment_future = pool.submit(analyze_round_sentiment, alpha_response, beta_response)
                metrics = metrics_future.result()
                sentiment = sentiment_future.result()
            _log_debug_round_trace(round_num + 1, round_info["name"], alpha_response, beta_response)

            return RoundResult(
                round_number=round_num + 1,
                round_name=round_info["name"],
                round_title=round_info["title"],
                alpha=alpha_response,
                beta=beta_response,
                metrics=metrics,
                sentiment=sentiment,
                status="completed",
            )

        except Exception as e:
            logger.warning(f"Round {round_num + 1} attempt {attempt + 1} failed: {type(e).__name__}: {e}")

            if not _is_retryable(e):
                logger.error(f"Round {round_num + 1} hit non-retryable error, skipping: {e}")
                break

            if attempt < MAX_RETRIES - 1:
                delay = _backoff_with_jitter(attempt)
                logger.info(f"Retrying round {round_num + 1} in {delay:.1f}s...")
                time.sleep(delay)

    return RoundResult(
        round_number=round_num + 1,
        round_name=round_info["name"],
        round_title=round_info["title"],
        alpha=alpha_response or "This perspective could not be generated. The AI service may be temporarily unavailable.",
        beta=beta_response or "This perspective could not be generated. The AI service may be temporarily unavailable.",
        metrics=None,
        status="partial",
    )


def _generate_verdict(transcript: list[RoundResult], user_ctx: dict) -> str:
    """Generate the final verdict from the debate transcript."""
    full_text = _format_transcript_for_llm(transcript, user_ctx)
    if not full_text.strip():
        return "The debate could not produce enough content for a verdict."

    prompt = build_verdict_prompt(user_ctx, full_text)

    try:
        return _generate_with_guardrails(
            user_ctx=user_ctx,
            transcript=transcript,
            content_kind="verdict",
            stage_label="verdict",
            fallback_text=_build_verdict_fallback_text(user_ctx),
            path_a=user_ctx["path_a"],
            path_b=user_ctx["path_b"],
            generator=lambda rewrite_instruction: validate_safe_content(
                validate_agent_output(
                    _safe_agent_output(
                        Agent(
                            model=_make_model(max_tokens=2048, temperature=0.6),
                            system_prompt=prompt,
                        )(_append_rewrite_instruction("Give your verdict now.", rewrite_instruction))
                    )
                )
            ),
        )
    except Exception as e:
        logger.error("Verdict generation failed: %s", e)
        return _build_verdict_fallback_text(user_ctx)


def _get_resources(user_context: dict) -> list[Resource]:
    """Get diversified deterministic fallback resources for the current user context."""
    try:
        from app.data.resources import get_rotating_fallback_resources

        raw = get_rotating_fallback_resources(
            user_context.get("path_a", ""),
            user_context.get("path_b", ""),
            user_context.get("constraints"),
            max_items=3,
            decision_category=user_context.get("_category"),
            writing_samples=user_context.get("writing_samples"),
        )
        return [Resource(**resource) for resource in raw]
    except Exception as e:
        logger.warning("Failed to load fallback resources: %s", e)
        return []


def _persist_to_agentcore_memory(debate_id: str, user_context: dict, transcript: list, verdict: str):
    """Fire-and-forget: save debate to AgentCore Memory in a background thread."""
    try:
        from app.agentcore import save_debate_to_memory
        user_id = user_context.get("user_id", "anonymous")
        t = threading.Thread(
            target=save_debate_to_memory,
            args=(debate_id, user_id, user_context, transcript, verdict),
            daemon=True,
        )
        t.start()
    except Exception as e:
        logger.debug("AgentCore Memory persistence skipped: %s", e)


def run_debate(user_context: dict) -> DebateResponse:
    """Run the complete 5-round debate synchronously.

    Returns the full DebateResponse with transcript, verdict, and metrics.
    Takes 60-120 seconds.
    """
    debate_id = str(uuid.uuid4())
    transcript: list[RoundResult] = []
    all_metrics: list[RoundMetrics | None] = []
    prev_beta = None
    debate_summary = ""

    category = detect_decision_category(
        user_context["path_a"],
        user_context["path_b"],
        constraints=user_context.get("constraints"),
        writing_samples=user_context.get("writing_samples"),
        template_id=user_context.get("template_id"),
    )
    user_context["debate_id"] = debate_id
    user_context["_category"] = category
    build_grounding_context(user_context, category)
    alpha_persona, beta_persona = _assign_personas(user_context["path_a"], user_context["path_b"])
    rounds = get_rounds(category)
    tools = TOOL_MAP.get(category, [research_insight])

    logger.info(
        f"Starting debate {debate_id}: {user_context['path_a']} vs {user_context['path_b']} "
        f"(category={category}, alpha={alpha_persona['label']}, beta={beta_persona['label']})"
    )
    start_time = time.time()

    for i, round_info in enumerate(rounds):
        logger.info(f"Debate {debate_id}: Starting round {i + 1} ({round_info['name']})")
        result = _run_round(round_info, user_context, prev_beta, i, transcript, debate_summary, tools, alpha_persona, beta_persona)
        transcript.append(result)
        all_metrics.append(result.metrics)
        prev_beta = result.beta if result.status == "completed" else prev_beta

        if result.status == "completed":
            debate_summary += f"\n[Round {i + 1} - {round_info['name']}]\n"
            debate_summary += f"Path A argued: {result.alpha[:400]}...\n"
            debate_summary += f"Path B argued: {result.beta[:400]}...\n"

        logger.info(f"Debate {debate_id}: Round {i + 1} {result.status}")

    completed = [r for r in transcript if r.status == "completed"]
    timeline = None
    if len(completed) >= 3:
        with ThreadPoolExecutor(max_workers=3) as pool:
            verdict_future = pool.submit(_generate_verdict, transcript, user_context)
            timeline_future = pool.submit(_generate_structured_timeline, transcript, user_context)
            resources_future = pool.submit(_get_resources, user_context)
            verdict = verdict_future.result()
            timeline = timeline_future.result()
            resources = resources_future.result()
    elif len(completed) >= 1:
        verdict = (
            f"Only {len(completed)} of 5 rounds completed successfully. "
            "The AI service may be experiencing high demand. "
            "Here's a partial analysis based on available rounds."
        )
        resources = _get_resources(user_context)
    else:
        verdict = "The debate could not be completed. Please check your AWS credentials and Bedrock model access, then try again."
        resources = _get_resources(user_context)

    elapsed = time.time() - start_time
    logger.info(f"Debate {debate_id} finished in {elapsed:.1f}s ({len(completed)}/{len(rounds)} rounds, category={category})")
    logger.info("Content guardrail stats debate_id=%s stats=%s", debate_id, _guardrail_stats(user_context))

    response = DebateResponse(
        debate_id=debate_id,
        transcript=transcript,
        verdict=verdict,
        timeline=timeline,
        metrics=all_metrics,
        completed_rounds=len(completed),
        total_rounds=len(rounds),
        resources=resources,
    )

    _persist_to_agentcore_memory(debate_id, user_context, transcript, verdict)

    return response


def run_debate_streaming(user_context: dict):
    """Generator that yields debate events one round at a time.

    Yields dicts: {"type": "round", "data": {...}} for each round,
    then {"type": "complete", ...} with verdict and metadata.
    """
    debate_id = str(uuid.uuid4())
    transcript: list[RoundResult] = []
    all_metrics: list[RoundMetrics | None] = []
    prev_beta = None
    debate_summary = ""

    category = detect_decision_category(
        user_context["path_a"],
        user_context["path_b"],
        constraints=user_context.get("constraints"),
        writing_samples=user_context.get("writing_samples"),
        template_id=user_context.get("template_id"),
    )
    user_context["debate_id"] = debate_id
    user_context["_category"] = category
    build_grounding_context(user_context, category)
    alpha_persona, beta_persona = _assign_personas(user_context["path_a"], user_context["path_b"])
    rounds = get_rounds(category)
    tools = TOOL_MAP.get(category, [research_insight])

    logger.info(
        f"Starting streaming debate {debate_id}: {user_context['path_a']} vs {user_context['path_b']} "
        f"(category={category})"
    )
    start_time = time.time()

    for i, round_info in enumerate(rounds):
        logger.info(f"Streaming debate {debate_id}: round {i + 1}")
        result = _run_round(round_info, user_context, prev_beta, i, transcript, debate_summary, tools, alpha_persona, beta_persona)
        transcript.append(result)
        all_metrics.append(result.metrics)
        prev_beta = result.beta if result.status == "completed" else prev_beta

        if result.status == "completed":
            debate_summary += f"\n[Round {i + 1}]\n"
            debate_summary += f"Path A: {result.alpha[:400]}...\n"
            debate_summary += f"Path B: {result.beta[:400]}...\n"

        yield {"type": "round", "data": result.model_dump()}

    completed = [r for r in transcript if r.status == "completed"]
    timeline = None
    if len(completed) >= 3:
        verdict = _generate_verdict(transcript, user_context)
        timeline = _generate_structured_timeline(transcript, user_context)
    elif len(completed) >= 1:
        verdict = f"Only {len(completed)} of 5 rounds completed. Partial analysis."
    else:
        verdict = "The debate could not be completed."

    elapsed = time.time() - start_time
    logger.info(f"Streaming debate {debate_id} finished in {elapsed:.1f}s")

    resources = _get_resources(user_context)

    yield {
        "type": "complete",
        "verdict": verdict,
        "timeline": timeline.model_dump() if timeline else None,
        "debate_id": debate_id,
        "metrics": [m.model_dump() if m else None for m in all_metrics],
        "completed_rounds": len(completed),
        "total_rounds": len(rounds),
        "resources": [r.model_dump() for r in resources],
    }


def _run_round_split(
    round_info: dict,
    user_ctx: dict,
    prev_beta: str | None,
    round_num: int,
    transcript: list[RoundResult] | None,
    debate_summary: str,
    tools: list,
    alpha_persona: dict,
    beta_persona: dict,
    interjection: str | None = None,
):
    """Like _run_round but yields alpha as soon as it's ready, then beta, then the final RoundResult.

    Emits tuples: ('alpha', text), ('beta', text), ('result', RoundResult).
    Keeps the same guardrail/retry/fallback semantics as _run_round; the only
    behavioral difference is that alpha no longer waits for beta before being
    returned to the caller.
    """
    chronology_guardrail = _build_chronology_guardrail(user_ctx, round_info, round_num)
    alpha_system_prompt = _build_round_system_prompt(
        build_alpha_prompt(user_ctx, round_info, alpha_persona),
        user_ctx,
        round_info,
        round_num,
        "Alpha",
    )
    path_a = user_ctx["path_a"]
    path_b = user_ctx["path_b"]
    timeline = round_info.get("timeline", f"round {round_num + 1}")

    if round_num == 0:
        alpha_input = (
            f"{chronology_guardrail}\n\n"
            f"You chose \"{path_a}\". You are living in {timeline} right now. "
            f"Do NOT use the phrase \"I remember\" or tell this in the past tense. "
            f"Speak from one emotionally loaded moment that makes this reality feel current, physical, and concrete. "
            f"Do not trap the rest of the timeline inside this exact room or trivial detail."
        )
    else:
        alpha_input = _build_runtime_wrapper_prompt(
            debate_summary=debate_summary,
            interjection=interjection,
            path=path_a,
            timeline=timeline,
            prev_response=prev_beta or "",
            chronology_guardrail=chronology_guardrail,
        )

    alpha_response = ""
    for attempt in range(MAX_RETRIES):
        try:
            alpha_response = _generate_with_guardrails(
                user_ctx=user_ctx,
                transcript=transcript,
                content_kind="round",
                stage_label=f"round_{round_num + 1}.alpha",
                fallback_text=_build_round_fallback_text(path_a, timeline, user_ctx.get("_category", "")),
                generator=lambda rewrite_instruction: validate_safe_content(
                    validate_agent_output(
                        _safe_agent_output(
                            Agent(
                                model=_make_model(persona_label=alpha_persona["label"]),
                                system_prompt=alpha_system_prompt,
                                tools=tools,
                            )(_append_rewrite_instruction(alpha_input, rewrite_instruction))
                        )
                    )
                ),
            )
            if not alpha_response:
                raise ValueError("Alpha agent returned empty response")
            break
        except Exception as e:
            logger.warning(f"Round {round_num + 1} alpha attempt {attempt + 1} failed: {type(e).__name__}: {e}")
            if not _is_retryable(e):
                logger.error(f"Round {round_num + 1} alpha hit non-retryable error, skipping: {e}")
                break
            if attempt < MAX_RETRIES - 1:
                delay = _backoff_with_jitter(attempt)
                logger.info(f"Retrying round {round_num + 1} alpha in {delay:.1f}s...")
                time.sleep(delay)

    alpha_failed = not alpha_response
    if alpha_failed:
        alpha_response = "This perspective could not be generated. The AI service may be temporarily unavailable."

    yield ("alpha", alpha_response)

    beta_response = ""
    if not alpha_failed:
        beta_system_prompt = _build_round_system_prompt(
            build_beta_prompt(user_ctx, round_info, beta_persona),
            user_ctx,
            round_info,
            round_num,
            "Beta",
        )
        beta_input = _build_runtime_wrapper_prompt(
            debate_summary=debate_summary,
            interjection=interjection,
            path=path_b,
            timeline=timeline,
            prev_response=alpha_response,
            chronology_guardrail=chronology_guardrail,
        )

        for attempt in range(MAX_RETRIES):
            try:
                beta_response = _generate_with_guardrails(
                    user_ctx=user_ctx,
                    transcript=transcript,
                    extra_prior_texts=[alpha_response],
                    content_kind="round",
                    stage_label=f"round_{round_num + 1}.beta",
                    fallback_text=_build_round_fallback_text(path_b, timeline, user_ctx.get("_category", "")),
                    generator=lambda rewrite_instruction: validate_safe_content(
                        validate_agent_output(
                            _safe_agent_output(
                                Agent(
                                    model=_make_model(persona_label=beta_persona["label"]),
                                    system_prompt=beta_system_prompt,
                                    tools=tools,
                                )(_append_rewrite_instruction(beta_input, rewrite_instruction))
                            )
                        )
                    ),
                )
                if not beta_response:
                    raise ValueError("Beta agent returned empty response")
                break
            except Exception as e:
                logger.warning(f"Round {round_num + 1} beta attempt {attempt + 1} failed: {type(e).__name__}: {e}")
                if not _is_retryable(e):
                    logger.error(f"Round {round_num + 1} beta hit non-retryable error, skipping: {e}")
                    break
                if attempt < MAX_RETRIES - 1:
                    delay = _backoff_with_jitter(attempt)
                    logger.info(f"Retrying round {round_num + 1} beta in {delay:.1f}s...")
                    time.sleep(delay)

    beta_failed = not beta_response
    if beta_failed:
        beta_response = "This perspective could not be generated. The AI service may be temporarily unavailable."

    yield ("beta", beta_response)

    status = "completed" if (not alpha_failed and not beta_failed) else "partial"
    metrics = None
    sentiment = None
    if status == "completed":
        debate_text = f"Path A argued:\n{alpha_response}\n\nPath B argued:\n{beta_response}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            metrics_future = pool.submit(extract_metrics, debate_text)
            sentiment_future = pool.submit(analyze_round_sentiment, alpha_response, beta_response)
            metrics = metrics_future.result()
            sentiment = sentiment_future.result()
        _log_debug_round_trace(round_num + 1, round_info["name"], alpha_response, beta_response)

    result = RoundResult(
        round_number=round_num + 1,
        round_name=round_info["name"],
        round_title=round_info["title"],
        alpha=alpha_response,
        beta=beta_response,
        metrics=metrics,
        sentiment=sentiment,
        status=status,
    )
    yield ("result", result)


def _stream_single_round(
    round_index: int,
    round_info: dict,
    user_context: dict,
    transcript: list[RoundResult],
    prev_beta: str | None,
    debate_summary: str,
    interjection: str | None,
    tools: list,
    alpha_persona: dict,
    beta_persona: dict,
):
    """Generator that streams one round of Alpha→Beta debate with token events.

    Yields: round_start, token, agent_done, round_complete events.
    Returns: (RoundResult, updated_debate_summary) via generator return value.
    Caller uses: result, summary = yield from _stream_single_round(...)
    """
    i = round_index

    yield {
        "type": "round_start",
        "round": i + 1,
        "round_name": round_info["name"],
        "round_title": round_info["title"],
    }

    result: RoundResult | None = None
    for phase, payload in _run_round_split(
        round_info,
        user_context,
        prev_beta,
        i,
        transcript,
        debate_summary,
        tools,
        alpha_persona,
        beta_persona,
        interjection=interjection,
    ):
        if phase == "alpha":
            if payload:
                for event in _iter_stream_events_for_text(
                    payload,
                    event_type="token",
                    agent="alpha",
                    round_num=i + 1,
                ):
                    yield event
            yield {"type": "agent_done", "agent": "alpha", "round": i + 1}
        elif phase == "beta":
            if payload:
                for event in _iter_stream_events_for_text(
                    payload,
                    event_type="token",
                    agent="beta",
                    round_num=i + 1,
                ):
                    yield event
            yield {"type": "agent_done", "agent": "beta", "round": i + 1}
        elif phase == "result":
            result = payload

    assert result is not None

    updated_summary = debate_summary
    if result.status == "completed":
        updated_summary += f"\n[Round {i + 1} - {round_info['name']}]\n"
        updated_summary += f"Path A argued: {result.alpha[:400]}...\n"
        updated_summary += f"Path B argued: {result.beta[:400]}...\n"

    yield {
        "type": "round_complete",
        "round": i + 1,
        "data": result.model_dump(),
    }

    return result, updated_summary


def run_debate_token_streaming(user_context: dict):
    """Generator yielding token-level events for real-time UI streaming.

    Event types:
      {"type": "round_start", "round": N, "round_name": str, "round_title": str}
      {"type": "token", "agent": "alpha"|"beta", "round": N, "text": str}
      {"type": "agent_done", "agent": "alpha"|"beta", "round": N}
      {"type": "round_complete", "round": N, "data": {...}, "metrics": {...}}
      {"type": "verdict_start"}
      {"type": "verdict_token", "text": str}
      {"type": "complete", "verdict": str, ...}
    """
    debate_id = str(uuid.uuid4())
    transcript: list[RoundResult] = []
    all_metrics: list[RoundMetrics | None] = []
    prev_beta = None
    debate_summary = ""

    category = detect_decision_category(
        user_context["path_a"],
        user_context["path_b"],
        constraints=user_context.get("constraints"),
        writing_samples=user_context.get("writing_samples"),
        template_id=user_context.get("template_id"),
    )
    user_context["debate_id"] = debate_id
    user_context["_category"] = category
    build_grounding_context(user_context, category)
    alpha_persona, beta_persona = _assign_personas(user_context["path_a"], user_context["path_b"])
    rounds = get_rounds(category)
    tools = TOOL_MAP.get(category, [research_insight])

    logger.info(
        f"Starting token-streaming debate {debate_id}: {user_context['path_a']} vs {user_context['path_b']} "
        f"(category={category})"
    )
    start_time = time.time()

    yield {
        "type": "debate_start",
        "debate_id": debate_id,
        "total_rounds": len(rounds),
    }

    for i, round_info in enumerate(rounds):
        logger.info(f"Token-streaming debate {debate_id}: round {i + 1}")

        interjection = _pop_interjection(debate_id) if i > 0 else None
        if interjection:
            debate_summary += f"\n[User interjects]: {interjection}\n"
            user_context.setdefault("_interjections", []).append(interjection)
            yield {
                "type": "interjection",
                "round": i + 1,
                "text": interjection,
            }

        result, debate_summary = yield from _stream_single_round(
            round_index=i,
            round_info=round_info,
            user_context=user_context,
            transcript=transcript,
            prev_beta=prev_beta,
            debate_summary=debate_summary,
            interjection=interjection,
            tools=tools,
            alpha_persona=alpha_persona,
            beta_persona=beta_persona,
        )

        transcript.append(result)
        all_metrics.append(result.metrics)
        prev_beta = result.beta if result.status == "completed" else prev_beta

    # --- Verdict with streaming ---
    completed = [r for r in transcript if r.status == "completed"]
    timeline = None
    if len(completed) >= 3:
        yield {"type": "verdict_start"}
        verdict = _generate_verdict(transcript, user_context)
        for event in _iter_stream_events_for_text(verdict, event_type="verdict_token"):
            yield event
        timeline = _generate_structured_timeline(transcript, user_context)
    elif len(completed) >= 1:
        verdict = f"Only {len(completed)} of 5 rounds completed. Partial analysis."
    else:
        verdict = "The debate could not be completed."

    elapsed = time.time() - start_time
    logger.info(f"Token-streaming debate {debate_id} finished in {elapsed:.1f}s")

    resources = _get_resources(user_context)

    yield {
        "type": "complete",
        "verdict": verdict,
        "timeline": timeline.model_dump() if timeline else None,
        "debate_id": debate_id,
        "metrics": [m.model_dump() if m else None for m in all_metrics],
        "completed_rounds": len(completed),
        "total_rounds": len(rounds),
        "resources": [r.model_dump() for r in resources],
    }

    _persist_to_agentcore_memory(debate_id, user_context, transcript, verdict)
