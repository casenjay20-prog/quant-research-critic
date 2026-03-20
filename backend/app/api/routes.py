# backend/app/api/routes.py
from __future__ import annotations

import hashlib
import io
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from backend.app.services.metrics import critic_score, normalized_metrics, red_flags
from backend.app.services.report import build_report
from backend.app.services.signature import analysis_signature
from backend.app.services.ai.commentary import (
    generate_portfolio_commentary,
    generate_strategy_diligence_summary,
    generate_allocation_rationale,
    generate_copilot_response,
)

from backend.app.services.reporting.page1.flags import select_top_flags
from backend.app.services.reporting.page1.layout import build_page1_pdf
from backend.app.services.reporting.page1.metrics import select_key_metrics
from backend.app.services.reporting.page1.verdict import build_verdict

from backend.app.services.reporting.page1.allocator import (
    build_capital_allocation_lens,
    recommend_deployment_sizing,
)

from backend.app.services.reporting.compare.compare_pdf import build_compare_pdf
from backend.app.services.reporting.allocator.allocator_pdf import build_allocator_view_pdf
from backend.app.services.reporting.portfolio.portfolio_pdf import build_portfolio_pdf

from backend.app.services.billing.stripe_checkout import create_checkout_session_url

from backend.app.services.robustness import compute_robustness_battery, compute_walk_forward
from backend.app.services.constraints import compute_deployability_constraints
from backend.app.services.portfolio.report import build_portfolio_report
from backend.app.services.portfolio.diversification import score_strategy_addition
from backend.app.services.portfolio.replacement import evaluate_replacement

router = APIRouter()

# -------------------------
# Versioning
# -------------------------
API_VERSION = "v1.1"
SCORING_VERSION = "v1.1"
SCHEMA_VERSION = "v1.1"

# -------------------------
# Tier 3 toggle (SOFT-DELETE MODE)
# -------------------------
TIER3_ENABLED = os.getenv("TIER3_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


class StrategySummary(BaseModel):
    name: str
    deployability_score: float
    deployability_verdict: str = ""
    score: float
    grade: str
    allocation_band: str
    rows: int
    years: float
    confidence: Optional[float] = None
    high_flags_count: int = 0
    critical_flags_count: int = 0
    top_risks: List[str] = []
    memo_line: str = ""

    fragility_index: Optional[float] = None
    fragility_breakdown: Optional[Dict[str, float]] = None
    deployability_breakdown: Optional[Dict[str, Any]] = None
    sizing_recommendation: Optional[Dict[str, Any]] = None
    robustness_battery: Optional[Dict[str, Any]] = None
    walk_forward: Optional[Dict[str, Any]] = None
    deployability_constraints: Optional[Dict[str, Any]] = None
    why_it_failed: Optional[List[str]] = None
    stability_transparency: Optional[Dict[str, Any]] = None

    provenance: Optional[Dict[str, Any]] = None
    peers: Optional[List[Dict[str, Any]]] = None


class CheckoutRequest(BaseModel):
    quantity: int = 1


class CopilotRequest(BaseModel):
    question: str
    portfolio_report: Dict[str, Any]
    conversation_history: Optional[List[Dict[str, str]]] = None


# -------------------------
# Helpers
# -------------------------
def _require_paid_api_key(x_api_key: str | None, api_key: str | None) -> str:
    expected = os.getenv("QRC_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="Server missing QRC_API_KEY env var for paid gating.")
    provided = (x_api_key or api_key or "").strip()
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return provided


def _deployability_verdict(deploy_score: float) -> str:
    try:
        s = float(deploy_score)
    except Exception:
        return "—"
    if s >= 60:
        return "Deployable"
    if s >= 30:
        return "Watchlist"
    return "Research Only"


async def _read_uploadfiles_once(files: List[UploadFile]) -> List[Tuple[str, bytes]]:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    out: List[Tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        if not raw:
            raise HTTPException(status_code=400, detail=f"Empty file: {f.filename}")
        out.append((f.filename or "strategy.csv", raw))
    return out


def _series_from_csv_bytes(filename: str, raw: bytes) -> Tuple[str, pd.Series]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail=f"File must be UTF-8 CSV: {filename}")

    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV {filename}: {e}")

    df.columns = [str(c).strip().lower() for c in df.columns]

    if "date" not in df.columns or "returns" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain columns: date, returns ({filename})",
        )

    df = df[["date", "returns"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["returns"] = pd.to_numeric(df["returns"], errors="coerce")
    df = df.dropna().sort_values("date")

    if df.empty:
        raise HTTPException(status_code=400, detail=f"No valid rows after parsing: {filename}")

    series = df.groupby("date", as_index=True)["returns"].mean()
    return _safe_name(filename), series


def _dataset_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse_returns_csv_bytes(raw: bytes) -> np.ndarray:
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 CSV.")

    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    df.columns = [str(c).strip().lower() for c in df.columns]
    if "date" not in df.columns or "returns" not in df.columns:
        raise HTTPException(status_code=400, detail="CSV must contain columns: date, returns")

    df = df[["date", "returns"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["returns"] = pd.to_numeric(df["returns"], errors="coerce")
    df = df.dropna().sort_values("date")
    if df.empty:
        raise HTTPException(status_code=400, detail="No valid rows after parsing.")

    df = df.groupby("date", as_index=False)["returns"].mean()
    r = df["returns"].to_numpy(dtype=float)
    if r.size == 0:
        raise HTTPException(status_code=400, detail="No returns values found.")
    return r


def _analyze_returns_array(r: np.ndarray) -> Dict[str, Any]:
    n = int(r.size)
    freq_per_year = 252
    years = (n / freq_per_year) if n else 0.0

    equity = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(equity)
    drawdowns = equity / peak - 1.0
    max_drawdown = float(np.min(drawdowns)) if n else 0.0

    cagr = float(equity[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0
    mean_r = float(np.mean(r))
    std_r = float(np.std(r, ddof=1)) if n > 1 else 0.0
    sharpe = float((mean_r / std_r) * np.sqrt(freq_per_year)) if std_r > 0 else 0.0
    volatility = float(std_r * np.sqrt(freq_per_year))

    normalized = normalized_metrics(
        returns=r,
        freq_per_year=freq_per_year,
        cagr=cagr,
        sharpe=sharpe,
    )
    scorecard = critic_score(normalized=normalized, max_drawdown=max_drawdown)
    flags = red_flags(
        rows=n,
        years=years,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        normalized=normalized,
    )

    critic = f"Score {scorecard['score']}/100 (Grade {scorecard['grade']}), CAGR {cagr:.2%}, Max DD {max_drawdown:.2%}."
    return {
        "api_version": API_VERSION,
        "scoring_version": SCORING_VERSION,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "rows": n,
        "years": round(years, 4),
        "cagr": cagr,
        "sharpe": sharpe,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "normalized": normalized,
        "scorecard": scorecard,
        "flags": flags,
        "critic": critic,
    }


def _safe_name(filename: str) -> str:
    name = (filename or "strategy").strip()
    if name.lower().endswith(".csv"):
        name = name[:-4]
    return name


def _severity_counts(flags: Any) -> Tuple[int, int]:
    hi = 0
    crit = 0
    if not flags or not isinstance(flags, list):
        return 0, 0
    for f in flags:
        sev = ""
        if isinstance(f, dict):
            sev = str(f.get("severity", "")).strip().upper()
        else:
            s = str(f).strip().upper()
            if s.startswith("CRITICAL"):
                sev = "CRITICAL"
            elif s.startswith("HIGH"):
                sev = "HIGH"
        if sev == "CRITICAL":
            crit += 1
        elif sev == "HIGH":
            hi += 1
    return hi, crit


def _deployability_score_with_breakdown(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    scorecard = payload.get("scorecard", {}) or {}
    base = float(scorecard.get("score", 0.0) or 0.0)

    flags = payload.get("flags", []) or []
    hi, crit = _severity_counts(flags)

    rows = int(payload.get("rows", 0) or 0)
    years = float(payload.get("years", 0.0) or 0.0)

    conf_raw = scorecard.get("confidence", None)
    confidence: Optional[float] = None
    try:
        if conf_raw is not None:
            confidence = float(conf_raw)
    except Exception:
        confidence = None

    penalties: Dict[str, float] = {
        "high_flag_penalty": 5.0 * hi,
        "critical_flag_penalty": 12.0 * crit,
        "sample_penalty": 20.0 if (rows and rows < 50) else 0.0,
        "history_penalty": 20.0 if (years and years < 0.5) else 0.0,
        "confidence_penalty": 15.0 if (confidence is not None and confidence < 0.35) else 0.0,
    }

    total_penalty = float(sum(penalties.values()))
    final = float(base - total_penalty)
    breakdown: Dict[str, Any] = {
        "base_score": float(base),
        "penalties": penalties,
        "total_penalty": float(total_penalty),
        "final_deployability": float(final),
    }
    return final, breakdown


def _top_risks(payload: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    flags = payload.get("flags", []) or []
    if isinstance(flags, list):
        for f in flags:
            if isinstance(f, dict):
                txt = str(f.get("flag", "") or f.get("message", "") or "").strip()
                if txt:
                    out.append(txt)
            else:
                s = str(f).strip()
                if s:
                    out.append(s)
    return out[:3]


def _memo_line(payload: Dict[str, Any], deploy_score: float) -> str:
    years = float(payload.get("years", 0.0) or 0.0)
    rows = int(payload.get("rows", 0) or 0)
    scorecard = payload.get("scorecard", {}) or {}
    conf = scorecard.get("confidence", None)
    try:
        conf_f = float(conf) if conf is not None else None
    except Exception:
        conf_f = None

    if (rows and rows < 50) or (years and years < 0.5):
        return "Insufficient history for institutional deployment; treat as research-only until sample length improves."
    if conf_f is not None and conf_f < 0.35:
        return "Low stability signal; requires extended out-of-sample validation before any allocation consideration."
    if deploy_score < 0:
        return "Risk-adjusted profile fails deployability threshold under deterministic penalties."
    return "Meets baseline deployability screen; requires standard due diligence and regime sensitivity review."


def _stable_results_signature(results: List[StrategySummary]) -> str:
    stable_blob = json.dumps([r.model_dump() for r in results], sort_keys=True).encode("utf-8")
    return hashlib.sha256(stable_blob).hexdigest()


def _walk_forward_signature(result: Dict[str, Any], raw: bytes) -> str:
    dataset_hash = hashlib.sha256(raw).hexdigest()
    result_hash = hashlib.sha256(
        json.dumps(result, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    combined = f"{dataset_hash}:{result_hash}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _compute_fragility(returns: np.ndarray, payload: Dict[str, Any]) -> Tuple[Optional[float], Optional[Dict[str, float]]]:
    try:
        from backend.app.services import fragility as fragility_mod  # type: ignore
    except Exception:
        return None, None

    if hasattr(fragility_mod, "compute_fragility"):
        try:
            idx, breakdown = fragility_mod.compute_fragility(returns, payload)
            bd = {k: float(v) for k, v in (breakdown or {}).items()} if breakdown else None
            return (float(idx) if idx is not None else None), bd
        except Exception:
            return None, None

    for fn in ["compute_fragility_index", "fragility_index", "calc_fragility_index"]:
        if hasattr(fragility_mod, fn):
            try:
                idx = getattr(fragility_mod, fn)(returns, payload)
                return (float(idx) if idx is not None else None), None
            except TypeError:
                try:
                    idx = getattr(fragility_mod, fn)(returns)
                    return (float(idx) if idx is not None else None), None
                except Exception:
                    return None, None
            except Exception:
                return None, None

    return None, None


def _what_would_change_mind(payload: Dict[str, Any]) -> List[str]:
    rows = int(payload.get("rows", 0) or 0)
    years = float(payload.get("years", 0.0) or 0.0)
    out: List[str] = []
    if rows < 252:
        out.append("Add ≥252 daily rows (≈1 year) and re-run robustness battery.")
    if years < 1.0:
        out.append("Add ≥1.0 years of history and validate regime stability.")
    out.append("Provide out-of-sample or live/paper track and re-score.")
    return out[:3]


def _why_it_failed(
    *,
    verdict: str,
    deploy_breakdown: Dict[str, Any],
    fragility_index: Optional[float],
    robustness: Dict[str, Any],
    walk_forward_result: Optional[Dict[str, Any]] = None,
    top_risks: List[str],
) -> List[str]:
    bullets: List[str] = []
    penalties = (deploy_breakdown or {}).get("penalties", {}) or {}
    drivers = sorted([(k, float(v)) for k, v in penalties.items() if float(v) > 0], key=lambda x: x[1], reverse=True)
    if drivers:
        bullets.append(
            "Deployability drivers: "
            + ", ".join([f"{k.replace('_', ' ')} (-{v:.0f})" for k, v in drivers[:3]])
        )

    if fragility_index is not None:
        try:
            fi = float(fragility_index)
            if fi >= 67:
                bullets.append("Fragility: High — backtest appears unstable under deterministic stress signals.")
            elif fi >= 34:
                bullets.append("Fragility: Medium — regime sensitivity risk; validate before sizing.")
        except Exception:
            pass

    if robustness and (robustness.get("overall_pass") is False):
        bullets.append("Robustness battery: FAIL — one or more stress tests did not pass conservative thresholds.")

    if walk_forward_result and (walk_forward_result.get("overall_pass") is False):
        cons = walk_forward_result.get("consistency_score", 0.0)
        oos_sh = walk_forward_result.get("oos_sharpe", 0.0)
        bullets.append(f"Walk-forward: FAIL — {cons:.0%} periods profitable, OOS Sharpe {oos_sh:+.2f}.")

    for r in (top_risks or [])[:2]:
        bullets.append(r)

    if not bullets:
        bullets.append(f"Verdict: {verdict}. Fails deterministic deployability screen.")
    return bullets[:5]


def _stability_transparency(payload: Dict[str, Any], deploy_breakdown: Dict[str, Any]) -> Dict[str, Any]:
    rows = int(payload.get("rows", 0) or 0)
    years = float(payload.get("years", 0.0) or 0.0)
    conf = None
    try:
        conf = float((payload.get("scorecard", {}) or {}).get("confidence"))
    except Exception:
        conf = None

    penalties = (deploy_breakdown or {}).get("penalties", {}) or {}
    stability_total = float(penalties.get("sample_penalty", 0.0)) + float(penalties.get("history_penalty", 0.0)) + float(
        penalties.get("confidence_penalty", 0.0)
    )

    drivers: List[str] = []
    if rows < 50:
        drivers.append("sample length < 50 rows")
    if years < 0.5:
        drivers.append("history < 0.5 years")
    if conf is not None and conf < 0.35:
        drivers.append("confidence < 0.35")

    return {
        "rows": rows,
        "years": years,
        "confidence": conf,
        "stability_penalty_total": stability_total,
        "drivers": drivers,
    }


# -------------------------
# Endpoints
# -------------------------
@router.get("/")
def root() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "quant-research-critic",
        "api_version": API_VERSION,
        "scoring_version": SCORING_VERSION,
        "schema_version": SCHEMA_VERSION,
        "tier3_enabled": TIER3_ENABLED,
    }


@router.post("/v1/analyze")
async def analyze(file: UploadFile = File(...)) -> Dict[str, Any]:
    raw = await file.read()
    r = _parse_returns_csv_bytes(raw)
    payload = _analyze_returns_array(r)
    diligence_summary = generate_strategy_diligence_summary(payload)
    walk_forward_result = compute_walk_forward(r)
    sig = analysis_signature(payload)
    wf_sig = _walk_forward_signature(walk_forward_result, raw)

    return {
        **payload,
        "report": build_report(payload),
        "ai_diligence_summary": diligence_summary,
        "walk_forward": {
            **walk_forward_result,
            "signature": wf_sig,
        },
        "analysis_signature": sig,
    }


@router.post("/v1/report/pdf")
async def report_pdf(file: UploadFile = File(...)) -> Response:
    raw = await file.read()
    r = _parse_returns_csv_bytes(raw)
    payload = _analyze_returns_array(r)

    verdict = build_verdict(payload)
    metrics = select_key_metrics(payload)
    flags = select_top_flags(payload)
    sig = analysis_signature(payload)

    pdf_bytes = build_page1_pdf(
        payload=payload,
        verdict=verdict,
        metrics=metrics,
        flags=flags,
        signature=sig,
        template="summary",
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=strategy_report.pdf"},
    )


@router.post("/v1/compare", response_model=List[StrategySummary])
async def compare(files: List[UploadFile] = File(...)) -> List[StrategySummary]:
    file_blobs = await _read_uploadfiles_once(files)

    results: List[StrategySummary] = []
    for filename, raw in file_blobs:
        r = _parse_returns_csv_bytes(raw)
        payload = _analyze_returns_array(r)

        key_metrics = select_key_metrics(payload)
        top_flags = select_top_flags(payload)
        lens = build_capital_allocation_lens(payload, key_metrics, top_flags)

        deploy, _ = _deployability_score_with_breakdown(payload)
        verdict = _deployability_verdict(deploy)

        scorecard = payload.get("scorecard", {}) or {}
        confidence = scorecard.get("confidence", None)
        try:
            confidence_f = float(confidence) if confidence is not None else None
        except Exception:
            confidence_f = None

        hi, crit = _severity_counts(payload.get("flags", []) or [])

        results.append(
            StrategySummary(
                name=_safe_name(filename),
                deployability_score=float(deploy),
                deployability_verdict=verdict,
                score=float(scorecard.get("score", 0.0) or 0.0),
                grade=str(scorecard.get("grade", "") or ""),
                allocation_band=str(lens.get("allocation_band", "—") or "—"),
                rows=int(payload.get("rows", 0) or 0),
                years=float(payload.get("years", 0.0) or 0.0),
                confidence=confidence_f,
                high_flags_count=hi,
                critical_flags_count=crit,
                top_risks=_top_risks(payload),
                memo_line=_memo_line(payload, float(deploy)),
            )
        )

    results.sort(key=lambda x: x.deployability_score, reverse=True)
    return results


@router.post("/v1/compare/pdf")
async def compare_pdf(files: List[UploadFile] = File(...)) -> Response:
    results = await compare(files)
    signature = _stable_results_signature(results)
    pdf_bytes = build_compare_pdf(results, signature, watermark=True)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=strategy_ranking_memo.pdf"},
    )


@router.post("/v1/compare/allocator-pdf")
async def compare_allocator_pdf(
    files: List[UploadFile] = File(...),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    api_key: str | None = Header(default=None, alias="api-key"),
) -> Response:
    _require_paid_api_key(x_api_key, api_key)

    file_blobs = await _read_uploadfiles_once(files)

    ranked: List[Tuple[str, StrategySummary, np.ndarray, Dict[str, Any], str]] = []
    for filename, raw in file_blobs:
        r = _parse_returns_csv_bytes(raw)
        payload = _analyze_returns_array(r)

        key_metrics = select_key_metrics(payload)
        top_flags = select_top_flags(payload)
        lens = build_capital_allocation_lens(payload, key_metrics, top_flags)

        deploy, _ = _deployability_score_with_breakdown(payload)
        verdict = _deployability_verdict(deploy)

        scorecard = payload.get("scorecard", {}) or {}
        confidence = scorecard.get("confidence", None)
        try:
            confidence_f = float(confidence) if confidence is not None else None
        except Exception:
            confidence_f = None

        hi, crit = _severity_counts(payload.get("flags", []) or [])

        s = StrategySummary(
            name=_safe_name(filename),
            deployability_score=float(deploy),
            deployability_verdict=verdict,
            score=float(scorecard.get("score", 0.0) or 0.0),
            grade=str(scorecard.get("grade", "") or ""),
            allocation_band=str(lens.get("allocation_band", "—") or "—"),
            rows=int(payload.get("rows", 0) or 0),
            years=float(payload.get("years", 0.0) or 0.0),
            confidence=confidence_f,
            high_flags_count=hi,
            critical_flags_count=crit,
            top_risks=_top_risks(payload),
            memo_line=_memo_line(payload, float(deploy)),
        )
        ranked.append((filename, s, r, payload, _dataset_hash(raw)))

    ranked.sort(key=lambda t: t[1].deployability_score, reverse=True)
    _top_filename, top_summary, top_returns, top_payload, top_datahash = ranked[0]

    deploy, deploy_breakdown = _deployability_score_with_breakdown(top_payload)
    verdict = _deployability_verdict(deploy)

    fi, fi_breakdown = _compute_fragility(top_returns, top_payload)
    robustness = compute_robustness_battery(top_returns)
    walk_forward_result = compute_walk_forward(top_returns)
    wf_sig = _walk_forward_signature(walk_forward_result, top_datahash.encode())
    constraints = compute_deployability_constraints(payload=top_payload, returns=top_returns)

    scorecard = top_payload.get("scorecard", {}) or {}
    conf_val = None
    try:
        conf_val = float(scorecard.get("confidence")) if scorecard.get("confidence") is not None else None
    except Exception:
        conf_val = None

    rows = int(top_payload.get("rows", 0) or 0)
    years = float(top_payload.get("years", 0.0) or 0.0)

    sizing = recommend_deployment_sizing(
        deployability_score=float(deploy),
        fragility_index=fi,
        confidence=conf_val,
        years=years,
        rows=rows,
    )

    risks = _top_risks(top_payload)
    why_failed = _why_it_failed(
        verdict=verdict,
        deploy_breakdown=deploy_breakdown,
        fragility_index=fi,
        robustness=robustness,
        walk_forward_result=walk_forward_result,
        top_risks=risks,
    )
    stability = _stability_transparency(top_payload, deploy_breakdown)

    provenance = {
        "api_version": API_VERSION,
        "scoring_version": SCORING_VERSION,
        "schema_version": SCHEMA_VERSION,
        "analysis_timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset_hash_sha256": top_datahash,
        "deterministic_mode": True,
    }

    peers: List[Dict[str, Any]] = []
    for rank_i, (_fn, summ, _r, _p, _h) in enumerate(ranked[:3], start=1):
        peers.append(
            {
                "rank": rank_i,
                "name": summ.name,
                "deployability_score": float(summ.deployability_score),
                "deployability_verdict": summ.deployability_verdict,
                "fragility_index": None,
                "score": float(summ.score),
                "grade": summ.grade,
            }
        )

    top: Dict[str, Any] = top_summary.model_dump()
    top["deployability_score"] = float(deploy)
    top["deployability_verdict"] = verdict
    top["fragility_index"] = fi
    top["fragility_breakdown"] = fi_breakdown
    top["deployability_breakdown"] = deploy_breakdown
    top["sizing_recommendation"] = sizing
    top["robustness_battery"] = robustness
    top["walk_forward"] = {**walk_forward_result, "signature": wf_sig}
    top["deployability_constraints"] = constraints
    top["why_it_failed"] = why_failed
    top["stability_transparency"] = stability
    top["top_risks"] = risks
    top["memo_line"] = _memo_line(top_payload, float(deploy))
    top["provenance"] = provenance
    top["peers"] = peers
    top["what_would_change_mind"] = _what_would_change_mind(top_payload)

    signature = _stable_results_signature([x[1] for x in ranked])

    top["returns"] = top_returns.astype(float).tolist()
    top["freq_per_year"] = 252

    # -------------------------
    # Tier 3 persistence (Option A soft-delete):
    # intentionally NOT called.
    # -------------------------

    pdf_bytes = build_allocator_view_pdf(strategy=top, signature=signature)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=allocator_view.pdf"},
    )


@router.post("/v1/portfolio/analyze")
async def portfolio_analyze(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    file_blobs = await _read_uploadfiles_once(files)

    strategies_for_report = []
    for filename, raw in file_blobs:
        name, series = _series_from_csv_bytes(filename, raw)
        strategies_for_report.append((name, series))

    try:
        report = build_portfolio_report(strategies_for_report)
        commentary = generate_portfolio_commentary(report)
        allocation_rationale = generate_allocation_rationale(report)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Portfolio report failed: {e}")

    return {
        "ok": True,
        "api_version": API_VERSION,
        "scoring_version": SCORING_VERSION,
        "schema_version": SCHEMA_VERSION,
        "portfolio_report": report,
        "ai_commentary": commentary,
        "allocation_rationale": allocation_rationale,
    }


@router.post("/v1/portfolio/pdf")
async def portfolio_pdf(files: List[UploadFile] = File(...)) -> Response:
    file_blobs = await _read_uploadfiles_once(files)

    strategies_for_report = []
    for filename, raw in file_blobs:
        name, series = _series_from_csv_bytes(filename, raw)
        strategies_for_report.append((name, series))

    try:
        report = build_portfolio_report(strategies_for_report)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Portfolio report failed: {e}")

    signature = hashlib.sha256(
        json.dumps(report, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    pdf_bytes = build_portfolio_pdf(report=report, signature=signature)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=portfolio_intelligence_memo.pdf"},
    )


@router.post("/v1/portfolio/diversification-score")
async def portfolio_diversification_score(
    current_files: List[UploadFile] = File(...),
    candidate_file: UploadFile = File(...),
) -> Dict[str, Any]:
    current_file_blobs = await _read_uploadfiles_once(current_files)
    candidate_raw = await candidate_file.read()
    if not candidate_raw:
        raise HTTPException(status_code=400, detail=f"Empty file: {candidate_file.filename}")

    current_strategies: List[Tuple[str, pd.Series]] = []
    for filename, raw in current_file_blobs:
        current_strategies.append(_series_from_csv_bytes(filename, raw))

    candidate_strategy = _series_from_csv_bytes(candidate_file.filename or "candidate.csv", candidate_raw)
    candidate_strategies = current_strategies + [candidate_strategy]

    try:
        current_report = build_portfolio_report(current_strategies)
        candidate_report = build_portfolio_report(candidate_strategies)
        score = score_strategy_addition(current_report, candidate_report)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Diversification score failed: {e}")

    return {
        "ok": True,
        "api_version": API_VERSION,
        "scoring_version": SCORING_VERSION,
        "schema_version": SCHEMA_VERSION,
        "current_portfolio_report": current_report,
        "candidate_portfolio_report": candidate_report,
        "diversification_score": score,
    }


@router.post("/v1/portfolio/replacement-test")
async def portfolio_replacement_test(
    current_files: List[UploadFile] = File(...),
    candidate_file: UploadFile = File(...),
) -> Dict[str, Any]:
    current_file_blobs = await _read_uploadfiles_once(current_files)
    candidate_raw = await candidate_file.read()

    strategies_for_report = []
    for filename, raw in current_file_blobs:
        name, series = _series_from_csv_bytes(filename, raw)
        strategies_for_report.append((name, series))

    candidate_name, candidate_series = _series_from_csv_bytes(
        candidate_file.filename or "candidate.csv",
        candidate_raw,
    )

    result = evaluate_replacement(
        current_strategies=strategies_for_report,
        candidate_name=candidate_name,
        candidate_series=candidate_series,
    )

    return {
        "ok": True,
        "api_version": API_VERSION,
        "replacement_analysis": result,
    }


# -------------------------
# Quant Copilot
# -------------------------
@router.post("/v1/portfolio/copilot")
async def portfolio_copilot(req: CopilotRequest) -> Dict[str, Any]:
    """
    Quant Copilot — answers follow-up questions about a specific portfolio.
    Receives the portfolio report and conversation history as context.
    """
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        answer = generate_copilot_response(
            question=req.question.strip(),
            portfolio_report=req.portfolio_report,
            conversation_history=req.conversation_history or [],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Copilot error: {e}")

    return {
        "ok": True,
        "question": req.question.strip(),
        "answer": answer,
    }


# -------------------------
# Walk-forward standalone endpoint
# -------------------------
@router.post("/v1/walk-forward")
async def walk_forward(file: UploadFile = File(...)) -> Dict[str, Any]:
    raw = await file.read()
    r = _parse_returns_csv_bytes(raw)
    result = compute_walk_forward(r)
    sig = _walk_forward_signature(result, raw)

    return {
        "ok": True,
        "api_version": API_VERSION,
        "scoring_version": SCORING_VERSION,
        "schema_version": SCHEMA_VERSION,
        "dataset_hash_sha256": _dataset_hash(raw),
        "analysis_signature": sig,
        "deterministic_mode": True,
        "walk_forward": result,
    }


# -------------------------
# Tier 3 Debug Endpoints
# -------------------------
@router.get("/v1/tier3/health")
def tier3_health() -> Dict[str, Any]:
    if not TIER3_ENABLED:
        return {"ok": True, "tier3_enabled": False}

    try:
        from backend.app.services.registry import registry_health  # type: ignore
    except Exception as e:
        return {"ok": False, "tier3_enabled": True, "error": f"registry import failed: {e.__class__.__name__}: {e!r}"}

    return {"ok": True, "tier3_enabled": True, "registry": registry_health()}


@router.get("/v1/tier3/runs")
def tier3_runs(limit: int = 200) -> Dict[str, Any]:
    if not TIER3_ENABLED:
        return {"ok": True, "tier3_enabled": False, "runs": []}

    try:
        from backend.app.services.registry import load_runs  # type: ignore
    except Exception as e:
        return {"ok": False, "tier3_enabled": True, "runs": [], "error": f"registry import failed: {e.__class__.__name__}: {e!r}"}

    try:
        return {"ok": True, "tier3_enabled": True, "runs": load_runs(limit=limit)}
    except Exception as e:
        return {"ok": False, "tier3_enabled": True, "runs": [], "error": f"load_runs failed: {e.__class__.__name__}: {e!r}"}


# -------------------------
# Billing
# -------------------------
@router.post("/v1/billing/checkout")
async def billing_checkout(req: CheckoutRequest) -> Dict[str, str]:
    url = create_checkout_session_url(quantity=req.quantity)
    return {"url": url}


@router.get("/success", response_class=HTMLResponse)
def billing_success() -> str:
    return "<html><body><h1>Payment successful ✅</h1><p><a href='/'>Back</a></p></body></html>"


@router.get("/cancel", response_class=HTMLResponse)
def billing_cancel() -> str:
    return "<html><body><h1>Checkout canceled</h1><p><a href='/'>Back</a></p></body></html>"


# -------------------------
# Verification curl steps
# -------------------------
# Copilot test:
# curl -sS -X POST "http://127.0.0.1:8000/v1/portfolio/copilot" \
#   -H "Content-Type: application/json" \
#   -d '{"question": "Which strategy is most at risk of being cut?", "portfolio_report": {}}' \
#   | python3 -m json.tool
#
# Walk-forward standalone:
# curl -sS -X POST "http://127.0.0.1:8000/v1/walk-forward" \
#   -F "file=@test_returns_1y.csv" | python3 -m json.tool
#
# Tier 3 portfolio analyze:
# curl -sS -X POST "http://127.0.0.1:8000/v1/portfolio/analyze" \
#   -F "files=@test_returns_1y.csv" \
#   -F "files=@another_returns.csv" | python3 -m json.tool
#
# Tier 3 health:
# curl -sS "http://127.0.0.1:8000/v1/tier3/health" | python3 -m json.tool