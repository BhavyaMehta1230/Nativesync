import os
import uuid
from datetime import datetime
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

OUTPUT_DIR = "generated_files"
os.makedirs(OUTPUT_DIR, exist_ok=True)

ACCENT = RGBColor(0xE6, 0x39, 0x4B)
GRAY = RGBColor(0x77, 0x77, 0x77)
DARK = RGBColor(0x22, 0x22, 0x22)


def _set_base_style(doc):
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    style.font.color.rgb = DARK
    style.paragraph_format.line_spacing = 1.2
    style.paragraph_format.space_after = Pt(8)


def _add_bottom_border(paragraph, color="E6394B", size="10"):
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), "6")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)
    p_pr.append(borders)


def _add_page_number_field(paragraph):
    run = paragraph.add_run()
    run.font.size = Pt(8)
    run.font.color.rgb = GRAY

    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")

    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)


def build_docx(title, sections, subtitle=""):
    doc = Document()
    _set_base_style(doc)

    for section in doc.sections:
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        section.top_margin = Inches(0.9)
        section.bottom_margin = Inches(0.9)

    # title block
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_p.add_run(title or "Untitled Document")
    title_run.font.size = Pt(30)
    title_run.font.bold = True
    title_run.font.color.rgb = ACCENT
    title_run.font.name = "Calibri"
    title_p.paragraph_format.space_after = Pt(4)

    if subtitle:
        sub_p = doc.add_paragraph()
        sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = sub_p.add_run(subtitle)
        sub_run.font.size = Pt(13)
        sub_run.font.color.rgb = GRAY
        sub_run.font.italic = True
        sub_p.paragraph_format.space_after = Pt(6)

    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_run = date_p.add_run(datetime.now().strftime("%B %d, %Y"))
    date_run.font.size = Pt(9)
    date_run.font.color.rgb = GRAY
    date_p.paragraph_format.space_after = Pt(4)
    _add_bottom_border(date_p, size="14")

    doc.add_paragraph()

    for sec in sections:
        heading = sec.get("heading", "").strip()
        content = sec.get("content", "").strip()
        bullets = sec.get("bullets", [])

        if heading:
            h = doc.add_paragraph()
            h_run = h.add_run(heading)
            h_run.font.size = Pt(16)
            h_run.font.bold = True
            h_run.font.color.rgb = ACCENT
            h.paragraph_format.space_before = Pt(18)
            h.paragraph_format.space_after = Pt(4)
            _add_bottom_border(h, color="E5E5E8", size="4")

        if content:
            for para in content.split("\n\n"):
                if para.strip():
                    p = doc.add_paragraph(para.strip())
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        for bullet in bullets:
            if bullet.strip():
                bp = doc.add_paragraph(bullet.strip(), style="List Bullet")
                bp.paragraph_format.space_after = Pt(4)

    # footer: branding left, page number right, using tab stops
    section = doc.sections[0]
    footer_p = section.footer.paragraphs[0]
    footer_p.text = ""
    brand_run = footer_p.add_run("NativeSync")
    brand_run.font.size = Pt(8)
    brand_run.font.color.rgb = GRAY

    tab_run = footer_p.add_run("\t\t\tPage ")
    tab_run.font.size = Pt(8)
    tab_run.font.color.rgb = GRAY
    _add_page_number_field(footer_p)

    filename = f"{uuid.uuid4().hex}.docx"
    filepath = os.path.join(OUTPUT_DIR, filename)
    doc.save(filepath)
    return filename