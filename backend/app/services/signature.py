from __future__ import annotations

import hashlib
import json
from pydantic import BaseModel

def stable_json_bytes(model: BaseModel) -> bytes:
    # Deterministic JSON: sorted keys, no whitespace
    payload = model.model_dump(mode="json")
    s = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return s.encode("utf-8")

def analysis_signature(model: BaseModel, prefix: str = "QRC") -> str:
    h = hashlib.sha256(stable_json_bytes(model)).hexdigest()
    return f"{prefix}-{h[:12]}"
