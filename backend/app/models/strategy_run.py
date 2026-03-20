# backend/app/models/strategy_run.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class StrategyRun(BaseModel):
    strategy_id: str
    timestamp: datetime
    returns: List[float]
    features: Dict[str, Any]
    deployability: Optional[float] = None
    verdict: Optional[str] = None
    confidence: Optional[float] = None