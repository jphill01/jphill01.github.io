#!/usr/bin/env python3
"""Rebuild the word cloud from the text of index.html and the CV.

Reads  index.html and the CV PDF it links to (the "Download CV" button).
Writes wordcloud.png and data/wordcloud-terms.json.

The vocabulary (which terms can appear) lives in .github/wordcloud/terms.py.
Word area is proportional to how often a term is mentioned. If the counts have
not changed since the last build, nothing is redrawn.

Needs: python3, numpy, pillow, matplotlib, pdftotext (poppler-utils) and the
Caladea fonts (fonts-crosextra-caladea).
"""
import html
import json
import math
import random
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github" / "wordcloud"))
import terms  # noqa: E402  (the editable vocabulary)

INDEX = ROOT / "index.html"
OUT_PNG = ROOT / "wordcloud.png"
OUT_JSON = ROOT / "data" / "wordcloud-terms.json"

# parts of the page that are not research text: the cloud itself and the download plots
SKIP_IDS = {"cloudfig", "usage"}
SKIP_TAGS = {"script", "style", "noscript", "head"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

# ---- picture geometry (pixels at 200 dpi) ----
W, H_OUT, DPI = 2400, 1420, 200
LAYOUT_H = 1500            # the layout area, as designed; the picture is cropped below it
LEGEND_H = 120
MARGIN = 70
SCALE = 0.5                # the layout search runs at half resolution
PAD = 20                   # air around every word
BG, TEXT_LO, TEXT_HI, TOOL = "#FFFFFF", "#2A6AB8", "#0D366B", "#C2410C"


# --------------------------------------------------------------------------
# 1. the text
# --------------------------------------------------------------------------
class PageText(HTMLParser):
    """Visible text of the page, without scripts, the head and the SKIP_IDS blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        if self.depth:
            self.depth += 1
        elif tag in SKIP_TAGS or dict(attrs).get("id") in SKIP_IDS:
            self.depth = 1

    def handle_endtag(self, tag):
        if tag not in VOID and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def website_text():
    parser = PageText()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    parser.close()
    if parser.depth:
        raise SystemExit("index.html: a skipped block was never closed; check for a missing end tag")
    return " ".join(parser.parts)


def cv_path():
    m = re.search(r'href="([^"]*CV[^"]*\.pdf)"', INDEX.read_text(encoding="utf-8"))
    if m:
        p = ROOT / html.unescape(m.group(1))
        if p.exists():
            return p
    found = sorted(ROOT.glob("CV*.pdf"))
    if not found:
        raise SystemExit("No CV PDF found (looked for the link in index.html and for CV*.pdf)")
    return found[-1]


def cv_text(path):
    s = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True,
                       capture_output=True, text=True).stdout
    s = re.sub(r"Jarrett D\. Phillips\s+[—–-]\s+Curriculum Vitae[^\n]*?Page \d+ of \d+", " ", s)  # page footers
    s = re.sub(r"https?://\S+", " ", s)       # URLs
    s = re.sub(r"DOI:?\s*\S+", " ", s)        # DOIs
    s = re.sub(r"10\.\d{4,}/\S+", " ", s)
    # the journals a person reviews for are not research content
    s = re.sub(r"ACADEMIC PEER REVIEW SERVICE.*?VOLUNTEER EXPERIENCE", "VOLUNTEER EXPERIENCE", s, flags=re.S)
    return s


# --------------------------------------------------------------------------
# 2. counts
# --------------------------------------------------------------------------
def count_terms(text):
    for pat in terms.STRIP:
        text = re.sub(pat, " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    counted = []
    for label, kind, pat in terms.LEX:
        rx = re.compile(pat, 0 if label in terms.CASE_SENSITIVE else re.I)
        counted.append((label, kind, len(rx.findall(text))))
        text = rx.sub(" ", text)           # a match is used once
    shown = [(l, k, n) for l, k, n in counted
             if l not in terms.HIDE and (n >= terms.MIN_COUNT or (l in terms.ALWAYS_SHOW and n >= 1))]
    shown.sort(key=lambda t: (-t[2], t[0].lower()))
    return shown


# --------------------------------------------------------------------------
# 3. layout: every word at a size proportional to sqrt(count) so area follows count
# --------------------------------------------------------------------------
def find_font(name):
    for base in ("/usr/share/fonts/truetype/crosextra", "/usr/share/fonts"):
        for p in Path(base).rglob(name):
            return str(p)
    raise SystemExit(f"Font {name} not found. Install fonts-crosextra-caladea.")


SERIF = find_font("Caladea-Regular.ttf")
SERIF_B = find_font("Caladea-Bold.ttf")


def font_for(kind):
    return SERIF_B if kind == "tool" else SERIF


CW, CH = int(W * SCALE), int(H_OUT * SCALE)
X_LO, X_HI = int(MARGIN * SCALE), int((W - MARGIN) * SCALE)
Y_LO, Y_HI = int(MARGIN * SCALE), int((LAYOUT_H - LEGEND_H - MARGIN * 0.4) * SCALE)
CX, CY = (X_LO + X_HI) // 2, (Y_LO + Y_HI) // 2
ASPECT = (X_HI - X_LO) / (Y_HI - Y_LO)


def word_mask(label, kind, px, rotate):
    f = ImageFont.truetype(font_for(kind), max(6, int(round(px * SCALE))))
    l, t, r, b = f.getbbox(label, anchor="ls")
    pad = int(PAD * SCALE)
    img = Image.new("L", (r - l + 2 * pad + 2, b - t + 2 * pad + 2), 0)
    ox, oy = pad + 1 - l, pad + 1 - t              # pen origin (baseline, left) inside the mask
    ImageDraw.Draw(img).text((ox, oy), label, font=f, fill=255, anchor="ls")
    img = img.filter(ImageFilter.MaxFilter(2 * pad + 1))
    m = np.array(img) > 0
    if rotate:
        m = np.rot90(m)                            # 90 degrees counter-clockwise
        return m, oy, (m.shape[0] - 1) - ox
    return m, ox, oy


def fit_positions(occ, m):
    """Every top-left (y, x) where mask m touches nothing placed so far (FFT cross-correlation)."""
    mh, mw = m.shape
    shape = (occ.shape[0] + mh, occ.shape[1] + mw)
    fo = np.fft.rfft2(occ.astype(np.float32), s=shape)
    fm = np.fft.rfft2(m.astype(np.float32), s=shape)
    ov = np.fft.irfft2(fo * np.conj(fm), s=shape)
    return ov[:occ.shape[0] - mh + 1, :occ.shape[1] - mw + 1] < 0.5


def layout(items, smax, seed):
    nmax = max(n for _, _, n in items)
    rng = random.Random(seed)
    occ = np.zeros((CH, CW), dtype=bool)
    placed = []
    for label, kind, n in items:
        px = smax * math.sqrt(n / nmax)
        rotate = (n <= 7 and len(label) <= 13 and sum(p["rot"] for p in placed) < 5 and rng.random() < 0.3)
        m, ox, oy = word_mask(label, kind, px, rotate)
        mh, mw = m.shape
        ys, xs = np.nonzero(fit_positions(occ, m))
        keep = (xs >= X_LO) & (ys >= Y_LO) & (xs + mw <= X_HI) & (ys + mh <= Y_HI)
        ys, xs = ys[keep], xs[keep]
        if not len(xs):
            return None, occ
        d = ((xs + ox - CX) / ASPECT) ** 2 + (ys + oy - CY) ** 2
        best = np.argsort(d)[:12]
        k = best[rng.randrange(len(best))]
        x, y = int(xs[k]), int(ys[k])
        occ[y:y + mh, x:x + mw] |= m
        placed.append(dict(label=label, kind=kind, n=n, px=px, rot=rotate, x=(x + ox) / SCALE, y=(y + oy) / SCALE))
    return placed, occ


def best_layout(items):
    """Largest word size at which every term fits; of 4 seeds, the one that fills the space best."""
    smax, best = 170.0, None
    while smax > 60 and best is None:
        for seed in range(1, 5):
            placed, occ = layout(items, smax, seed)
            if placed:
                fill = occ[Y_LO:Y_HI, X_LO:X_HI].mean()
                if best is None or fill > best[0]:
                    best = (fill, smax, placed)
        smax *= 0.97
    if best is None:
        raise SystemExit("The terms do not fit; raise MIN_COUNT or add terms to HIDE in terms.py")
    return best


# --------------------------------------------------------------------------
# 4. drawing
# --------------------------------------------------------------------------
def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def colour(word, nmax):
    if word["kind"] == "tool":
        return TOOL
    t = math.sqrt(word["n"] / nmax)                # 1 = the most frequent term
    lo, hi = hex2rgb(TEXT_LO), hex2rgb(TEXT_HI)
    return "#%02X%02X%02X" % tuple(int(round(a + (b - a) * t)) for a, b in zip(lo, hi))


def draw(placed, path):
    nmax = max(w["n"] for w in placed)
    fig = plt.figure(figsize=(W / DPI, H_OUT / DPI), dpi=DPI, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H_OUT, 0)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, H_OUT, color=BG, lw=0))
    for w in placed:
        fp = FontProperties(fname=font_for(w["kind"]), size=w["px"] * 72 / DPI)
        # matplotlib aligns the ink of a string, the layout used its pen origin: shift by the left bearing
        lb = ImageFont.truetype(font_for(w["kind"]), int(round(w["px"]))).getbbox(w["label"], anchor="ls")[0]
        ax.text(w["x"] + (0 if w["rot"] else lb), w["y"] - (lb if w["rot"] else 0), w["label"],
                fontproperties=fp, color=colour(w, nmax), ha="left", va="baseline",
                rotation=90 if w["rot"] else 0, rotation_mode="anchor")
    tmp = path.with_suffix(".tmp.png")
    fig.savefig(tmp, dpi=DPI, facecolor=BG)
    plt.close(fig)
    # flat colours plus anti-aliasing: a 128-colour palette is visually identical and about a third the size
    Image.open(tmp).convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT,
                                            dither=Image.Dither.NONE).save(path, optimize=True)
    tmp.unlink()


# --------------------------------------------------------------------------
def main():
    cv = cv_path()
    items = count_terms(website_text() + "\n" + cv_text(cv))
    if not items:
        raise SystemExit("No terms found; is the text empty?")
    doc = {
        "sources": {"site": INDEX.name, "cv": cv.name},
        "terms": [{"label": l, "type": "tool" if k == "tool" else "topic", "n": n} for l, k, n in items],
    }
    if OUT_PNG.exists() and OUT_JSON.exists():
        try:
            if json.loads(OUT_JSON.read_text(encoding="utf-8")).get("terms") == doc["terms"]:
                print("Term counts are unchanged; keeping the existing word cloud.")
                return
        except (OSError, json.JSONDecodeError):
            pass
    fill, smax, placed = best_layout(items)
    draw(placed, OUT_PNG)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Drew {len(placed)} terms (largest word {smax:.0f}px, {fill * 100:.0f}% filled). "
          f"Top terms: " + ", ".join(f"{l} {n}" for l, _, n in items[:6]))


if __name__ == "__main__":
    main()
