"""PDF report generator using ReportLab."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from babel.numbers import format_currency

from domain.entities import PortfolioCustodian, Position


def _fmt_brl(value) -> str:
    try:
        return format_currency(float(value), "BRL", locale="pt_BR")
    except Exception:
        return f"R$ {float(value):,.2f}"


def _fmt_qty(value) -> str:
    v = float(value)
    if v == int(v):
        return str(int(v))
    return f"{v:.8f}".rstrip("0").rstrip(".")


class PdfReportGenerator:
    """Generates a portfolio PDF report using ReportLab."""

    def generate(
        self,
        output_path: str,
        positions: list[Position],
        custodians: list[PortfolioCustodian] | None = None,
    ) -> str:
        """Generate a PDF and return the output path."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        doc = SimpleDocTemplate(
            output_path, pagesize=A4,
            leftMargin=20 * mm, rightMargin=20 * mm,
            topMargin=20 * mm, bottomMargin=20 * mm,
        )

        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle(
            "CustomTitle", parent=styles["Title"],
            fontSize=18, textColor=colors.HexColor("#0078D4"),
            spaceAfter=6,
        )
        story.append(Paragraph("💰 Relatório de Portfólio", title_style))
        story.append(Spacer(1, 4 * mm))

        # Metadata
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        open_positions = [p for p in positions if p.quantity > Decimal("0")]
        total_cost = sum(float(p.total_cost) for p in open_positions)

        meta_style = ParagraphStyle(
            "Meta", parent=styles["Normal"], fontSize=10, spaceAfter=4,
        )
        story.append(Paragraph(f"Gerado em: {now}", meta_style))
        story.append(Paragraph(
            f"Patrimônio Total (Custo): <b>{_fmt_brl(total_cost)}</b> | "
            f"Posições Abertas: <b>{len(open_positions)}</b>",
            meta_style,
        ))
        story.append(Spacer(1, 6 * mm))

        # ── Positions Table ────────────────────────────────────────────
        story.append(Paragraph("Posições", styles["Heading2"]))
        story.append(Spacer(1, 2 * mm))

        pos_data = [["Ticker", "Classe", "Qtd", "PM", "Custo Total", "Instituição"]]
        for p in open_positions:
            pos_data.append([
                p.ticker,
                p.asset_class.label,
                _fmt_qty(p.quantity),
                _fmt_brl(p.avg_price),
                _fmt_brl(p.total_cost),
                p.institution,
            ])

        if len(pos_data) > 1:
            t = Table(pos_data, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F9F9F9")]),
                ("ALIGN", (2, 1), (4, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("Nenhuma posição aberta.", meta_style))

        story.append(Spacer(1, 8 * mm))

        # ── Custody Table ──────────────────────────────────────────────
        if custodians:
            story.append(Paragraph("Custódia por Instituição", styles["Heading2"]))
            story.append(Spacer(1, 2 * mm))

            cust_data = [["Instituição", "Ticker", "Quantidade"]]
            for c in sorted(custodians, key=lambda x: (x.institution, x.ticker)):
                cust_data.append([c.institution, c.ticker, _fmt_qty(c.quantity)])

            t2 = Table(cust_data, repeatRows=1)
            t2.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F9F9F9")]),
                ("ALIGN", (2, 1), (2, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t2)

        # Footer
        story.append(Spacer(1, 10 * mm))
        footer_style = ParagraphStyle(
            "Footer", parent=styles["Normal"],
            fontSize=8, textColor=colors.HexColor("#999999"),
            alignment=1,  # center
        )
        story.append(Paragraph(
            "Portfolio Control System V3.1 — Gerado automaticamente", footer_style
        ))

        doc.build(story)
        return output_path
