"""Metrics extraction using LLM tool/function calling for constrained JSON output.

Supports both OpenAI and Bedrock via DIVERGE_MODEL_PROVIDER setting.

Edge cases handled:
- Pydantic validation failure (values out of range) -> clamp + fallback
- No tool call in response -> explicit log + fallback
- Network timeout -> fallback (metrics are non-critical)
- Model returning floats as ints or vice versa -> coercion
"""

import json
import logging
from app.config import get_settings
from app.schemas import RoundMetrics, PathMetrics

logger = logging.getLogger(__name__)

METRICS_FUNCTION_SCHEMA = {
    "financial_confidence": {"type": "number", "description": "0.0-1.0 how financially secure is this path"},
    "happiness_estimate": {"type": "integer", "description": "1-10 how happy does the person seem"},
    "growth_potential": {"type": "integer", "description": "1-10 how much room for growth"},
    "regret_risk": {"type": "number", "description": "0.0-1.0 how likely to regret this path"},
    "values_alignment": {"type": "integer", "description": "1-10 how well does it match stated values"},
    "key_insight": {"type": "string", "description": "one sentence summary of strongest argument"},
}

PATH_SCHEMA = {
    "type": "object",
    "properties": METRICS_FUNCTION_SCHEMA,
    "required": list(METRICS_FUNCTION_SCHEMA.keys()),
}

FALLBACK = RoundMetrics(
    path_a=PathMetrics(financial_confidence=0.5, happiness_estimate=5, growth_potential=5, regret_risk=0.5, values_alignment=5, key_insight="Analysis pending"),
    path_b=PathMetrics(financial_confidence=0.5, happiness_estimate=5, growth_potential=5, regret_risk=0.5, values_alignment=5, key_insight="Analysis pending"),
)

_openai_client = None
_bedrock_client = None

METRICS_PROMPT = (
    "Analyze this debate round and extract metrics for both paths. "
    "Rate each dimension from the debate arguments. Be objective.\n\n"
    "financial_confidence: 0.0-1.0 (how financially secure is this path?)\n"
    "happiness_estimate: 1-10 (how happy does the person seem?)\n"
    "growth_potential: 1-10 (how much room for growth?)\n"
    "regret_risk: 0.0-1.0 (how likely to regret this path?)\n"
    "values_alignment: 1-10 (how well does it match stated values?)\n"
    "key_insight: one sentence summary of strongest argument\n\n"
    "DEBATE TEXT:\n{debate_text}"
)


def _clamp(value, lo, hi):
    try:
        v = float(value)
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return (lo + hi) / 2


def _safe_parse_path(raw: dict) -> PathMetrics:
    return PathMetrics(
        financial_confidence=_clamp(raw.get("financial_confidence", 0.5), 0.0, 1.0),
        happiness_estimate=int(_clamp(raw.get("happiness_estimate", 5), 1, 10)),
        growth_potential=int(_clamp(raw.get("growth_potential", 5), 1, 10)),
        regret_risk=_clamp(raw.get("regret_risk", 0.5), 0.0, 1.0),
        values_alignment=int(_clamp(raw.get("values_alignment", 5), 1, 10)),
        key_insight=str(raw.get("key_insight", "No insight extracted"))[:500],
    )


def _extract_openai(debate_text: str) -> RoundMetrics:
    """Extract metrics using OpenAI function calling."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        settings = get_settings()
        _openai_client = OpenAI(**settings.openai_client_args())

    settings = get_settings()
    response = _openai_client.chat.completions.create(
        model=settings.metrics_model_id,
        messages=[{"role": "user", "content": METRICS_PROMPT.format(debate_text=debate_text[:4000])}],
        tools=[{
            "type": "function",
            "function": {
                "name": "record_metrics",
                "description": "Record the extracted debate metrics for both paths",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path_a": PATH_SCHEMA,
                        "path_b": PATH_SCHEMA,
                    },
                    "required": ["path_a", "path_b"],
                },
            },
        }],
        tool_choice={"type": "function", "function": {"name": "record_metrics"}},
        temperature=0,
    )

    msg = response.choices[0].message
    if msg.tool_calls:
        raw = json.loads(msg.tool_calls[0].function.arguments)
        if "path_a" in raw and "path_b" in raw:
            return RoundMetrics(
                path_a=_safe_parse_path(raw["path_a"]),
                path_b=_safe_parse_path(raw["path_b"]),
            )
        logger.warning(f"Tool call response missing path_a/path_b keys: {list(raw.keys())}")

    logger.warning("No tool call in metrics response")
    return FALLBACK


def _extract_bedrock(debate_text: str) -> RoundMetrics:
    """Extract metrics using Bedrock Converse API with forced tool use."""
    global _bedrock_client
    if _bedrock_client is None:
        import boto3
        from botocore.config import Config as BotocoreConfig
        settings = get_settings()
        _bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=BotocoreConfig(
                retries={"max_attempts": 2, "mode": "adaptive"},
                read_timeout=60,
                connect_timeout=10,
            ),
        )

    settings = get_settings()
    bedrock_tool = {
        "toolSpec": {
            "name": "record_metrics",
            "description": "Record the extracted debate metrics for both paths",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path_a": PATH_SCHEMA,
                        "path_b": PATH_SCHEMA,
                    },
                    "required": ["path_a", "path_b"],
                }
            },
        }
    }

    response = _bedrock_client.converse(
        modelId=settings.metrics_model_id,
        messages=[{"role": "user", "content": [{"text": METRICS_PROMPT.format(debate_text=debate_text[:4000])}]}],
        toolConfig={"tools": [bedrock_tool], "toolChoice": {"tool": {"name": "record_metrics"}}},
        inferenceConfig={"temperature": 0},
    )

    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    for block in content_blocks:
        if "toolUse" in block:
            raw = block["toolUse"]["input"]
            if "path_a" in raw and "path_b" in raw:
                return RoundMetrics(
                    path_a=_safe_parse_path(raw["path_a"]),
                    path_b=_safe_parse_path(raw["path_b"]),
                )
            logger.warning(f"Tool use response missing path_a/path_b keys: {list(raw.keys())}")

    logger.warning("No toolUse block in metrics response")
    return FALLBACK


def extract_metrics(debate_text: str) -> RoundMetrics:
    """Extract structured metrics from a debate round.

    Uses forced function/tool calling for constrained output. Non-critical —
    always returns valid metrics (fallback on any failure).
    """
    if not debate_text or len(debate_text) < 50:
        logger.warning("Debate text too short for metrics extraction")
        return FALLBACK

    try:
        settings = get_settings()
        if settings.model_provider == "openai":
            return _extract_openai(debate_text)
        else:
            return _extract_bedrock(debate_text)
    except Exception as e:
        logger.warning(f"Metrics extraction failed ({type(e).__name__}): {e}")
        return FALLBACK
