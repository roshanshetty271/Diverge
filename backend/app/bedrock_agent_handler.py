"""Bedrock Agent Action Group handler.

Translates Bedrock Agent Action Group invocation events into Diverge orchestrator calls.
This is used when a console-based Bedrock Agent calls the Diverge Lambda via Action Group.

The Bedrock Agent sends events in a specific format:
  https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html

This handler extracts path_a, path_b, etc. from the Action Group parameters,
runs the debate, and returns results in the format Bedrock Agent expects.
"""

import logging
from typing import Any

logger = logging.getLogger("diverge.bedrock_agent")


def is_bedrock_agent_event(event: dict) -> bool:
    """Detect if this Lambda event comes from a Bedrock Agent Action Group."""
    return (
        "actionGroup" in event
        and "apiPath" in event
        and "messageVersion" in event
    )


def handle_bedrock_agent_event(event: dict) -> dict:
    """Process a Bedrock Agent Action Group event and return the agent-formatted response.

    Event structure:
      {
        "messageVersion": "1.0",
        "agent": {...},
        "inputText": "...",
        "sessionId": "...",
        "actionGroup": "diverge-debate-action",
        "apiPath": "/debate",
        "httpMethod": "POST",
        "parameters": [...],
        "requestBody": {
          "content": {
            "application/json": {
              "properties": [
                {"name": "path_a", "type": "string", "value": "..."},
                {"name": "path_b", "type": "string", "value": "..."},
              ]
            }
          }
        }
      }

    Returns:
      Bedrock Agent Action Group response format
    """
    api_path = event.get("apiPath", "")
    http_method = event.get("httpMethod", "")
    action_group = event.get("actionGroup", "")
    session_id = event.get("sessionId", "")

    logger.info(
        "Bedrock Agent Action Group invocation: %s %s (group=%s, session=%s)",
        http_method, api_path, action_group, session_id,
    )

    if api_path == "/debate" and http_method == "POST":
        return _handle_debate(event)

    return _build_response(event, 404, {"error": f"Unknown path: {api_path}"})


def _handle_debate(event: dict) -> dict:
    """Extract debate parameters and run the orchestrator."""
    from app.orchestrator import run_debate
    from app.security.llm_security import sanitize_user_input, detect_injection

    params = _extract_body_params(event)
    path_a = params.get("path_a", "")
    path_b = params.get("path_b", "")

    if not path_a or not path_b:
        return _build_response(event, 400, {"error": "path_a and path_b are required"})

    for field_val in [path_a, path_b]:
        is_suspicious, _ = detect_injection(field_val)
        if is_suspicious:
            return _build_response(event, 400, {"error": "Input contains patterns that can't be processed."})

    user_context = {
        "path_a": sanitize_user_input(path_a),
        "path_b": sanitize_user_input(path_b),
        "constraints": sanitize_user_input(params.get("constraints", "")),
        "financial_context": sanitize_user_input(params.get("financial_context", "")),
    }

    try:
        result = run_debate(user_context)
        body = {
            "debate_id": result.debate_id,
            "verdict": result.verdict,
            "completed_rounds": result.completed_rounds,
            "total_rounds": result.total_rounds,
            "transcript_summary": _summarize_transcript(result.transcript),
        }
        return _build_response(event, 200, body)
    except Exception as e:
        logger.error("Debate failed in Bedrock Agent handler: %s", e)
        return _build_response(event, 500, {"error": "Debate execution failed"})


def _extract_body_params(event: dict) -> dict[str, str]:
    """Extract parameters from the Action Group request body."""
    params: dict[str, str] = {}

    request_body = event.get("requestBody", {})
    content = request_body.get("content", {})
    json_content = content.get("application/json", {})
    properties = json_content.get("properties", [])

    for prop in properties:
        name = prop.get("name", "")
        value = prop.get("value", "")
        if name and value:
            params[name] = value

    return params


def _summarize_transcript(transcript: list) -> str:
    """Create a concise summary of the debate transcript for the agent response."""
    lines = []
    for r in transcript:
        rnd = r if isinstance(r, dict) else r.model_dump()
        lines.append(
            f"Round {rnd['round_number']} ({rnd['round_name']}): "
            f"Path A: {rnd['alpha'][:200]}... | "
            f"Path B: {rnd['beta'][:200]}..."
        )
    return "\n".join(lines)


def _build_response(event: dict, status_code: int, body: Any) -> dict:
    """Build the response in the format Bedrock Agent expects."""
    import json
    return {
        "messageVersion": event.get("messageVersion", "1.0"),
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "apiPath": event.get("apiPath", ""),
            "httpMethod": event.get("httpMethod", ""),
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(body),
                }
            },
        },
    }
