"""Generate the Indonesian TraceLens audience briefing PDF from Markdown."""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "TRACELENS_AUDIENCE_BRIEFING_ID.md"
OUTPUT = ROOT / "docs" / "TraceLens_AI_Audience_Briefing_ID.pdf"

NAVY = colors.HexColor("#081426")
BLUE = colors.HexColor("#2563EB")
CYAN = colors.HexColor("#0891B2")
INK = colors.HexColor("#182235")
MUTED = colors.HexColor("#526176")
LIGHT = colors.HexColor("#EEF4FB")
BORDER = colors.HexColor("#C9D6E7")
WHITE = colors.white
RED = colors.HexColor("#B42318")


def register_fonts() -> tuple[str, str, str]:
    candidates = [
        (
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/consola.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        ),
    ]
    for regular, bold, mono in candidates:
        if regular.exists() and bold.exists() and mono.exists():
            pdfmetrics.registerFont(TTFont("TL-Regular", str(regular)))
            pdfmetrics.registerFont(TTFont("TL-Bold", str(bold)))
            pdfmetrics.registerFont(TTFont("TL-Mono", str(mono)))
            return "TL-Regular", "TL-Bold", "TL-Mono"
    return "Helvetica", "Helvetica-Bold", "Courier"


REGULAR, BOLD, MONO = register_fonts()


class BriefingDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="content",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(PageTemplate(id="main", frames=[frame], onPage=self.draw_page))
        self._heading_counter = 0

    def beforeDocument(self):
        # multiBuild performs several passes to resolve the table of contents.
        # Bookmark identifiers must remain identical on every pass.
        self._heading_counter = 0

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in {"H1", "H2"}:
            level = 0 if flowable.style.name == "H1" else 1
            text = flowable.getPlainText()
            key = f"heading-{self._heading_counter}"
            self._heading_counter += 1
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=False)
            self.notify("TOCEntry", (level, text, self.page, key))

    def draw_page(self, canvas, doc):
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.4)
        canvas.line(17 * mm, 14 * mm, A4[0] - 17 * mm, 14 * mm)
        canvas.setFont(REGULAR, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(17 * mm, 9.5 * mm, "TraceLens AI - Audience Briefing")
        canvas.drawRightString(A4[0] - 17 * mm, 9.5 * mm, f"Halaman {doc.page}")
        canvas.restoreState()


def styles():
    base = getSampleStyleSheet()
    return {
        "Title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName=BOLD,
            fontSize=30,
            leading=34,
            textColor=WHITE,
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "Subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName=REGULAR,
            fontSize=14,
            leading=20,
            textColor=colors.HexColor("#CFE2FF"),
            alignment=TA_CENTER,
        ),
        "H1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName=BOLD,
            fontSize=17,
            leading=21,
            textColor=NAVY,
            spaceBefore=6 * mm,
            spaceAfter=3 * mm,
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=BOLD,
            fontSize=12.5,
            leading=16,
            textColor=BLUE,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=REGULAR,
            fontSize=9.3,
            leading=14,
            textColor=INK,
            alignment=TA_JUSTIFY,
            spaceAfter=2.2 * mm,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName=REGULAR,
            fontSize=9.2,
            leading=13.5,
            textColor=INK,
            leftIndent=6 * mm,
            firstLineIndent=-3 * mm,
            spaceAfter=1.4 * mm,
        ),
        "Quote": ParagraphStyle(
            "Quote",
            parent=base["BodyText"],
            fontName=REGULAR,
            fontSize=10,
            leading=15,
            textColor=NAVY,
            leftIndent=8 * mm,
            rightIndent=8 * mm,
            borderColor=CYAN,
            borderWidth=1.4,
            borderPadding=7,
            backColor=LIGHT,
            spaceBefore=2 * mm,
            spaceAfter=4 * mm,
        ),
        "Code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName=MONO,
            fontSize=7.8,
            leading=11,
            textColor=colors.HexColor("#D8E6FF"),
            backColor=NAVY,
            borderPadding=8,
            leftIndent=3 * mm,
            rightIndent=3 * mm,
            spaceBefore=2 * mm,
            spaceAfter=4 * mm,
        ),
        "TOCHeading": ParagraphStyle(
            "TOCHeading",
            parent=base["Heading1"],
            fontName=BOLD,
            fontSize=20,
            leading=24,
            textColor=NAVY,
            spaceAfter=6 * mm,
        ),
        "Small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName=REGULAR,
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
    }


STYLES = styles()


def inline_markup(text: str) -> str:
    value = escape(text)
    value = re.sub(r"`([^`]+)`", r'<font name="TL-Mono">\1</font>' if MONO == "TL-Mono" else r"<font face='Courier'>\1</font>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", rf'<font name="{BOLD}">\1</font>', value)
    return value


def markdown_table(lines: list[str]) -> Table:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue
        rows.append([Paragraph(inline_markup(c), STYLES["Small"]) for c in cells])
    count = len(rows[0])
    widths = [170 * mm / count] * count
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), BOLD),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def cover() -> list:
    banner = Table(
        [
            [Spacer(1, 21 * mm)],
            [Paragraph("TRACELENS AI", STYLES["Title"])],
            [Paragraph("Panduan Lengkap Penjelasan Sistem<br/>dan Hasil Review Teknis", STYLES["Subtitle"])],
            [Spacer(1, 22 * mm)],
            [Paragraph("EVIDENCE-GROUNDED LOG INVESTIGATION", ParagraphStyle(
                "strap", parent=STYLES["Subtitle"], fontName=BOLD, fontSize=9, leading=12,
                textColor=colors.HexColor("#7DD3FC"), letterSpacing=2,
            ))],
            [Spacer(1, 21 * mm)],
        ],
        colWidths=[176 * mm],
        rowHeights=None,
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0, NAVY),
    ]))
    meta_style = ParagraphStyle(
        "covermeta", parent=STYLES["Body"], alignment=TA_CENTER,
        fontSize=10, leading=15, textColor=MUTED,
    )
    return [
        Spacer(1, 14 * mm),
        banner,
        Spacer(1, 15 * mm),
        Paragraph("Dokumen audiensi dan speaker guide", meta_style),
        Paragraph("Status review: Strong MVP - belum production-ready", meta_style),
        Paragraph("28 Juli 2026", meta_style),
        Spacer(1, 12 * mm),
        HRFlowable(width="45%", thickness=2, color=BLUE, hAlign="CENTER"),
        Spacer(1, 8 * mm),
        Paragraph(
            "Dokumen ini menjelaskan visi, arsitektur, alur investigasi, kontrol keamanan, "
            "hasil validasi, temuan teknis, roadmap, skenario demo, dan FAQ TraceLens AI.",
            ParagraphStyle("coverdesc", parent=STYLES["Body"], alignment=TA_CENTER,
                           leftIndent=24 * mm, rightIndent=24 * mm, textColor=MUTED),
        ),
        PageBreak(),
    ]


def parse_markdown(text: str) -> list:
    lines = text.splitlines()
    story: list = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []
    table_lines: list[str] = []
    skipped_title = 0

    def flush_paragraph():
        if paragraph:
            story.append(Paragraph(inline_markup(" ".join(paragraph)), STYLES["Body"]))
            paragraph.clear()

    def flush_table():
        if table_lines:
            story.extend([markdown_table(table_lines.copy()), Spacer(1, 3 * mm)])
            table_lines.clear()

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            flush_paragraph()
            flush_table()
            if in_code:
                story.append(Preformatted("\n".join(code_lines), STYLES["Code"]))
                code_lines.clear()
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        if line.startswith("|"):
            flush_paragraph()
            table_lines.append(line)
            continue
        flush_table()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("# "):
            skipped_title += 1
            if skipped_title == 1:
                continue
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[2:]), STYLES["H1"]))
        elif line.startswith("## "):
            if skipped_title == 1 and line.startswith("## Panduan"):
                continue
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[3:]), STYLES["H1"]))
        elif line.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[4:]), STYLES["H2"]))
        elif line.startswith("> "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[2:]), STYLES["Quote"]))
        elif re.match(r"^[-*] ", line):
            flush_paragraph()
            story.append(Paragraph("- " + inline_markup(line[2:]), STYLES["Bullet"]))
        elif re.match(r"^\d+\. ", line):
            flush_paragraph()
            number, body = line.split(". ", 1)
            story.append(Paragraph(f"{number}. " + inline_markup(body), STYLES["Bullet"]))
        elif line.startswith("**Dokumen audiensi"):
            continue
        else:
            paragraph.append(line)
    flush_paragraph()
    flush_table()
    return story


def build() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    document = BriefingDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=17 * mm,
        bottomMargin=19 * mm,
        title="TraceLens AI - Panduan Lengkap Penjelasan Sistem dan Hasil Review Teknis",
        author="TraceLens AI Engineering",
        subject="Audience briefing, architecture, security review, validation, and roadmap",
    )
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOC1", fontName=BOLD, fontSize=9.5, leading=14,
            leftIndent=0, firstLineIndent=0, textColor=NAVY, spaceBefore=2,
        ),
        ParagraphStyle(
            "TOC2", fontName=REGULAR, fontSize=8.5, leading=12,
            leftIndent=8 * mm, firstLineIndent=0, textColor=MUTED,
        ),
    ]
    story = cover()
    story.extend([
        Paragraph("Daftar Isi", STYLES["TOCHeading"]),
        toc,
        PageBreak(),
    ])
    story.extend(parse_markdown(source))
    document.multiBuild(story)


if __name__ == "__main__":
    build()
    print(OUTPUT)
