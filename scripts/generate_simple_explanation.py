"""Generate a short, non-technical TraceLens audience PDF."""

from __future__ import annotations

import re
import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "TRACELENS_PENJELASAN_SINGKAT_ID.md"
OUTPUT = ROOT / "docs" / "TraceLens_AI_Penjelasan_Singkat_ID.pdf"

NAVY = colors.HexColor("#081426")
BLUE = colors.HexColor("#2563EB")
CYAN = colors.HexColor("#0891B2")
INK = colors.HexColor("#182235")
MUTED = colors.HexColor("#526176")
LIGHT = colors.HexColor("#EEF4FB")
BORDER = colors.HexColor("#C9D6E7")


def fonts():
    candidates = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf"), Path("C:/Windows/Fonts/consola.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")),
    ]
    for regular, bold, mono in candidates:
        if regular.exists() and bold.exists() and mono.exists():
            pdfmetrics.registerFont(TTFont("Simple-Regular", str(regular)))
            pdfmetrics.registerFont(TTFont("Simple-Bold", str(bold)))
            pdfmetrics.registerFont(TTFont("Simple-Mono", str(mono)))
            return "Simple-Regular", "Simple-Bold", "Simple-Mono"
    return "Helvetica", "Helvetica-Bold", "Courier"


REGULAR, BOLD, MONO = fonts()


class SimpleDoc(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(filename, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=17 * mm, bottomMargin=18 * mm, title="TraceLens AI - Penjelasan Sederhana", author="TraceLens AI Engineering")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="content", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(PageTemplate(id="main", frames=[frame], onPage=self.page_footer))

    def page_footer(self, canvas, doc):
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canvas.setFont(REGULAR, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 8.5 * mm, "TraceLens AI - Penjelasan Sederhana")
        canvas.drawRightString(A4[0] - 18 * mm, 8.5 * mm, f"Halaman {doc.page}")
        canvas.restoreState()


STYLES = getSampleStyleSheet()
TITLE = ParagraphStyle("SimpleTitle", parent=STYLES["Title"], fontName=BOLD, fontSize=28, leading=33, textColor=colors.white, alignment=TA_CENTER, spaceAfter=8 * mm)
SUBTITLE = ParagraphStyle("SimpleSubtitle", parent=STYLES["Normal"], fontName=REGULAR, fontSize=13, leading=18, textColor=colors.HexColor("#D9E9FF"), alignment=TA_CENTER)
H1 = ParagraphStyle("SimpleH1", parent=STYLES["Heading1"], fontName=BOLD, fontSize=17, leading=21, textColor=NAVY, spaceBefore=5 * mm, spaceAfter=3 * mm, keepWithNext=True)
H2 = ParagraphStyle("SimpleH2", parent=STYLES["Heading2"], fontName=BOLD, fontSize=12.5, leading=16, textColor=BLUE, spaceBefore=4 * mm, spaceAfter=2 * mm, keepWithNext=True)
BODY = ParagraphStyle("SimpleBody", parent=STYLES["BodyText"], fontName=REGULAR, fontSize=10, leading=15, textColor=INK, alignment=TA_LEFT, spaceAfter=2.5 * mm)
BULLET = ParagraphStyle("SimpleBullet", parent=BODY, leftIndent=6 * mm, firstLineIndent=-3 * mm, alignment=TA_LEFT, spaceAfter=1.3 * mm)
QUOTE = ParagraphStyle("SimpleQuote", parent=BODY, leftIndent=7 * mm, rightIndent=7 * mm, borderColor=CYAN, borderWidth=1.2, borderPadding=7, backColor=LIGHT, textColor=NAVY, spaceBefore=2 * mm, spaceAfter=4 * mm)
CODE = ParagraphStyle("SimpleCode", parent=STYLES["Code"], fontName=MONO, fontSize=8.6, leading=12, textColor=colors.HexColor("#F8FAFC"), backColor=NAVY, borderPadding=8, leftIndent=2 * mm, rightIndent=2 * mm, spaceBefore=2 * mm, spaceAfter=4 * mm)


def inline(text: str) -> str:
    value = escape(text)
    value = re.sub(r"`([^`]+)`", rf'<font name="{MONO}">\1</font>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", rf'<font name="{BOLD}">\1</font>', value)
    return value


def code_block(lines: list[str]):
    code = Preformatted("\n".join(lines), CODE)
    box = Table([[code]], colWidths=[174 * mm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#334E75")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return box


def cover(title="TRACELENS AI", subtitle="Penjelasan Sederhana untuk Audiensi", strapline="LOG MENTAH → TIMELINE → BUKTI"):
    box = Table([[Spacer(1, 22 * mm)], [Paragraph(inline(title), TITLE)], [Paragraph(inline(subtitle), SUBTITLE)], [Spacer(1, 20 * mm)], [Paragraph(inline(strapline), SUBTITLE)], [Spacer(1, 20 * mm)]], colWidths=[174 * mm])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    meta = ParagraphStyle("Meta", parent=BODY, alignment=TA_CENTER, textColor=MUTED, fontSize=10, leading=15)
    return [Spacer(1, 12 * mm), box, Spacer(1, 13 * mm), Paragraph("Versi ringkas, tanpa jargon teknis", meta), Paragraph("Untuk menjelaskan konsep dan demo TraceLens AI", meta), Spacer(1, 8 * mm), PageBreak()]


def parse(text: str):
    story = []
    paragraph = []
    code = []
    in_code = False

    def flush():
        if paragraph:
            story.append(Paragraph(inline(" ".join(paragraph)), BODY))
            paragraph.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            flush()
            if in_code:
                story.append(code_block(code))
                code.clear()
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if not line:
            flush()
            continue
        if line.startswith("# "):
            flush()
            story.append(Paragraph(inline(line[2:]), H1))
        elif line.startswith("## "):
            flush()
            story.append(Paragraph(inline(line[3:]), H1))
        elif line.startswith("#### "):
            flush()
            story.append(Paragraph(inline(line[5:]), H2))
        elif line.startswith("### "):
            flush()
            story.append(Paragraph(inline(line[4:]), H2))
        elif line.startswith("> "):
            flush()
            story.append(Paragraph(inline(line[2:]), QUOTE))
        elif re.match(r"^[-*] ", line):
            flush()
            story.append(Paragraph("• " + inline(line[2:]), BULLET))
        elif re.match(r"^\d+\. ", line):
            flush()
            story.append(Paragraph(inline(line), BULLET))
        else:
            paragraph.append(line)
    flush()
    return story


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--title", default="TRACELENS AI")
    parser.add_argument("--subtitle", default="Penjelasan Sederhana untuk Audiensi")
    parser.add_argument("--strapline", default="LOG MENTAH → TIMELINE → BUKTI")
    args = parser.parse_args()
    doc = SimpleDoc(str(args.output))
    doc.build(cover(args.title, args.subtitle, args.strapline) + parse(args.source.read_text(encoding="utf-8")))
    print(args.output)


if __name__ == "__main__":
    main()
