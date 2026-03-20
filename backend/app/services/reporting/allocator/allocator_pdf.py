# backend/app/services/reporting/allocator/allocator_pdf.py
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.app.services.reporting.page1.layout import _draw_footer
from backend.app.services.robustness import summarize_robustness_for_pdf, compute_robustness_battery

TITLE = "Allocator View — Strategy Decision Memo"
SCOPE_LINE = "Scope: deterministic backtest diagnostic + sizing gate (not a forecast)."
PREPARED_BY = "Prepared by: Quant Research Critic (deterministic)."

SHOW_PROVENANCE_BLOCK = False  # keep off by default

# Palette
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#475569")
HAIRLINE = colors.HexColor("#E2E8F0")
CARD_BG = colors.HexColor("#F8FAFC")
ACCENT = colors.HexColor("#2563EB")

GOOD = colors.HexColor("#16A34A")
WARN = colors.HexColor("#F59E0B")
BAD = colors.HexColor("#DC2626")
GOOD_BG = colors.HexColor("#F0FDF4")
WARN_BG = colors.HexColor("#FFFBEB")
BAD_BG = colors.HexColor("#FEF2F2")


# ---------------------------
# Helpers
# ---------------------------
def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _as_strategy(strategy_or_list: Union[Any, List[Any], Dict[str, Any]]) -> Any:
    if isinstance(strategy_or_list, list):
        return strategy_or_list[0] if strategy_or_list else {}
    return strategy_or_list


def _short_sig(sig: str, n: int = 8) -> str:
    return (sig or "UNKNOWN").strip()[:n].upper()


def _fmt_float(v: Any, digits: int = 1, default: str = "—") -> str:
    try:
        if v is None:
            return default
        return f"{float(v):.{digits}f}"
    except Exception:
        return default


def _fmt_int(v: Any, default: str = "—") -> str:
    try:
        if v is None:
            return default
        return str(int(v))
    except Exception:
        return default


def _fragility_label(value: Any) -> str:
    try:
        v = float(value)
    except Exception:
        return "—"
    if v >= 67:
        return "High"
    if v >= 34:
        return "Medium"
    return "Low"


def _verdict_color(verdict: str) -> colors.Color:
    v = (verdict or "").strip().lower()
    if "deploy" in v or "approve" in v:
        return GOOD
    if "watch" in v or "pilot" in v:
        return WARN
    if "research" in v or "reject" in v or "fail" in v:
        return BAD
    return MUTED


def _verdict_bg(verdict: str) -> colors.Color:
    v = (verdict or "").strip().lower()
    if "deploy" in v or "approve" in v:
        return GOOD_BG
    if "watch" in v or "pilot" in v:
        return WARN_BG
    if "research" in v or "reject" in v or "fail" in v:
        return BAD_BG
    return CARD_BG


def _pill(text: str, fg: colors.Color, bg: colors.Color) -> Table:
    t = Table(
        [[
            Paragraph(
                text,
                ParagraphStyle(
                    "pill",
                    fontName="Helvetica-Bold",
                    fontSize=9,
                    leading=11,
                    textColor=fg,
                    alignment=1,
                ),
            )
        ]],
        colWidths=[None],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _card(title: str, body_flowables: List[Any], styles: Dict[str, ParagraphStyle]) -> KeepTogether:
    header = Paragraph(title, styles["card_title"])
    inner = [header, Spacer(1, 0.08 * inch)] + body_flowables
    box = Table([[inner]], colWidths=[7.2 * inch])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
        ("BOX", (0, 0), (-1, -1), 0.75, HAIRLINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return KeepTogether([box])


def _bullets(items: List[str], styles: Dict[str, ParagraphStyle], max_items: int = 6) -> List[Any]:
    out: List[Any] = []
    for s in (items or [])[:max_items]:
        s = (s or "").strip()
        if not s:
            continue
        out.append(Paragraph(f"• {s}", styles["body"]))
        out.append(Spacer(1, 0.05 * inch))
    if not out:
        out.append(Paragraph("—", styles["muted"]))
    return out


def _compute_equity_and_max_dd(returns_list: Optional[List[float]]) -> Tuple[List[float], Optional[float]]:
    if not returns_list:
        return [], None
    e = 1.0
    peak = 1.0
    max_dd = 0.0
    eq: List[float] = []
    n = 0
    for r in returns_list:
        try:
            rr = float(r)
        except Exception:
            continue
        if rr != rr:  # NaN
            continue
        e *= (1.0 + rr)
        eq.append(e)
        if e > peak:
            peak = e
        dd = (e / peak) - 1.0
        if dd < max_dd:
            max_dd = dd
        n += 1
    if n < 5:
        return eq, None
    return eq, float(max_dd)


# ---------------------------
# Strategy Health Monitor (ADD)
# ---------------------------
def _strategy_health_monitor(
    *,
    verdict: str,
    fragility_index: Any,
    max_dd: Any,
    robustness_raw: Dict[str, Any],
    stability_transparency: Dict[str, Any],
    sizing: Dict[str, Any],
) -> Tuple[str, List[str], str]:
    """
    Returns: (health_label, signals, recommendation_line)
    This is intentionally simple + deterministic. It does NOT change scoring—only presents a monitoring-style view.
    """

    # Signals (simple heuristics)
    signals: List[str] = []

    # Rolling Sharpe stable: we don't have a rolling Sharpe series in Tier 2 payload,
    # so we proxy "stability" via stability_penalty_total + confidence.
    conf = stability_transparency.get("confidence", None)
    stab_pen = stability_transparency.get("stability_penalty_total", None)

    try:
        conf_f = float(conf) if conf is not None else None
    except Exception:
        conf_f = None

    try:
        stab_pen_f = float(stab_pen) if stab_pen is not None else None
    except Exception:
        stab_pen_f = None

    if conf_f is not None and conf_f >= 0.35 and (stab_pen_f is None or stab_pen_f <= 35.0):
        signals.append("✓ Rolling Sharpe stable")
    else:
        signals.append("✗ Rolling Sharpe unstable (proxy: confidence / stability penalty)")

    # Drawdown exceeds expected distribution: we only have max_dd; we flag if it's large in magnitude.
    try:
        mdd = float(max_dd) if max_dd is not None else None
    except Exception:
        mdd = None

    if mdd is not None and abs(mdd) >= 0.30:
        signals.append("✗ Drawdown exceeds expected distribution")
    else:
        signals.append("✓ Drawdown within expected envelope")

    # Bootstrap stability intact: use robustness overall_pass + presence of bootstrap stats
    boot = (robustness_raw.get("tests") or {}).get("bootstrap") or {}
    if bool(robustness_raw.get("overall_pass")) and (boot != {}):
        signals.append("✓ Bootstrap stability intact")
    else:
        signals.append("✗ Bootstrap stability not confirmed")

    # Regime shift detected: we don't have regime classifier yet, so we infer from fragility index.
    try:
        fi = float(fragility_index) if fragility_index is not None else None
    except Exception:
        fi = None

    if fi is not None and fi >= 34:
        signals.append("✗ Regime shift detected (proxy: fragility)")
    else:
        signals.append("✓ No regime shift detected (proxy: fragility)")

    # Health label
    # WARNING if: robustness fail OR fragility high OR large drawdown
    warning = False
    if robustness_raw and (robustness_raw.get("overall_pass") is False):
        warning = True
    if fi is not None and fi >= 67:
        warning = True
    if mdd is not None and abs(mdd) >= 0.30:
        warning = True

    health = "WARNING" if warning else "STABLE"

    # Recommendation (use sizing if available; otherwise your sample)
    # If sizing has a max_risk_pct, show it; otherwise show sample reduce line when warning.
    rec = "Maintain allocation; continue monitoring."
    if warning:
        rec = "Reduce allocation from 1.0% → 0.5%. Re-run robustness battery."

    try:
        mr = sizing.get("max_risk_pct", None)
        if mr is not None:
            mr_f = float(mr)
            # If warning, include both
            if warning:
                rec = f"Reduce allocation from 1.0% → 0.5% (cap risk at {mr_f:.2f}%). Re-run robustness battery."
            else:
                rec = f"Maintain sizing (cap risk at {mr_f:.2f}%). Continue monitoring."
    except Exception:
        pass

    return health, signals, rec


# ---------------------------
# Sparkline Flowable (stable + width-safe)
# ---------------------------
class SparklineWithDD(Flowable):
    """
    IMPORTANT: This flowable MUST fit inside a Table cell.
    Prior bug: width (230) exceeded the column width (~187pt), causing the line to run off the page.
    Fix: shrink-to-fit in wrap(), then clip to the fitted width.
    """

    def __init__(self, returns_list: Optional[List[float]], width: float = 9999.0, height: float = 46.0):
        super().__init__()
        self.returns_list = returns_list
        self._req_w = float(width)
        self._h = float(height)
        self._w = float(width)

    def wrap(self, availWidth, availHeight):
        # shrink-to-fit to the actual available width inside the table cell
        try:
            aw = float(availWidth)
        except Exception:
            aw = self._req_w
        if aw and aw > 0:
            self._w = min(self._req_w, aw)
        else:
            self._w = self._req_w
        return (self._w, self._h)

    def draw(self):
        c = self.canv
        w = float(getattr(self, "_w", self._req_w))
        h = float(self._h)

        eq, max_dd = _compute_equity_and_max_dd(self.returns_list)

        # Fixed vertical regions (prevents curve hugging the DD bar)
        label_y = 2.0
        label_h = 9.0

        bar_y = label_y + label_h + 2.0  # ~13
        bar_h = 2.0

        gap = 6.0
        spark_bottom = bar_y + bar_h + gap  # curve always above bar
        top_pad = 4.0
        spark_top = h - top_pad
        spark_h = max(12.0, spark_top - spark_bottom)

        if not eq or len(eq) < 2 or spark_h <= 0:
            c.setFont("Helvetica", 8)
            c.setFillColor(MUTED)
            c.drawString(0, h - 12, "Visual unavailable")
            return

        mn = min(eq)
        mx = max(eq)
        if abs(mx - mn) < 1e-12:
            mx = mn + 1e-12

        n = len(eq)

        # Build points inside [1, w-1] so strokes never exceed the clip
        x0 = 1.0
        x1 = max(x0 + 1.0, w - 1.0)

        pts: List[Tuple[float, float]] = []
        for i, val in enumerate(eq):
            t = i / (n - 1) if n > 1 else 0.0
            x = x0 + t * (x1 - x0)
            y = spark_bottom + ((val - mn) / (mx - mn)) * spark_h
            if y < spark_bottom:
                y = spark_bottom
            if y > spark_bottom + spark_h:
                y = spark_bottom + spark_h
            pts.append((x, y))

        # Clip region so line cannot bleed outside chart bounds
        c.saveState()
        clip_path = c.beginPath()
        clip_path.rect(0, spark_bottom, w, spark_h)
        c.clipPath(clip_path, stroke=0, fill=0)

        c.setStrokeColor(ACCENT)
        c.setLineWidth(1.2)
        c.setLineCap(1)
        c.setLineJoin(1)

        path = c.beginPath()
        path.moveTo(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            path.lineTo(x, y)
        c.drawPath(path, stroke=1, fill=0)

        c.restoreState()

        # DD bar (scaled to fixed 50%)
        dd_txt = "Max DD: —"
        dd_mag = 0.0
        if max_dd is not None:
            try:
                dd_txt = f"Max DD: {float(max_dd):.0%}"
                dd_mag = min(0.50, abs(float(max_dd)))
            except Exception:
                dd_txt = "Max DD: —"
                dd_mag = 0.0

        c.setStrokeColor(HAIRLINE)
        c.setLineWidth(2)
        c.line(0, bar_y, w, bar_y)

        if dd_mag > 0:
            bar_w = w * (dd_mag / 0.50)
            color = BAD if dd_mag >= 0.30 else WARN
            c.setStrokeColor(color)
            c.setLineWidth(2)
            c.line(0, bar_y, bar_w, bar_y)

        c.setFont("Helvetica", 8)
        c.setFillColor(MUTED)
        c.drawString(0, label_y, dd_txt)


# ---------------------------
# PDF Builder
# ---------------------------
def build_allocator_view_pdf(strategy: Union[Any, List[Any], Dict[str, Any]], signature: str) -> bytes:
    strat = _as_strategy(strategy)

    name = str(_get_field(strat, "name", "—") or "—")
    deploy = _get_field(strat, "deployability_score", None)
    verdict = str(_get_field(strat, "deployability_verdict", "—") or "—")
    grade = str(_get_field(strat, "grade", "—") or "—")
    band = str(_get_field(strat, "allocation_band", "—") or "—")

    confidence = _get_field(strat, "confidence", None)
    years = _get_field(strat, "years", None)
    rows = _get_field(strat, "rows", None)

    fragility = _get_field(strat, "fragility_index", None)
    memo_line = str(_get_field(strat, "memo_line", "—") or "—")

    sizing = _as_dict(_get_field(strat, "sizing_recommendation", None))
    deploy_breakdown = _as_dict(_get_field(strat, "deployability_breakdown", None))
    stability = _as_dict(_get_field(strat, "stability_transparency", None))
    constraints = _as_dict(_get_field(strat, "deployability_constraints", None))
    robustness_raw = _as_dict(_get_field(strat, "robustness_battery", None))

    peers = _as_list(_get_field(strat, "peers", None))
    what_change = _as_list(_get_field(strat, "what_would_change_mind", None))

    returns_list = _get_field(strat, "returns", None)
    if isinstance(returns_list, list):
        try:
            returns_list = [float(x) for x in returns_list]
        except Exception:
            returns_list = None
    else:
        returns_list = None

    prov = _as_dict(_get_field(strat, "provenance", None))
    api_v = str(prov.get("api_version", "") or "")
    scoring_v = str(prov.get("scoring_version", "") or "")
    schema_v = str(prov.get("schema_version", "") or "")
    ts_utc = str(prov.get("analysis_timestamp_utc", "") or "")
    dataset_hash = str(prov.get("dataset_hash_sha256", "") or "")
    det_mode = bool(prov.get("deterministic_mode", True))

    deploy_str = _fmt_float(deploy, 1)
    conf_str = _fmt_float(confidence, 2)
    years_str = _fmt_float(years, 4)
    rows_str = _fmt_int(rows)
    frag_str = _fmt_float(fragility, 1)
    frag_lab = _fragility_label(fragility)

    sizing_band = str(sizing.get("band") or sizing.get("suggested_band") or "—")
    max_risk_pct = sizing.get("max_risk_pct", None)
    max_risk_str = "—"
    try:
        if max_risk_pct is not None:
            max_risk_str = f"{float(max_risk_pct):.2f}%"
    except Exception:
        max_risk_str = "—"

    gates = sizing.get("gating_conditions") or []
    if isinstance(gates, str):
        gates = [gates]
    gates = [str(x).strip() for x in gates if str(x).strip()]
    sizing_rationale = str(sizing.get("rationale") or "").strip()

    rows_i = int(rows or 0)
    years_f = float(years or 0.0)
    conf_f: Optional[float] = None
    try:
        conf_f = float(confidence) if confidence is not None else None
    except Exception:
        conf_f = None

    if not robustness_raw and returns_list:
        try:
            robustness_raw = compute_robustness_battery(returns_list) or {}
        except Exception:
            robustness_raw = {}

    robustness = summarize_robustness_for_pdf(robustness_raw) if robustness_raw else {}

    data_ok = (rows_i >= 252) and (years_f >= 1.0)
    robust_ok = bool(robustness_raw.get("overall_pass")) if robustness_raw else False
    stability_ok = (
        (conf_f is not None and conf_f >= 0.35)
        and (float(stability.get("stability_penalty_total", 0.0) or 0.0) <= 35.0)
    )
    cap = str(constraints.get("capacity") or "Unknown")
    impl_ok = (cap.strip().lower() != "unknown")

    def _gate_icon(ok: bool) -> str:
        return "✅" if ok else "❌"

    ladder_line = (
        f"Gate status: Data {_gate_icon(data_ok)} • Robustness {_gate_icon(robust_ok)} • "
        f"Stability {_gate_icon(stability_ok)} • Implementability {_gate_icon(impl_ok)}"
    )

    if verdict.strip().lower().startswith("research"):
        next_action = "Pilot (max 0.25%)"
        result_line = "Result: Research"
    elif verdict.strip().lower().startswith("watch"):
        next_action = "Pilot (max 0.50–1.00%)"
        result_line = "Result: Pilot"
    else:
        next_action = "Deploy (scaled sizing)"
        result_line = "Result: Deploy"

    upgrade_conditions: List[str] = []
    if not data_ok:
        upgrade_conditions.append("≥252 rows and ≥1.0y history")
    if conf_f is None or conf_f < 0.35:
        upgrade_conditions.append("confidence ≥0.35")
    if not robust_ok:
        upgrade_conditions.append("robustness PASS")
    upgrade_conditions.append("OOS / paper track validation")
    upgrade_conditions = upgrade_conditions[:4]

    base_score = deploy_breakdown.get("base_score")
    total_penalty = deploy_breakdown.get("total_penalty")
    final_dep = deploy_breakdown.get("final_deployability") or deploy_breakdown.get("final")

    fail_drivers: List[str] = []
    if robustness and robustness.get("rows"):
        for row in robustness.get("rows", []):
            if isinstance(row, dict) and str(row.get("status", "")).upper() == "FAIL":
                lbl = str(row.get("label", "")).strip()
                if lbl:
                    fail_drivers.append(lbl)
    fail_drivers = fail_drivers[:2]

    boot = (robustness_raw.get("tests") or {}).get("bootstrap") or {}
    p05 = boot.get("sharpe_p05")
    p50 = boot.get("sharpe_p50")
    p95 = boot.get("sharpe_p95")

    def _fmt_maybe(v: Any, digits: int = 2) -> str:
        try:
            if v is None:
                return "—"
            fv = float(v)
            if abs(fv) > 1e6:
                return "—"
            return f"{fv:.{digits}f}"
        except Exception:
            return "—"

    bootstrap_line = f"Bootstrap Sharpe (p05/p50/p95): {_fmt_maybe(p05)} / {_fmt_maybe(p50)} / {_fmt_maybe(p95)}"

    rationale_lines: List[str] = []
    rationale_lines.append(
        f"Action is <b>{verdict}</b> driven by gate failures: "
        f"Data {_gate_icon(data_ok)}, Robustness {_gate_icon(robust_ok)}, Stability {_gate_icon(stability_ok)}."
    )
    if fail_drivers:
        rationale_lines.append(f"Primary robustness blockers: {', '.join(fail_drivers)}.")
    if upgrade_conditions:
        rationale_lines.append(f"Re-run after: {', '.join(upgrade_conditions[:3])}.")
    decision_rationale = " ".join(rationale_lines[:3])

    styles = getSampleStyleSheet()
    s: Dict[str, ParagraphStyle] = {}
    s["h1"] = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=INK, spaceAfter=4)
    s["sub"] = ParagraphStyle("sub", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=12, textColor=MUTED, spaceAfter=8)
    s["stamp"] = ParagraphStyle("stamp", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=11, textColor=MUTED, spaceAfter=8)
    s["body"] = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica", fontSize=9.6, leading=12.5, textColor=INK)
    s["muted"] = ParagraphStyle("muted", parent=styles["Normal"], fontName="Helvetica", fontSize=9.6, leading=12.5, textColor=MUTED)
    s["label"] = ParagraphStyle("label", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.7, leading=11, textColor=INK)
    s["card_title"] = ParagraphStyle("card_title", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10.5, leading=12.5, textColor=INK, spaceAfter=1)
    s["tiny"] = ParagraphStyle("tiny", parent=styles["Normal"], fontName="Helvetica", fontSize=8.7, leading=11, textColor=MUTED)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=44,
        rightMargin=44,
        topMargin=50,
        bottomMargin=72,
        title=TITLE,
    )

    elements: List[Any] = []
    elements.append(Paragraph(TITLE, s["h1"]))
    elements.append(Paragraph(SCOPE_LINE, s["sub"]))
    elements.append(Paragraph(PREPARED_BY, s["sub"]))

    if SHOW_PROVENANCE_BLOCK:
        elements.append(Paragraph(f"Deterministic output — SHA256 signature: {_short_sig(signature)}", s["stamp"]))
        meta_bits: List[str] = []
        if api_v or scoring_v or schema_v:
            meta_bits.append(f"API {api_v} • Scoring {scoring_v} • Schema {schema_v}".strip())
        if ts_utc:
            meta_bits.append(f"Generated (UTC): {ts_utc}")
        if dataset_hash:
            meta_bits.append(f"Dataset hash (sha256): {dataset_hash[:12]}…")
        meta_bits.append(f"Deterministic mode: {'ON' if det_mode else 'OFF'}")
        elements.append(Paragraph("<br/>".join(meta_bits), s["tiny"]))

    elements.append(Spacer(1, 0.14 * inch))

    v_fg = _verdict_color(verdict)
    v_bg = _verdict_bg(verdict)

    decision_left = [
        Paragraph("COMMITTEE ACTION", ParagraphStyle("cap", parent=s["label"], textColor=MUTED)),
        Spacer(1, 0.03 * inch),
        _pill(verdict.upper(), fg=v_fg, bg=v_bg),
        Spacer(1, 0.06 * inch),
        Paragraph(ladder_line, s["tiny"]),
        Paragraph(result_line, s["tiny"]),
        Spacer(1, 0.06 * inch),
        Paragraph("NEXT ELIGIBLE ACTION", ParagraphStyle("cap2", parent=s["label"], textColor=MUTED)),
        Paragraph(next_action, s["body"]),
    ]

    decision_mid = [
        Paragraph("DEPLOYABILITY", s["label"]),
        Paragraph(deploy_str, ParagraphStyle("big", parent=s["body"], fontName="Helvetica-Bold", fontSize=16, leading=18)),
        Spacer(1, 0.08 * inch),
        Paragraph("GRADE / BAND", s["label"]),
        Paragraph(f"{grade} • {band}", s["body"]),
        Spacer(1, 0.08 * inch),
        Paragraph("FRAGILITY", s["label"]),
        Paragraph(f"{frag_str} ({frag_lab})", ParagraphStyle("frag", parent=s["body"], fontName="Helvetica-Bold")),
    ]

    # width auto-fits the cell in wrap(); do NOT hardcode 230 again
    spark = SparklineWithDD(returns_list, width=9999.0, height=46.0)

    decision_right = [
        Paragraph("CONF / HISTORY", s["label"]),
        Paragraph(f"Conf {conf_str} • {years_str}y • {rows_str} rows", s["body"]),
        Spacer(1, 0.06 * inch),
        Paragraph("CONFIDENCE RANGE (BOOTSTRAP)", s["label"]),
        Paragraph(bootstrap_line, s["tiny"]),
        Spacer(1, 0.06 * inch),
        Paragraph("VISUAL", s["label"]),
        spark,
    ]

    decision_table = Table(
        [[decision_left, decision_mid, decision_right]],
        colWidths=[2.35 * inch, 2.25 * inch, 2.6 * inch],
    )
    decision_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 1.0, HAIRLINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    elements.append(decision_table)
    elements.append(Spacer(1, 0.12 * inch))

    elements.append(_card("Decision Rationale", [Paragraph(decision_rationale, s["body"])], s))
    elements.append(Spacer(1, 0.10 * inch))

    sd_lines = [
        f"<b>Deployability:</b> {_fmt_float(final_dep, 1)}",
        f"<b>Base signal:</b> {_fmt_float(base_score, 1)}",
        f"<b>Total penalty:</b> -{_fmt_float(total_penalty, 1)}",
        f"<b>Stability penalty:</b> {_fmt_float(stability.get('stability_penalty_total'), 1)}",
        f"<b>Fragility overlay:</b> {frag_lab}",
    ]
    elements.append(_card("Score Decomposition (Deterministic)", [Paragraph("<br/>".join(sd_lines), s["body"])], s))
    elements.append(Spacer(1, 0.10 * inch))

    sizing_body: List[Any] = [
        Paragraph(f"<b>Band:</b> {sizing_band}", s["body"]),
        Paragraph(f"<b>Max risk %:</b> {max_risk_str}", s["body"]),
    ]
    if sizing_rationale:
        sizing_body.append(Spacer(1, 0.04 * inch))
        sizing_body.append(Paragraph(f"<b>Rationale:</b> {sizing_rationale}", s["body"]))
    if gates:
        sizing_body.append(Spacer(1, 0.04 * inch))
        sizing_body.append(Paragraph(f"<b>Gates:</b> {', '.join(gates[:4])}", s["body"]))
    if upgrade_conditions:
        sizing_body.append(Spacer(1, 0.04 * inch))
        sizing_body.append(Paragraph(f"<b>Conditions to upgrade:</b> {', '.join(upgrade_conditions)}", s["body"]))
    elements.append(_card("Sizing Guidance (Committee-Ready)", sizing_body, s))
    elements.append(Spacer(1, 0.10 * inch))

    exec_lines = [
        "<b>Instrument:</b> ___",
        "<b>Rebalance cadence:</b> ___",
        "<b>Slippage assumption:</b> ___ bps",
        "<b>Kill-switch:</b> DD &gt; __% or robustness drift",
    ]
    elements.append(_card("Execution Notes (If Upgraded to Pilot)", [Paragraph("<br/>".join(exec_lines), s["body"])], s))
    elements.append(Spacer(1, 0.10 * inch))

    corr_lines = [
        "<b>Diversification:</b> Unknown (requires correlation to core book)",
        "<b>Next step:</b> run overlap vs benchmark/sleeve proxy",
        "<b>Known unknowns:</b> capacity, slippage, live execution constraints, correlation to book",
    ]
    elements.append(_card("Overlap & Portfolio Fit", [Paragraph("<br/>".join(corr_lines), s["body"])], s))
    elements.append(Spacer(1, 0.10 * inch))

    # ---------------------------
    # Strategy Health Monitor (ADD)
    # ---------------------------
    eq, max_dd = _compute_equity_and_max_dd(returns_list)
    health, signals, rec = _strategy_health_monitor(
        verdict=verdict,
        fragility_index=fragility,
        max_dd=max_dd,
        robustness_raw=robustness_raw or {},
        stability_transparency=stability or {},
        sizing=sizing or {},
    )
    hm_body: List[Any] = []
    hm_body.append(Paragraph(f"<b>Current Health:</b> {health}", s["body"]))
    hm_body.append(Spacer(1, 0.05 * inch))
    for sig_line in signals:
        hm_body.append(Paragraph(sig_line, s["body"]))
        hm_body.append(Spacer(1, 0.02 * inch))
    hm_body.append(Spacer(1, 0.04 * inch))
    hm_body.append(Paragraph(f"<b>Recommendation:</b> {rec}", s["body"]))
    hm_body.append(Spacer(1, 0.02 * inch))
    hm_body.append(Paragraph("Note: signals are deterministic proxies until live monitoring is implemented in Tier 3.", s["tiny"]))
    elements.append(_card("Strategy Health Monitor (Sample)", hm_body, s))
    elements.append(Spacer(1, 0.10 * inch))

    if robustness:
        rows_rb = robustness.get("rows") if isinstance(robustness.get("rows"), list) else []
        tdata = [["Test", "Status", "Detail"]]
        for row in rows_rb[:4]:
            if not isinstance(row, dict):
                continue
            tdata.append([
                str(row.get("label", "—")),
                str(row.get("status", "—")),
                str(row.get("detail", "—")),
            ])
        rt = Table(tdata, colWidths=[2.3 * inch, 0.9 * inch, 4.0 * inch], hAlign="LEFT")
        rt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2FF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("LEADING", (0, 0), (-1, -1), 11),
            ("GRID", (0, 0), (-1, -1), 0.25, HAIRLINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        overall = str(robustness.get("overall", "—"))
        elements.append(_card(
            "Robustness Battery (Deterministic)",
            [Paragraph(f"<b>Overall:</b> {overall}", s["body"]), Spacer(1, 0.05 * inch), rt],
            s,
        ))
        elements.append(Spacer(1, 0.10 * inch))

    if peers:
        pr = peers[:3]
        tdata = [["Rank", "Strategy", "Deploy", "Verdict"]]
        for row in pr:
            if not isinstance(row, dict):
                continue
            tdata.append([
                str(row.get("rank", "—")),
                str(row.get("name", "—")),
                _fmt_float(row.get("deployability_score"), 1),
                str(row.get("deployability_verdict", "—")),
            ])
        pt = Table(tdata, colWidths=[0.55 * inch, 3.35 * inch, 1.15 * inch, 1.85 * inch], hAlign="LEFT")
        pt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2FF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("LEADING", (0, 0), (-1, -1), 11),
            ("GRID", (0, 0), (-1, -1), 0.25, HAIRLINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))

        rel_line = "Relative edge: insufficient separation vs #2; require more data and OOS validation before preference is durable."
        try:
            if len(pr) >= 2:
                d0 = float(pr[0].get("deployability_score") or 0.0)
                d1 = float(pr[1].get("deployability_score") or 0.0)
                delta = d0 - d1
                rel_line = f"Relative edge: winner vs #2 deployability Δ {delta:+.1f}."
        except Exception:
            pass

        elements.append(_card("Peer Comparison (Top 3)", [pt, Spacer(1, 0.05 * inch), Paragraph(rel_line, s["tiny"])], s))
        elements.append(Spacer(1, 0.10 * inch))

    monitoring = [
        "Weekly drift check (Sharpe/DD stability).",
        "Monthly robustness re-run (bootstrap/windows/outliers/regime).",
        "Quarterly regime review + sizing re-approval if gates change.",
    ]
    elements.append(_card("Monitoring Plan (Pilot)", _bullets(monitoring, s, max_items=4), s))
    elements.append(Spacer(1, 0.10 * inch))

    appendix_blocks: List[Any] = []

    if deploy_breakdown:
        penalties = _as_dict(deploy_breakdown.get("penalties"))
        lines = [
            f"<b>Base score:</b> {_fmt_float(base_score, 1)}",
            f"<b>Total penalty:</b> {_fmt_float(total_penalty, 1)}",
            f"<b>Final deployability:</b> {_fmt_float(final_dep, 1)}",
        ]
        pen_items: List[tuple[str, float]] = []
        for k, v in penalties.items():
            try:
                fv = float(v)
            except Exception:
                continue
            if fv > 0:
                pen_items.append((k, fv))
        pen_items.sort(key=lambda x: x[1], reverse=True)
        for k, fv in pen_items[:5]:
            lines.append(f"{k.replace('_', ' ')}: -{fv:.0f}")
        appendix_blocks.append(_card("Penalty Transparency", [Paragraph("<br/>".join(lines), s["body"])], s))
        appendix_blocks.append(Spacer(1, 0.10 * inch))

    if stability:
        st_lines = []
        for k in ["rows", "years", "confidence", "stability_penalty_total"]:
            if k in stability:
                st_lines.append(f"<b>{k.replace('_', ' ').title()}:</b> {stability.get(k)}")
        drivers = stability.get("drivers") or []
        if isinstance(drivers, str):
            drivers = [drivers]
        drivers = [str(x).strip() for x in drivers if str(x).strip()]
        if drivers:
            st_lines.append(f"<b>Drivers:</b> {', '.join(drivers)}")
        appendix_blocks.append(_card("Stability Transparency", [Paragraph("<br/>".join(st_lines), s["body"])], s))
        appendix_blocks.append(Spacer(1, 0.10 * inch))

    if constraints:
        breakeven = constraints.get("fees_slippage_breakeven") or constraints.get("breakeven") or None
        breakeven_str = "—"
        try:
            if breakeven is not None:
                breakeven_str = f"{float(breakeven):.0f} bps/year"
        except Exception:
            breakeven_str = "—"
        checklist = constraints.get("checklist") or constraints.get("items") or []
        if isinstance(checklist, str):
            checklist = [checklist]
        checklist = [str(x).strip() for x in checklist if str(x).strip()]

        c_lines = [
            f"<b>Capacity:</b> {cap}",
            f"<b>Fees+slippage breakeven:</b> {breakeven_str}",
            "<b>Known unknowns:</b> capacity, slippage, correlation to book, live execution constraints.",
        ]
        if checklist:
            c_lines.append("<b>Checklist:</b>")
            c_lines.extend([f"• {x}" for x in checklist[:8]])

        appendix_blocks.append(_card("Deployability Constraints", [Paragraph("<br/>".join(c_lines), s["body"])], s))
        appendix_blocks.append(Spacer(1, 0.10 * inch))

    if what_change:
        appendix_blocks.append(_card("Upgrade Path (Procedural)", _bullets([str(x) for x in what_change], s, max_items=6), s))
        appendix_blocks.append(Spacer(1, 0.10 * inch))

    if memo_line and memo_line.strip() and memo_line.strip() != "—":
        appendix_blocks.append(_card("Allocator Memo", [Paragraph(memo_line, s["body"])], s))
        appendix_blocks.append(Spacer(1, 0.10 * inch))

    if appendix_blocks:
        elements.append(PageBreak())
        elements.append(Paragraph("Appendix — Audit & Implementation Notes", ParagraphStyle(
            "appendix_h", parent=s["h1"], fontSize=13.5, leading=17, spaceAfter=4
        )))
        elements.append(Paragraph("Deterministic drivers for internal review.", s["sub"]))
        elements.append(Spacer(1, 0.08 * inch))
        elements.extend(appendix_blocks)

    doc.build(
        elements,
        onFirstPage=lambda c, d: _draw_footer(c, d, signature),
        onLaterPages=lambda c, d: _draw_footer(c, d, signature),
    )
    return buffer.getvalue()