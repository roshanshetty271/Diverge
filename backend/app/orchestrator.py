"""Debate orchestrator — runs the 5-round structured debate.

Edge cases handled:
- Model throttling → longer backoff + jitter
- Model timeout → retry
- Validation errors → no retry (same input will fail again)
- Agent returning empty/None → explicit fallback text
- Verdict output validated for prompt leakage

Supports both OpenAI and Bedrock via DIVERGE_MODEL_PROVIDER setting.
"""

import uuid
import time
import random
import logging
from strands import Agent

from app.config import get_settings
from app.agents.prompts import (
    get_rounds, detect_decision_category, detect_brave_path,
    build_alpha_prompt, build_beta_prompt, build_verdict_prompt,
    PERSONA_CHALLENGER, PERSONA_DEFENDER, PERSONA_EQUAL,
)
from app.agents.metrics import extract_metrics
from app.schemas import RoundResult, RoundMetrics, DebateResponse
from app.tools.monte_carlo import monte_carlo_financial
from app.tools.data_tools import get_salary_data, compare_cost_of_living, calculate_runway
from app.tools.knowledge import research_insight
from app.security.llm_security import validate_agent_output, validate_safe_content

logger = logging.getLogger(__name__)

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
        return BedrockModel(
            model_id=s.debate_model_id,
            region_name=s.aws_region,
            max_tokens=tokens,
            temperature=temp,
            boto_client_config=boto_config,
        )


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
    """Safely convert agent output to string, handling None/empty."""
    text = str(result) if result is not None else ""
    if text in ("None", "null", ""):
        return ""
    return text.strip()


def _assign_personas(brave: str, user_ctx: dict) -> tuple[dict, dict]:
    """Assign personas to alpha (path_a) and beta (path_b) based on bravery detection.

    For neutral decisions: devil's advocate if no values, values-based if values exist.
    """
    if brave == "a":
        return PERSONA_CHALLENGER, PERSONA_DEFENDER
    if brave == "b":
        return PERSONA_DEFENDER, PERSONA_CHALLENGER

    values = user_ctx.get("values") or ""
    if values:
        return PERSONA_EQUAL, PERSONA_EQUAL

    # No values, neutral paths: beta plays devil's advocate (challenges path_a, which
    # the user likely leans toward since they listed it first)
    return PERSONA_EQUAL, PERSONA_CHALLENGER


def _run_round(
    round_info: dict,
    user_ctx: dict,
    prev_beta: str | None,
    round_num: int,
    debate_summary: str,
    tools: list,
    alpha_persona: dict,
    beta_persona: dict,
) -> RoundResult:
    """Execute one debate round with smart retry logic."""
    alpha_response = ""
    beta_response = ""

    summary_prefix = f"DEBATE SO FAR:\n{debate_summary}\n\n" if debate_summary else ""

    for attempt in range(MAX_RETRIES):
        try:
            alpha_agent = Agent(
                model=_make_model(),
                system_prompt=build_alpha_prompt(user_ctx, round_info, alpha_persona),
                tools=tools,
            )
            path_a = user_ctx["path_a"]
            path_b = user_ctx["path_b"]
            timeline = round_info.get("timeline", f"round {round_num + 1}")

            if round_num == 0:
                alpha_input = (
                    f"{summary_prefix}"
                    f"You chose \"{path_a}\". It's {timeline}. "
                    f"Give your opening statement — what happened?"
                )
            else:
                alpha_input = (
                    f"{summary_prefix}"
                    f"You chose \"{path_a}\". It's now {timeline}.\n\n"
                    f"The version of you who chose \"{path_b}\" just said:\n\n"
                    f"\"{prev_beta}\"\n\n"
                    f"Fight back. What's YOUR reality at {timeline}?"
                )
            raw_alpha = alpha_agent(alpha_input)
            alpha_response = validate_safe_content(validate_agent_output(_safe_agent_output(raw_alpha)))

            if not alpha_response:
                raise ValueError("Alpha agent returned empty response")

            beta_agent = Agent(
                model=_make_model(),
                system_prompt=build_beta_prompt(user_ctx, round_info, beta_persona),
                tools=tools,
            )
            raw_beta = beta_agent(
                f"{summary_prefix}"
                f"You chose \"{path_b}\". It's now {timeline}.\n\n"
                f"The version of you who chose \"{path_a}\" just said:\n\n"
                f"\"{alpha_response}\"\n\n"
                f"Fight back. What's YOUR reality at {timeline}?"
            )
            beta_response = validate_safe_content(validate_agent_output(_safe_agent_output(raw_beta)))

            if not beta_response:
                raise ValueError("Beta agent returned empty response")

            debate_text = f"Path A argued:\n{alpha_response}\n\nPath B argued:\n{beta_response}"
            metrics = extract_metrics(debate_text)

            return RoundResult(
                round_number=round_num + 1,
                round_name=round_info["name"],
                round_title=round_info["title"],
                alpha=alpha_response,
                beta=beta_response,
                metrics=metrics,
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
    full_text = ""
    for r in transcript:
        if r.status == "completed":
            full_text += f"\n--- Round {r.round_number}: {r.round_title} ---\n"
            full_text += f"Path A ({user_ctx['path_a']}): {r.alpha}\n"
            full_text += f"Path B ({user_ctx['path_b']}): {r.beta}\n"

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


def _get_resources(category: str) -> list:
    """Get curated resources for the given category."""
    try:
        from app.data.resources import get_resources_for_category
        from app.schemas import Resource
        raw = get_resources_for_category(category)
        return [Resource(**r) for r in raw[:3]]
    except Exception as e:
        logger.warning(f"Failed to load resources for {category}: {e}")
        return []


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
    brave = detect_brave_path(user_context["path_a"], user_context["path_b"])
    alpha_persona, beta_persona = _assign_personas(brave, user_context)
    rounds = get_rounds(category)
    tools = TOOL_MAP.get(category, [research_insight])

    logger.info(
        f"Starting debate {debate_id}: {user_context['path_a']} vs {user_context['path_b']} "
        f"(category={category}, brave={brave}, alpha={alpha_persona['label']}, beta={beta_persona['label']})"
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
    if len(completed) >= 3:
        verdict = _generate_verdict(transcript, user_context)
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

    resources = _get_resources(category)

    return DebateResponse(
        debate_id=debate_id,
        transcript=transcript,
        verdict=verdict,
        metrics=all_metrics,
        completed_rounds=len(completed),
        total_rounds=len(rounds),
        resources=resources,
    )


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
    brave = detect_brave_path(user_context["path_a"], user_context["path_b"])
    alpha_persona, beta_persona = _assign_personas(brave, user_context)
    rounds = get_rounds(category)
    tools = TOOL_MAP.get(category, [research_insight])

    logger.info(
        f"Starting streaming debate {debate_id}: {user_context['path_a']} vs {user_context['path_b']} "
        f"(category={category}, brave={brave})"
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
    if len(completed) >= 3:
        verdict = _generate_verdict(transcript, user_context)
    elif len(completed) >= 1:
        verdict = f"Only {len(completed)} of 5 rounds completed. Partial analysis."
    else:
        verdict = "The debate could not be completed."

    elapsed = time.time() - start_time
    logger.info(f"Streaming debate {debate_id} finished in {elapsed:.1f}s")

    resources = _get_resources(category)

    yield {
        "type": "complete",
        "verdict": verdict,
        "debate_id": debate_id,
        "metrics": [m.model_dump() if m else None for m in all_metrics],
        "completed_rounds": len(completed),
        "total_rounds": len(rounds),
        "resources": [r.model_dump() for r in resources],
    }
