"""Amazon Bedrock AgentCore integration for Diverge.

Provides two deployment paths:
  1. AgentCore Runtime — managed serverless deployment with streaming support
  2. AgentCore Memory — persistent debate session storage with semantic retrieval

The AgentCore entrypoint supports:
  - Full token-streaming debates via SSE (generators auto-wrapped by AgentCore)
  - User interjections between rounds
  - Session-aware debate tracking via AgentCore Memory

Usage:
  Local development:  python -m app.agentcore
  AgentCore Runtime:  deployed via AWS CLI / console

References:
  - https://aws.amazon.com/bedrock/agentcore/
  - https://strandsagents.com/latest/documentation/docs/user-guide/deploy/deploy_to_bedrock_agentcore/
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("diverge.agentcore")

_memory_manager = None
MEMORY_ID: Optional[str] = None


def _get_memory_manager():
    """Lazy-initialize the AgentCore Memory session manager."""
    global _memory_manager, MEMORY_ID
    if _memory_manager is not None:
        return _memory_manager
    try:
        from bedrock_agentcore.memory.session import MemorySessionManager
        from app.config import get_settings
        settings = get_settings()
        mid = getattr(settings, "agentcore_memory_id", "") or ""
        if not mid:
            logger.info("DIVERGE_AGENTCORE_MEMORY_ID not set — Memory integration disabled")
            return None
        MEMORY_ID = mid
        _memory_manager = MemorySessionManager(
            memory_id=mid,
            region_name=settings.aws_region,
        )
        logger.info("AgentCore Memory initialized: %s", mid)
        return _memory_manager
    except Exception as e:
        logger.warning("AgentCore Memory unavailable: %s", e)
        return None


def save_debate_to_memory(debate_id: str, user_id: str, user_context: dict, transcript: list, verdict: str):
    """Persist a completed debate as conversation events in AgentCore Memory.

    Each round becomes an event with USER (alpha argument) + ASSISTANT (beta argument).
    The verdict is stored as a final ASSISTANT event.
    """
    mgr = _get_memory_manager()
    if not mgr:
        return

    try:
        from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

        session = mgr.create_memory_session(
            actor_id=user_id,
            session_id=debate_id,
        )

        path_a = user_context.get("path_a", "Option A")
        path_b = user_context.get("path_b", "Option B")

        for rnd in transcript:
            alpha_text = rnd.get("alpha", "") if isinstance(rnd, dict) else getattr(rnd, "alpha", "")
            beta_text = rnd.get("beta", "") if isinstance(rnd, dict) else getattr(rnd, "beta", "")
            round_name = rnd.get("round_name", "") if isinstance(rnd, dict) else getattr(rnd, "round_name", "")

            session.add_turns(messages=[
                ConversationalMessage(f"[{path_a} — {round_name}] {alpha_text}", MessageRole.USER),
                ConversationalMessage(f"[{path_b} — {round_name}] {beta_text}", MessageRole.ASSISTANT),
            ])

        if verdict:
            session.add_turns(messages=[
                ConversationalMessage("Give the final verdict.", MessageRole.USER),
                ConversationalMessage(verdict, MessageRole.ASSISTANT),
            ])

        logger.info("Saved debate %s to AgentCore Memory (%d rounds)", debate_id, len(transcript))

    except Exception as e:
        logger.warning("Failed to save debate to AgentCore Memory: %s", e)


def retrieve_past_insights(user_id: str, query: str, top_k: int = 3) -> list[dict]:
    """Retrieve relevant insights from past debates via AgentCore Memory semantic search."""
    mgr = _get_memory_manager()
    if not mgr or not MEMORY_ID:
        return []

    try:
        namespace = f"semantic/facts/{user_id}/"
        records = mgr.search_long_term_memories(
            query=query,
            namespace_prefix=namespace,
            top_k=top_k,
        )
        return [{"text": r.get("content", {}).get("text", ""), "score": r.get("relevanceScore", 0)} for r in records]
    except Exception as e:
        logger.warning("Memory retrieval failed: %s", e)
        return []


def create_agentcore_app():
    """Create the BedrockAgentCoreApp with full streaming + interjection support.

    The entrypoint accepts:
      {"action": "debate", "user_context": {...}}           — start a streaming debate
      {"action": "interject", "debate_id": str, "text": str} — inject user interjection
      {"action": "status"}                                    — health check
    """
    try:
        from bedrock_agentcore import BedrockAgentCoreApp
        from app.orchestrator import run_debate_token_streaming, set_interjection
        from app.security.llm_security import sanitize_user_input, detect_injection
        from app.security.safety import detect_crisis, detect_blocked_topic

        app = BedrockAgentCoreApp()

        @app.entrypoint
        def handle_request(request: dict, context=None):
            action = request.get("action", "debate")

            if action == "status":
                return {"status": "Sic Mundus Creatus Est", "service": "diverge-agentcore"}

            if action == "interject":
                debate_id = request.get("debate_id", "")
                text = sanitize_user_input(request.get("text", ""))
                if debate_id and text:
                    set_interjection(debate_id, text)
                    return {"status": "ok", "debate_id": debate_id}
                return {"error": "Missing debate_id or text"}

            user_context = request.get("user_context", {})
            if not user_context.get("path_a") or not user_context.get("path_b"):
                return {"error": "path_a and path_b are required"}

            for field in ["path_a", "path_b"]:
                value = user_context.get(field, "")
                is_suspicious, _ = detect_injection(value)
                if is_suspicious:
                    return {"error": "Input contains patterns that can't be processed."}
                user_context[field] = sanitize_user_input(value)

            all_text = f"{user_context['path_a']} {user_context['path_b']} {user_context.get('constraints', '')}"
            is_crisis, crisis_cat = detect_crisis(all_text)
            if is_crisis:
                return {"type": "crisis", "category": crisis_cat}

            is_blocked, block_reason = detect_blocked_topic(
                user_context["path_a"], user_context["path_b"], user_context.get("constraints", "")
            )
            if is_blocked:
                return {"error": block_reason}

            for field in ["financial_context", "constraints", "writing_samples"]:
                if user_context.get(field):
                    user_context[field] = sanitize_user_input(user_context[field])

            return run_debate_token_streaming(user_context)

        from bedrock_agentcore import PingStatus

        @app.ping
        def health():
            return PingStatus.HEALTHY

        logger.info("AgentCore app initialized with streaming + interjection + memory support")
        return app

    except ImportError:
        logger.warning(
            "bedrock-agentcore SDK not installed. "
            "Running without AgentCore features. "
            "Install with: pip install bedrock-agentcore"
        )
        return None
    except Exception as e:
        logger.error("AgentCore initialization failed: %s", e)
        return None


if __name__ == "__main__":
    app = create_agentcore_app()
    if app:
        print("Starting Diverge on AgentCore Runtime (localhost:8080)...")
        print("  POST /invocations  — start debate / interject / status")
        print("  GET  /ping         — health check")
        app.run(port=8080)
    else:
        import uvicorn
        from app.main import app as fastapi_app
        print("AgentCore unavailable, falling back to FastAPI (localhost:8080)...")
        uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)
