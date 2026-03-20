from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class Scorecard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    grade: str
    confidence: float = Field(ge=0, le=1)


class RiskFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    details: Optional[str] = None


class AnalysisResult(BaseModel):
    # Strict, but allows the known extra sections your analyzer already returns
    model_config = ConfigDict(extra="forbid")

    api_version: str
    scoring_version: str
    schema_version: str
    ok: bool

    rows: int = Field(ge=0)
    years: float = Field(ge=0)

    cagr: float
    sharpe: float
    volatility: float
    max_drawdown: float

    # Your analyzer provides confidence inside scorecard
    scorecard: Scorecard

    # Keep these as structured/typed later; for now we accept exact shapes
    normalized: Dict[str, Any]
    flags: List[str]
    critic: str
    report: Dict[str, Any]

    # Optional narrative fields you might add later
    recommendation: Optional[str] = None
    rationale: Optional[str] = None

    @field_validator("ok")
    @classmethod
    def ok_must_be_true(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("analysis ok must be true to generate a report")
        return v

    @model_validator(mode="after")
    def enforce_confidence_present(self):
        # Guarantees confidence is present via scorecard (paid-user strictness)
        if self.scorecard.confidence is None:
            raise ValueError("scorecard.confidence is required")
        return self
