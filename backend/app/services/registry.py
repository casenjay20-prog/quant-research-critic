# backend/app/services/registry.py
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from backend.app.models.strategy_run import StrategyRun

# Keep DB inside backend/app so relative path is stable from repo root
DB_PATH = Path("backend/app/strategy_registry.db")


def _ensure_parent_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_parent_dir()
    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=30,
        check_same_thread=False,
    )
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            returns TEXT NOT NULL,
            features TEXT NOT NULL,
            deployability REAL,
            verdict TEXT,
            confidence REAL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy_id ON strategy_runs(strategy_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON strategy_runs(timestamp)")
    return conn


def registry_health() -> Dict[str, Any]:
    """
    Lightweight health check for Tier 3 registry.
    Returns DB path + counts. Safe to call anytime.
    """
    try:
        conn = _get_conn()
        runs_count = int(conn.execute("SELECT COUNT(*) FROM strategy_runs").fetchone()[0])
        strategies_count = int(conn.execute("SELECT COUNT(DISTINCT strategy_id) FROM strategy_runs").fetchone()[0])
        conn.close()
        return {
            "db_path": str(DB_PATH),
            "runs_count": runs_count,
            "strategies_count": strategies_count,
        }
    except Exception as e:
        return {"db_path": str(DB_PATH), "error": f"{e.__class__.__name__}: {e!r}"}


def save_run(run: StrategyRun) -> None:
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO strategy_runs
        (strategy_id, timestamp, returns, features, deployability, verdict, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.strategy_id,
            run.timestamp.isoformat(),
            json.dumps(run.returns),
            json.dumps(run.features),
            float(run.deployability) if run.deployability is not None else None,
            run.verdict,
            float(run.confidence) if run.confidence is not None else None,
        ),
    )
    conn.commit()
    conn.close()


def get_runs(strategy_id: str) -> List[StrategyRun]:
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT strategy_id, timestamp, returns, features, deployability, verdict, confidence
        FROM strategy_runs
        WHERE strategy_id = ?
        ORDER BY timestamp ASC
        """,
        (strategy_id,),
    ).fetchall()
    conn.close()

    out: List[StrategyRun] = []
    for r in rows:
        out.append(
            StrategyRun(
                strategy_id=str(r[0]),
                timestamp=datetime.fromisoformat(str(r[1])),
                returns=list(json.loads(r[2])),
                features=dict(json.loads(r[3])),
                deployability=float(r[4]) if r[4] is not None else None,
                verdict=str(r[5]) if r[5] is not None else None,
                confidence=float(r[6]) if r[6] is not None else None,
            )
        )
    return out


def load_runs(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Debug-friendly: returns recent runs as dicts (JSON serializable).
    """
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT strategy_id, timestamp, returns, features, deployability, verdict, confidence
        FROM strategy_runs
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    conn.close()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "strategy_id": str(r[0]),
                "timestamp": str(r[1]),
                "returns": json.loads(r[2]),
                "features": json.loads(r[3]),
                "deployability": r[4],
                "verdict": r[5],
                "confidence": r[6],
            }
        )
    return out