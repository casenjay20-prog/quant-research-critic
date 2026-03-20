# backend/app/services/robustness.py
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple

import numpy as np

__all__ = [
    "compute_robustness_battery",
    "compute_walk_forward",
    "summarize_robustness_for_pdf",
    "summarize_walk_forward_for_pdf",
]


# -----------------------------
# Core metric helpers
# -----------------------------
def _seed_from_returns(r: np.ndarray) -> int:
    b = np.asarray(r, dtype=np.float64).tobytes()
    h = hashlib.sha256(b).digest()
    return int.from_bytes(h[:8], "big", signed=False) % (2**32)


def _cagr_from_returns(r: np.ndarray, freq_per_year: int = 252) -> float:
    n = int(r.size)
    if n <= 0:
        return 0.0
    years = n / float(freq_per_year)
    if years <= 0:
        return 0.0
    equity = float(np.prod(1.0 + r))
    if equity <= 0:
        return -1.0
    return float(equity ** (1.0 / years) - 1.0)


def _sharpe_from_returns(r: np.ndarray, freq_per_year: int = 252) -> float:
    n = int(r.size)
    if n <= 1:
        return 0.0
    mu = float(np.mean(r))
    sd = float(np.std(r, ddof=1))
    if sd <= 0:
        return 0.0
    return float((mu / sd) * np.sqrt(freq_per_year))


def _rolling_window_returns(r: np.ndarray, window: int) -> np.ndarray:
    if r.size < window or window <= 1:
        return np.array([], dtype=float)
    lr = np.log1p(r)
    c = np.cumsum(lr)
    win = c[window - 1 :] - np.concatenate(([0.0], c[:-window]))
    return np.expm1(win)


def _max_drawdown_from_equity(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return float(np.min(dd))


def _worst_window_stats(r: np.ndarray, window: int) -> Tuple[float, float]:
    win_rets = _rolling_window_returns(r, window)
    worst_win_ret = float(np.min(win_rets)) if win_rets.size else 0.0

    if r.size < window:
        return worst_win_ret, 0.0

    worst_win_dd = 0.0
    for i in range(0, r.size - window + 1):
        seg = r[i : i + window]
        eq = np.cumprod(1.0 + seg)
        dd = _max_drawdown_from_equity(eq)
        if dd < worst_win_dd:
            worst_win_dd = dd

    return worst_win_ret, float(worst_win_dd)


# -----------------------------
# Public API
# -----------------------------
def compute_robustness_battery(
    returns: np.ndarray,
    *,
    freq_per_year: int = 252,
    bootstrap_samples: int = 400,
) -> Dict[str, Any]:
    """
    Deterministic robustness battery.

    Output format:
    {
      "overall_pass": bool,
      "tests": {
        "bootstrap": {..., "pass": bool},
        "worst_windows": {..., "pass": bool},
        "outlier_sensitivity": {..., "pass": bool},
        "regime_split": {..., "pass": bool},
      }
    }
    """
    r = np.asarray(returns, dtype=float)
    n = int(r.size)

    if n < 20:
        return {
            "overall_pass": False,
            "tests": {
                "bootstrap": {"pass": False, "reason": "insufficient rows"},
                "worst_windows": {"pass": False, "reason": "insufficient rows"},
                "outlier_sensitivity": {"pass": False, "reason": "insufficient rows"},
                "regime_split": {"pass": False, "reason": "insufficient rows"},
            },
        }

    base_sharpe = _sharpe_from_returns(r, freq_per_year=freq_per_year)
    base_cagr = _cagr_from_returns(r, freq_per_year=freq_per_year)

    # --- 1) Bootstrap stability ---
    rng = np.random.default_rng(_seed_from_returns(r))
    sharpe_s: List[float] = []
    cagr_s: List[float] = []

    for _ in range(int(bootstrap_samples)):
        idx = rng.integers(0, n, size=n)
        rb = r[idx]
        sharpe_s.append(_sharpe_from_returns(rb, freq_per_year=freq_per_year))
        cagr_s.append(_cagr_from_returns(rb, freq_per_year=freq_per_year))

    sharpe_s_arr = np.asarray(sharpe_s, dtype=float)
    cagr_s_arr = np.asarray(cagr_s, dtype=float)

    pct_sharpe_gt0 = float(np.mean(sharpe_s_arr > 0.0))
    pct_cagr_gt0 = float(np.mean(cagr_s_arr > 0.0))
    sharpe_p05, sharpe_p50, sharpe_p95 = [float(x) for x in np.quantile(sharpe_s_arr, [0.05, 0.50, 0.95])]
    cagr_p05, cagr_p50, cagr_p95 = [float(x) for x in np.quantile(cagr_s_arr, [0.05, 0.50, 0.95])]

    bootstrap_pass = (pct_sharpe_gt0 >= 0.70) and (sharpe_p05 >= -0.25)

    # --- 2) Worst rolling windows (3m ~63, 6m ~126) ---
    worst_3m_ret, worst_3m_dd = _worst_window_stats(r, 63)
    worst_6m_ret, worst_6m_dd = _worst_window_stats(r, 126)

    windows_pass = (worst_6m_ret > -0.35) and (worst_6m_dd > -0.45)

    # --- 3) Outlier sensitivity (remove best/worst 1 day) ---
    if n >= 10:
        best_i = int(np.argmax(r))
        worst_i = int(np.argmin(r))
        mask = np.ones(n, dtype=bool)
        mask[[best_i, worst_i]] = False
        r_trim = r[mask]
    else:
        r_trim = r

    trim_sharpe = _sharpe_from_returns(r_trim, freq_per_year=freq_per_year)
    trim_cagr = _cagr_from_returns(r_trim, freq_per_year=freq_per_year)
    delta_sharpe = float(trim_sharpe - base_sharpe)
    delta_cagr = float(trim_cagr - base_cagr)

    outlier_pass = (abs(delta_sharpe) <= 0.75) and (abs(delta_cagr) <= 0.10)

    # --- 4) Regime split (first half vs second half) ---
    mid = n // 2
    r1 = r[:mid]
    r2 = r[mid:]
    s1 = _sharpe_from_returns(r1, freq_per_year=freq_per_year)
    s2 = _sharpe_from_returns(r2, freq_per_year=freq_per_year)
    c1 = _cagr_from_returns(r1, freq_per_year=freq_per_year)
    c2 = _cagr_from_returns(r2, freq_per_year=freq_per_year)

    sharpe_gap = float(s2 - s1)
    cagr_gap = float(c2 - c1)

    regime_pass = (abs(sharpe_gap) <= 1.25) and (abs(cagr_gap) <= 0.20)

    tests: Dict[str, Any] = {
        "bootstrap": {
            "pass": bool(bootstrap_pass),
            "pct_sharpe_gt_0": pct_sharpe_gt0,
            "pct_cagr_gt_0": pct_cagr_gt0,
            "sharpe_p05": sharpe_p05,
            "sharpe_p50": sharpe_p50,
            "sharpe_p95": sharpe_p95,
            "cagr_p05": cagr_p05,
            "cagr_p50": cagr_p50,
            "cagr_p95": cagr_p95,
        },
        "worst_windows": {
            "pass": bool(windows_pass),
            "worst_3m_return": worst_3m_ret,
            "worst_3m_max_dd": worst_3m_dd,
            "worst_6m_return": worst_6m_ret,
            "worst_6m_max_dd": worst_6m_dd,
        },
        "outlier_sensitivity": {
            "pass": bool(outlier_pass),
            "base_sharpe": float(base_sharpe),
            "trim_sharpe": float(trim_sharpe),
            "delta_sharpe": delta_sharpe,
            "base_cagr": float(base_cagr),
            "trim_cagr": float(trim_cagr),
            "delta_cagr": delta_cagr,
        },
        "regime_split": {
            "pass": bool(regime_pass),
            "first_half_sharpe": float(s1),
            "second_half_sharpe": float(s2),
            "sharpe_gap": sharpe_gap,
            "first_half_cagr": float(c1),
            "second_half_cagr": float(c2),
            "cagr_gap": cagr_gap,
        },
    }

    overall_pass = bool(bootstrap_pass and windows_pass and outlier_pass and regime_pass)
    return {"overall_pass": overall_pass, "tests": tests}


def compute_walk_forward(
    returns: np.ndarray,
    *,
    train_window: int = 252,
    test_window: int = 63,
    freq_per_year: int = 252,
) -> Dict[str, Any]:
    """
    Walk-forward robustness test.

    Rolls a train window forward in test_window steps, measuring
    out-of-sample performance in each test period.

    Output:
    {
      "overall_pass": bool,
      "periods_total": int,
      "periods_profitable": int,
      "consistency_score": float,        # pct profitable periods
      "oos_sharpe": float,               # avg out-of-sample Sharpe
      "oos_cagr": float,                 # avg out-of-sample CAGR
      "sharpe_degradation": float,       # oos_sharpe - in_sample_sharpe
      "in_sample_sharpe": float,
      "periods": [ { "period": int, "train_sharpe": float, "test_sharpe": float,
                     "test_cagr": float, "profitable": bool } ]
    }
    """
    r = np.asarray(returns, dtype=float)
    n = int(r.size)

    min_rows = train_window + test_window
    if n < min_rows:
        return {
            "overall_pass": False,
            "reason": f"insufficient rows — need ≥{min_rows}, got {n}",
            "periods_total": 0,
            "periods_profitable": 0,
            "consistency_score": 0.0,
            "oos_sharpe": 0.0,
            "oos_cagr": 0.0,
            "sharpe_degradation": 0.0,
            "in_sample_sharpe": 0.0,
            "periods": [],
        }

    in_sample_sharpe = _sharpe_from_returns(r[:train_window], freq_per_year=freq_per_year)

    periods: List[Dict[str, Any]] = []
    start = 0

    while start + train_window + test_window <= n:
        train = r[start : start + train_window]
        test  = r[start + train_window : start + train_window + test_window]

        train_sharpe = _sharpe_from_returns(train, freq_per_year=freq_per_year)
        test_sharpe  = _sharpe_from_returns(test,  freq_per_year=freq_per_year)
        test_cagr    = _cagr_from_returns(test,    freq_per_year=freq_per_year)
        profitable   = bool(test_cagr > 0.0)

        periods.append({
            "period": len(periods) + 1,
            "train_sharpe": float(train_sharpe),
            "test_sharpe":  float(test_sharpe),
            "test_cagr":    float(test_cagr),
            "profitable":   profitable,
        })

        start += test_window

    if not periods:
        return {
            "overall_pass": False,
            "reason": "no complete walk-forward periods found",
            "periods_total": 0,
            "periods_profitable": 0,
            "consistency_score": 0.0,
            "oos_sharpe": 0.0,
            "oos_cagr": 0.0,
            "sharpe_degradation": 0.0,
            "in_sample_sharpe": float(in_sample_sharpe),
            "periods": [],
        }

    periods_total      = len(periods)
    periods_profitable = sum(1 for p in periods if p["profitable"])
    consistency_score  = float(periods_profitable / periods_total)
    oos_sharpe         = float(np.mean([p["test_sharpe"] for p in periods]))
    oos_cagr           = float(np.mean([p["test_cagr"]   for p in periods]))
    sharpe_degradation = float(oos_sharpe - in_sample_sharpe)

    # Pass criteria:
    # - majority of periods profitable
    # - average OOS Sharpe > 0
    # - degradation not catastrophic
    overall_pass = bool(
        consistency_score >= 0.55
        and oos_sharpe > 0.0
        and sharpe_degradation > -1.5
    )

    return {
        "overall_pass": overall_pass,
        "periods_total": periods_total,
        "periods_profitable": periods_profitable,
        "consistency_score": consistency_score,
        "oos_sharpe": oos_sharpe,
        "oos_cagr": oos_cagr,
        "sharpe_degradation": sharpe_degradation,
        "in_sample_sharpe": float(in_sample_sharpe),
        "train_window": train_window,
        "test_window": test_window,
        "periods": periods,
    }


# -----------------------------
# PDF-friendly formatting
# -----------------------------
def summarize_robustness_for_pdf(battery: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert compute_robustness_battery() output into a render-friendly structure
    (no dict dumps in the PDF).

    Output:
    {
      "overall": "PASS"/"FAIL",
      "rows": [ { "label": "...", "status": "PASS"/"FAIL", "detail": "..." }, ... ]
    }
    """
    overall = "PASS" if bool(battery.get("overall_pass")) else "FAIL"
    tests = (battery.get("tests") or {}) if isinstance(battery.get("tests"), dict) else {}

    def _pf(x: Any) -> str:
        return "PASS" if bool(x) else "FAIL"

    rows: List[Dict[str, str]] = []

    # Bootstrap
    boot = tests.get("bootstrap", {}) if isinstance(tests.get("bootstrap"), dict) else {}
    if "reason" in boot:
        rows.append({"label": "Bootstrap stability", "status": "FAIL", "detail": str(boot.get("reason"))})
    else:
        rows.append(
            {
                "label": "Bootstrap stability",
                "status": _pf(boot.get("pass")),
                "detail": f"% Sharpe>0: {float(boot.get('pct_sharpe_gt_0', 0.0)):.0%} | Sharpe p05: {float(boot.get('sharpe_p05', 0.0)):.2f}",
            }
        )

    # Worst windows
    ww = tests.get("worst_windows", {}) if isinstance(tests.get("worst_windows"), dict) else {}
    if "reason" in ww:
        rows.append({"label": "Worst windows", "status": "FAIL", "detail": str(ww.get("reason"))})
    else:
        rows.append(
            {
                "label": "Worst windows (3m/6m)",
                "status": _pf(ww.get("pass")),
                "detail": f"Worst 6m ret: {float(ww.get('worst_6m_return', 0.0)):.0%} | Worst 6m DD: {float(ww.get('worst_6m_max_dd', 0.0)):.0%}",
            }
        )

    # Outlier sensitivity
    osen = tests.get("outlier_sensitivity", {}) if isinstance(tests.get("outlier_sensitivity"), dict) else {}
    if "reason" in osen:
        rows.append({"label": "Outlier sensitivity", "status": "FAIL", "detail": str(osen.get("reason"))})
    else:
        rows.append(
            {
                "label": "Outlier sensitivity (trim best/worst day)",
                "status": _pf(osen.get("pass")),
                "detail": f"ΔSharpe: {float(osen.get('delta_sharpe', 0.0)):+.2f} | ΔCAGR: {float(osen.get('delta_cagr', 0.0)):+.1%}",
            }
        )

    # Regime split
    rs = tests.get("regime_split", {}) if isinstance(tests.get("regime_split"), dict) else {}
    if "reason" in rs:
        rows.append({"label": "Regime split", "status": "FAIL", "detail": str(rs.get("reason"))})
    else:
        rows.append(
            {
                "label": "Regime split (first vs second half)",
                "status": _pf(rs.get("pass")),
                "detail": f"Sharpe gap: {float(rs.get('sharpe_gap', 0.0)):+.2f} | CAGR gap: {float(rs.get('cagr_gap', 0.0)):+.1%}",
            }
        )

    return {"overall": overall, "rows": rows}


def summarize_walk_forward_for_pdf(wf: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert compute_walk_forward() output into a render-friendly structure for PDF.

    Output:
    {
      "overall": "PASS"/"FAIL",
      "summary_line": "...",
      "rows": [ { "label": "...", "status": "PASS"/"FAIL", "detail": "..." } ]
    }
    """
    if not wf or wf.get("periods_total", 0) == 0:
        reason = wf.get("reason", "insufficient data") if wf else "no data"
        return {
            "overall": "FAIL",
            "summary_line": f"Walk-forward skipped: {reason}",
            "rows": [{"label": "Walk-forward", "status": "FAIL", "detail": str(reason)}],
        }

    overall = "PASS" if bool(wf.get("overall_pass")) else "FAIL"
    total   = int(wf.get("periods_total", 0))
    profit  = int(wf.get("periods_profitable", 0))
    cons    = float(wf.get("consistency_score", 0.0))
    oos_sh  = float(wf.get("oos_sharpe", 0.0))
    oos_cagr = float(wf.get("oos_cagr", 0.0))
    degrad  = float(wf.get("sharpe_degradation", 0.0))
    in_sh   = float(wf.get("in_sample_sharpe", 0.0))
    tw      = int(wf.get("train_window", 252))
    tsw     = int(wf.get("test_window", 63))

    summary_line = (
        f"Train {tw}d / Test {tsw}d · {total} periods · "
        f"{profit}/{total} profitable · OOS Sharpe {oos_sh:+.2f}"
    )

    rows: List[Dict[str, str]] = [
        {
            "label": "Consistency",
            "status": "PASS" if cons >= 0.55 else "FAIL",
            "detail": f"{profit}/{total} periods profitable ({cons:.0%})",
        },
        {
            "label": "OOS Sharpe",
            "status": "PASS" if oos_sh > 0.0 else "FAIL",
            "detail": f"Avg out-of-sample Sharpe: {oos_sh:+.2f}",
        },
        {
            "label": "OOS CAGR",
            "status": "PASS" if oos_cagr > 0.0 else "FAIL",
            "detail": f"Avg out-of-sample CAGR: {oos_cagr:+.1%}",
        },
        {
            "label": "Sharpe degradation",
            "status": "PASS" if degrad > -1.5 else "FAIL",
            "detail": f"In-sample {in_sh:+.2f} → OOS {oos_sh:+.2f} (Δ{degrad:+.2f})",
        },
    ]

    return {"overall": overall, "summary_line": summary_line, "rows": rows}