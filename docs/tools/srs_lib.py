"""Formatting helpers for the SRS generator (python-docx).

All department formatting rules live here so the content script stays readable:
Times New Roman; body 12 pt, 1.15 line spacing, justified; H1 16 / H2 14 / H3 13 /
H4 12 pt bold, left-aligned; spacing by before/after settings (never blank lines);
captions above tables and below figures, numbered chapter-wise with SEQ fields so
Word can build the List of Figures and List of Tables.

Inline markup accepted by rich(): **bold**, *italic*, ~subscript~, ^superscript^.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

FONT = "Times New Roman"
TOKEN = re.compile(r"(\*\*.+?\*\*|\*[^*\s][^*]*?\*|~[^~]+~|\^[^^]+\^)")


def _set_fonts(element_with_rpr) -> None:
    """Force Times New Roman on every script slot and drop theme-font overrides."""
    rpr = element_with_rpr.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(a), FONT)
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rfonts.get(qn(a)) is not None:
            del rfonts.attrib[qn(a)]


class SRS:
    def __init__(self, chapter_breaks: bool = True) -> None:
        # chapter_breaks: every Heading 1 starts a new page (SRS chapters). A proposal's
        # numbered sections flow on, so the scope document turns this off.
        self.chapter_breaks = chapter_breaks
        self.doc = Document()
        self.chapter = "0"
        self.fig_n: dict[str, int] = {}
        self.tab_n: dict[str, int] = {}
        self.refs: dict[str, str] = {}        # key -> formatted reference
        self.ref_order: list[str] = []        # keys in order of first citation
        self._styles()

    # ------------------------------------------------------------------ styles
    def _style(self, name: str, base: str | None = None):
        st = self.doc.styles
        try:
            return st[name]
        except KeyError:
            s = st.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            if base:
                s.base_style = st[base]
            return s

    def _styles(self) -> None:
        d = self.doc
        sec = d.sections[0]
        sec.page_width, sec.page_height = Inches(8.5), Inches(11)
        for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            setattr(sec, side, Inches(1))
        sec.header_distance = sec.footer_distance = Inches(0.5)

        normal = d.styles["Normal"]
        _set_fonts(normal.element)
        normal.font.size = Pt(12)
        pf = normal.paragraph_format
        pf.line_spacing = 1.15
        pf.space_before = Pt(0)
        pf.space_after = Pt(6)
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pf.widow_control = True

        for lvl, size, before, after in ((1, 16, 0, 12), (2, 14, 12, 6), (3, 13, 10, 6), (4, 12, 8, 4)):
            h = d.styles[f"Heading {lvl}"]
            _set_fonts(h.element)
            h.font.size = Pt(size)
            h.font.bold = True
            h.font.italic = False
            h.font.color.rgb = RGBColor(0, 0, 0)
            f = h.paragraph_format
            f.alignment = WD_ALIGN_PARAGRAPH.LEFT
            f.space_before, f.space_after = Pt(before), Pt(after)
            f.keep_with_next = True
            f.line_spacing = 1.15
            f.page_break_before = lvl == 1 and self.chapter_breaks
            if lvl == 1 and not self.chapter_breaks:
                f.space_before = Pt(18)

        # Front-matter headings: same look as Heading 1 but kept out of the TOC.
        fh = self._style("Front Heading", "Normal")
        fh.font.size, fh.font.bold = Pt(16), True
        fh.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        fh.paragraph_format.space_after = Pt(12)
        fh.paragraph_format.keep_with_next = True
        fh.paragraph_format.page_break_before = True

        cap = d.styles["Caption"]
        _set_fonts(cap.element)
        cap.font.size, cap.font.bold, cap.font.italic = Pt(11), True, False
        cap.font.color.rgb = RGBColor(0, 0, 0)
        cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_before, cap.paragraph_format.space_after = Pt(6), Pt(6)
        cap.paragraph_format.line_spacing = 1.0

        tt = self._style("Table Text", "Normal")
        tt.font.size = Pt(10)
        tt.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        tt.paragraph_format.line_spacing = 1.0
        tt.paragraph_format.space_before, tt.paragraph_format.space_after = Pt(1), Pt(1)

        fg = self._style("Figure Body", "Normal")
        fg.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fg.paragraph_format.line_spacing = 1.0
        fg.paragraph_format.space_before, fg.paragraph_format.space_after = Pt(6), Pt(0)
        fg.paragraph_format.keep_with_next = True

        lb = d.styles["List Bullet"]
        _set_fonts(lb.element)
        lb.paragraph_format.space_after = Pt(3)

        # TOC and table-of-figures styles (Word built-in names, lower case).
        # The styleId must match Word's built-in ID or Word ignores the style when it builds the TOC.
        for name, sid, indent, hang, bold in (("toc 1", "TOC1", 0, 0, True), ("toc 2", "TOC2", 0.25, 0, False),
                                              ("toc 3", "TOC3", 0.5, 0, False),
                                              ("table of figures", "TableofFigures", 0.95, 0.95, False)):
            s = self._style(name, "Normal")
            s.element.set(qn("w:styleId"), sid)
            if s.element.get(qn("w:customStyle")) is not None:   # built-in, not custom
                del s.element.attrib[qn("w:customStyle")]
            s.font.bold = bold
            f = s.paragraph_format
            f.alignment = WD_ALIGN_PARAGRAPH.LEFT
            f.left_indent = Inches(indent)
            f.first_line_indent = Inches(-hang) if hang else None
            f.right_indent = Inches(0.4)
            f.space_before = Pt(4 if name == "toc 1" else 0)
            f.space_after = Pt(2)
            f.line_spacing = 1.15
            f.tab_stops.add_tab_stop(Inches(6.5), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)

        # Doc defaults too, so stray runs never fall back to Calibri.
        rpr_default = d.styles.element.find(qn("w:docDefaults")).find(qn("w:rPrDefault"))
        if rpr_default is not None:
            rpr = rpr_default.find(qn("w:rPr"))
            rf = rpr.find(qn("w:rFonts")) if rpr is not None else None
            if rf is not None:
                for a in list(rf.attrib):
                    del rf.attrib[a]
                for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                    rf.set(qn(a), FONT)

    # ------------------------------------------------------------------ text
    def rich(self, par, text: str, bold: bool = False, italic: bool = False, size: float | None = None) -> None:
        for part in TOKEN.split(text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                self.rich(par, part[2:-2], True, italic, size)
                continue
            if part.startswith("*") and part.endswith("*") and len(part) > 2 and not part.startswith("**"):
                self.rich(par, part[1:-1], bold, True, size)
                continue
            sub = part.startswith("~") and part.endswith("~") and len(part) > 2
            sup = part.startswith("^") and part.endswith("^") and len(part) > 2
            run = par.add_run(part[1:-1] if (sub or sup) else part)
            run.bold = bold or None
            run.italic = italic or None
            if size:
                run.font.size = Pt(size)
            if sub:
                run.font.subscript = True
            if sup:
                run.font.superscript = True

    def p(self, text: str = "", style: str | None = None, align=None, after: float | None = None,
          before: float | None = None, keep: bool = False, bold: bool = False, size: float | None = None,
          italic: bool = False):
        par = self.doc.add_paragraph(style=style)
        self.rich(par, text, bold=bold, italic=italic, size=size)
        f = par.paragraph_format
        if align is not None:
            f.alignment = align
        if after is not None:
            f.space_after = Pt(after)
        if before is not None:
            f.space_before = Pt(before)
        if keep:
            f.keep_with_next = True
        return par

    def item(self, label: str, text: str):
        """An identified requirement line such as 'BO-1: ...' with a hanging indent."""
        par = self.doc.add_paragraph()
        self.rich(par, f"**{label}:** {text}")
        f = par.paragraph_format
        f.left_indent = Inches(0.55)
        f.first_line_indent = Inches(-0.55)
        f.space_after = Pt(4)
        return par

    def bullet(self, text: str):
        par = self.doc.add_paragraph(style="List Bullet")
        self.rich(par, text)
        return par

    def h1(self, text: str, chapter: str | None = None):
        if chapter is not None:
            self.chapter = chapter
        return self.p(text, style="Heading 1")

    def h2(self, text: str):
        return self.p(text, style="Heading 2")

    def h3(self, text: str):
        return self.p(text, style="Heading 3")

    def h4(self, text: str):
        return self.p(text, style="Heading 4")

    def front_heading(self, text: str, first: bool = False):
        par = self.p(text, style="Front Heading")
        if first:
            par.paragraph_format.page_break_before = False
        return par

    def page_break(self) -> None:
        from docx.enum.text import WD_BREAK
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ------------------------------------------------------------------ references
    def cite(self, *keys: str) -> str:
        nums = []
        for k in keys:
            if k not in self.refs:
                raise KeyError(f"unknown reference key {k}")
            if k not in self.ref_order:
                self.ref_order.append(k)
            nums.append(self.ref_order.index(k) + 1)
        return "[" + ", ".join(str(n) for n in nums) + "]"

    # ------------------------------------------------------------------ fields
    @staticmethod
    def field(par, instr: str, result: str = "") -> None:
        def fc(kind: str):
            r = par.add_run()
            e = OxmlElement("w:fldChar")
            e.set(qn("w:fldCharType"), kind)
            r._r.append(e)
        fc("begin")
        r = par.add_run()
        it = OxmlElement("w:instrText")
        it.set(qn("xml:space"), "preserve")
        it.text = f" {instr} "
        r._r.append(it)
        fc("separate")
        par.add_run(result)
        fc("end")

    def toc(self, instr: str, placeholder: str) -> None:
        par = self.doc.add_paragraph()
        self.field(par, instr, placeholder)

    # ------------------------------------------------------------------ captions
    def next_fig(self, offset: int = 1) -> str:
        return f"Figure {self.chapter}.{self.fig_n.get(self.chapter, 0) + offset}"

    def next_tab(self, offset: int = 1) -> str:
        return f"Table {self.chapter}.{self.tab_n.get(self.chapter, 0) + offset}"

    def _caption(self, kind: str, counter: dict, text: str, keep: bool):
        n = counter.get(self.chapter, 0) + 1
        counter[self.chapter] = n
        par = self.doc.add_paragraph(style="Caption")
        par.add_run(f"{kind} {self.chapter}.")
        self.field(par, f"SEQ {kind} \\* ARABIC" + (" \\r 1" if n == 1 else ""), str(n))
        self.rich(par, f": {text}")
        par.paragraph_format.keep_with_next = keep
        return f"{kind} {self.chapter}.{n}"

    def figure(self, path: Path, caption: str, width: float = 6.5) -> str:
        par = self.doc.add_paragraph(style="Figure Body")
        par.add_run().add_picture(str(path), width=Inches(width))
        return self._caption("Figure", self.fig_n, caption, keep=False)

    # ------------------------------------------------------------------ tables
    @staticmethod
    def _shade(cell, fill: str) -> None:
        tcpr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        tcpr.append(shd)

    def table(self, caption: str | None, headers: list[str], rows: list[list[str]], widths: list[float],
              size: float = 10, first_col_bold: bool = False, header_fill: str = "D9D9D9") -> str:
        # Front-matter tables (revision history, abbreviations) are not numbered captions.
        label = self._caption("Table", self.tab_n, caption, keep=True) if caption else ""
        t = self.doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        # Header row repeats on every page the table spans.
        trpr = t.rows[0]._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        th.set(qn("w:val"), "true")
        trpr.append(th)
        for i, htxt in enumerate(headers):
            c = t.rows[0].cells[i]
            c.paragraphs[0].style = self.doc.styles["Table Text"]
            self.rich(c.paragraphs[0], htxt, bold=True, size=size)
            c.paragraphs[0].paragraph_format.keep_with_next = True   # header never alone at page end
            self._shade(c, header_fill)
        for row in rows:
            cells = t.add_row().cells
            for i, txt in enumerate(row):
                lines = txt.split("\n") if txt else [""]
                cells[i].paragraphs[0].style = self.doc.styles["Table Text"]
                self.rich(cells[i].paragraphs[0], lines[0], bold=first_col_bold and i == 0, size=size)
                for extra in lines[1:]:
                    par = cells[i].add_paragraph(style="Table Text")
                    self.rich(par, extra, size=size)
        # Keep every row on one page so no row is cut in half at a page break.
        for r in t.rows:
            cs = OxmlElement("w:cantSplit")
            r._tr.get_or_add_trPr().insert(0, cs)
        for i, w in enumerate(widths):
            t.columns[i].width = Inches(w)
            for r in t.rows:
                r.cells[i].width = Inches(w)
        # A small gap after the table (spacing via paragraph settings, not blank text). The
        # paragraph itself is only 1 pt high, so a table that ends at the page foot never
        # pushes an empty line onto a page of its own.
        self._tiny(self.doc.add_paragraph(), after=6)
        return label

    @staticmethod
    def _tiny(par, after: float = 0) -> None:
        """Make an empty paragraph 1 pt high (exact line spacing, 1 pt paragraph mark)."""
        from docx.enum.text import WD_LINE_SPACING
        f = par.paragraph_format
        f.space_before = Pt(0)
        f.space_after = Pt(after)
        f.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        f.line_spacing = Pt(1)
        ppr = par._p.get_or_add_pPr()
        rpr = ppr.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            sect = ppr.find(qn("w:sectPr"))      # schema order: rPr must come before sectPr
            if sect is not None:
                sect.addprevious(rpr)
            else:
                ppr.append(rpr)
        if rpr.find(qn("w:sz")) is None:
            sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), "2")
            rpr.append(sz)

    # ------------------------------------------------------------------ sections
    @staticmethod
    def page_numbers(section, fmt: str, start: int | None) -> None:
        sp = section._sectPr
        pg = sp.find(qn("w:pgNumType"))
        if pg is None:
            pg = OxmlElement("w:pgNumType")
            cols = sp.find(qn("w:cols"))
            if cols is not None:
                cols.addprevious(pg)
            else:
                sp.append(pg)
        pg.set(qn("w:fmt"), fmt)
        if start is None:
            if pg.get(qn("w:start")) is not None:
                del pg.attrib[qn("w:start")]
        else:
            pg.set(qn("w:start"), str(start))

    def footer_page_field(self, section) -> None:
        section.footer.is_linked_to_previous = False
        par = section.footer.paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.style = self.doc.styles["Normal"]
        par.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.field(par, "PAGE", "1")

    def new_section(self, landscape: bool | None = None):
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        # python-docx ends the previous section with an empty paragraph holding its sectPr;
        # keep it 1 pt high so it cannot spill onto an otherwise blank page.
        ends = [p for p in self.doc.paragraphs if p._p.pPr is not None and p._p.pPr.find(qn("w:sectPr")) is not None]
        if ends:
            self._tiny(ends[-1])
        if landscape is not None:
            want = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
            if sec.orientation != want:
                sec.orientation = want
                sec.page_width, sec.page_height = sec.page_height, sec.page_width
        return sec

    def save(self, path: Path) -> None:
        self.doc.save(str(path))
