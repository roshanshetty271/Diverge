"""Debate orchestrator — runs the 5-round structured debate.

Edge cases handled:
- Model throttling → longer backoff + jitter
- Model timeout → retry
- Validation errors → no retry (same input will fail again)
- Agent returning empty/None → explicit fallback text
- Verdict output validated for prompt leakage

Supports both OpenAI and Bedrock via DIVERGE_MODEL_PROVIDER setting.
Token-level streaming supported via QueueCallbackHandler.
"""

import re
import json
import uuid
import time
import random
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from strands import Agent

from app.config import get_settings
from app.agents.prompts import (
    get_rounds, detect_decision_category,
    build_alpha_prompt, build_beta_prompt, build_verdict_prompt, build_timeline_simulator_prompt,
    PERSONA_CHALLENGER, PERSONA_DEFENDER, PERSONA_EQUAL,
)
from app.agents.metrics import extract_metrics
from app.schemas import (
    DebateResponse,
    Resource,
    RoundMetrics,
    RoundResult,
    StructuredTimeline,
    TimelineExploreItem,
)
from app.tools.monte_carlo import monte_carlo_financial
from app.tools.data_tools import get_salary_data, compare_cost_of_living, calculate_runway
from app.tools.knowledge import research_insight
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
    (re.compile(r"\bnavigate(?:d|s)?\s+(?:the\s+)?(?:challenges?|complexit(?:y|ies)|landscape)", re.I), "deal with it"),
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


class QueueCallbackHandler:
    """Callback handler that pushes tokens into a thread-safe queue for SSE streaming."""

    def __init__(self, token_queue: queue.Queue, agent_label: str, round_num: int):
        self.q = token_queue
        self.agent_label = agent_label
        self.round_num = round_num

    def __call__(self, **kwargs: Any) -> None:
        data = kwargs.get("data", "")
        if data:
            self.q.put({
                "type": "token",
                "agent": self.agent_label,
                "round": self.round_num,
                "text": data,
            })


def _make_model(max_tokens: int | None = None, temperature: float | None = None):
    """Create a model instance based on the configured provider (openai or bedrock)."""
    s = get_settings()
    tokens = max_tokens or s.debate_max_tokens
    temp = temperature if temperature is not None else s.debate_temperature

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

    return (
        "CHRONOLOGY ENFORCEMENT - FOLLOW THIS EXACTLY:\n"
        f"- This round takes place {jump_label}. Treat the lived moment as {timeline}.\n"
        f"{age_line}\n"
        f"{setting_line}\n"
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
    """Force the agent to weaponize or defend the widening timeline gap explicitly."""
    elapsed_window = _get_chronological_awareness_window(round_num)

    if agent_name.lower() == "alpha":
        agent_specific_rule = (
            f'- If you are Alpha, you must weaponize the timeline. Contrast your compounding growth over the last {elapsed_window} '
            "with Beta's stagnation. "
            "(e.g., 'It has been 3 years now. Look at what my choice built, while you are still stuck where we started.')"
        )
    else:
        agent_specific_rule = (
            f"- If you are Beta, you must defend your long-term reality based on the time passed, or express the compounding regret of the last {elapsed_window}."
        )

    return (
        "CHRONOLOGICAL AWARENESS:\n"
        "You must actively acknowledge the passage of time in your argument. Do not just describe your current state; "
        "you must explicitly reference how much time has passed since the decision was made.\n"
        f"{agent_specific_rule}\n"
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
        "Name the illusion they are clinging to or the hidden cost they are ignoring in that specific moment.\n"
        f"2. Then, pivot to YOUR reality right now at {timeline}.\n"
        f'3. CRITICAL TIME RULE: Do NOT use the phrase "I remember" or tell a story in the past tense. '
        f"You are living this moment RIGHT NOW in {timeline}. Make it visceral. "
        "What are you looking at? What do you feel in your body?\n"
        "4. CRITICAL SETTING RULE: You may not remain in the exact physical setting from a previous round. "
        "Change the environment to prove time has passed.\n"
        "5. CRITICAL DETAIL RULE: Drop trivial old details like clothes or exact rooms from earlier rounds. "
        "Focus on the long-term compounding consequences."
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


def _resource_candidate_signature(resource: dict | TimelineExploreItem) -> tuple[str, str, str, str]:
    """Normalize a candidate resource into a stable comparison key."""
    if isinstance(resource, TimelineExploreItem):
        return (
            resource.type.strip().lower(),
            resource.title.strip(),
            resource.author.strip(),
            resource.url.strip(),
        )

    return (
        str(resource.get("type", "")).strip().lower(),
        str(resource.get("title", "")).strip(),
        str(resource.get("author", "")).strip(),
        str(resource.get("url", "")).strip(),
    )


def _format_candidates_for_prompt(candidates: list[dict]) -> str:
    """Serialize the vetted candidate list into a compact prompt-friendly JSON string."""
    prompt_candidates = [
        {
            "type": candidate["type"],
            "title": candidate["title"],
            "author": candidate["author"],
            "url": candidate["url"],
            "catalog_why": candidate["why"],
        }
        for candidate in candidates
    ]
    return json.dumps(prompt_candidates, indent=2, ensure_ascii=False)


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


def _finalize_structured_timeline(
    timeline: StructuredTimeline,
    user_ctx: dict,
    candidates: list[dict],
) -> StructuredTimeline:
    """Validate stage-06 selections against vetted candidates and repair with fallback if needed."""
    fallback_items = _build_stage06_fallback(user_ctx)
    candidate_map = {_resource_candidate_signature(candidate): candidate for candidate in candidates}
    valid_types = {"book", "video", "concept"}

    items = list(timeline.stage_06_what_to_explore_next or [])
    if len(items) != 3 or {item.type for item in items} != valid_types:
        return timeline.model_copy(update={"stage_06_what_to_explore_next": fallback_items})

    type_order = {"book": 0, "video": 1, "concept": 2}
    normalized_items: list[TimelineExploreItem] = []

    for item in sorted(items, key=lambda current: type_order.get(current.type, 99)):
        key = _resource_candidate_signature(item)
        candidate = candidate_map.get(key)
        if not candidate or not item.why_it_helps.strip():
            return timeline.model_copy(update={"stage_06_what_to_explore_next": fallback_items})

        normalized_items.append(
            TimelineExploreItem(
                type=item.type,
                title=candidate["title"],
                author=candidate["author"],
                why_it_helps=item.why_it_helps.strip(),
                url=candidate["url"],
            )
        )

    return timeline.model_copy(update={"stage_06_what_to_explore_next": normalized_items})


def _generate_structured_timeline(transcript: list[RoundResult], user_ctx: dict) -> StructuredTimeline | None:
    """Generate the strict timeline JSON used by the verdict timeline UI."""
    full_text = _format_transcript_for_llm(transcript, user_ctx)
    if not full_text:
        return None

    from app.data.resources import shortlist_resource_candidates

    candidates = shortlist_resource_candidates(
        user_ctx.get("path_a", ""),
        user_ctx.get("path_b", ""),
        user_ctx.get("constraints"),
        max_candidates=12,
    )
    prompt = build_timeline_simulator_prompt(
        user_ctx,
        full_text,
        _format_candidates_for_prompt(candidates),
    )
    settings = get_settings()

    for attempt in range(2):
        try:
            if settings.model_provider == "openai":
                from openai import OpenAI

                client = OpenAI(api_key=settings.openai_api_key)
                completion = client.beta.chat.completions.parse(
                    model=settings.debate_model_id,
                    temperature=0.4,
                    max_completion_tokens=1800,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": "Generate the structured timeline JSON now."},
                    ],
                    response_format=StructuredTimeline,
                )
                parsed = completion.choices[0].message.parsed
                if parsed:
                    return _finalize_structured_timeline(parsed, user_ctx, candidates)
            else:
                timeline_agent = Agent(
                    model=_make_model(max_tokens=1800, temperature=0.4),
                    system_prompt=prompt,
                )
                raw = timeline_agent("Generate the structured timeline JSON now.")
                parsed = StructuredTimeline.model_validate_json(_strip_json_fences(str(raw)))
                return _finalize_structured_timeline(parsed, user_ctx, candidates)
        except Exception as e:
            logger.error("Structured timeline generation attempt %s failed: %s", attempt + 1, e)
            if attempt < 1:
                time.sleep(1.5)

    return None


def _run_round(
    round_info: dict,
    user_ctx: dict,
    prev_beta: str | None,
    round_num: int,
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
            alpha_agent = Agent(
                model=_make_model(),
                system_prompt=_build_round_system_prompt(
                    build_alpha_prompt(user_ctx, round_info, alpha_persona),
                    user_ctx,
                    round_info,
                    round_num,
                    "Alpha",
                ),
                tools=tools,
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
            raw_alpha = alpha_agent(alpha_input)
            alpha_response = validate_safe_content(validate_agent_output(_safe_agent_output(raw_alpha)))

            if not alpha_response:
                raise ValueError("Alpha agent returned empty response")

            beta_agent = Agent(
                model=_make_model(),
                system_prompt=_build_round_system_prompt(
                    build_beta_prompt(user_ctx, round_info, beta_persona),
                    user_ctx,
                    round_info,
                    round_num,
                    "Beta",
                ),
                tools=tools,
            )
            raw_beta = beta_agent(
                _build_runtime_wrapper_prompt(
                    debate_summary=debate_summary,
                    interjection=interjection,
                    path=path_b,
                    timeline=timeline,
                    prev_response=alpha_response,
                    chronology_guardrail=chronology_guardrail,
                )
            )
            beta_response = validate_safe_content(validate_agent_output(_safe_agent_output(raw_beta)))

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

    for attempt in range(2):
        try:
            verdict_agent = Agent(
                model=_make_model(max_tokens=2048, temperature=0.6),
                system_prompt=prompt,
            )
            raw = verdict_agent("Give your verdict now.")
            result = validate_safe_content(validate_agent_output(_safe_agent_output(raw)))
            if result:
                return result
        except Exception as e:
            logger.error(f"Verdict generation attempt {attempt + 1} failed: {e}")
            if attempt < 1:
                time.sleep(2)

    return "The verdict could not be generated. Please review the debate rounds above."


def _get_resources(user_context: dict) -> list[Resource]:
    """Get diversified deterministic fallback resources for the current user context."""
    try:
        from app.data.resources import get_rotating_fallback_resources

        raw = get_rotating_fallback_resources(
            user_context.get("path_a", ""),
            user_context.get("path_b", ""),
            user_context.get("constraints"),
            max_items=3,
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

    category = detect_decision_category(user_context["path_a"], user_context["path_b"])
    user_context["_category"] = category
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
        result = _run_round(round_info, user_context, prev_beta, i, debate_summary, tools, alpha_persona, beta_persona)
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
        verdict = _generate_verdict(transcript, user_context)
        timeline = _generate_structured_timeline(transcript, user_context)
    elif len(completed) >= 1:
        verdict = (
            f"Only {len(completed)} of 5 rounds completed successfully. "
            "The AI service may be experiencing high demand. "
            "Here's a partial analysis based on available rounds."
        )
    else:
        verdict = "The debate could not be completed. Please check your AWS credentials and Bedrock model access, then try again."

    elapsed = time.time() - start_time
    logger.info(f"Debate {debate_id} finished in {elapsed:.1f}s ({len(completed)}/{len(rounds)} rounds, category={category})")

    resources = _get_resources(user_context)

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

    category = detect_decision_category(user_context["path_a"], user_context["path_b"])
    user_context["_category"] = category
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
        result = _run_round(round_info, user_context, prev_beta, i, debate_summary, tools, alpha_persona, beta_persona)
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


def _run_agent_with_streaming(
    system_prompt: str,
    user_input: str,
    tools: list,
    token_queue: queue.Queue,
    agent_label: str,
    round_num: int,
) -> str:
    """Run an agent with a streaming callback, returning the full response text."""
    handler = QueueCallbackHandler(token_queue, agent_label, round_num)
    agent = Agent(
        model=_make_model(),
        system_prompt=system_prompt,
        tools=tools,
        callback_handler=handler,
    )
    raw = agent(user_input)
    return _safe_agent_output(raw)


def _stream_single_round(
    round_index: int,
    round_info: dict,
    user_context: dict,
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

    path_a = user_context["path_a"]
    path_b = user_context["path_b"]
    timeline = round_info.get("timeline", f"round {i + 1}")
    chronology_guardrail = _build_chronology_guardrail(user_context, round_info, i)

    token_q: queue.Queue = queue.Queue()
    alpha_response = ""
    beta_response = ""

    if i == 0:
        alpha_input = (
            f"{chronology_guardrail}\n\n"
            f'You chose "{path_a}". You are living in {timeline} right now. '
            f'Do NOT use the phrase "I remember" or tell this in the past tense. '
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

    try:
        alpha_result_holder: list[str] = []
        alpha_error_holder: list[Exception] = []

        def run_alpha():
            try:
                text = _run_agent_with_streaming(
                    _build_round_system_prompt(
                        build_alpha_prompt(user_context, round_info, alpha_persona),
                        user_context,
                        round_info,
                        i,
                        "Alpha",
                    ),
                    alpha_input, tools, token_q, "alpha", i + 1,
                )
                alpha_result_holder.append(text)
            except Exception as e:
                alpha_error_holder.append(e)
            finally:
                token_q.put({"type": "_done"})

        thread = threading.Thread(target=run_alpha, daemon=True)
        thread.start()

        while True:
            try:
                event = token_q.get(timeout=180)
            except queue.Empty:
                break
            if event.get("type") == "_done":
                break
            yield event

        thread.join(timeout=5)

        if alpha_error_holder:
            raise alpha_error_holder[0]
        alpha_response = validate_safe_content(
            validate_agent_output(alpha_result_holder[0] if alpha_result_holder else "")
        )
        if not alpha_response:
            raise ValueError("Alpha agent returned empty response")

        yield {"type": "agent_done", "agent": "alpha", "round": i + 1}

        beta_q: queue.Queue = queue.Queue()
        beta_input = _build_runtime_wrapper_prompt(
            debate_summary=debate_summary,
            interjection=interjection,
            path=path_b,
            timeline=timeline,
            prev_response=alpha_response,
            chronology_guardrail=chronology_guardrail,
        )

        beta_result_holder: list[str] = []
        beta_error_holder: list[Exception] = []

        def run_beta():
            try:
                text = _run_agent_with_streaming(
                    _build_round_system_prompt(
                        build_beta_prompt(user_context, round_info, beta_persona),
                        user_context,
                        round_info,
                        i,
                        "Beta",
                    ),
                    beta_input, tools, beta_q, "beta", i + 1,
                )
                beta_result_holder.append(text)
            except Exception as e:
                beta_error_holder.append(e)
            finally:
                beta_q.put({"type": "_done"})

        beta_thread = threading.Thread(target=run_beta, daemon=True)
        beta_thread.start()

        while True:
            try:
                event = beta_q.get(timeout=180)
            except queue.Empty:
                break
            if event.get("type") == "_done":
                break
            yield event

        beta_thread.join(timeout=5)

        if beta_error_holder:
            raise beta_error_holder[0]
        beta_response = validate_safe_content(
            validate_agent_output(beta_result_holder[0] if beta_result_holder else "")
        )
        if not beta_response:
            raise ValueError("Beta agent returned empty response")

        yield {"type": "agent_done", "agent": "beta", "round": i + 1}

        debate_text = f"Path A argued:\n{alpha_response}\n\nPath B argued:\n{beta_response}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            metrics_future = pool.submit(extract_metrics, debate_text)
            sentiment_future = pool.submit(analyze_round_sentiment, alpha_response, beta_response)
            metrics = metrics_future.result()
            sentiment = sentiment_future.result()

        result = RoundResult(
            round_number=i + 1,
            round_name=round_info["name"],
            round_title=round_info["title"],
            alpha=alpha_response,
            beta=beta_response,
            metrics=metrics,
            sentiment=sentiment,
            status="completed",
        )
        _log_debug_round_trace(i + 1, round_info["name"], alpha_response, beta_response)

    except Exception as e:
        logger.warning(f"Token-streaming round {i + 1} failed: {type(e).__name__}: {e}")
        result = RoundResult(
            round_number=i + 1,
            round_name=round_info["name"],
            round_title=round_info["title"],
            alpha=alpha_response or "This perspective could not be generated.",
            beta=beta_response or "This perspective could not be generated.",
            metrics=None,
            status="partial",
        )

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

    category = detect_decision_category(user_context["path_a"], user_context["path_b"])
    user_context["_category"] = category
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
            yield {
                "type": "interjection",
                "round": i + 1,
                "text": interjection,
            }

        result, debate_summary = yield from _stream_single_round(
            round_index=i,
            round_info=round_info,
            user_context=user_context,
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
        verdict_q: queue.Queue = queue.Queue()

        verdict_text_holder: list[str] = []

        def run_verdict():
            try:
                full_text = ""
                for r in transcript:
                    if r.status == "completed":
                        full_text += f"\n--- Round {r.round_number}: {r.round_title} ---\n"
                        full_text += f"Path A ({user_context['path_a']}): {r.alpha}\n"
                        full_text += f"Path B ({user_context['path_b']}): {r.beta}\n"

                prompt = build_verdict_prompt(user_context, full_text)
                handler = QueueCallbackHandler(verdict_q, "verdict", 0)
                verdict_agent = Agent(
                    model=_make_model(max_tokens=2048, temperature=0.6),
                    system_prompt=prompt,
                    callback_handler=handler,
                )
                raw = verdict_agent("Give your verdict now.")
                text = validate_safe_content(validate_agent_output(_safe_agent_output(raw)))
                verdict_text_holder.append(text or "The verdict could not be generated.")
            except Exception as e:
                logger.error(f"Token-streaming verdict failed: {e}")
                verdict_text_holder.append("The verdict could not be generated. Please review the debate rounds above.")
            finally:
                verdict_q.put({"type": "_done"})

        v_thread = threading.Thread(target=run_verdict, daemon=True)
        v_thread.start()

        while True:
            try:
                event = verdict_q.get(timeout=180)
            except queue.Empty:
                break
            if event.get("type") == "_done":
                break
            if event.get("type") == "token":
                yield {"type": "verdict_token", "text": event["text"]}

        v_thread.join(timeout=5)
        verdict = verdict_text_holder[0] if verdict_text_holder else "The verdict could not be generated."
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
