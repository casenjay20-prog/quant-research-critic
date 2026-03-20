# backend/app/services/reporting/compare/compare_pdf.py
from __future__ import annotations

from io import BytesIO
from typing import Any, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


TITLE = "Strategy Ranking Memo (Tier 1 — Research Tool)"
SUBTITLE = "Deterministic ranking memo for research triage. Verdict is a deployability badge (not a return forecast)."


def _short_sig(sig: str, n: int = 8) -> str:
    return (sig or "UNKNOWN").strip()[:n].upper()


def build_compare_pdf(results: List[Any], signature: str, watermark: bool = True) -> bytes:
    """
    Tier 1 PDF: shows ranking + deployability verdict + watermark.
    results: list of StrategySummary-like objects or dicts.
    signature: deterministic sha256 hex.
    watermark: if True, prints a large subtle watermark.
    """
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=48,
        rightMargin=48,
        topMargin=54,
        bottomMargin=54,
        title=TITLE,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceAfter=4,
        textColor=colors.HexColor("#111827"),
    )

    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#374151"),
        spaceAfter=16,
    )

    stamp_style = ParagraphStyle(
        "stamp",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#6B7280"),
        spaceAfter=14,
    )

    cell_style = ParagraphStyle(
        "cell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111827"),
    )

    header_style = ParagraphStyle(
        "header",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111827"),
    )

    verdict_ok_style = ParagraphStyle(
        "verdict_ok",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#065F46"),
    )

    verdict_mid_style = ParagraphStyle(
        "verdict_mid",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400E"),
    )

    verdict_bad_style = ParagraphStyle(
        "verdict_bad",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#991B1B"),
    )

    upsell_style = ParagraphStyle(
        "upsell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#6B7280"),
    )

    def _get(obj: Any, key: str, default: Any = "") -> Any:
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _verdict_style(v: str) -> ParagraphStyle:
        vv = (v or "").strip().lower()
        if vv == "deployable":
            return verdict_ok_style
        if vv == "watchlist":
            return verdict_mid_style
        return verdict_bad_style

    # --- elements ---
    elements: List[Any] = []
    elements.append(Paragraph(TITLE, title_style))
    elements.append(Paragraph(SUBTITLE, subtitle_style))
    elements.append(Paragraph(f"Deterministic output — SHA256 signature: {_short_sig(signature)}", stamp_style))

    # --- table ---
    header = [
        Paragraph("Rank", header_style),
        Paragraph("Strategy", header_style),
        Paragraph("Deploy", header_style),
        Paragraph("Verdict", header_style),
        Paragraph("Grade", header_style),
        Paragraph("Band", header_style),
        Paragraph("Years", header_style),
    ]

    rows: List[List[Any]] = [header]

    for i, r in enumerate(results, start=1):
        name = str(_get(r, "name", "—") or "—")
        deploy = _get(r, "deployability_score", None)
        verdict = str(_get(r, "deployability_verdict", "—") or "—")
        grade = str(_get(r, "grade", "—") or "—")
        band = str(_get(r, "allocation_band", "—") or "—")
        years = _get(r, "years", None)

        deploy_str = "—"
        try:
            if deploy is not None:
                deploy_str = f"{float(deploy):.1f}"
        except Exception:
            deploy_str = "—"

        years_str = "—"
        try:
            if years is not None:
                years_str = f"{float(years):.4f}"
        except Exception:
            years_str = "—"

        rows.append(
            [
                Paragraph(str(i), cell_style),
                Paragraph(name, cell_style),
                Paragraph(deploy_str, cell_style),
                Paragraph(verdict, _verdict_style(verdict)),
                Paragraph(grade, cell_style),
                Paragraph(band, cell_style),
                Paragraph(years_str, cell_style),
            ]
        )

    tbl = Table(
        rows,
        colWidths=[
            0.55 * inch,  # Rank
            1.9 * inch,   # Strategy
            0.85 * inch,  # Deploy
            1.05 * inch,  # Verdict
            0.55 * inch,  # Grade
            2.0 * inch,   # Band (tightened)
            0.75 * inch,  # Years
        ],
        hAlign="LEFT",
    )

    tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F9FAFB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),     # tightened
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),  # tightened
            ]
        )
    )

    elements.append(tbl)

    # --- subtle upsell ---
    elements.append(Spacer(1, 0.18 * inch))
    elements.append(
        Paragraph(
            "For fragility diagnostics and capital sizing guidance, see Allocator View.",
            upsell_style,
        )
    )

    def _draw_watermark(canvas, doc) -> None:
        if not watermark:
            return
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 64)
        canvas.setFillColor(colors.Color(0, 0, 0, alpha=0.06))
        canvas.translate(doc.pagesize[0] / 2, doc.pagesize[1] / 2)
        canvas.rotate(30)
        canvas.drawCentredString(0, 0, "RESEARCH PREVIEW")
        canvas.restoreState()

    doc.build(elements, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
    return buffer.getvalue()