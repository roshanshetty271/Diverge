"""Application configuration using pydantic-settings.

Best practice: centralize all config, load from env vars, validate types at startup.
Never hardcode secrets. Use .env for local dev, environment variables in production.

Bedrock-ready defaults (for when account access is restored):
  DIVERGE_MODEL_PROVIDER=bedrock
  DIVERGE_DEBATE_MODEL_ID=us.amazon.nova-pro-v1:0
  DIVERGE_METRICS_MODEL_ID=us.amazon.nova-lite-v1:0
  DIVERGE_DEBATE_TEMPERATURE=0.65  (Nova is more creative at lower temps than GPT)
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "Diverge API"
    app_version: str = "1.0.0"
    debug: bool = False

    # AWS
    aws_region: str = "us-east-1"

    # Model provider: "openai" or "bedrock"
    model_provider: str = "openai"
    intended_provider: str = "bedrock"
    allow_openai_fallback: bool = True

    # OpenAI (used when model_provider == "openai")
    openai_api_key: str = ""

    # Model IDs (provider-specific)
    # OpenAI: gpt-4o-mini, gpt-4o, etc.
    # Bedrock: us.amazon.nova-pro-v1:0, us.amazon.nova-lite-v1:0, etc.
    debate_model_id: str = "gpt-4o-mini"
    metrics_model_id: str = "gpt-4o-mini"

    # Time limits. The debate Lambda has 300 s per request, so a round stops
    # starting new generations or retries once it can't finish them in time.
    model_timeout_seconds: float = 60.0  # per OpenAI request
    model_max_retries: int = 1  # OpenAI client-level retries
    round_deadline_seconds: float = 150.0  # budget for one debate round
    min_attempt_seconds: float = 30.0  # don't start a generation with less time left

    # Model parameters
    debate_temperature: float = 0.75
    debate_max_tokens: int = 1024
    metrics_temperature: float = 0.0
    metrics_max_tokens: int = 2048

    # DynamoDB
    debates_table: str = "diverge-debates"
    users_table: str = "diverge-users"

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""

    # CORS — production CloudFront URL added via env var
    public_app_url: str = ""
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Rate limiting
    # Temporary testing kill switch. Set DIVERGE_RATE_LIMITING_ENABLED=true to restore.
    rate_limiting_enabled: bool = False
    max_debates_per_hour: int = 5
    # Key for hashing rate-limit subjects (IPs, user ids). Falls back to a constant.
    rate_limit_hash_key: str = ""

    # Origin verification (protects Function URL from direct access)
    origin_verify_header: str = ""
    origin_verify_secret: str = ""

    # Turnstile CAPTCHA (anonymous debate starts)
    turnstile_secret_key: str = ""

    # SES (check-in emails + feedback notifications)
    ses_sender_email: str = ""
    feedback_notify_email: str = ""
    ses_region: str = "us-east-1"
    checkins_table: str = "diverge-checkins"
    checkins_scheduler_enabled: bool = False

    # Bedrock Knowledge Base (for research_insight tool)
    kb_id: str = ""
    kb_region: str = ""

    # Bedrock Guardrails (content safety)
    guardrail_id: str = ""
    guardrail_version: str = "DRAFT"

    # Amazon Comprehend (sentiment analysis)
    comprehend_enabled: bool = False

    # AgentCore Memory (debate session persistence)
    agentcore_memory_id: str = ""

    model_config = {"env_file": ".env", "env_prefix": "DIVERGE_"}

    def openai_client_args(self) -> dict:
        """Keyword arguments for every OpenAI client: explicit timeout and bounded retries."""
        return {
            "api_key": self.openai_api_key,
            "timeout": self.model_timeout_seconds,
            "max_retries": self.model_max_retries,
        }

    def get_all_cors_origins(self) -> list[str]:
        """Return CORS origins including CloudFront URL if configured."""
        origins = list(self.cors_origins)
        if self.public_app_url and self.public_app_url not in origins:
            origins.append(self.public_app_url)
        return origins


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
