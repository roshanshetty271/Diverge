"""Request and response schemas using Pydantic v2.

Best practice: separate schemas from routes. Use strict validation.
All API contracts defined here — single source of truth.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ── Request schemas ──────────────────────────────────────────────

class DecisionInput(BaseModel):
    """User's decision input from the intake form."""
    path_a: str = Field(..., min_length=2, max_length=200, description="Option A")
    path_b: str = Field(..., min_length=2, max_length=200, description="Option B")
    user_name: Optional[str] = Field(None, max_length=50)
    age: Optional[int] = Field(None, ge=13, le=120)
    financial_context: Optional[str] = Field(None, max_length=500)
    values: Optional[str] = Field(None, max_length=200)
    risk_level: str = Field("moderate", pattern="^(conservative|moderate|aggressive)$")
    time_horizon: str = Field("5 years", max_length=50)
    constraints: Optional[str] = Field(None, max_length=500)
    writing_samples: Optional[str] = Field(None, max_length=2000)


class InterjectionRequest(BaseModel):
    """User interjection sent between debate rounds."""
    debate_id: str = Field(..., min_length=1, max_length=100)
    text: str = Field(..., min_length=1, max_length=500, description="What the user wants the agents to consider")


class SaveDebateRequest(BaseModel):
    """Request to save a completed debate to the journal.

    Note: user_id comes from the JWT token, not the request body (Kiro audit #3.2).
    """
    debate_data: dict


class CheckinRequest(BaseModel):
    """Request to schedule follow-up check-in emails."""
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    path_a: str = Field(..., max_length=200)
    path_b: str = Field(..., max_length=200)
    micro_action: str = Field("", max_length=500)
    user_name: str = Field("", max_length=50)


class EmailResultsRequest(BaseModel):
    """Request to email debate results to the user."""
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    path_a: str = Field(..., max_length=200)
    path_b: str = Field(..., max_length=200)
    verdict_summary: str = Field("", max_length=2000)
    resources: list[dict] = []


# ── Response schemas ─────────────────────────────────────────────

class PathMetrics(BaseModel):
    """Metrics for one path extracted after a debate round."""
    financial_confidence: float = Field(ge=0.0, le=1.0)
    happiness_estimate: int = Field(ge=1, le=10)
    growth_potential: int = Field(ge=1, le=10)
    regret_risk: float = Field(ge=0.0, le=1.0)
    values_alignment: int = Field(ge=1, le=10)
    key_insight: str = ""


class RoundMetrics(BaseModel):
    """Metrics for both paths in a single round."""
    path_a: PathMetrics
    path_b: PathMetrics


class SentimentScores(BaseModel):
    """Sentiment analysis scores from Amazon Comprehend."""
    positive: float = 0.0
    negative: float = 0.0
    neutral: float = 0.0
    mixed: float = 0.0


class RoundSentiment(BaseModel):
    """Sentiment for both paths in a round."""
    path_a: SentimentScores = SentimentScores()
    path_b: SentimentScores = SentimentScores()


class RoundResult(BaseModel):
    """Complete result of one debate round."""
    round_number: int
    round_name: str
    round_title: str
    alpha: str
    beta: str
    metrics: Optional[RoundMetrics] = None
    sentiment: Optional[RoundSentiment] = None
    status: str = "completed"


class Resource(BaseModel):
    """A curated resource recommendation."""
    type: str
    title: str
    author: str
    url: Optional[str] = None
    why: str


class DebateResponse(BaseModel):
    """Complete debate response returned to the frontend."""
    debate_id: str
    transcript: list[RoundResult]
    verdict: str
    metrics: list[Optional[RoundMetrics]]
    completed_rounds: int
    total_rounds: int
    resources: list[Resource] = []


class TemplateResponse(BaseModel):
    """Decision template for the template picker."""
    id: str
    emoji: str
    title: str
    question: str
    pathA: str
    pathB: str


class ShareDebateRequest(BaseModel):
    """Request to create a shareable link for a debate."""
    debate_data: dict
    input_data: dict


class ChoosePathRequest(BaseModel):
    """Request to record which path the user chose."""
    chosen_path: str = Field(..., min_length=1, max_length=200)


class ReflectionRequest(BaseModel):
    """Request to record a reflection on a past decision."""
    satisfaction: int = Field(..., ge=1, le=10)
    note: str = Field("", max_length=1000)


class HealthResponse(BaseModel):
    status: str
    version: str