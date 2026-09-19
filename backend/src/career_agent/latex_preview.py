from __future__ import annotations

import re
import zlib

_WIDTHS = {
    "Times-Roman": (
        250, 333, 408, 500, 500, 833, 778, 180, 333, 333, 500, 564, 250, 333, 250, 278, 500, 500, 500, 500,
        500, 500, 500, 500, 500, 500, 278, 278, 564, 564, 564, 444, 921, 722, 667, 667, 722, 611, 556, 722,
        722, 333, 389, 722, 611, 889, 722, 722, 556, 722, 667, 556, 611, 722, 722, 944, 722, 722, 611, 333,
        278, 333, 469, 500, 333, 444, 500, 444, 500, 444, 333, 500, 500, 278, 278, 500, 278, 778, 500, 500,
        500, 500, 333, 389, 278, 500, 500, 722, 500, 500, 444, 480, 200, 480, 541, 761, 500, 250, 333, 500,
        444, 1000, 500, 500, 333, 1000, 556, 333, 889, 250, 611, 250, 250, 333, 333, 444, 444, 350, 500,
        1000, 333, 980, 389, 333, 722, 250, 444, 722, 250, 333, 500, 500, 500, 500, 200, 500, 333, 760, 276,
        500, 564, 333, 760, 333, 400, 564, 300, 300, 333, 500, 453, 250, 333, 300, 310, 500, 750, 750, 750,
        444, 722, 722, 722, 722, 722, 722, 889, 667, 611, 611, 611, 611, 333, 333, 333, 333, 722, 722, 722,
        722, 722, 722, 722, 564, 722, 722, 722, 722, 722, 722, 556, 500, 444, 444, 444, 444, 444, 444, 667,
        444, 444, 444, 444, 444, 278, 278, 278, 278, 500, 500, 500, 500, 500, 500, 500, 564, 500, 500, 500,
        500, 500, 500, 500, 500,
    ),
    "Times-Bold": (
        250, 333, 555, 500, 500, 1000, 833, 278, 333, 333, 500, 570, 250, 333, 250, 278, 500, 500, 500, 500,
        500, 500, 500, 500, 500, 500, 333, 333, 570, 570, 570, 500, 930, 722, 667, 722, 722, 667, 611, 778,
        778, 389, 500, 778, 667, 944, 722, 778, 611, 778, 722, 556, 667, 722, 722, 1000, 722, 722, 667, 333,
        278, 333, 581, 500, 333, 500, 556, 444, 556, 444, 333, 500, 556, 278, 333, 556, 278, 833, 556, 500,
        556, 556, 444, 389, 333, 556, 500, 722, 500, 500, 444, 394, 220, 394, 520, 761, 500, 250, 333, 500,
        500, 1000, 500, 500, 333, 1000, 556, 333, 1000, 250, 667, 250, 250, 333, 333, 500, 500, 350, 500,
        1000, 333, 1000, 389, 333, 722, 250, 444, 722, 250, 333, 500, 500, 500, 500, 220, 500, 333, 747,
        300, 500, 570, 333, 747, 333, 400, 570, 300, 300, 333, 556, 540, 250, 333, 300, 330, 500, 750, 750,
        750, 500, 722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667, 389, 389, 389, 389, 722, 722,
        778, 778, 778, 778, 778, 570, 778, 722, 722, 722, 722, 722, 611, 556, 500, 500, 500, 500, 500, 500,
        722, 444, 444, 444, 444, 444, 278, 278, 278, 278, 500, 556, 500, 500, 500, 500, 500, 570, 500, 556,
        556, 556, 556, 500, 556, 500,
    ),
    "Times-Italic": (
        250, 333, 420, 500, 500, 833, 778, 214, 333, 333, 500, 675, 250, 333, 250, 278, 500, 500, 500, 500,
        500, 500, 500, 500, 500, 500, 333, 333, 675, 675, 675, 500, 920, 611, 611, 667, 722, 611, 611, 722,
        722, 333, 444, 667, 556, 833, 667, 722, 611, 722, 611, 500, 556, 722, 611, 833, 611, 556, 556, 389,
        278, 389, 422, 500, 333, 500, 500, 444, 500, 444, 278, 500, 500, 278, 278, 444, 278, 722, 500, 500,
        500, 500, 389, 389, 278, 500, 444, 667, 444, 444, 389, 400, 275, 400, 541, 761, 500, 250, 333, 500,
        556, 889, 500, 500, 333, 1000, 500, 333, 944, 250, 556, 250, 250, 333, 333, 556, 556, 350, 500, 889,
        333, 980, 389, 333, 667, 250, 389, 556, 250, 389, 500, 500, 500, 500, 275, 500, 333, 760, 276, 500,
        675, 333, 760, 333, 400, 675, 300, 300, 333, 500, 523, 250, 333, 300, 310, 500, 750, 750, 750, 500,
        611, 611, 611, 611, 611, 611, 889, 667, 611, 611, 611, 611, 333, 333, 333, 333, 722, 667, 722, 722,
        722, 722, 722, 675, 722, 722, 722, 722, 722, 556, 611, 500, 500, 500, 500, 500, 500, 500, 667, 444,
        444, 444, 444, 444, 278, 278, 278, 278, 500, 500, 500, 500, 500, 500, 500, 675, 500, 500, 500, 500,
        500, 444, 500, 444,
    ),
    "Times-BoldItalic": (
        250, 389, 555, 500, 500, 833, 778, 278, 333, 333, 500, 570, 250, 333, 250, 278, 500, 500, 500, 500,
        500, 500, 500, 500, 500, 500, 333, 333, 570, 570, 570, 500, 832, 667, 667, 667, 722, 667, 667, 722,
        778, 389, 500, 667, 611, 889, 722, 722, 611, 722, 667, 556, 611, 722, 667, 889, 667, 611, 611, 333,
        278, 333, 570, 500, 333, 500, 500, 444, 500, 444, 333, 500, 556, 278, 278, 500, 278, 778, 556, 500,
        500, 500, 389, 389, 278, 556, 444, 667, 500, 444, 389, 348, 220, 348, 570, 761, 500, 250, 333, 500,
        500, 1000, 500, 500, 333, 1000, 556, 333, 944, 250, 611, 250, 250, 333, 333, 500, 500, 350, 500,
        1000, 333, 1000, 389, 333, 722, 250, 389, 611, 250, 389, 500, 500, 500, 500, 220, 500, 333, 747,
        266, 500, 606, 333, 747, 333, 400, 570, 300, 300, 333, 576, 500, 250, 333, 300, 300, 500, 750, 750,
        750, 500, 667, 667, 667, 667, 667, 667, 944, 667, 667, 667, 667, 667, 389, 389, 389, 389, 722, 722,
        722, 722, 722, 722, 722, 570, 722, 722, 722, 722, 722, 611, 611, 500, 500, 500, 500, 500, 500, 500,
        722, 444, 444, 444, 444, 444, 278, 278, 278, 278, 500, 556, 500, 500, 500, 500, 500, 570, 500, 556,
        556, 556, 556, 444, 500, 444,
    ),
}
_FONTS = {"R": "Times-Roman", "B": "Times-Bold", "I": "Times-Italic", "BI": "Times-BoldItalic"}
_FONT_KEY = {"R": "F1", "B": "F2", "I": "F3", "BI": "F4"}

_STRUCTURE = re.compile(
    r"\\(?:resumeSubHeadingListStart|resumeSubHeadingListEnd|resumeItemListStart|resumeItemListEnd"
    r"|begin\{itemize\}(?:\[[^\]]*\])?|end\{itemize\}|item(?![A-Za-z])|small|scshape|raggedright|noindent|centering)"
)
_MACRO = re.compile(r"\\(section\*?|resumeSubheading|resumeSubSubheading|resumeProjectHeading|resumeItem|resumeSubItem)(?![A-Za-z])")
_DROP_WITH_ARG = ("vspace", "hspace", "rule", "setlength", "titlerule", "vskip")
_SYMBOLS = {
    "textbullet": "\u2022", "bullet": "\u2022", "quad": " ", "qquad": "  ", "hfill": " ", "textbar": "|",
    "LaTeX": "LaTeX", "TeX": "TeX", "ldots": "...", "dots": "...", "&": "&", "%": "%", "$": "$", "#": "#", "_": "_",
    "{": "{", "}": "}", "textasciitilde": "~", "textasciicircum": "^", "textbackslash": "\\", " ": " ", ",": " ",
}


def is_jake_style(latex: str) -> bool:
    body = latex.split("\\begin{document}", 1)[-1]
    return bool(re.search(r"\\(resumeSubheading|resumeProjectHeading|resumeItem)\b", body))


# --- LaTeX reading ------------------------------------------------------------------------

def _strip_comments(s: str) -> str:
    return re.sub(r"(?<!\\)%[^\n]*", "", s)


def _group(s: str, i: int) -> tuple[str, int]:
    """Read one balanced {...} group at/after i (skipping whitespace). Returns ("", i) when none."""
    n = len(s)
    while i < n and s[i] in " \t\r\n":
        i += 1
    if i >= n or s[i] != "{":
        return "", i
    depth, j = 0, i
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], n


def _runs(s: str, bold: bool = False, italic: bool = False) -> list[tuple[str, str]]:
    """Inline LaTeX -> [(text, style)] with style in R/B/I/BI."""
    out: list[tuple[str, str]] = []
    style = lambda b, i: ("B" if b else "") + ("I" if i else "") or "R"  # noqa: E731
    i, n, buf = 0, len(s), []

    def flush() -> None:
        if buf:
            out.append(("".join(buf), style(bold, italic)))
            buf.clear()

    while i < n:
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+)\*?", s[i:])
            if not m:  # \& \% \$ \\ \, etc.
                nxt = s[i + 1] if i + 1 < n else ""
                buf.append(_SYMBOLS.get(nxt, " " if nxt == "\\" else nxt))
                i += 2
                continue
            name = m.group(1)
            i += m.end()
            if name in ("textbf", "textit", "emph", "underline", "textsc", "textsf", "texttt", "small", "large", "Large", "LARGE",
                        "Huge", "huge", "normalsize", "footnotesize", "tiny", "text", "mbox"):
                arg, j = _group(s, i)
                if j == i:  # declaration form (\small ...): no argument, just drop it
                    continue
                flush()
                out.extend(_runs(arg, bold or name == "textbf", italic or name in ("textit", "emph")))
                i = j
            elif name == "href":
                _, j = _group(s, i)
                arg, j = _group(s, j)
                flush()
                out.extend(_runs(arg, bold, italic))
                i = j
            elif name in _DROP_WITH_ARG:
                _, i = _group(s, i)
            elif name in _SYMBOLS:
                buf.append(_SYMBOLS[name])
                if s[i:i + 2] == "{}":
                    i += 2
            # other control words (\bfseries, \scshape, \selectfont...) are dropped
            continue
        if c == "$":
            j = s.find("$", i + 1)
            if j != -1:
                inner = s[i + 1:j].strip()
                buf.append({"|": " | ", "\\bullet": "\u2022", "\\cdot": "\u00b7", "\\times": "x"}.get(inner, inner))
                i = j + 1
                continue
        if c in "{}":
            i += 1
            continue
        if c == "~":
            buf.append(" ")
        elif s.startswith("---", i):
            buf.append("\u2014")
            i += 2
        elif s.startswith("--", i):
            buf.append("\u2013")
            i += 1
        elif s.startswith("``", i):
            buf.append("\u201c")
            i += 1
        elif s.startswith("''", i):
            buf.append("\u201d")
            i += 1
        else:
            buf.append(c)
        i += 1
    flush()
    # collapse whitespace across run boundaries
    cleaned: list[tuple[str, str]] = []
    prev_space = True
    for text, st in out:
        text = re.sub(r"\s+", " ", text)
        if prev_space and text.startswith(" "):
            text = text[1:]
        if text:
            cleaned.append((text, st))
            prev_space = text.endswith(" ")
    if cleaned:
        cleaned[-1] = (cleaned[-1][0].rstrip(), cleaned[-1][1])
    return [r for r in cleaned if r[0]]


def _plain(s: str) -> str:
    return "".join(t for t, _ in _runs(s))


# --- document model -----------------------------------------------------------------------

def _parse(latex: str) -> dict:
    src = _strip_comments(latex)
    page = (595.28, 841.89) if re.search(r"\\documentclass\[[^\]]*a4paper", src) else (612.0, 792.0)
    body = src.split("\\begin{document}", 1)[-1].split("\\end{document}", 1)[0]

    header: list[str] = []
    m = re.search(r"\\begin\{center\}(.*?)\\end\{center\}", body, re.S)
    small_caps = False
    if m:
        header = [ln for ln in re.split(r"\\\\(?:\[[^\]]*\])?", m.group(1)) if _plain(ln)]
        small_caps = "scshape" in (header[0] if header else "")
        body = body[:m.start()] + body[m.end():]

    blocks: list[tuple] = []
    pos = 0

    def loose(chunk: str) -> None:
        text = _STRUCTURE.sub("", chunk)
        for ln in re.split(r"\\\\(?:\[[^\]]*\])?", text):
            r = _runs(ln)
            if r:
                blocks.append(("line", r))

    for mm in _MACRO.finditer(body):
        if mm.start() < pos:
            continue
        loose(body[pos:mm.start()])
        name, i = mm.group(1), mm.end()
        argc = {"section": 1, "section*": 1, "resumeSubheading": 4, "resumeSubSubheading": 2, "resumeProjectHeading": 2,
                "resumeItem": 1, "resumeSubItem": 1}[name]
        args = []
        for _ in range(argc):
            a, i = _group(body, i)
            args.append(a)
        pos = i
        if name.startswith("section"):
            blocks.append(("section", _plain(args[0])))
        elif name == "resumeSubheading":
            blocks.append(("sub", [_runs(a) for a in args]))
        elif name == "resumeSubSubheading":
            blocks.append(("subsub", [_runs(a) for a in args]))
        elif name == "resumeProjectHeading":
            blocks.append(("project", [_runs(a) for a in args]))
        else:
            blocks.append(("item", _runs(args[0])))
    loose(body[pos:])
    return {"page": page, "header": header, "small_caps": small_caps, "blocks": blocks}


# --- drawing ------------------------------------------------------------------------------

def _width(text: str, style: str, size: float) -> float:
    table = _WIDTHS[_FONTS[style]]
    return sum(table[b - 32] if 32 <= b <= 255 else 250 for b in text.encode("cp1252", "replace")) * size / 1000.0


def _pdf_str(text: str) -> bytes:
    raw = text.encode("cp1252", "replace")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


class _Canvas:
    def __init__(self, size: tuple[float, float], margin: float = 36.0) -> None:
        self.w, self.h = size
        self.left, self.right = margin, size[0] - margin
        self.top, self.bottom = size[1] - margin, margin
        self.pages: list[list[bytes]] = []
        self.ops: list[bytes] = []
        self.y = self.top
        self.new_page()

    def new_page(self) -> None:
        if self.ops or self.pages:
            self.pages.append(self.ops)
        self.ops = []
        self.y = self.top

    def need(self, height: float) -> None:
        if self.y - height < self.bottom:
            self.new_page()

    def text(self, x: float, y: float, runs: list[tuple[str, str]], size: float) -> float:
        """One text object per line: consecutive Tj advance the cursor, so extractors read it as one line."""
        parts = [b"BT %.2f %.2f Td" % (x, y)]
        for t, st in runs:
            parts.append(b"/%s %.2f Tf %s Tj" % (_FONT_KEY[st].encode(), size, _pdf_str(t)))
            x += _width(t, st, size)
        parts.append(b"ET")
        self.ops.append(b" ".join(parts))
        return x

    def rule(self, y: float, weight: float = 0.4) -> None:
        self.ops.append(b"%.2f w %.2f %.2f m %.2f %.2f l S" % (weight, self.left, y, self.right, y))

    def finish(self) -> bytes:
        pages = self.pages + [self.ops]
        objs: list[bytes] = []
        n_pages = len(pages)
        kids = b" ".join(b"%d 0 R" % (3 + 2 * k) for k in range(n_pages))
        font_ids = [3 + 2 * n_pages + k for k in range(4)]
        resources = b"<< /Font << " + b" ".join(b"/F%d %d 0 R" % (k + 1, font_ids[k]) for k in range(4)) + b" >> >>"
        objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objs.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % n_pages)
        for k, ops in enumerate(pages):
            content = zlib.compress(b"\n".join(ops))
            objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Resources %s /Contents %d 0 R >>"
                        % (self.w, self.h, resources, 4 + 2 * k))
            objs.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(content) + content + b"\nendstream")
        for style in ("R", "B", "I", "BI"):
            objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % _FONTS[style].encode())
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for i, body in enumerate(objs, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
        return bytes(out)


def _wrap(runs: list[tuple[str, str]], size: float, max_w: float) -> list[list[tuple[str, str]]]:
    words: list[tuple[str, str]] = []
    for text, st in runs:
        for part in re.findall(r"\S+\s*", text):
            words.append((part, st))
    lines: list[list[tuple[str, str]]] = [[]]
    used = 0.0
    for word, st in words:
        w = _width(word.rstrip(), st, size)
        if lines[-1] and used + w > max_w:
            lines.append([])
            used = 0.0
        lines[-1].append((word, st))
        used += _width(word, st, size)
    return [ln for ln in lines if ln]


def _runs_width(runs: list[tuple[str, str]], size: float) -> float:
    return sum(_width(t, st, size) for t, st in runs)


def _caps(text: str, size: float) -> list[tuple[str, str, float]]:
    """Simulated small caps: capitals full size, lowercase set as reduced capitals."""
    out: list[tuple[str, str, float]] = []
    for ch in text:
        big = ch.isupper() or not ch.isalpha()
        seg = (ch if big else ch.upper(), "B" if size > 20 else "R", size if big else size * 0.8)
        if out and out[-1][2] == seg[2]:
            out[-1] = (out[-1][0] + seg[0], seg[1], seg[2])
        else:
            out.append(seg)
    return out


def _draw_caps(cv: _Canvas, text: str, size: float, x: float | None = None, center: bool = False) -> None:
    segs = _caps(text, size)
    total = sum(_width(t, st, sz) for t, st, sz in segs)
    x0 = (cv.left + cv.right - total) / 2 if center else (cv.left if x is None else x)
    parts = [b"BT %.2f %.2f Td" % (x0, cv.y)]
    for t, st, sz in segs:
        parts.append(b"/%s %.2f Tf %s Tj" % (_FONT_KEY[st].encode(), sz, _pdf_str(t)))
    parts.append(b"ET")
    cv.ops.append(b" ".join(parts))


def _heading(cv: _Canvas, left: list[tuple[str, str]], right: list[tuple[str, str]], lsize: float, rsize: float, lead: float) -> None:
    cv.need(lead)
    cv.y -= lead
    cv.text(cv.left + 8, cv.y, left, lsize)
    if right:
        cv.text(cv.right - _runs_width(right, rsize), cv.y, right, rsize)


def render_resume_pdf(latex: str) -> bytes | None:
    """PDF bytes for a Jake-style resume, or None when the source isn't in that style."""
    if not is_jake_style(latex):
        return None
    doc = _parse(latex)
    cv = _Canvas(doc["page"])
    body_w = cv.right - cv.left

    # header
    lines = doc["header"]
    if lines:
        cv.y -= 26
        name = _plain(lines[0])
        if doc["small_caps"]:
            _draw_caps(cv, name, 24.0, center=True)
        else:
            cv.text(cv.left + (body_w - _runs_width([(name, "B")], 24)) / 2, cv.y, [(name, "B")], 24)
        for ln in lines[1:]:
            runs = _runs(ln)
            cv.y -= 13
            cv.text(cv.left + (body_w - _runs_width(runs, 10)) / 2, cv.y, runs, 10)

    for kind, *data in doc["blocks"]:
        if kind == "section":
            cv.need(44)
            cv.y -= 20
            _draw_caps(cv, data[0], 12.0)
            cv.y -= 3
            cv.rule(cv.y)
            cv.y -= 1
        elif kind == "sub":
            a, b, c, d = data[0]
            cv.need(30)
            cv.y -= 2
            _heading(cv, [(t, "B") for t, _ in a] or a, b, 11, 11, 13)
            _heading(cv, [(t, "I") for t, _ in c], [(t, "I") for t, _ in d], 10, 10, 12)
        elif kind == "subsub":
            _heading(cv, [(t, "I") for t, _ in data[0][0]], [(t, "I") for t, _ in data[0][1]], 10, 10, 12)
        elif kind == "project":
            cv.need(28)
            cv.y -= 3
            _heading(cv, data[0][0], data[0][1], 10, 11, 13)
        elif kind == "item":
            wrapped = _wrap(data[0], 10, body_w - 34)
            cv.need(12 * len(wrapped[:2]))
            for k, ln in enumerate(wrapped):
                cv.need(12)
                cv.y -= 12
                if k == 0:
                    cv.text(cv.left + 16, cv.y, [("\u2022", "R")], 10)
                cv.text(cv.left + 28, cv.y, ln, 10)
            cv.y -= 1
        else:  # free line: skills rows, summaries
            for ln in _wrap(data[0], 10, body_w - 10):
                cv.need(13)
                cv.y -= 12.5
                cv.text(cv.left + 8, cv.y, ln, 10)
    return cv.finish()
