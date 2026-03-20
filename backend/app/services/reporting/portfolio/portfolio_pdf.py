from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.app.services.reporting.page1.layout import _draw_footer

TITLE = "Portfolio Intelligence Memo"
SUBTITLE = "Scope: cross-strategy overlap, clustering, and diversification diagnostics."

INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#475569")
HAIRLINE = colors.HexColor("#E2E8F0")
CARD_BG = colors.HexColor("#F8FAFC")
ACCENT = colors.HexColor("#2563EB")
GOOD = colors.HexColor("#16A34A")
WARN = colors.HexColor("#F59E0B")
BAD = colors.HexColor("#DC2626")


def _fmt_float(v: Any, digits: int = 2, default: str = "—") -> str:
    try:
        return f"{float(v):.{digits}f}"
    except Exception:
        return default


def _risk_color(risk: str):
    r = str(risk or "").upper()
    if r == "HIGH":
        return BAD
    if r == "MEDIUM":
        return WARN
    return GOOD


def _card(title: str, body_flowables: List[Any], width: float, styles: Dict[str, ParagraphStyle]) -> Table:
    inner = [Paragraph(title, styles["card_title"]), Spacer(1, 0.08 * inch)] + body_flowables
    t = Table([[inner]], colWidths=[width])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
                ("BOX", (0, 0), (-1, -1), 0.75, HAIRLINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return t


def build_portfolio_pdf(report: Dict[str, Any], signature: str) -> bytes:
    styles_src = getSampleStyleSheet()
    styles: Dict[str, ParagraphStyle] = {}

    styles["h1"] = ParagraphStyle(
        "h1",
        parent=styles_src["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=20,
        textColor=INK,
        spaceAfter=4,
    )
    styles["sub"] = ParagraphStyle(
        "sub",
        parent=styles_src["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=12,
        textColor=MUTED,
        spaceAfter=8,
    )
    styles["body"] = ParagraphStyle(
        "body",
        parent=styles_src["Normal"],
        fontName="Helvetica",
        fontSize=9.6,
        leading=12.5,
        textColor=INK,
    )
    styles["tiny"] = ParagraphStyle(
        "tiny",
        parent=styles_src["Normal"],
        fontName="Helvetica",
        fontSize=8.7,
        leading=11,
        textColor=MUTED,
    )
    styles["card_title"] = ParagraphStyle(
        "card_title",
        parent=styles_src["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=12.5,
        textColor=INK,
    )

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

    content_width = LETTER[0] - doc.leftMargin - doc.rightMargin

    names = report.get("names", [])
    matrix_shape = report.get("matrix_shape", ["—", "—"])
    correlation = report.get("correlation", {}) or {}
    clustering = report.get("clustering", {}) or {}
    overlap = report.get("overlap", {}) or {}
    recommendations = report.get("recommendations", {}) or {}
    allocation = report.get("allocation", {}) or {}

    avg_corr = correlation.get("average_correlation")
    div_score = correlation.get("diversification_score")
    corr_matrix = correlation.get("correlation_matrix", [])

    cluster_count = clustering.get("cluster_count", 0)
    clusters = clustering.get("clusters", [])

    overlap_risk = overlap.get("portfolio_overlap_risk", "—")
    overlap_groups = overlap.get("overlap_groups", [])

    summary = recommendations.get("summary", "—")
    action = recommendations.get("action", "—")
    bullets = recommendations.get("bullets", [])

    alloc_weights = allocation.get("weights", [])
    alloc_method = allocation.get("method", "—")
    alloc_improvement = allocation.get("expected_diversification_improvement", 0.0)
    alloc_notes = allocation.get("notes", [])

    elements: List[Any] = []
    elements.append(Paragraph(TITLE, styles["h1"]))
    elements.append(Paragraph(SUBTITLE, styles["sub"]))
    elements.append(Paragraph("Prepared by: Quant Research Critic (deterministic).", styles["sub"]))
    elements.append(Spacer(1, 0.10 * inch))

    summary_lines: List[Any] = [
        Paragraph(f"<b>Strategies:</b> {', '.join(names) if names else '—'}", styles["body"]),
        Paragraph(f"<b>Matrix shape:</b> {matrix_shape}", styles["body"]),
        Paragraph(f"<b>Average correlation:</b> {_fmt_float(avg_corr, 4)}", styles["body"]),
        Paragraph(f"<b>Diversification score:</b> {_fmt_float(div_score, 4)}", styles["body"]),
        Paragraph(
            f"<b>Portfolio overlap risk:</b> <font color='{_risk_color(overlap_risk).hexval()}'>{overlap_risk}</font>",
            styles["body"],
        ),
    ]
    elements.append(_card("Executive Summary", summary_lines, content_width, styles))
    elements.append(Spacer(1, 0.10 * inch))

    cluster_lines: List[Any] = [
        Paragraph(f"<b>Cluster count:</b> {cluster_count}", styles["body"]),
    ]
    for i, cluster in enumerate(clusters, start=1):
        cluster_lines.append(Spacer(1, 0.03 * inch))
        cluster_lines.append(Paragraph(f"<b>Cluster {i}:</b> {', '.join(cluster)}", styles["body"]))
    elements.append(_card("Strategy Clusters", cluster_lines, content_width, styles))
    elements.append(Spacer(1, 0.10 * inch))

    overlap_body: List[Any] = []
    if overlap_groups:
        tdata = [["Members", "Avg Corr", "Risk"]]
        for g in overlap_groups:
            members = ", ".join(g.get("members", []))
            avg_internal = _fmt_float(g.get("average_internal_correlation"), 4)
            risk = str(g.get("risk", "—"))
            tdata.append([members, avg_internal, risk])

        ot = Table(tdata, colWidths=[4.8 * inch, 1.0 * inch, 1.0 * inch], hAlign="LEFT")
        ot.setStyle(
            TableStyle(
                [
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
                ]
            )
        )
        overlap_body.append(ot)
    else:
        overlap_body.append(Paragraph("No overlap groups available.", styles["body"]))

    elements.append(_card("Overlap Diagnostics", overlap_body, content_width, styles))
    elements.append(Spacer(1, 0.10 * inch))

    rec_body: List[Any] = [
        Paragraph(f"<b>Summary:</b> {summary}", styles["body"]),
        Spacer(1, 0.04 * inch),
        Paragraph(f"<b>Action:</b> {action}", styles["body"]),
        Spacer(1, 0.04 * inch),
    ]
    for bullet in bullets:
        rec_body.append(Paragraph(f"• {bullet}", styles["body"]))
        rec_body.append(Spacer(1, 0.02 * inch))
    elements.append(_card("Allocator Recommendations", rec_body, content_width, styles))
    elements.append(Spacer(1, 0.10 * inch))

    allocation_body: List[Any] = [
        Paragraph(f"<b>Method:</b> {alloc_method}", styles["body"]),
        Paragraph(
            f"<b>Expected diversification improvement:</b> {_fmt_float(alloc_improvement, 2)}%",
            styles["body"],
        ),
        Spacer(1, 0.05 * inch),
    ]

    if alloc_weights:
        atdata = [["Strategy", "Suggested Weight"]]
        for row in alloc_weights:
            atdata.append([
                str(row.get("name", "—")),
                f"{_fmt_float(row.get('weight'), 2)}%",
            ])

        at = Table(atdata, colWidths=[5.4 * inch, 1.4 * inch], hAlign="LEFT")
        at.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2FF")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("LEADING", (0, 0), (-1, -1), 11),
                    ("GRID", (0, 0), (-1, -1), 0.25, HAIRLINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        allocation_body.append(at)
        allocation_body.append(Spacer(1, 0.05 * inch))

    for note in alloc_notes:
        allocation_body.append(Paragraph(f"• {note}", styles["body"]))
        allocation_body.append(Spacer(1, 0.02 * inch))

    elements.append(_card("Suggested Allocation", allocation_body, content_width, styles))
    elements.append(Spacer(1, 0.10 * inch))

    corr_body: List[Any] = []
    if corr_matrix and names:
        header = [""] + names
        tdata = [header]
        for name, row in zip(names, corr_matrix):
            tdata.append([name] + [_fmt_float(v, 4) for v in row])

        n_cols = len(header)
        col_width = min(1.2 * inch, content_width / max(1, n_cols))
        ct = Table(tdata, colWidths=[col_width] * n_cols, hAlign="LEFT")
        ct.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2FF")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.25, HAIRLINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ]
            )
        )
        corr_body.append(ct)
    else:
        corr_body.append(Paragraph("Correlation matrix unavailable.", styles["body"]))

    elements.append(_card("Correlation Matrix", corr_body, content_width, styles))

    doc.build(
        elements,
        onFirstPage=lambda c, d: _draw_footer(c, d, signature),
        onLaterPages=lambda c, d: _draw_footer(c, d, signature),
    )

    return buffer.getvalue()