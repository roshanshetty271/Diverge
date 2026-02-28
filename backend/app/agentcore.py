"""Amazon Bedrock AgentCore integration.

Wraps Diverge's debate engine for deployment via AgentCore.
AgentCore provides: managed runtime, memory, auth, observability, and tool interoperability.

Usage:
  For local development: import and call run_debate() directly (orchestrator.py)
  For AgentCore deployment: python -m app.agentcore

References:
- https://aws.amazon.com/bedrock/agentcore/
- https://github.com/aws/bedrock-agentcore-sdk-python
"""

import logging

logger = logging.getLogger(__name__)


def create_agentcore_app():
    """Create a BedrockAgentCoreApp wrapper for AgentCore deployment.

    AgentCore provides:
    - Secure, session-isolated compute (Runtime)
    - Persistent knowledge across sessions (Memory)
    - Built-in auth via Cognito/IAM (Identity)
    - OpenTelemetry tracing (Observability)

    Returns the app, or None if the SDK isn't available.
    """
    try:
        from bedrock_agentcore import BedrockAgentCoreApp
        from app.orchestrator import run_debate
        from app.security.llm_security import sanitize_user_input, detect_injection

        app = BedrockAgentCoreApp()

        @app.entrypoint
        def handle_debate(request: dict) -> dict:
            user_context = request.get("user_context", {})

            for field in ["path_a", "path_b"]:
                value = user_context.get(field, "")
                is_suspicious, _ = detect_injection(value)
                if is_suspicious:
                    return {"error": "Input contains patterns that can't be processed."}
                user_context[field] = sanitize_user_input(value)

            result = run_debate(user_context)
            return result.model_dump()

        logger.info("AgentCore app initialized successfully")
        return app

    except ImportError:
        logger.warning(
            "bedrock-agentcore SDK not installed. "
            "Running without AgentCore features. "
            "Install with: pip install bedrock-agentcore"
        )
        return None
    except Exception as e:
        logger.error(f"AgentCore initialization failed: {e}")
        return None


if __name__ == "__main__":
    app = create_agentcore_app()
    if app:
        app.run()
    else:
        import uvicorn
        from app.main import app as fastapi_app
        uvicorn.run(fastapi_app, host="0.0.0.0", port=8080)
