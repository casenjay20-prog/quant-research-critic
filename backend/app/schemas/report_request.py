from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.analysis_result import AnalysisResult


# Allowed template modes (strict)
TemplateMode = Literal["summary", "risk_heavy", "allocator"]


class ReportPDFRequest(BaseModel):
    """
    Strict request model for generating report PDFs.
    """

    model_config = ConfigDict(extra="forbid")

    # NEW: Template mode selector (Revenue Layer hook)
    template: TemplateMode = Field(default="summary")

    # Existing analysis payload
    analysis: AnalysisResult
