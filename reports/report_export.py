"""Centralized PDF and CSV export for all reports.

Uses ReportLab for PDF generation. Each export function takes headers
and rows (list of lists of strings) plus a title, and writes to the
given output path.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


def export_csv(
    path: str,
    headers: list[str],
    rows: list[list[str]],
) -> str:
    """Write headers + rows to a CSV file. Returns the path."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def export_pdf(
    path: str,
    title: str,
    headers: list[str],
    rows: list[list[str]],
    *,
    landscape_mode: bool = False,
) -> str:
    """Generate a PDF table report. Returns the path."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    page = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(
        path, pagesize=page,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    story: list = []

    # Title
    title_style = ParagraphStyle(
        "RptTitle", parent=styles["Title"],
        fontSize=16, textColor=colors.HexColor("#0078D4"),
        spaceAfter=4,
    )
    story.append(Paragraph(title, title_style))

    # Date
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    meta = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9, spaceAfter=4)
    story.append(Paragraph(f"Gerado em: {now}", meta))
    story.append(Spacer(1, 4 * mm))

    # Table
    table_data = [headers] + rows
    if len(table_data) > 1:
        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F9F9F9")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("Nenhum dado disponível.", meta))

    # Footer
    story.append(Spacer(1, 8 * mm))
    footer = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontSize=7, textColor=colors.HexColor("#999999"), alignment=1,
    )
    story.append(Paragraph(
        "Portfolio Control System — Gerado automaticamente", footer,
    ))

    doc.build(story)
    return path
