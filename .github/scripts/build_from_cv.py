#!/usr/bin/env python3
"""Rebuild the CV-driven parts of index.html from the newest CV PDF in the repo.

What it does
  1. Finds the newest CV (CV*.pdf in the repo root, newest by the date printed
     in the page footer, for example "Curriculum Vitae (October 2026)").
  2. Reads it with pdftotext (including where each line sits on the page, so
     wrapped lines and right-aligned years are read correctly).
  3. Rewrites every block of index.html that sits between a pair of markers
        <!--cv:begin NAME--> ... <!--cv:end NAME-->
     Everything outside the markers is left exactly as you wrote it.
  4. Points the "Download CV" links at the newest CV and updates its date.
  5. Writes data/cv.json, a plain record of what was read.

If the CV cannot be read properly (a section vanished, or far fewer entries than
last time) it stops with an error and changes nothing, so a bad read never
reaches the site.

Run by hand:  python3 .github/scripts/build_from_cv.py [--dry-run] [--dump]
Needs: python3 and pdftotext (poppler-utils). No other packages.
"""
import html
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "index.html"
DATA_FILE = ROOT / "data" / "cv.json"

# =============================================================================
# SETTINGS: the things you might want to change
# =============================================================================

# Link shown after the publication summary.
SCHOLAR_URL = "https://scholar.google.ca/citations?user=2YE-Y4cAAAAJ&hl=en"

# How your name is written in author lists (it is shown in bold).
MY_NAME = r"Phillips, J\.(?:D\.)?"

# Funding groups whose heading matches this are not shown on the site
# (for example "Submitted" and "To be Submitted"). Everything else is shown.
HIDDEN_FUNDING = r"submit|review|pending|prepar|plan"

# How many items appear under "Latest publications" on the About tab.
LATEST_COUNT = 3

# Plain-text corrections applied to the CV text before anything else.
TEXT_FIXES = [
    ("Optimzation", "Optimization"),
    ("Belem, Brazil", "Belém, Brazil"),
    ("ON., Canada", "ON, Canada"),
]

# Wording tweaks applied to the finished HTML: (regular expression, replacement).
# They keep the wording that was on the site before it was generated from the CV.
# Delete a line to show the CV's exact wording instead.
REWRITES = [
    (r"Co-Advisors:", "Co-advisors:"),
    (r"Advisory Committee Members:", "Advisory committee:"),
    (r"Major Paper:", "Major paper:"),
    (r"Contributed guest post to the", "Guest post on the"),
    (r"Contributed (CEPS Research Highlights article)", r"\1"),
    (r"Contributed newsletter article to the Barcode Bulletin, 7\(1\)",
     "Newsletter article, <i>Barcode Bulletin</i>, 7(1)"),
    (r"Mentored/co-supervised", "I have mentored or co-supervised"),
    (r"reviewer for Long and Short Papers Track", "reviewer for the Long and Short Papers Track"),
    (r"Member of hiring panel for Associate Professor", "Member of the hiring panel for an Associate Professor"),
    (r"Member of hiring panel for 2-year", "Member of the hiring panel for a 2-year"),
    (r"Wireframing session", "wireframing session"),
    (r"most viewed article in category", "most viewed article in the category"),
    (r"Macrogenetics of North American butterflies &ndash; The", "Macrogenetics of North American butterflies: The"),
    (r"Macrogenetics of North American butterflies – The", "Macrogenetics of North American butterflies: The"),
]

# DOIs that should link somewhere other than https://doi.org/<doi>.
# (The link text still reads "DOI: ...". Use a file in the top folder of the repo or a permanent web address,
# not a temporary signed link, which stops working after a few hours.)
DOI_LINKS = {
    "10.64898/2026.09.16.752056": "https://www.biorxiv.org/content/10.64898/2026.09.16.752056v1",
    "10.1515/dna-2015-0008": "Phillips_et_al_2015.pdf",   # the DOI no longer resolves to the article
}

# Link text for a web address (first match wins; the last rule is the fallback).
LINK_LABELS = [
    (r"youtube\.com|youtu\.be", "YouTube"),
    (r"link\.springer\.com", "Springer"),
    (r"atrium\.lib\.uoguelph\.ca", "Atrium"),
    (r"journal\.lib\.uoguelph\.ca", "Issue"),
    (r"uoguelph\.ca/ceps", "Article"),
    (r"wordpress\.com|blogspot\.com", "Post"),
    (r"", "Link"),
]

# =============================================================================
# 1. Read the PDF: one "row" per printed line, with its position on the page
# =============================================================================
LINE_RE = re.compile(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>', re.S)
WORD_RE = re.compile(r'<word xMin="([\d.]+)" yMin="[\d.]+" xMax="([\d.]+)" yMax="[\d.]+">(.*?)</word>', re.S)
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]


def fail(msg):
    print(f"::error::{msg}")
    sys.exit(f"ERROR: {msg}")


def warn(msg):
    print(f"::warning::{msg}")


def pdf_rows(pdf):
    xml = subprocess.run(["pdftotext", "-bbox-layout", str(pdf), "-"], check=True,
                         capture_output=True, text=True).stdout
    rows = []
    for pno, chunk in enumerate(xml.split("<page ")[1:], 1):
        pw = float(re.match(r'width="([\d.]+)"', chunk).group(1))
        lines = []
        for m in LINE_RE.finditer(chunk):
            words = [(float(a), float(b), html.unescape(t)) for a, b, t in WORD_RE.findall(m.group(5))]
            if words:
                text = words[0][2]
                for a, b in zip(words, words[1:]):
                    text += ("" if b[0] - a[1] < 1.2 else " ") + b[2]
                lines.append(dict(x0=float(m.group(1)), x1=float(m.group(3)),
                                  y=(float(m.group(2)) + float(m.group(4))) / 2,
                                  text=unicodedata.normalize("NFC", text), fw=words[0][1] - words[0][0]))
        lines.sort(key=lambda l: (l["y"], l["x0"]))
        groups = []
        for l in lines:
            if groups and abs(l["y"] - groups[-1][0]["y"]) < 3:
                groups[-1].append(l)
            else:
                groups.append([l])
        for g in groups:
            g.sort(key=lambda l: l["x0"])
            right = [l for l in g[1:] if l["x0"] >= 280 and l["x1"] >= pw - 76]   # right-aligned years, amounts
            left = [l for l in g if l not in right]
            text = left[0]["text"]
            for a, b in zip(left, left[1:]):
                text += ("" if b["x0"] - a["x1"] < 1.5 else " ") + b["text"]     # a superscript touches its word
            numbered = bool(re.match(r"\d{1,3}\.$", left[0]["text"]))
            rows.append(dict(page=pno, pw=pw, y=left[0]["y"], x0=left[0]["x0"],
                             x1=max(l["x1"] for l in left), fw=0.0 if numbered else left[0]["fw"],
                             text=text,
                             right=" ".join(l["text"] for l in right)))
    return rows


def cv_footer_date(pdf):
    """('October', 2026) from the page footer, or None."""
    try:
        txt = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"], check=True,
                             capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
        return None
    m = re.search(r"Curriculum Vitae\s*\(\s*([A-Za-z]+)\s+(\d{4})\s*\)", txt)
    return (m.group(1), int(m.group(2))) if m else None


def pick_cv():
    cands = [p for p in ROOT.glob("*.pdf") if re.search(r"CV|curriculum|vitae", p.name, re.I)]
    if not cands:
        fail("No CV found: put the PDF in the top folder of the repo with CV at the start of its name.")

    def key(p):
        d = cv_footer_date(p)
        if d and d[0].lower() in MONTHS:
            return (d[1], MONTHS.index(d[0].lower()) + 1, p.name)
        return (0, 0, p.name)
    return max(cands, key=key)


def load(pdf):
    rows = pdf_rows(pdf)
    footer = [r for r in rows if re.search(r"Curriculum Vitae", r["text"]) and re.match(r"Page \d+ of \d+", r["right"])]
    body = [r for r in rows if r not in footer]
    date = None
    for r in footer:
        m = re.search(r"Curriculum Vitae\s*\(\s*([A-Za-z]+\s+\d{4})\s*\)", r["text"])
        if m:
            date = m.group(1)
            break
    if not date:
        fail("Could not find the date in the CV footer, for example: Curriculum Vitae (October 2026).")
    left = min(r["x0"] for r in body)
    for i, r in enumerate(body):
        nxt = body[i + 1] if i + 1 < len(body) else None
        # A line "wraps" when the next word would not have fitted on it.
        r["wraps"] = bool(nxt) and not r["right"] and r["x1"] + 3.0 + nxt["fw"] > r["pw"] - left + 1.0
    return body, date, left


# ---- turning rows into paragraphs -------------------------------------------
def last_token_is_link(text):
    t = text.split(" ")[-1]
    return t.startswith("http") or "://" in t or bool(re.match(r"10\.\d{4,9}/", t))


def paragraphs(rows):
    """Join lines that wrapped into paragraphs (web addresses and DOIs are re-joined without a space)."""
    out, cur = [], None
    for r in rows:
        if cur is not None and cur["open"]:
            first = r["text"].split(" ")[0]
            glue = cur["inlink"] and not re.fullmatch(r"[A-Z][a-z]+[.,;:]?", first) and not first.endswith(":")
            hyphen = bool(re.search(r"[A-Za-z0-9]-$", cur["text"])) and first[:1].islower()
            cur["text"] += ("" if (glue or hyphen) else " ") + r["text"]
            cur["right"] = cur["right"] or r["right"]
            cur["inlink"] = r["wraps"] and (last_token_is_link(r["text"]) or (glue and " " not in r["text"]))
            cur["open"] = r["wraps"]
        else:
            cur = dict(text=r["text"], right=r["right"], x0=r["x0"], open=r["wraps"],
                       inlink=r["wraps"] and last_token_is_link(r["text"]))
            out.append(cur)
    return [dict(text=c["text"], right=c["right"], x0=c["x0"]) for c in out]


SECTION_KEYS = [  # (key, pattern on the heading); first match wins
    ("peer_review", r"PEER REVIEW"),
    ("nonref", r"NON.?REFEREED"),
    ("refereed", r"REFEREED|PUBLICATIONS"),
    ("research_areas", r"RESEARCH AREAS|RESEARCH INTERESTS"),
    ("appointments", r"APPOINTMENT"),
    ("education", r"EDUCATION"),
    ("experience", r"RESEARCH EXPERIENCE|POSTDOC"),
    ("funding", r"FUNDING|GRANTS"),
    ("software", r"SOFTWARE"),
    ("supervision", r"SUPERVISION|MENTOR"),
    ("teaching", r"TEACHING"),
    ("talks", r"PRESENTATION|CONFERENCE"),
    ("service", r"ACADEMIC SERVICE|^SERVICE"),
    ("volunteer", r"VOLUNTEER"),
]


def split_sections(rows, left):
    secs, cur, unknown = {}, None, []
    for r in rows:
        if not r["right"] and abs(r["x0"] - left) < 3 and re.fullmatch(r"[A-Z][A-Z &/,\-–]{3,}", r["text"]):
            key = next((k for k, pat in SECTION_KEYS if re.search(pat, r["text"])), None)
            if key is None:
                unknown.append(r["text"])
            cur = key
            if key:
                secs.setdefault(key, [])
            continue
        if cur:
            secs[cur].append(r)
    return secs, unknown


# =============================================================================
# 2. Understand each kind of section
# =============================================================================
DATE_RE = re.compile(r"(?:\d{4}\s*[–—-]\s*(?:\d{4}|[Pp]resent)|\d{4}|[Pp]resent)")
COURSE_RE = re.compile(r"[A-Z]{2,5}\*\d{3,4}\b")
NUM_RE = re.compile(r"(\d{1,3})\.\s+(\S.*)$")


def is_dated(r):
    return bool(r["right"]) and bool(DATE_RE.fullmatch(r["right"].strip()))


def dated_blocks(rows, is_head=is_dated, labels=False):
    """Entries that start with a line carrying a date on the right."""
    pre, blocks, label, cur, prev_wraps = [], [], None, None, False
    for i, r in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if is_head(r):
            cur = dict(label=label, head=r["text"], date=r["right"].strip(), rows=[])
            blocks.append(cur)
        elif (labels and not prev_wraps and not r["right"] and len(r["text"]) <= 25 and nxt is not None
              and is_head(nxt) and not re.search(r"[·•*\d]", r["text"])):
            label, cur = r["text"], None
        elif cur is None:
            pre.append(r)
        else:
            cur["rows"].append(r)
        prev_wraps = r["wraps"]
    for b in blocks:
        b["paras"] = [dict(text=p["text"], right=p["right"]) for p in paragraphs(b.pop("rows"))]
    return pre, blocks


def numbered(rows, left):
    """Numbered lists with optional group headings. Returns (flush paragraphs, entries)
    where each entry has the group labels above it and its lines as paragraphs."""
    items, cur = [], None
    for r in rows:
        m = NUM_RE.match(r["text"])
        if m and r["x0"] < left + 4:
            cur = dict(num=int(m.group(1)), rows=[dict(r, text=m.group(2))])
            items.append(("entry", cur))
        elif r["x0"] < left + 4:
            cur = None
            items.append(("flush", r))
        elif cur is not None:
            cur["rows"].append(r)
    # merge consecutive flush lines into paragraphs, drop the "* Indicates ..." key lines
    seq, buf = [], []
    for kind, obj in items:
        if kind == "flush":
            buf.append(obj)
            continue
        if buf:
            seq.append(("flush", paragraphs(buf)))
            buf = []
        seq.append(("entry", obj))
    if buf:
        seq.append(("flush", paragraphs(buf)))
    flat = []
    for kind, obj in seq:
        if kind == "flush":
            for p in obj:
                if re.match(r"\*+\s+Indicates", p["text"]):
                    continue
                flat.append(("label" if len(p["text"]) <= 45 and not p["text"].startswith(("Publication", "URL")) else "text", p["text"]))
        else:
            flat.append(("entry", obj))
    # level one = a heading directly followed by another heading
    entries, parent, sub, texts = [], None, None, []
    for i, (kind, obj) in enumerate(flat):
        if kind == "label":
            nxt = flat[i + 1][0] if i + 1 < len(flat) else None
            if nxt == "label":
                parent, sub = obj, None
            else:
                sub = obj
        elif kind == "text":
            texts.append(obj)
        else:
            e = dict(num=obj["num"], parent=parent, group=sub,
                     paras=[dict(text=p["text"], right=p["right"]) for p in paragraphs(obj["rows"])])
            entries.append(e)
    return texts, entries


def one_line(entry):
    return " ".join(p["text"] for p in entry["paras"])


# ---- sections that are lists of dated blocks -------------------------------
def parse_appointments(rows):
    _, blocks = dated_blocks(rows)
    return [dict(title=b["head"], date=b["date"], lines=[p["text"] for p in b["paras"]]) for b in blocks]


def parse_education(rows):
    _, blocks = dated_blocks(rows)
    return [dict(degree=b["head"], date=b["date"], lines=[p["text"] for p in b["paras"]]) for b in blocks]


def parse_teaching(rows):
    _, blocks = dated_blocks(rows, is_head=lambda r: is_dated(r) and not COURSE_RE.match(r["text"]))
    out = []
    for b in blocks:
        inst = [p["text"] for p in b["paras"] if not p["right"] and not COURSE_RE.match(p["text"])]
        courses = [dict(text=p["text"], date=p["right"].strip()) for p in b["paras"] if COURSE_RE.match(p["text"])]
        out.append(dict(title=b["head"], date=b["date"], institution=inst[0] if inst else "", courses=courses))
    return out


def parse_volunteer(rows):
    _, blocks = dated_blocks(rows)
    out = []
    for b in blocks:
        inst = [p["text"] for p in b["paras"] if not p["text"].startswith("•")]
        bullets = [p["text"].lstrip("• ").strip() for p in b["paras"] if p["text"].startswith("•")]
        out.append(dict(name=b["head"], date=b["date"], institution=inst[0] if inst else "", bullets=bullets))
    return out


def parse_supervision(rows):
    pre, blocks = dated_blocks(rows, labels=True)
    intro = ""
    for p in paragraphs(pre):
        if re.match(r"\*+\s+Indicates", p["text"]):
            continue
        intro = intro or p["text"]
    students = []
    for b in blocks:
        detail = b["paras"][0]["text"] if b["paras"] else ""
        students.append(dict(group=b["label"] or "", name=b["head"], date=b["date"], detail=detail))
    return dict(intro=intro, students=students)


# ---- numbered sections --------------------------------------------------------
def parse_service(rows, left):
    _, entries = numbered(rows, left)
    out = []
    for e in entries:
        p = e["paras"]
        bullets = [x["text"].lstrip("• ").strip() for x in p[1:] if x["text"].startswith("•")]
        inst = [x["text"] for x in p[1:] if not x["text"].startswith("•")]
        out.append(dict(name=p[0]["text"], date=p[0]["right"].strip(), institution=inst[0] if inst else "", bullets=bullets))
    return out


def parse_funding(rows, left):
    _, entries = numbered(rows, left)
    out = []
    for e in entries:
        p = e["paras"]
        inst = p[1]["text"] if len(p) > 1 else ""
        amount = p[1]["right"] if len(p) > 1 else ""
        role = next((x["text"][5:].strip() for x in p[2:] if x["text"].startswith("Role:")), "")
        title = " ".join(x["text"] for x in p[2:] if not x["text"].startswith("Role:"))
        out.append(dict(group=e["group"] or "", name=p[0]["text"], date=p[0]["right"].strip(),
                        institution=inst, amount=amount, title=title, role=role))
    return out


def parse_talks(rows, left):
    _, entries = numbered(rows, left)
    out = []
    for e in entries:
        p = e["paras"]
        head, date = p[0]["text"], p[0]["right"].strip()
        rest = [x["text"] for x in p[1:]]
        dot = next((i for i, t in enumerate(rest) if " · " in t), None)
        if dot is not None:
            who, _, title = rest[dot].partition(" · ")
            loc = rest[dot - 1] if dot >= 1 else ""
            event = " ".join([head] + rest[:max(dot - 1, 0)])
        else:
            who, title = "", rest[0] if rest else ""
            loc = rest[-1] if len(rest) > 1 else ""
            event = head
        out.append(dict(event=event, date=date, location=loc, authors=who, title=title))
    return out


def parse_software(rows, left):
    texts, entries = numbered(rows, left)
    lines = [p["text"] for p in paragraphs([r for r in rows if r["x0"] < left + 4 and not NUM_RE.match(r["text"])])]
    total = next((t for t in lines + texts if re.search(r"software downloads", t)), "")
    return dict(total=total, tools=[one_line(e) for e in entries])


def parse_refereed(rows, left):
    texts, entries = numbered(rows, left)
    record = next((t for t in texts if t.startswith("Publication record")), "")
    # the parent label is the list ("Journal Articles"), the group is the status ("Published or Accepted")
    return dict(record=record, entries=[dict(parent=e["parent"] or "", group=e["group"] or "", text=one_line(e))
                                        for e in entries])


def parse_nonref(rows, left):
    texts, entries = numbered(rows, left)
    thesis = ""
    flush = [r for r in rows if r["x0"] < left + 4 and not NUM_RE.match(r["text"])]
    paras = [p["text"] for p in paragraphs(flush) if not re.match(r"\*+\s+Indicates", p["text"])]
    for i, t in enumerate(paras):
        if re.match(r"Ph\.?D\.? Thesis", t, re.I):
            thesis = " ".join(paras[i + 1:])
            break
    return dict(thesis=thesis, entries=[one_line(e) for e in entries])


def parse_lines(rows):
    return " ".join(p["text"] for p in paragraphs(rows))


# =============================================================================
# 3. Words, names and links
# =============================================================================
def clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=\w)\s+([.,;])(?=\s|$)", r"\1", s)
    s = re.sub(r"“([^”\"]*)\"", r"“\1”", s)
    for a, b in TEXT_FIXES:
        s = s.replace(a, b)
    return s


def esc(s):
    return html.escape(s, quote=False)


def attr(s):
    return html.escape(s, quote=True)


def cap(s):
    return s[:1].upper() + s[1:]


def rewrite(h):
    for pat, rep in REWRITES:
        h = re.sub(pat, rep, h)
    return h


def when(d):
    d = re.sub(r"\s*[–—-]\s*", "–", d.strip())
    return d.replace("Present", "present")


def start_year(d):
    m = re.match(r"\d{4}", d.strip())
    return int(m.group(0)) if m else 0


def plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def label_for(url, text=""):
    for pat, label in LINK_LABELS:
        if re.search(pat, url):
            if not pat and re.search(r"\bvideo\b", text, re.I):
                return "Video"
            return label
    return "Link"


def link(url, label):
    return f'<a href="{attr(url)}">{esc(label)}</a>'


ABBREV = {"al.", "ed.", "eds.", "vs.", "St.", "Dr.", "Jr.", "Sr.", "No.", "Fig.", "cf.", "vol.", "pp.", "Prof.", "Ph.D.", "e.g.", "i.e."}


def split_first(text):
    """Split at the first sentence end: 'Title. Rest' -> ('Title', 'Rest')."""
    for m in re.finditer(r"(?<=[.?!])\s+(?=[A-Z0-9“\"‘'(]|[a-z]+[A-Z])", text):
        before = re.sub(r"^[(\[“\"‘']+", "", text[:m.start()].split(" ")[-1])
        if before in ABBREV or re.fullmatch(r"(?:[A-Z]\.)+", before):
            continue
        return text[:m.start()].rstrip(), text[m.end():].strip()
    return text.strip(), ""


def end_punct(s):
    s = s.strip()
    return s if s and s[-1] in ".?!" else s + "."


# ---- authors -------------------------------------------------------------------
SURN = r"[A-Za-zÀ-ɏ’'\-]+(?:\s[A-Za-zÀ-ɏ’'\-]+)*?"
AUTH = rf"\*{{0,2}}{SURN},?\s(?:[A-Z]\.){{1,4}}"
SEP = r"(?:,\s+and\s+|,\s+|\s+and\s+)"
AUTH_RE = re.compile(AUTH)
SEP_RE = re.compile(SEP)
ONE_AUTH = re.compile(rf"(\*{{0,2}})({SURN}),?\s((?:[A-Z]\.){{1,4}})$")


def split_authors(text):
    """(['Surname, I.I.', ...], rest). Every name is written Surname, I.I."""
    text = text.strip()
    names, pos = [], 0
    while True:
        m = AUTH_RE.match(text, pos)
        if not m:
            break
        mm = ONE_AUTH.match(m.group(0))
        names.append(f"{mm.group(1)}{mm.group(2)}, {mm.group(3)}" if mm else m.group(0))
        pos = m.end()
        s = SEP_RE.match(text, pos)
        if not s:
            break
        nxt = AUTH_RE.match(text, s.end())
        if not nxt:
            break
        pos = s.end()
    return names, text[pos:].strip()


def authors_html(names):
    items = []
    for n in names:
        bare = n.lstrip("*")
        items.append(f"<b>{esc(n)}</b>" if re.fullmatch(MY_NAME, bare) else esc(n))
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]


def plain_authors(text):
    """Authors written in free text (talks: 'A, B and C'); bold your own name."""
    names, rest = split_authors(text)
    if names and not rest:
        return authors_html(names)
    return re.sub(MY_NAME, lambda m: f"<b>{esc(m.group(0))}</b>", esc(text))


# =============================================================================
# 4. Publications
# =============================================================================
VOL_TAIL = re.compile(r"^(?P<pre>(?:.*,\s)?)(?P<j>[^,]+?)(?P<tail>,\s*(?:\d+(?:\(\d+\))?:\s*\S+|e?\d+))$")


def parse_pub(text, cv_year, kind):
    text = clean(text)
    names, rest = split_authors(text)
    year = ""
    m = re.match(r"\((\d{4})\)\.?\s*", rest)
    if m:
        year, rest = m.group(1), rest[m.end():]
    doi = url = ""
    m = re.search(r"\bDOI:\s*(10\.\d{4,9}/\S+)", rest)
    after = ""
    if m:
        doi = m.group(1).rstrip(".,;")
        after = rest[m.end():].lstrip(". ").strip()
        rest = rest[:m.start()].strip()
    m = re.search(r"\bURL:\s*(https?://\S+)", rest)
    if m:
        url = m.group(1).rstrip(".,;")
        rest = (rest[:m.start()] + " " + rest[m.end():]).strip()
    title, venue = split_first(rest)
    return dict(kind=kind, names=names, year=year, title=title, venue=venue.rstrip("."),
                doi=doi, url=url, note=after, raw=text, cv_year=cv_year)


def doi_year(doi):
    m = re.search(r"/(\d{4})\.\d{2}\.\d{2}\.\d+", doi or "")
    return m.group(1) if m else ""


def pub_year(p):
    return p["year"] or doi_year(p["doi"]) or str(p["cv_year"])


def venue_html(v):
    """Italicise the journal / book / conference name inside a venue string."""
    if not v:
        return ""
    main, note = split_first(v + ".") if ". " in v else (v, "")
    main = main.rstrip(".")
    m = VOL_TAIL.match(main)
    if m:
        out = f"{esc(m.group('pre'))}<i>{esc(m.group('j'))}</i>{esc(m.group('tail'))}."
    else:
        out = f"<i>{esc(main)}</i>."
    if note:
        out += " " + esc(end_punct(note))
    return out


def chapter_venue_html(v):
    m = re.match(r"In:\s*(?P<ed>.+?)\s*\((?P<eds>eds?\.?)\)\s*(?P<book>.+?),\s*(?P<vol>vol\.?\s*\d+\..*)$", v)
    if not m:
        return esc(end_punct(v))
    many = bool(re.search(r"\band\b|;", m.group("ed")))
    return (f"In: {esc(m.group('ed'))} ({'eds' if many else 'ed.'}) "
            f"<i>{esc(m.group('book'))}</i>, {esc(end_punct(m.group('vol')))}")


def doi_href(doi):
    return DOI_LINKS.get(doi, f"https://doi.org/{doi}")


def pub_html(p, tag=""):
    """The HTML inside <p> for one publication."""
    a = authors_html(p["names"]) if p["names"] else esc(p["raw"])
    parts = []
    if p["names"]:
        parts.append(f"{a} ({p['year']})." if p["year"] else a)
    else:
        return rewrite(esc(p["raw"]))
    parts.append(esc(end_punct(p["title"])))
    kind, v = p["kind"], p["venue"]
    if kind == "chapter" and v:
        parts.append(chapter_venue_html(v))
    elif kind in ("article", "preprint", "proceedings") and v:
        parts.append(venue_html(v))
    elif kind == "chapter_submitted" and v:
        name, _, rest = v.partition(", ")
        parts.append(f"<i>{esc(name)}</i>" + (f", {esc(end_punct(rest))}" if rest else "."))
    elif v and not tag:
        m = re.match(r"(Submitted|Targeted) to (.+)$", v)
        if m:
            tag = f"{m.group(1)} to <i>{esc(m.group(2))}</i>."
        else:
            parts.append(esc(end_punct(v)))
    if p["doi"]:
        parts.append(link(doi_href(p["doi"]), f"DOI: {p['doi']}") + ("." if (p["note"] or tag) else ""))
    if p["url"] and kind == "chapter":
        parts.append(link(p["url"], label_for(p["url"], p["raw"])))
    if p["note"]:
        parts.append(esc(end_punct(p["note"])))
    if tag:
        parts.append(f'<span class="tag">{tag}</span>')
    return rewrite(" ".join(parts))


def li(when_text, inner, extra=""):
    return f'<li><span class="when">{esc(when_text)}</span>{inner}{extra}</li>'


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def build_publications(cv, cv_year):
    ref = cv["refereed"]
    groups = {"articles": [], "manuscripts": [], "chapters": [], "proceedings": []}
    unparsed = 0
    preprints, submitted, rest = [], [], []
    for e in ref["entries"]:
        parent, group, text = e["parent"].lower(), e["group"].lower(), e["text"]
        if "journal" in parent:
            kind_parent = "articles"
        elif "chapter" in parent:
            kind_parent = "chapters"
        elif "proceeding" in parent or "conference" in parent:
            kind_parent = "proceedings"
        else:
            kind_parent = "articles"
        if re.search(r"published|accepted", group) or not group:
            status = "published"
        elif "preprint" in group:
            status = "preprint"
        elif re.search(r"submitted or|under (revision|review)", group):
            status = "submitted"
        elif re.search(r"to be submitted|to submit", group):
            status = "tobesubmitted"
        elif "prepar" in group:
            status = "inprep"
        else:
            status = "other:" + e["group"]
        kind = {"articles": "article", "chapters": "chapter", "proceedings": "proceedings"}[kind_parent]
        if status == "preprint":
            kind = "preprint"
        elif status == "submitted" and kind_parent == "chapters":
            kind = "chapter_submitted"
        elif status not in ("published",):
            kind = "manuscript"
        p = parse_pub(text, cv_year, kind)
        if not p["names"]:
            unparsed += 1
        rest.append((kind_parent, status, p))

    # a "Submitted" entry that is also listed as a preprint becomes a tag on the preprint
    sub_titles = {norm_title(p["title"]): p for kp, st, p in rest if st == "submitted" and kp == "articles"}
    used = set()
    for kp, st, p in rest:
        if kp == "articles":
            if st == "published":
                groups["articles"].append(li(pub_year(p), f"<p>{pub_html(p)}</p>"))
            elif st == "preprint":
                tag = ""
                s = sub_titles.get(norm_title(p["title"]))
                if s:
                    used.add(id(s))
                    m = re.match(r"(Submitted|Targeted) to (.+)$", s["venue"])
                    tag = f"{m.group(1)} to <i>{esc(m.group(2))}</i>." if m else ""
                preprints.append((pub_year(p), p, tag))
        elif kp == "chapters" and st == "published":
            groups["chapters"].append(li(pub_year(p), f"<p>{pub_html(p)}</p>"))
        elif kp == "proceedings" and st == "published":
            groups["proceedings"].append(li(pub_year(p), f"<p>{pub_html(p)}</p>"))
    man = [li(y, f"<p>{pub_html(p, tag)}</p>") for y, p, tag in preprints]
    for kp, st, p in rest:
        label = {"submitted": "Submitted", "tobesubmitted": "To submit", "inprep": "In prep."}.get(st)
        if st.startswith("other:"):
            label = st[6:]
        if not label or id(p) in used:
            continue
        if kp == "chapters" and st == "submitted":
            groups["chapters"].append(li(label, f"<p>{pub_html(p)}</p>"))
        elif kp == "articles":
            man.append(li(label, f"<p>{pub_html(p)}</p>"))
    groups["manuscripts"] = man

    # outreach and other writing
    nr = cv["nonref"]
    out = []
    for text in nr["entries"]:
        out.append(outreach(text, cv_year, False))
    if nr["thesis"]:
        out.append(outreach(nr["thesis"], cv_year, True))
    out.sort(key=lambda t: -int(t[0]) if t[0].isdigit() else 0)
    groups["outreach"] = [li(y, f"<p>{h}</p>") for y, h in out]

    # latest publications on the About tab: newest year first, journal articles before preprints
    latest = []
    for kp, st, p in rest:
        if kp == "articles" and st == "published":
            latest.append((int(pub_year(p)), 0, len(latest), p, ""))
    for y, p, tag in preprints:
        latest.append((int(y), 1, len(latest), p, tag))
    latest.sort(key=lambda t: (-t[0], t[1], t[2]))
    latest_html = [li(str(y), f"<p>{pub_html(p, tag)}</p>") for y, _, _, p, tag in latest[:LATEST_COUNT]]
    return groups, latest_html, unparsed


def outreach(text, cv_year, thesis):
    text = clean(text)
    names, rest = split_authors(text)
    year = ""
    m = re.match(r"\((\d{4})\)\.?\s*", rest)
    if m:
        year, rest = m.group(1), rest[m.end():]
    url = ""
    m = re.search(r"\bURL:\s*(https?://\S+)", rest)
    if m:
        url = m.group(1).rstrip(".,;")
        rest = (rest[:m.start()] + rest[m.end():]).strip()
    title, desc = split_first(rest)
    if thesis:
        inst = re.sub(r"\s*Atrium\.?$", "", desc).strip(" .")
        desc = f"Ph.D. thesis, {inst}."
    parts = [f"{authors_html(names)} ({year})." if year else authors_html(names), esc(end_punct(title))]
    if desc:
        parts.append(esc(end_punct(desc)))
    if url:
        parts.append(link(url, label_for(url, rest)))
    return (year or str(cv_year), rewrite(" ".join(parts)))


def thesis_info(text):
    """(title, url) of the thesis entry."""
    text = clean(text)
    names, rest = split_authors(text)
    rest = re.sub(r"^\(\d{4}\)\.?\s*", "", rest)
    m = re.search(r"\bURL:\s*(https?://\S+)", rest)
    url = m.group(1).rstrip(".,;") if m else ""
    if m:
        rest = rest[:m.start()].strip()
    return split_first(rest)[0], url


def legend_text(cv):
    blob = " ".join([e["text"] for e in cv["refereed"]["entries"]] + [t["authors"] for t in cv["talks"]]
                    + cv["nonref"]["entries"])
    out = "* marks a student under my direct supervision."
    if re.search(r"(?<![\w*])\*\*[A-Z]", blob):
        out += " ** marks a student under my co-supervision."
    return out


def publication_summary(cv):
    rec = clean(cv["refereed"]["record"])
    rec = re.sub(r"^Publication record:\s*", "", rec)
    m = re.match(r"(\d+) peer-reviewed journal articles? \((\d+) first-author[^)]*\) and (\d+) book chapters? "
                 r"\([^)]*\), plus (\d+) first-author manuscripts? in preprint or to be submitted\.\s*"
                 r"Senior \(last\) author on (\d+) student-led manuscripts?", rec)
    if m:
        j, f, c, mn, s = (int(x) for x in m.groups())
        listed_j = sum(1 for e in cv["refereed"]["entries"]
                       if "journal" in e["parent"].lower() and re.search(r"published|accepted", e["group"], re.I))
        listed_c = sum(1 for e in cv["refereed"]["entries"]
                       if "chapter" in e["parent"].lower() and re.search(r"published|accepted", e["group"], re.I))
        if listed_j != j or listed_c != c:
            warn(f"The CV's 'Publication record' says {j} journal articles and {c} book chapters, but the lists "
                 f"show {listed_j} and {listed_c}. The page shows the CV's sentence; update it in the CV.")
        text = (f"{plural(j, 'peer-reviewed journal article')} ({f} as first author), "
                f"{plural(c, 'book chapter')}, and {plural(mn, 'first-author manuscript')} in preprint or to be submitted. "
                f"I am senior (last) author on {plural(s, 'student-led manuscript')}.")
    else:
        warn("Could not read the 'Publication record' sentence in the CV; showing it as written.")
        text = rec if rec.endswith(".") else rec + "."
    return esc(text) + f' Citation counts are on <a href="{attr(SCHOLAR_URL)}">Google Scholar</a>.'


# =============================================================================
# 5. Other sections
# =============================================================================
def split_inst(head):
    m = re.match(r"^(.*?),\s*((?:University|College|Universit|Institut|École).*)$", head)
    return (m.group(1), m.group(2)) if m else (head, "")


def build_appointments(cv):
    items = []
    for key in ("appointments", "experience"):
        for e in cv[key]:
            items.append(e)
    items.sort(key=lambda e: -start_year(e["date"]))       # stable: keeps CV order within a year
    out = []
    for e in items:
        lines = list(e["lines"])
        sup = [l for l in lines if re.match(r"Supervisors?:", l)]
        det = [l for l in lines if l not in sup]
        if det and "," not in det[0] and "University" in det[0]:
            det = det[1:] + det[:1]                            # put the institution last
        sub = ("; " if sum("," in d for d in det) > 1 else ", ").join(det)
        inner = f'<p><span class="role">{esc(e["title"])}</span>' + (f"<br>{esc(sub)}" if sub else "") + "</p>"
        inner += "".join(f'<p class="what">{esc(s)}</p>' for s in sup)
        out.append(li(when(e["date"]), rewrite(inner)))
    return out


def build_education(cv, thesis_urls):
    out = []
    for e in cv["education"]:
        role, inst = split_inst(e["degree"])
        inner = f'<p><span class="role">{esc(role)}</span>' + (f", {esc(inst)}" if inst else "") + "</p>"
        for l in e["lines"]:
            body = esc(l)
            m = re.match(r"Dissertation:\s*(.+)$", l)
            if m and norm_title(m.group(1)) in thesis_urls:
                body = f"Dissertation: {link(thesis_urls[norm_title(m.group(1))], m.group(1))}"
            inner += f'<p class="what">{body}</p>'
        out.append(li(when(e["date"]), rewrite(inner)))
    return out


def build_funding(cv):
    grants, awards = [], []
    for e in cv["funding"]:
        if re.search(HIDDEN_FUNDING, e["group"], re.I):
            continue
        tail = (f", {esc(e['institution'])}" if e["institution"] else "") + "."
        tail += f" {esc(e['amount'])}" if e["amount"] else ""
        inner = f'<p><span class="role">{esc(e["name"])}</span>{tail}</p>'
        if e["title"] or e["role"]:
            role = e["role"]
            role = role if role.isupper() else role[:1].lower() + role[1:]
            what = (end_punct(e["title"]) + " " if e["title"] else "") + (f"Role: {role}." if role else "")
            inner += f'<p class="what">{esc(what.strip())}</p>'
            grants.append(li(when(e["date"]), rewrite(inner)))
        else:
            awards.append(li(when(e["date"]), rewrite(inner)))
    return grants, awards


def build_teaching(cv):
    out = []
    for e in cv["teaching"]:
        inner = f'<p><span class="role">{esc(e["title"])}</span>' + (f", {esc(e['institution'])}" if e["institution"] else "") + "</p>"
        if e["courses"]:
            lines = []
            for c in e["courses"]:
                t = re.sub(r"\s+[–-]\s+", " ", c["text"], count=1)
                lines.append(esc(t) + (f" ({esc(when(c['date']))})" if c["date"] else ""))
            inner += '<p class="what">' + "<br>".join(lines) + "</p>"
        out.append(li(when(e["date"]), rewrite(inner)))
    return out


def build_supervision(cv):
    sup = cv["supervision"]
    groups = {}
    for s in sup["students"]:
        name = s["name"].lstrip("*").strip()
        note = ""
        m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", name)
        if m:
            name, note = m.group(1), m.group(2)
        role, _, desc = s["detail"].partition(" · ")
        if note:
            role = f"{role}, {note}"
        text = end_punct(role) + (" " + end_punct(desc) if desc else "")
        inner = f'<p><span class="role">{esc(name)}</span></p><p class="what">{esc(text)}</p>'
        groups.setdefault(s["group"], []).append(li(when(s["date"]), rewrite(inner)))
    intro = rewrite(esc(sup["intro"]))
    return intro, groups


def build_service(entries):
    out = []
    for e in entries:
        inner = f'<p><span class="role">{esc(e["name"])}</span>' + (f", {esc(e['institution'])}" if e["institution"] else "") + "</p>"
        for b in e["bullets"]:
            inner += f'<p class="what">{esc(end_punct(b))}</p>'
        out.append(li(when(e["date"]), rewrite(inner)))
    return out


def build_talks(cv):
    out, seen = [], set()
    for e in cv["talks"]:
        event = clean(e["event"])
        kind = ""
        m = re.search(r"\s*\(([^()]*)\)\s*$", event)
        if m and not re.search(r"^[A-Z]{2,}[A-Za-z&]*$", m.group(1)):
            kind, event = m.group(1), event[:m.start()].strip()
        title = clean(e["title"])
        note = ""
        m = re.search(r"\s*\(([^()]*(?:accepted|attended|not attend|withdrawn)[^()]*)\)\s*$", title, re.I)
        if m:
            note, title = m.group(1), title[:m.start()].strip()
        if not kind and note and re.fullmatch(r"attended", note, re.I):
            kind, note = note, ""
        shown = event
        am = re.match(r"^.*\((\w[\w&]*)\)\s+(.*)$", event)
        if am and event in seen:
            shown = f"{am.group(1)} {am.group(2)}"
        seen.add(event)
        where = shown + (f", {clean(e['location'])}" if e["location"] else "")
        where = end_punct(where)
        if kind:
            where += " " + end_punct(cap(kind) + (f" ({note})" if note else ""))
        if e["authors"]:
            head = f"<p>{plain_authors(clean(e['authors']))} {esc(title if title.endswith(")") else end_punct(title))}</p>"
        else:
            head = f"<p>{esc(title if title.endswith(')') else end_punct(title))}</p>"
        out.append(li(when(e["date"]), rewrite(head + f'<p class="where">{esc(where)}</p>')))
    return out


def build_peer_review(cv):
    names = [n.strip() for n in re.split(r",\s*", clean(cv["peer_review"])) if n.strip()]
    if not names:
        return ""
    it = [f"<i>{esc(n)}</i>" for n in names]
    body = it[0] if len(it) == 1 else (f"{it[0]} and {it[1]}" if len(it) == 2 else ", ".join(it[:-1]) + ", and " + it[-1])
    return f"I review manuscripts for {body}."


def build_research_areas(cv):
    items = [i.strip() for i in clean(cv["research_areas"]).split("·") if i.strip()]
    out = []
    for n, i in enumerate(items):
        first = i.split(" ")[0]
        if n and not (first[:1].islower() or first.isupper() or (len(first) > 1 and first[1:].lower() != first[1:])):
            i = i[:1].lower() + i[1:]
        out.append(i)
    if not out:
        return ""
    body = out[0] if len(out) == 1 else (f"{out[0]} and {out[1]}" if len(out) == 2 else ", ".join(out[:-1]) + ", and " + out[-1])
    return esc(body) + "."


def software_numbers(cv):
    sw = cv["software"]
    out = {}
    m = re.search(r"([\d,]+)\+?\s*software downloads", sw["total"])
    if m:
        out["software-total"] = f"{int(m.group(1).replace(',', '')):,}"
    for t in sw["tools"]:
        name = re.split(r"\s+[·(]", t)[0].strip()
        m = re.search(r">\s*([\d,]+)\s*downloads", t)
        if m:
            out[f"downloads-{re.sub(r'[^A-Za-z0-9]+', '', name)}"] = f"More than {int(m.group(1).replace(',', '')):,} downloads"
    return out


# =============================================================================
# 6. Read the whole CV, write the page
# =============================================================================
def read_cv(pdf):
    rows, date, left = load(pdf)
    secs, unknown = split_sections(rows, left)
    for u in unknown:
        warn(f'CV section "{u}" is not used on the site (add it to SECTION_KEYS if it should be).')
    need = ["refereed", "nonref"]
    for k in need:
        if k not in secs:
            fail(f"The CV has no {k.replace('nonref', 'non-referred work').replace('refereed', 'referred work')} section I can read.")
    cv = dict(date=date, source=pdf.name)
    cv["research_areas"] = parse_lines(secs.get("research_areas", []))
    cv["appointments"] = parse_appointments(secs.get("appointments", []))
    cv["education"] = parse_education(secs.get("education", []))
    cv["experience"] = parse_appointments(secs.get("experience", []))
    cv["funding"] = parse_funding(secs.get("funding", []), left)
    cv["software"] = parse_software(secs.get("software", []), left)
    cv["supervision"] = parse_supervision(secs.get("supervision", []))
    cv["teaching"] = parse_teaching(secs.get("teaching", []))
    cv["service"] = parse_service(secs.get("service", []), left)
    cv["talks"] = parse_talks(secs.get("talks", []), left)
    cv["refereed"] = parse_refereed(secs["refereed"], left)
    cv["nonref"] = parse_nonref(secs["nonref"], left)
    cv["peer_review"] = parse_lines(secs.get("peer_review", []))
    cv["volunteer"] = parse_volunteer(secs.get("volunteer", []))
    cv["_sections_found"] = sorted(secs)
    return cv


def counts(cv):
    pubs = cv["refereed"]["entries"]
    return {
        "appointments": len(cv["appointments"]) + len(cv["experience"]),
        "education": len(cv["education"]),
        "funding": len(cv["funding"]),
        "supervision": len(cv["supervision"]["students"]),
        "teaching": len(cv["teaching"]),
        "service": len(cv["service"]),
        "talks": len(cv["talks"]),
        "publications": len(pubs),
        "outreach": len(cv["nonref"]["entries"]) + (1 if cv["nonref"]["thesis"] else 0),
        "volunteer": len(cv["volunteer"]),
        "peer_review_journals": len([n for n in re.split(r",", cv["peer_review"]) if n.strip()]),
    }


def check_against_previous(cv, n):
    if not DATA_FILE.exists():
        return
    try:
        old = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("counts", {})
    except ValueError:
        return
    long_lists = {"funding", "supervision", "talks", "publications", "outreach"}
    for k, was in old.items():
        now = n.get(k, 0)
        # a long list that suddenly shrinks a lot usually means the layout changed and it was only half read
        if k in long_lists and was >= 8 and now < 0.6 * was:
            fail(f"The CV now has {now} {k} entries, down from {was}. This usually means the layout changed "
                 f"and a section could not be read. Nothing was changed on the site. If the drop is real, "
                 f"delete data/cv.json and run this again.")
        if was >= 1 and now == 0:
            fail(f"The {k} section is empty in this CV but had {was} entries last time. Nothing was changed on the site. "
                 f"If that is intended, delete data/cv.json and run this again.")


def regions(cv):
    cv_year = int(cv["date"].split()[-1])
    groups, latest, unparsed = build_publications(cv, cv_year)
    grants, awards = build_funding(cv)
    intro, sup_groups = build_supervision(cv)
    thesis_urls = {}
    if cv["nonref"]["thesis"]:
        t, u = thesis_info(cv["nonref"]["thesis"])
        if u:
            thesis_urls[norm_title(t)] = u
    reg = {
        "cv-date": esc(cv["date"]),
        "research-areas": build_research_areas(cv),
        "latest-publications": latest,
        "appointments": build_appointments(cv),
        "education": build_education(cv, thesis_urls),
        "publication-summary": publication_summary(cv),
        "pub-legend": legend_text(cv),
        "pubs-articles": groups["articles"],
        "pubs-manuscripts": groups["manuscripts"],
        "pubs-chapters": groups["chapters"],
        "pubs-proceedings": groups["proceedings"],
        "pubs-talks": build_talks(cv),
        "pubs-outreach": groups["outreach"],
        "funding-grants": grants,
        "funding-awards": awards,
        "teaching": build_teaching(cv),
        "supervision-intro": intro,
        "service": build_service(cv["service"]),
        "peer-review": build_peer_review(cv),
        "volunteer": build_service(cv["volunteer"]),
    }
    for g, items in sup_groups.items():
        reg["supervision-" + re.sub(r"[^a-z]+", "", g.lower())] = items
    reg.update(software_numbers(cv))
    return reg, unparsed


def cv_links(cv):
    href = quote(cv["source"])
    return {
        "cv-button": f'<a class="btn" href="{href}">Download CV</a>',
        "cv-link": f'<a href="{href}">Download my CV (PDF)</a>, last updated {esc(cv["date"])}.',
    }


MARK = re.compile(r"(<!--cv:begin ([\w-]+)-->)(.*?)(<!--cv:end \2-->)", re.S)


def patch(page, reg):
    used, missing = set(), []

    def sub(m):
        name = m.group(2)
        if name not in reg:
            missing.append(name)
            return m.group(0)
        used.add(name)
        val = reg[name]
        if isinstance(val, list):
            start = page.rfind("\n", 0, m.start()) + 1
            lead = page[start:m.start()]
            indent = lead if not lead.strip() else "          "
            body = "\n" + "\n".join(indent + x for x in val) if val else ""
            return m.group(1) + body + "\n" + indent + m.group(4)
        return m.group(1) + val + m.group(4)

    return MARK.sub(sub, page), used, missing


def main():
    dry = "--dry-run" in sys.argv
    pdf = pick_cv()
    cv = read_cv(pdf)
    n = counts(cv)
    check_against_previous(cv, n)
    reg, unparsed = regions(cv)
    reg.update(cv_links(cv))
    if "--dump" in sys.argv:
        print(json.dumps(cv, indent=1, ensure_ascii=False))
    page = INDEX.read_text(encoding="utf-8")
    new, used, missing = patch(page, reg)
    for name in missing:
        warn(f'index.html has a "{name}" marker that this script does not fill.')
    absent = sorted(set(reg) - used)
    if absent:
        print("Not in index.html (no marker): " + ", ".join(absent))
    if unparsed:
        warn(f"{unparsed} publication(s) could not be split into authors and title and are shown as written.")
    print(f"Read {pdf.name} ({cv['date']}).")
    print("  " + ", ".join(f"{k} {v}" for k, v in n.items()))
    if dry:
        return
    if new != page:
        INDEX.write_text(new, encoding="utf-8")
        print("index.html updated.")
    else:
        print("index.html already matches the CV.")
    DATA_FILE.parent.mkdir(exist_ok=True)
    out = dict(cv, counts=n)
    text = json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    if not DATA_FILE.exists() or DATA_FILE.read_text(encoding="utf-8") != text:
        DATA_FILE.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
