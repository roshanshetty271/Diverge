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


class SaveDebateRequest(BaseModel):
    """Request to save a completed debate to the journal.

    Note: user_id comes from the JWT token, not the request body (Kiro audit #3.2).
    """
    debate_data: dict


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


class RoundResult(BaseModel):
    """Complete result of one debate round."""
    round_number: int
    round_name: str
    round_title: str
    alpha: str
    beta: str
    metrics: Optional[RoundMetrics] = None
    status: str = "completed"


class DebateResponse(BaseModel):
    """Complete debate response returned to the frontend."""
    debate_id: str
    transcript: list[RoundResult]
    verdict: str
    metrics: list[Optional[RoundMetrics]]
    completed_rounds: int
    total_rounds: int


class TemplateResponse(BaseModel):
    """Decision template for the template picker."""
    id: str
    emoji: str
    title: str
    question: str
    pathA: str
    pathB: str


class HealthResponse(BaseModel):
    status: str
    version: str