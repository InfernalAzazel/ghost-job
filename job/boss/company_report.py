"""把查企业的结果（CompanyRow.get_dict）导出为 PDF。"""

from __future__ import annotations

from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from job import __version__

# reportlab 内置的中文字体，不用随安装包附带字体文件
FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(FONT))

ACCENT = "#2B6DE5"
TEXT = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#6B7280")
BORDER = colors.HexColor("#E5E7EB")
RISK_COLORS = {"low": "#16A34A", "medium": "#EA580C", "high": "#DC2626"}


def _style(name: str, size: float, color: Any = TEXT, **kw: Any) -> ParagraphStyle:
    return ParagraphStyle(
        name,
        fontName=FONT,
        fontSize=size,
        leading=size * 1.5,
        textColor=color,
        wordWrap="CJK",
        **kw,
    )


TITLE = _style("title", 18, spaceAfter=2 * mm)
META = _style("meta", 9, MUTED)
SECTION = _style("section", 12, spaceBefore=6 * mm, spaceAfter=2 * mm)
BODY = _style("body", 10)
SMALL = _style("small", 8.5, MUTED)


def _text(value: Any) -> str:
    # STSong-Light 里没有「·」（会显示成▲），换成字形相近的「・」
    return escape(str(value or "").replace("·", "・"))


def _link(text: str, href: str) -> str:
    if not href:
        return text
    return f'<a href="{escape(href, {chr(34): "&quot;"})}" color="{ACCENT}">{text}</a>'


def company_pdf(report: dict[str, Any]) -> bytes:
    """生成企业报告 PDF：AI 评估、工商信息、网上搜索结果。"""
    story: list[Any] = [
        Paragraph(_text(report.get("full_name") or report.get("name")), TITLE),
        Paragraph(
            f"{_text(report.get('name'))} ・ 查询于 {_text(report.get('checked_at'))}"
            f" ・ Ghost Job v{__version__}",
            META,
        ),
        Paragraph("AI 评估", SECTION),
    ]

    risk_color = RISK_COLORS.get(str(report.get("risk")), "#6B7280")
    story.append(
        Paragraph(
            f'<font color="{risk_color}">【{_text(report.get("risk_label"))}】</font>'
            f" {_text(report.get('summary'))}",
            BODY,
        )
    )
    for point in report.get("points") or []:
        text = _link(_text(point.get("text")), str(point.get("href") or ""))
        story.append(Paragraph(f"・ {text}", BODY))

    story.append(Paragraph("工商信息", SECTION))
    info = report.get("info") or []
    if info:
        table = Table(
            [
                [
                    Paragraph(_text(i.get("label")), SMALL),
                    Paragraph(_text(i.get("value")), BODY),
                ]
                for i in info
            ],
            colWidths=[35 * mm, None],
        )
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(table)
    else:
        story.append(Paragraph("BOSS 公司主页上没有工商信息", SMALL))

    hits = report.get("hits") or []
    story.append(Paragraph(f"网上搜索（{len(hits)} 条）", SECTION))
    for hit in hits:
        title = _link(_text(hit.get("title")), str(hit.get("href") or ""))
        story += [
            Paragraph(
                f"{title} <font color='#6B7280' size='8'>[{_text(hit.get('query'))}]</font>",
                BODY,
            ),
            Paragraph(_text(hit.get("body")), SMALL),
            Spacer(0, 2 * mm),
        ]

    buffer = BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=str(report.get("full_name") or report.get("name") or "企业报告"),
    ).build(story)
    return buffer.getvalue()
