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
import uuid
import time
import random
import logging
import queue
import threading
from typing import Any
from strands import Agent

from app.config import get_settings
from app.agents.prompts import (
    get_rounds, detect_decision_category,
    build_alpha_prompt, build_beta_prompt, build_verdict_prompt,
    PERSONA_CHALLENGER, PERSONA_DEFENDER,
)
from app.agents.metrics import extract_metrics
from app.schemas import RoundResult, RoundMetrics, DebateResponse
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


def _assign_personas() -> tuple[dict, dict]:
    """Keep alpha as the cautious voice and beta as the bold voice."""
    return PERSONA_DEFENDER, PERSONA_CHALLENGER


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

    summary_prefix = f"DEBATE SO FAR:\n{debate_summary}\n\n" if debate_summary else ""
    interjection_prefix = (
        "IMPORTANT USER CONTEXT FOR THIS ROUND:\n"
        f"- The user just added this and you must account for it explicitly: \"{interjection}\"\n\n"
        if interjection
        else ""
    )

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
                    f"{interjection_prefix}"
                    f"You chose \"{path_a}\". It's {timeline}. "
                    f"Speak from one emotionally loaded moment that shows what choosing this path did to you. "
                    f"Make it concrete."
                )
            else:
                alpha_input = (
                    f"{summary_prefix}"
                    f"{interjection_prefix}"
                    f"You chose \"{path_a}\". It's now {timeline}.\n\n"
                    f"The version of you who chose \"{path_b}\" just said:\n\n"
                    f"\"{prev_beta}\"\n\n"
                    f"Do not spar line by line. Let what they said sharpen your own clarity. "
                    f"Answer with quiet conviction from one emotionally loaded moment, and name the cost they are underestimating."
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
                f"{interjection_prefix}"
                f"You chose \"{path_b}\". It's now {timeline}.\n\n"
                f"The version of you who chose \"{path_a}\" just said:\n\n"
                f"\"{alpha_response}\"\n\n"
                f"Do not spar line by line. Let what they said sharpen your own clarity. "
                f"Answer with quiet conviction from one emotionally loaded moment, and name the cost they are underestimating."
            )
            beta_response = validate_safe_content(validate_agent_output(_safe_agent_output(raw_beta)))

            if not beta_response:
                raise ValueError("Beta agent returned empty response")

            debate_text = f"Path A argued:\n{alpha_response}\n\nPath B argued:\n{beta_response}"
            metrics = extract_metrics(debate_text)
            sentiment = analyze_round_sentiment(alpha_response, beta_response)

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
    alpha_persona, beta_persona = _assign_personas()
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

    response = DebateResponse(
        debate_id=debate_id,
        transcript=transcript,
        verdict=verdict,
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
    alpha_persona, beta_persona = _assign_personas()
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
    alpha_persona, beta_persona = _assign_personas()
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

        # Check for user interjection from previous round
        interjection = _pop_interjection(debate_id) if i > 0 else None
        if interjection:
            debate_summary += f"\n[User interjects]: {interjection}\n"
            yield {
                "type": "interjection",
                "round": i + 1,
                "text": interjection,
            }

        yield {
            "type": "round_start",
            "round": i + 1,
            "round_name": round_info["name"],
            "round_title": round_info["title"],
        }

        summary_prefix = f"DEBATE SO FAR:\n{debate_summary}\n\n" if debate_summary else ""
        interjection_prefix = (
            "IMPORTANT USER CONTEXT FOR THIS ROUND:\n"
            f"- The user just added this and you must account for it explicitly: \"{interjection}\"\n\n"
            if interjection
            else ""
        )
        path_a = user_context["path_a"]
        path_b = user_context["path_b"]
        timeline = round_info.get("timeline", f"round {i + 1}")

        # --- Alpha agent (streams tokens via queue) ---
        token_q: queue.Queue = queue.Queue()
        alpha_response = ""
        beta_response = ""

        if i == 0:
            alpha_input = (
                f"{summary_prefix}"
                f"{interjection_prefix}"
                f'You chose "{path_a}". It\'s {timeline}. '
                f"Speak from one emotionally loaded moment that shows what choosing this path did to you. "
                f"Make it concrete."
            )
        else:
            alpha_input = (
                f"{summary_prefix}"
                f"{interjection_prefix}"
                f'You chose "{path_a}". It\'s now {timeline}.\n\n'
                f'The version of you who chose "{path_b}" just said:\n\n'
                f'"{prev_beta}"\n\n'
                f"Do not spar line by line. Let what they said sharpen your own clarity. "
                f"Answer with quiet conviction from one emotionally loaded moment, and name the cost they are underestimating."
            )

        try:
            # Run alpha in a thread so we can drain tokens from the queue
            alpha_result_holder: list[str] = []
            alpha_error_holder: list[Exception] = []

            def run_alpha():
                try:
                    text = _run_agent_with_streaming(
                        build_alpha_prompt(user_context, round_info, alpha_persona),
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

            # --- Beta agent (streams tokens via queue) ---
            beta_q: queue.Queue = queue.Queue()
            beta_input = (
                f"{summary_prefix}"
                f"{interjection_prefix}"
                f'You chose "{path_b}". It\'s now {timeline}.\n\n'
                f'The version of you who chose "{path_a}" just said:\n\n'
                f'"{alpha_response}"\n\n'
                f"Do not spar line by line. Let what they said sharpen your own clarity. "
                f"Answer with quiet conviction from one emotionally loaded moment, and name the cost they are underestimating."
            )

            beta_result_holder: list[str] = []
            beta_error_holder: list[Exception] = []

            def run_beta():
                try:
                    text = _run_agent_with_streaming(
                        build_beta_prompt(user_context, round_info, beta_persona),
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
            metrics = extract_metrics(debate_text)
            sentiment = analyze_round_sentiment(alpha_response, beta_response)

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

        transcript.append(result)
        all_metrics.append(result.metrics)
        prev_beta = result.beta if result.status == "completed" else prev_beta

        if result.status == "completed":
            debate_summary += f"\n[Round {i + 1} - {round_info['name']}]\n"
            debate_summary += f"Path A argued: {result.alpha[:400]}...\n"
            debate_summary += f"Path B argued: {result.beta[:400]}...\n"

        yield {
            "type": "round_complete",
            "round": i + 1,
            "data": result.model_dump(),
        }

    # --- Verdict with streaming ---
    completed = [r for r in transcript if r.status == "completed"]
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
    elif len(completed) >= 1:
        verdict = f"Only {len(completed)} of 5 rounds completed. Partial analysis."
    else:
        verdict = "The debate could not be completed."

    elapsed = time.time() - start_time
    logger.info(f"Token-streaming debate {debate_id} finished in {elapsed:.1f}s")

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

    _persist_to_agentcore_memory(debate_id, user_context, transcript, verdict)
