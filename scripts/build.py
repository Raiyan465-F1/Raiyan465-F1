#!/usr/bin/env python3
"""Builds every SVG panel of the profile README.

No dependencies beyond the Python standard library. All text is drawn as
vector paths from the bitmap tables in pixelfonts.json, because an SVG shown
through an <img> tag cannot load web fonts.

    python3 scripts/build.py

Reads  profile.json            what the panels say
       data/live.json          contribution calendar + counters (fetch.py)
Writes assets/*.svg
       README.md               only the quest and link blocks between markers
"""
import datetime
import html
import json
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = json.load(open(os.path.join(ROOT, "scripts", "pixelfonts.json")))
CFG = json.load(open(os.path.join(ROOT, "profile.json")))

BG = "#07070f"
INK = "#e9f3ff"
SOFT = "#9fb0d6"
DIM = "#56628a"
DIM2 = "#252c4c"
CYAN = "#22e6ff"
MAG = "#ff2e88"
YEL = "#ffe14a"
GRN = "#5dff8f"
VIO = "#8a5cff"
NAMED = {"cyan": CYAN, "magenta": MAG, "yellow": YEL, "green": GRN, "violet": VIO}

W = 960

# ---------------------------------------------------------------- pixel text

_cache = {}
_top = {}
NATIVE = {"term": 0.8}   # the terminal face has a 10 px cell; 0.8 makes sc=1 an 8 px advance


def _rows(font, ch):
    g = FONTS[font]["g"].get(ch) or FONTS[font]["g"]["?"]
    return g, [bin(int(r, 16))[2:].zfill(g["w"]) for r in g["r"]]


def _font_top(font):
    """First row used by capital letters, so y always means 'top of caps'."""
    if font not in _top:
        best = 99
        for ch in "ABEHTZ0":
            _, rows = _rows(font, ch)
            for i, r in enumerate(rows):
                if "1" in r:
                    best = min(best, i)
                    break
        _top[font] = best
    return _top[font]


def _rects(rows):
    """Bitmap rows -> list of (x, y, w, h), merging runs down consecutive rows."""
    out, active = [], {}
    width = len(rows[0]) if rows else 0
    for y, row in enumerate(list(rows) + ["0" * width]):
        runs, x = set(), 0
        while x < len(row):
            if row[x] != "0" and row[x] != ".":
                x0 = x
                while x < len(row) and row[x] != "0" and row[x] != ".":
                    x += 1
                runs.add((x0, x - x0))
            else:
                x += 1
        for key in list(active):
            if key not in runs:
                y0 = active.pop(key)
                out.append((key[0], y0, key[1], y - y0))
        for key in runs:
            active.setdefault(key, y)
    return out


def _d(rects, dx=0, dy=0):
    return "".join("M%d %dh%dv%dh-%dz" % (x + dx, y + dy, w, h, w) for x, y, w, h in rects)


def glyph(font, ch):
    key = (font, ch)
    if key not in _cache:
        g, rows = _rows(font, ch)
        _cache[key] = (_rects(rows), g["a"])
    return _cache[key]


def measure(font, s, sc=1, track=0):
    return sum(glyph(font, c)[1] + track for c in s) * sc * NATIVE.get(font, 1)


def text_d(font, s, track=0):
    top = _font_top(font)
    x, parts = 0, []
    for c in s:
        rects, adv = glyph(font, c)
        parts.append(_d(rects, x, -top))
        x += adv + track
    return "".join(parts), x


def fmt(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


def T(font, s, x, y, sc=1, fill=INK, anchor="l", track=0, attrs=""):
    """One string as a single path. Returns the SVG fragment."""
    d, w = text_d(font, s, track)
    sc *= NATIVE.get(font, 1)
    if anchor == "r":
        x -= w * sc
    elif anchor == "c":
        x -= w * sc / 2
    return '<path transform="translate(%s %s) scale(%s)" fill="%s" d="%s"%s/>' % (
        fmt(x), fmt(y), fmt(sc), fill, d, (" " + attrs) if attrs else "")


def typed(font, segs, x, y, sc, t0, cps=60.0):
    """Types (text, colour) segments one glyph at a time.

    The resting state is fully visible; the animation only hides glyphs
    before their turn, so a viewer with reduced motion still sees the text.
    Returns (svg, end_time, end_x).
    """
    top = _font_top(font)
    sc *= NATIVE.get(font, 1)
    out, t, cx = [], t0, 0
    for s, col in segs:
        chunk = []
        for c in s:
            rects, adv = glyph(font, c)
            if rects:
                chunk.append('<path class="ty" style="animation-delay:%ss" d="%s"/>' % (
                    fmt(t), _d(rects, cx, -top)))
            cx += adv
            t += 1.0 / cps
        out.append('<g fill="%s">%s</g>' % (col, "".join(chunk)))
    svg = '<g transform="translate(%s %s) scale(%s)">%s</g>' % (fmt(x), fmt(y), fmt(sc), "".join(out))
    return svg, t, x + cx * sc


def sprite(rows, palette, px, x=0, y=0, attrs=""):
    """ASCII pixel art -> one path per colour."""
    out = []
    for ch, col in palette.items():
        mask = ["".join("1" if c == ch else "0" for c in r) for r in rows]
        rects = _rects(mask)
        if rects:
            out.append('<path fill="%s" d="%s"/>' % (col, _d(rects)))
    return '<g transform="translate(%s %s) scale(%s)"%s>%s</g>' % (
        fmt(x), fmt(y), fmt(px), (" " + attrs) if attrs else "", "".join(out))


# ------------------------------------------------------------- shared chrome

BASE_CSS = """
.ty{animation:ty .01s steps(1) both}
@keyframes ty{from{opacity:0}to{opacity:1}}
.blink{animation:blink 1.1s steps(1) infinite}
@keyframes blink{0%{opacity:1}50%{opacity:0}100%{opacity:1}}
.sweep{animation:sweep 7s linear infinite}
@keyframes sweep{from{transform:translateY(-140px)}to{transform:translateY(700px)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def chamfer(w, h, c):
    return "%d,0 %d,0 %d,%d %d,%d 0,%d 0,%d" % (c, w, w, h - c, w - c, h, h, c)


def svg_doc(w, h, body, css="", defs="", label="", cut=18, accent=CYAN, sweep=True, bg=BG):
    pts = chamfer(w, h, cut)
    label = html.escape(label, quote=True)
    tick = int(min(34, h * 0.3))
    uid = "p%d%d" % (w, h)
    overlay = '<rect width="%d" height="%d" fill="url(#sl%s)"/>' % (w, h, uid)
    if sweep:
        overlay += '<rect class="sweep" width="%d" height="120" fill="url(#sw%s)"/>' % (w, uid)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s">'
        "<title>%s</title><style>%s%s</style><defs>"
        '<clipPath id="cf%s"><polygon points="%s"/></clipPath>'
        '<pattern id="sl%s" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" y="3" fill="#000" opacity=".28"/></pattern>'
        '<linearGradient id="sw%s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#fff" stop-opacity=".045"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        "%s</defs>"
        '<g clip-path="url(#cf%s)"><rect width="%d" height="%d" fill="%s"/>%s%s</g>'
        '<polygon points="%s" fill="none" stroke="%s" stroke-width="2" stroke-opacity=".55"/>'
        '<path d="M%d 1H%dV%d" fill="none" stroke="%s" stroke-width="4"/>'
        '<path d="M1 %dV%dH%d" fill="none" stroke="%s" stroke-width="4"/>'
        "</svg>"
    ) % (
        w, h, w, h, label, label, BASE_CSS, css,
        uid, pts, uid, uid, defs,
        uid, w, h, bg, body, overlay,
        pts, accent,
        w - tick, w - 1, tick, accent,
        h - tick, h - 1, tick, accent,
    )


def header(w, title, right="", accent=CYAN, num=""):
    out = ['<rect width="%d" height="36" fill="%s" opacity=".07"/>' % (w, accent),
           '<rect y="36" width="%d" height="1" fill="%s" opacity=".45"/>' % (w, accent)]
    x = 30
    if num:
        out.append(T("display", num, x, 13, 1.5, DIM))
        x += measure("display", num, 1.5) + 10
        out.append(T("display", "//", x, 13, 1.5, DIM2))
        x += measure("display", "//", 1.5) + 10
    out.append(T("display", title, x, 13, 1.5, accent))
    if right:
        out.append(T("micro", right, w - 48, 13, 2, DIM, anchor="r"))
    return "".join(out)


def write(name, svg):
    path = os.path.join(ROOT, "assets", name)
    with open(path, "w") as f:
        f.write(svg)
    return len(svg)


# ---------------------------------------------------------------------- hero

RAMP = ".:-=+*#%@"


def core_frames(cols=34, rows=13, frames=16, cw=7.2, lh=12.0):
    """Ray-marched ASCII crystal inside an orbit ring.

    The crystal is an octahedron spinning on its own axis; the ring shares
    that axis, so the picture repeats every quarter turn and 16 frames over
    90 degrees loop without a seam.
    """
    tilt = math.radians(28)
    ct, st = math.cos(tilt), math.sin(tilt)
    light = (-0.5, 0.65, -0.57)
    ln = math.sqrt(sum(v * v for v in light))
    light = tuple(v / ln for v in light)
    hh = 1.45
    aspect = (cols * cw) / (rows * lh)

    def sdf(p, ca, sa):
        x, y, z = p
        y, z = y * ct - z * st, y * st + z * ct          # undo tilt
        x, z = x * ca + z * sa, -x * sa + z * ca          # undo spin
        crystal = (abs(x) + abs(y) / 1.5 + abs(z) - 0.95) * 0.5
        q = math.sqrt(x * x + z * z) - 1.9
        ring = math.sqrt(q * q + (y * 2.2) ** 2) - 0.2
        return min(crystal, ring * 0.45)

    out = []
    for f in range(frames):
        a = (math.pi / 2) * f / frames
        ca, sa = math.cos(a), math.sin(a)
        grid = []
        for j in range(rows):
            line = []
            for i in range(cols):
                px = ((i + 0.5) / cols - 0.5) * 2 * hh * aspect
                py = (0.5 - (j + 0.5) / rows) * 2 * hh
                z, hit = -5.0, False
                for _ in range(90):
                    d = sdf((px, py, z), ca, sa)
                    if d < 0.003:
                        hit = True
                        break
                    z += d
                    if z > 5:
                        break
                if not hit:
                    line.append(" ")
                    continue
                e = 0.002
                n = (sdf((px + e, py, z), ca, sa) - sdf((px - e, py, z), ca, sa),
                     sdf((px, py + e, z), ca, sa) - sdf((px, py - e, z), ca, sa),
                     sdf((px, py, z + e), ca, sa) - sdf((px, py, z - e), ca, sa))
                nl = math.sqrt(sum(v * v for v in n)) or 1
                lum = max(0.0, sum(n[k] / nl * light[k] for k in range(3)))
                line.append(RAMP[min(len(RAMP) - 1, int(0.5 + lum * (len(RAMP) - 1)))])
            grid.append("".join(line))
        out.append(grid)
    return out


def build_hero():
    c = CFG
    extra = (30 * len(c.get("intro", [])) + 10) if c.get("intro") else 0
    H = 536 + extra
    body, css = [], []

    # backdrop grid
    defs = ('<pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">'
            '<path d="M48 0H0V48" fill="none" stroke="%s" stroke-opacity=".07"/></pattern>'
            '<radialGradient id="vig" cx=".5" cy=".5" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/>'
            '<stop offset="1" stop-color="#000" stop-opacity=".6"/></radialGradient>') % CYAN
    body.append('<rect width="%d" height="%d" fill="url(#grid)"/>' % (W, H))

    # status bar
    bar = [header(W, c["os_name"], accent=CYAN)]
    x = 30 + measure("display", c["os_name"], 1.5) + 12
    bar.append(T("micro", "V" + c["os_version"], x, 13, 2, DIM))
    right = "NODE %s  %s  %s" % (c["node"], c["coords"], c["timezone"])
    rw = measure("micro", right, 2)
    bar.append(T("micro", right, W - 48, 13, 2, DIM, anchor="r"))
    bar.append('<rect class="blink" x="%s" y="14" width="8" height="8" fill="%s"/>' % (fmt(W - 48 - rw - 58), MAG))
    bar.append(T("micro", "REC", W - 48 - rw - 44, 13, 2, MAG))
    body.append("".join(bar))

    # boot log
    t, y = 0.55, 62
    stamps = ["0.000", "0.137", "0.412", "0.731", "1.024", "1.337"]
    cols = 46
    for i, (msg, status, colour) in enumerate(c["boot"]):
        dots = "." * max(3, cols - len(msg) - len(status) - 2)
        svg, t, _ = typed("term", [("[%s] " % stamps[i], DIM), (msg + " ", SOFT), (dots + " ", DIM2),
                                   (status, NAMED[colour])], 30, y, 1, t, cps=190)
        body.append(svg)
        t += 0.07
        y += 21
    svg, t, ex = typed("term", [("[%s] " % stamps[5], DIM), ("HELLO, WORLD. I AM", INK)], 30, y, 1, t, cps=60)
    body.append(svg)
    t_name = t + 0.15

    # ascii core
    frames = core_frames()
    ccols, crows = len(frames[0][0]), len(frames[0])
    cw, lh, n = 7.2, 12.0, len(frames)
    cx0, cy0 = W - 40 - ccols * cw, 46
    period = 1.76
    fr = []
    for fi, grid in enumerate(frames):
        rows = []
        for j, line in enumerate(grid):
            i = 0
            while i < len(line):       # one <text> per run, so spacing never depends on the viewer's font
                if line[i] == " ":
                    i += 1
                    continue
                k = i
                while k < len(line) and line[k] != " ":
                    k += 1
                rows.append('<text x="%s" y="%s" textLength="%s">%s</text>' % (
                    fmt(cx0 + i * cw), fmt(cy0 + (j + 1) * lh - 2), fmt((k - i) * cw), line[i:k]))
                i = k
        delay = -(period - fi * period / n) if fi else 0
        fr.append('<g class="cf%s" style="animation-delay:%ss">%s</g>' % (
            " cf0" if fi == 0 else "", fmt(delay), "".join(rows)))
    body.append('<g fill="%s" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,\'Liberation Mono\',\'DejaVu Sans Mono\',monospace" '
                'font-size="12" font-weight="700" lengthAdjust="spacingAndGlyphs">%s</g>' % (CYAN, "".join(fr)))
    css.append(".cf{opacity:0;animation:cf %ss steps(1) infinite}.cf0{opacity:1}" % fmt(period))
    css.append("@keyframes cf{0%%{opacity:1}%s%%,100%%{opacity:0}}" % fmt(100.0 / n))
    css.append("@media (prefers-reduced-motion:reduce){.cf{opacity:0}.cf0{opacity:1}}")
    cbot = cy0 + crows * lh
    body.append(T("micro", "CORE.SYS", cx0, cbot + 8, 2, DIM))
    body.append(T("micro", "ONLINE", cx0 + ccols * cw, cbot + 8, 2, GRN, anchor="r", attrs='class="blink"'))
    bx0, bx1, by0, by1 = cx0 - 10, cx0 + ccols * cw + 10, cy0, cbot + 26
    body.append('<path d="M%s %sH%sV%s M%s %sH%sV%s M%s %sH%sV%s M%s %sH%sV%s" fill="none" stroke="%s" stroke-width="2"/>' % (
        fmt(bx0 + 14), fmt(by0), fmt(bx0), fmt(by0 + 14),
        fmt(bx1 - 14), fmt(by0), fmt(bx1), fmt(by0 + 14),
        fmt(bx0 + 14), fmt(by1), fmt(bx0), fmt(by1 - 14),
        fmt(bx1 - 14), fmt(by1), fmt(bx1), fmt(by1 - 14), DIM))

    # the name: three colour layers, cut into bands that jump sideways
    name = c["name"]
    sc = 8
    nw = measure("display", name, sc)
    nx, ny = (W - nw) / 2.0, 252
    d, _ = text_d("display", name)
    defs += '<path id="nm" d="%s"/>' % d
    bands, band_h = 5, 13
    rnd = random.Random(465)
    layer = []
    for b in range(bands):
        defs += '<clipPath id="nb%d"><rect x="-40" y="%d" width="%d" height="%d"/></clipPath>' % (
            b, ny - 2 + b * band_h, W + 80, band_h + (4 if b == bands - 1 else 0))
        layer.append(
            '<g clip-path="url(#nb%d)"><g class="gl gl%d"><g transform="translate(%s %s) scale(%d)">'
            '<use href="#nm" x="-.6" fill="%s"/><use href="#nm" x=".6" fill="%s"/><use href="#nm" fill="%s"/>'
            "</g></g></g>" % (b, b, fmt(nx), ny, sc, MAG, CYAN, INK))
        # each band glitches at its own moments inside a 6.5s loop
        keys = ["0%{transform:translateX(0)}"]
        base = 62 + rnd.random() * 6
        for k in range(4):
            p = base + k * 1.1 + rnd.random() * 0.4
            keys.append("%s%%{transform:translateX(%dpx)}" % (fmt(p), rnd.choice([-22, -12, -6, 7, 14, 26])))
        keys.append("%s%%,100%%{transform:translateX(0)}" % fmt(base + 5.2))
        css.append("@keyframes gl%d{%s}.gl%d{animation:gl%d 6.5s steps(1) infinite;animation-delay:%ss}" % (
            b, "".join(keys), b, b, fmt(t_name - 3.2)))
    # scrambled frames that flash before the name locks in
    alphabet = "#%$@&!?/\\<>[]{}=+*0123456789ABCDEFGHJKMNPQRSTUVWXYZ"
    scr = []
    for k in range(5):
        junk = "".join(" " if ch == " " else rnd.choice(alphabet) for ch in name)
        scr.append(T("display", junk, nx, ny, sc, [CYAN, MAG, CYAN, YEL, INK][k],
                     attrs='class="scr" style="animation-delay:%ss"' % fmt(t_name + k * 0.09)))
    css.append(".scr{opacity:0;animation:scr .09s steps(1)}@keyframes scr{from{opacity:.85}to{opacity:.85}}")
    t_lock = t_name + 5 * 0.09
    body.append("".join(scr))
    body.append('<g class="ty" style="animation-delay:%ss">%s</g>' % (fmt(t_lock), "".join(layer)))
    # underline rule with ticks
    body.append('<g class="ty" style="animation-delay:%ss"><rect x="%s" y="%d" width="%s" height="2" fill="%s" opacity=".7"/>'
                '<rect x="%s" y="%d" width="64" height="6" fill="%s"/></g>' % (
                    fmt(t_lock), fmt(nx), ny + 82, fmt(nw), MAG, fmt(nx), ny + 80, MAG))

    # roles + tagline
    t = t_lock + 0.25
    svg, t, _ = typed("display", [(c["role_a"], CYAN), (" // ", DIM), (c["role_b"], MAG)], nx, ny + 104, 2, t, cps=55)
    body.append(svg)
    t += 0.2
    svg, t, ex = typed("term", [("> ", YEL), (c["tagline"], SOFT)], nx, ny + 142, 1.5, t, cps=70)
    body.append(svg)
    cur_y = ny + 139
    # intro sentence, set in its own face
    iy = ny + 186
    for line in c.get("intro", []):
        t += 0.15
        svg, t, ex = typed("body", [(line, INK)], nx, iy, 1.6, t, cps=110)
        body.append(svg)
        cur_y = iy - 1
        iy += 30
    body.append('<g class="ty" style="animation-delay:%ss"><rect class="blink" x="%s" y="%s" width="12" height="20" fill="%s"/></g>' % (
        fmt(t), fmt(ex + 6), fmt(cur_y), YEL))
    shift = iy - (ny + 186) + (10 if c.get("intro") else 0)

    # ticker
    ty = 440 + shift
    body.append('<rect y="%d" width="%d" height="34" fill="%s" opacity=".09"/>' % (ty, W, MAG))
    body.append('<rect y="%d" width="%d" height="1" fill="%s" opacity=".5"/><rect y="%d" width="%d" height="1" fill="%s" opacity=".5"/>' % (
        ty, W, MAG, ty + 34, W, MAG))
    one = "".join(item + "   ///   " for item in c["ticker"])
    lw = measure("micro", one, 2)
    reps = int(math.ceil((W + lw) / lw)) + 1
    body.append('<g class="tick">%s</g>' % "".join(
        T("micro", one, k * lw, ty + 12, 2, INK) for k in range(reps)))
    css.append(".tick{animation:tick %ss linear infinite}@keyframes tick{to{transform:translateX(-%spx)}}" % (
        fmt(lw / 42.0), fmt(lw)))

    # footer strip: prompt + equaliser
    fy = 492 + shift
    body.append(T("display", ">", 30, fy + 3, 1.5, YEL))
    body.append(T("display", "SCROLL TO CONTINUE", 52, fy + 3, 1.5, YEL, attrs='class="blink"'))
    bars = 28
    ex0 = W - 30 - bars * 9
    eq = []
    for k in range(bars):
        hgt = 26
        dur = 0.7 + rnd.random() * 0.9
        eq.append('<rect class="eq" x="%d" y="%d" width="6" height="%d" fill="%s" style="animation-duration:%ss;animation-delay:-%ss"/>' % (
            ex0 + k * 9, fy - 6, hgt, CYAN if k % 5 else MAG, fmt(dur), fmt(rnd.random() * 2)))
    body.append("".join(eq))
    body.append(T("micro", "SIGNAL", ex0 - 12, fy + 3, 2, DIM, anchor="r"))
    css.append(".eq{transform-box:fill-box;transform-origin:50% 100%;animation:eq 1s steps(5) infinite alternate}"
               "@keyframes eq{0%{transform:scaleY(.15)}35%{transform:scaleY(.9)}60%{transform:scaleY(.4)}100%{transform:scaleY(1)}}")

    # CRT switch-on
    css.append(".crt{transform-origin:480px " + str(H // 2) + "px;animation:crt .45s cubic-bezier(.2,.9,.3,1) both}"
               "@keyframes crt{0%{transform:scale(1,.004);filter:brightness(6)}55%{transform:scale(1,.004);filter:brightness(6)}"
               "100%{transform:scale(1,1);filter:brightness(1)}}")
    inner = '<g class="crt">%s</g><rect width="%d" height="%d" fill="url(#vig)"/>' % ("".join(body), W, H)
    label = "%s. %s, %s. %s %s" % (c["name"].title(), c["role_a"], c["role_b"], c["tagline"], " ".join(c.get("intro", [])))
    return svg_doc(W, H, inner, "".join(css), defs, label, cut=26)


# --------------------------------------------------------------- commit city

LEVELS = ["#1b2147", "#0f6d7d", CYAN, YEL, MAG]

RICKSHAW = [
    "..................................",
    "...MMMMMMMMMMM........KKK.........",
    "..MMCCCCCCCCCMM......KSSK.........",
    "..MC.........CMM.....KSSK.........",
    "..MC...........M....TTTT..........",
    "..MC...............TTTTT..........",
    "..MC..............TTTTSSSSFF......",
    "..MC..YYYYYYYY....TTTT.....F......",
    "..MCYYYYYYYYYYY..FTTT......F......",
    "..MYYYMMMMMMMYYY.FPP.......F......",
    "..YYYYYYYYYYYYYYFFFPFFFFFFFFF.....",
    "...YYYYYYYYYYYY....P........F.....",
    ".......F..........PP.........F....",
    ".......F..........P..........F....",
    ".......F.........PP..........F....",
    "..................................",
    "..................................",
    "..................................",
    "..................................",
    "..................................",
]
RICK_PAL = {"M": MAG, "C": CYAN, "Y": YEL, "K": "#0c0c18", "S": "#d9a074", "T": INK, "P": "#3b4a8c", "F": "#8fa0c8"}


def wheel(cx, cy, r, phase):
    """Pixel ring with spokes; two phases make it look like it turns."""
    rows = []
    for y in range(20):
        line = ""
        for x in range(34):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx * dx + dy * dy)
            ch = "."
            if r - 0.75 <= dist <= r + 0.45:
                ch = "W"
            elif dist < r - 0.75:
                if phase == 0 and (abs(dx) <= 0.5 or abs(dy) <= 0.5):
                    ch = "s"
                if phase == 1 and abs(abs(dx) - abs(dy)) < 0.5:
                    ch = "s"
                if dist < 1:
                    ch = "W"
            line += ch
        rows.append(line)
    return rows


def month_marks(weeks_n, today=None):
    """Month labels for a calendar that ends this week (used by the stand-in data)."""
    today = today or datetime.date.today()
    sunday = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
    out, last = [], None
    for i in range(weeks_n):
        first = sunday - datetime.timedelta(days=7 * (weeks_n - 1 - i))
        if first.month != last:
            if last is not None:
                out.append({"name": first.strftime("%b"), "week": i})
            last = first.month
    return out


def demo_calendar(seed=465):
    """Stand-in data so the panel can be previewed before the first real fetch.
    The panel labels itself DEMO DATA whenever this is what it is drawing."""
    rnd = random.Random(seed)
    weeks = []
    for wk in range(53):
        mood = 0.25 + 0.75 * abs(math.sin(wk / 5.3)) * rnd.random()
        days = []
        for dow in range(7):
            lvl = 0
            if rnd.random() < mood:
                lvl = 1 + min(3, int(rnd.random() * rnd.random() * 5))
            days.append({"level": lvl, "count": lvl * 3})
        weeks.append(days)
    return {"demo": True, "total": 0, "weeks": weeks, "months": month_marks(53)}


def load_live():
    live = {}
    path = os.path.join(ROOT, "data", "live.json")
    if os.path.exists(path):
        try:
            live = json.load(open(path))
        except ValueError:
            live = {}
    if not live.get("weeks"):
        demo = demo_calendar()
        demo["counters"] = live.get("counters") or {}
        return demo
    return live


def build_city(live):
    H = 372
    rnd = random.Random(7)
    body, css = [], []
    ground = 306
    defs = ('<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#05050f"/>'
            '<stop offset=".55" stop-color="#150a36"/><stop offset="1" stop-color="#4b1460"/></linearGradient>'
            '<pattern id="rain" width="60" height="120" patternUnits="userSpaceOnUse">'
            '<path d="M50 4l-6 18M22 40l-6 18M40 78l-6 18M8 96l-6 18" stroke="%s" stroke-width="1.5" opacity=".22"/></pattern>') % CYAN
    body.append('<rect y="37" width="%d" height="%d" fill="url(#sky)"/>' % (W, ground - 37))

    # stars
    stars = []
    for k in range(70):
        sx, sy = rnd.randrange(10, W - 10), rnd.randrange(46, 190)
        cls = ' class="tw" style="animation-delay:-%ss"' % fmt(rnd.random() * 4) if k % 4 == 0 else ""
        stars.append('<rect x="%d" y="%d" width="2" height="2" fill="%s" opacity="%s"%s/>' % (
            sx, sy, rnd.choice([INK, INK, CYAN, MAG]), fmt(0.35 + rnd.random() * 0.5), cls))
    body.append("".join(stars))
    css.append(".tw{animation:tw 3.2s steps(2) infinite}@keyframes tw{50%{opacity:.1}}")

    # pixel moon
    mrows = []
    R = 9
    for y in range(-R, R + 1):
        line = ""
        for x in range(-R, R + 1):
            if x * x + y * y <= R * R + 2:
                crater = ((x + 3) ** 2 + (y + 2) ** 2 <= 5) or ((x - 4) ** 2 + (y - 4) ** 2 <= 3) or ((x + 1) ** 2 + (y - 5) ** 2 <= 2)
                line += "c" if crater else "m"
            else:
                line += "."
        mrows.append(line)
    body.append(sprite(mrows, {"m": "#fff0b8", "c": "#e6c97a"}, 4, 812, 58))

    # distant skyline
    far = []
    x = -6
    while x < W:
        bw = rnd.randrange(22, 58)
        bh = rnd.randrange(40, 150)
        far.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#1a0d3f"/>' % (x, ground - bh, bw, bh))
        x += bw + rnd.randrange(-4, 8)
    body.append("".join(far))

    # towers: one per week, one window per day
    weeks = live["weeks"][-53:]
    pitch, bw = 17, 13
    x0 = (W - len(weeks) * pitch + (pitch - bw)) // 2
    stack_top = ground - 8 - 7 * 9
    sums = [sum(d.get("count") or 0 for d in wk if d) for wk in weeks]
    top = max(sums) or 1
    towers, windows, lights = [], [[] for _ in LEVELS], []
    shades = ["#141a3a", "#0f1430", "#181f46"]
    order = sorted(range(len(weeks)), key=lambda i: -sums[i])
    beacons = set(order[:6])
    flick = 0
    for i, wk in enumerate(weeks):
        bx = x0 + i * pitch
        ext = int(round(86 * (sums[i] / float(top)) ** 0.8))
        ty = stack_top - 6 - ext
        col = shades[(i * 7 + sums[i]) % 3]
        towers.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s"/>' % (bx, ty, bw, ground - ty, col))
        towers.append('<rect x="%d" y="%d" width="1" height="%d" fill="#2c376c"/>' % (bx, ty, ground - ty))
        yy = stack_top - 12
        while yy > ty + 4:   # dark upper floors: taller tower, busier week
            towers.append('<rect x="%d" y="%d" width="9" height="2" fill="#090c20"/>' % (bx + 2, yy))
            yy -= 9
        if i in beacons and sums[i]:
            towers.append('<rect x="%d" y="%d" width="1" height="12" fill="#2c376c"/>' % (bx + 6, ty - 12))
            lights.append('<rect class="blink" x="%d" y="%d" width="3" height="3" fill="%s" style="animation-delay:-%ss"/>' % (
                bx + 5, ty - 15, MAG, fmt(rnd.random())))
        for dow, day in enumerate(wk):
            if day is None:
                continue
            lvl = max(0, min(4, int(day.get("level", 0))))
            wx, wy = bx + 2, stack_top + dow * 9
            extra = ""
            if lvl >= 2 and flick < 26 and rnd.random() < 0.12:
                extra = ' class="fl" style="animation-delay:-%ss"' % fmt(rnd.random() * 6)
                flick += 1
            windows[lvl].append('<rect x="%d" y="%d" width="9" height="6"%s/>' % (wx, wy, extra))
    body.append("".join(towers))
    for lvl, items in enumerate(windows):
        body.append('<g fill="%s">%s</g>' % (LEVELS[lvl], "".join(items)))
    body.append("".join(lights))
    css.append(".fl{animation:fl 6s steps(1) infinite}@keyframes fl{0%{opacity:1}91%{opacity:.25}93%{opacity:1}95%{opacity:.4}97%{opacity:1}}")

    # rain over the scene
    body.append('<g clip-path="url(#sc)"><rect class="rain" x="-60" y="-120" width="%d" height="%d" fill="url(#rain)"/></g>' % (W + 120, ground + 240))
    defs += '<clipPath id="sc"><rect y="37" width="%d" height="%d"/></clipPath>' % (W, ground - 37)
    css.append(".rain{animation:rain .9s linear infinite}@keyframes rain{to{transform:translate(-40px,120px)}}")

    # street
    body.append('<rect y="%d" width="%d" height="%d" fill="#090912"/>' % (ground, W, H - ground))
    body.append('<rect y="%d" width="%d" height="2" fill="%s" opacity=".7"/>' % (ground, W, CYAN))
    dashes = "".join('<rect x="%d" y="%d" width="22" height="2" fill="%s" opacity=".5"/>' % (k, ground + 20, YEL)
                     for k in range(8, W, 46))
    body.append(dashes)
    body.append('<rect y="%d" width="%d" height="1" fill="%s" opacity=".35"/>' % (ground + 40, W, MAG))

    # month labels under the towers they start at
    for m in live.get("months") or []:
        idx = m["week"] - (len(live["weeks"]) - len(weeks))
        if 0 <= idx < len(weeks) - 1:
            body.append(T("micro", m["name"].upper(), x0 + idx * pitch, ground + 48, 2, DIM))

    # the rickshaw
    px = 2
    f0 = sprite(wheel(7.5, 14.5, 4.6, 0), {"W": INK, "s": "#6b7aa8"}, px) + sprite(wheel(27.5, 14.5, 4.6, 0), {"W": INK, "s": "#6b7aa8"}, px)
    f1 = sprite(wheel(7.5, 14.5, 4.6, 1), {"W": INK, "s": "#6b7aa8"}, px) + sprite(wheel(27.5, 14.5, 4.6, 1), {"W": INK, "s": "#6b7aa8"}, px)
    rick = ('<g class="ride"><g transform="translate(0 %d)">%s<g class="wa">%s</g><g class="wb">%s</g>'
            '<rect x="56" y="10" width="3" height="3" fill="%s" class="blink"/></g></g>') % (
        ground - 5, sprite(RICKSHAW, RICK_PAL, px), f0, f1, YEL)
    body.append(rick)
    css.append(".ride{animation:ride 19s linear infinite}@keyframes ride{from{transform:translateX(-90px)}to{transform:translateX(%dpx)}}" % (W + 30))
    css.append(".wa{animation:blink .24s steps(1) infinite}.wb{animation:blink .24s steps(1) infinite;animation-delay:-.12s}"
               "@media (prefers-reduced-motion:reduce){.wb{opacity:0}.ride{transform:translateX(120px)}}")

    # header + readout
    body.append(header(W, "COMMIT CITY", num="02", accent=CYAN))
    lx = W - 48
    body.append(T("micro", "MORE", lx, 13, 2, DIM, anchor="r"))
    lx -= measure("micro", "MORE", 2) + 8
    for lvl in range(4, -1, -1):
        lx -= 12
        body.append('<rect x="%d" y="13" width="10" height="10" fill="%s"/>' % (lx, LEVELS[lvl]))
        lx -= 2
    body.append(T("micro", "LESS", lx - 6, 13, 2, DIM, anchor="r"))

    if live.get("demo"):
        body.append(T("display", "DEMO DATA", 30, 54, 3, YEL))
        body.append(T("micro", "LIVE FEED CONNECTS ON THE FIRST WORKFLOW RUN", 30, 86, 2, SOFT))
    else:
        num = "{:,}".format(int(live.get("total", 0)))
        body.append(T("display", num, 30, 54, 3, YEL))
        body.append(T("micro", "CONTRIBUTIONS IN THE LAST YEAR", 30 + measure("display", num, 3) + 12, 62, 2, SOFT))
        body.append(T("micro", "ONE TOWER PER WEEK / ONE WINDOW PER DAY", 30, 86, 2, DIM))
    label = "Commit City: a pixel skyline of the last year of contributions, one tower per week and one window per day"
    if not live.get("demo"):
        label += ". Total: %s contributions" % live.get("total", 0)
    return svg_doc(W, H, "".join(body), "".join(css), defs, label, sweep=False)


# ----------------------------------------------------------- character sheet

HERO_SPRITE = [
    "....KKKKKKKK....",
    "...KHHHHHHHHK...",
    "..KHHHHHHHHHHK..",
    "..KHHhhhhhhHHK..",
    ".KHHhKKKKKKhHHK.",
    ".KHHKVVVVVVKHHK.",
    ".KHHKVVVVVVKHHK.",
    ".KHHhKKKKKKhHHK.",
    "..KHHhhhhhhHHK..",
    "..KKHHHHHHHHKK..",
    ".KCCMMMMMMMMCCK.",
    "KCCCCCCCCCCCCCCK",
    "KCCcCCCCCCCCcCCK",
    "KCCcKLLLLLLKcCCK",
    "KCCcKLGGGGLKcCCK",
    ".KCCKLGGGGLKCCK.",
    ".KCCKLLLLLLKCCK.",
    "..KCCCCCCCCCCK..",
    "..KBBK....KBBK..",
    "..KKKK....KKKK..",
]
HERO_PAL = {"K": "#04040b", "H": "#6a48e8", "h": "#3d2a96", "V": CYAN, "M": MAG, "C": "#2b3266",
            "c": "#1b2048", "L": "#9aa7c7", "G": GRN, "B": "#11142c"}

TROPHY = ["YYYYYYY", "Y.YYY.Y", ".YYYYY.", "..YYY..", "...Y...", "..YYY.."]


def chip(label, x, y, colour, sc=2, pad=8, icon=None):
    w = measure("micro", label, sc) + pad * 2 + (18 if icon else 0)
    out = ['<rect x="%s" y="%s" width="%s" height="24" fill="%s" opacity=".1"/>' % (fmt(x), fmt(y), fmt(w), colour),
           '<path d="M%s %sh%sv24h-%sz" fill="none" stroke="%s" stroke-opacity=".75"/>' % (
               fmt(x + .5), fmt(y + .5), fmt(w - 1), fmt(w - 1), colour)]
    tx = x + pad
    if icon:
        out.append(sprite(icon, {"Y": colour}, 2, tx - 1, y + 6))
        tx += 18
    out.append(T("micro", label, tx, y + 7, sc, colour))
    return "".join(out), w


def build_sheet(live):
    H = 404
    body, css = [], []
    c = CFG
    body.append(header(W, "CHARACTER SHEET", "PLAYER 1", num="01", accent=MAG))

    # portrait card
    cx, cy, cw_, ch_ = 30, 58, 208, 316
    body.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#0c0d1e"/>' % (cx, cy, cw_, ch_))
    body.append('<path d="M%d.5 %d.5h%dv%dh-%dz" fill="none" stroke="%s" stroke-opacity=".8"/>' % (cx, cy, cw_ - 1, ch_ - 1, cw_ - 1, DIM2))
    defs = ('<radialGradient id="aura" cx=".5" cy=".55" r=".5"><stop offset="0" stop-color="%s" stop-opacity=".35"/>'
            '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient>') % (VIO, VIO)
    body.append('<rect x="%d" y="%d" width="%d" height="190" fill="url(#aura)"/>' % (cx, cy + 6, cw_))
    px = 8
    sx, sy = cx + (cw_ - 16 * px) / 2.0, cy + 22
    body.append('<g class="bob">%s<rect class="visor" x="%s" y="%s" width="%d" height="%d" fill="#fff" opacity="0"/>'
                '<rect class="scr2" x="%s" y="%s" width="%d" height="%d" fill="#fff" opacity="0"/></g>' % (
                    sprite(HERO_SPRITE, HERO_PAL, px, sx, sy),
                    fmt(sx + 5 * px), fmt(sy + 5 * px), 6 * px, 2 * px,
                    fmt(sx + 6 * px), fmt(sy + 14 * px), px, px))
    css.append(".bob{animation:bob 1.4s steps(2) infinite}@keyframes bob{50%{transform:translateY(4px)}}"
               ".visor{animation:visor 5s steps(1) infinite}@keyframes visor{0%{opacity:0}92%{opacity:.85}94%{opacity:0}96%{opacity:.85}98%{opacity:0}}"
               ".scr2{animation:scr2 .8s steps(4) infinite}@keyframes scr2{0%{opacity:.7;transform:translateX(0)}"
               "100%{opacity:.7;transform:translateX(" + str(3 * px) + "px)}}")
    body.append('<rect x="%s" y="%s" width="%d" height="5" fill="#000" opacity=".5"/>' % (fmt(sx + px), fmt(sy + 20 * px + 4), 14 * px))

    counters = live.get("counters") or {}
    lv = counters.get("public_repos")
    if lv is not None:   # level = public repositories
        body.append(T("display", "LV %s" % lv, cx + cw_ - 12, cy + 12, 1.5, YEL, anchor="r"))
    first = c["name"].split()[0]
    ny = sy + 20 * px + 22
    body.append(T("display", first, cx + cw_ / 2.0, ny, 2, INK, anchor="c"))
    by = ny + 30
    for k, (lab, colour, cls) in enumerate([("HP", GRN, ""), ("MP", CYAN, "mp")]):
        yy = by + k * 18
        body.append(T("micro", lab, cx + 16, yy, 2, colour))
        for seg in range(13):
            extra = ' class="mp" style="animation-delay:-%ss"' % fmt(2.6 - seg * 0.2) if cls else ""
            body.append('<rect x="%d" y="%d" width="9" height="10" fill="%s"%s/>' % (cx + 46 + seg * 11, yy, colour, extra))
    css.append(".mp{animation:mp 2.6s steps(1) infinite}@keyframes mp{0%{opacity:1}70%{opacity:.18}100%{opacity:.18}}")
    yy = by + 42
    for key, lab in (("public_repos", "REPOS"), ("followers", "FOLLOWERS")):
        if counters.get(key) is not None:
            body.append(T("micro", lab, cx + 16, yy, 2, DIM))
            body.append(T("micro", str(counters[key]), cx + cw_ - 16, yy, 2, SOFT, anchor="r"))
            yy += 16

    # attributes
    rx = 268
    rows = [("CLASS", c["sheet"]["class"], INK), ("ORIGIN", c["sheet"]["origin"], INK),
            ("QUEST", c["sheet"]["quest"], CYAN), ("STATUS", c["sheet"]["status"], YEL)]
    t = 0.3
    for k, (key, val, colour) in enumerate(rows):
        y = 64 + k * 30
        dots = "." * (9 - len(key))
        svg, t, ex = typed("term", [(key + " ", MAG), (dots + " ", DIM2), (val, colour)], rx, y, 1.5, t, cps=120)
        body.append(svg)
        t += 0.1
        if key == "STATUS":
            body.append('<rect class="blink" x="%s" y="%d" width="11" height="18" fill="%s"/>' % (fmt(ex + 6), y - 2, YEL))

    # loadout
    ly = 196
    body.append(T("display", "LOADOUT", rx, ly, 1.5, MAG))
    body.append('<rect x="%s" y="%d" width="%s" height="1" fill="%s" opacity=".35"/>' % (
        fmt(rx + measure("display", "LOADOUT", 1.5) + 12), ly + 6, fmt(W - 30 - rx - measure("display", "LOADOUT", 1.5) - 12), MAG))
    yy = ly + 24
    colours = [CYAN, VIO, GRN, YEL]
    n = 0
    for k, (group, items) in enumerate(c["loadout"].items()):
        body.append(T("micro", group, rx, yy + 7, 2, DIM))
        x = rx + 64
        for item in items:
            svg, w = chip(item, x, yy, colours[k % 4])
            body.append('<g class="pop" style="animation-delay:%ss">%s</g>' % (fmt(1.6 + n * 0.07), svg))
            x += w + 8
            n += 1
        yy += 31
    css.append(".pop{animation:ty .01s steps(1) both}")

    # trophies
    ty_ = yy + 8
    body.append(T("display", "TROPHIES", rx, ty_, 1.5, YEL))
    body.append('<rect x="%s" y="%d" width="%s" height="1" fill="%s" opacity=".35"/>' % (
        fmt(rx + measure("display", "TROPHIES", 1.5) + 12), ty_ + 6, fmt(W - 30 - rx - measure("display", "TROPHIES", 1.5) - 12), YEL))
    x = rx
    for item in c["trophies"]:
        svg, w = chip(item, x, ty_ + 24, YEL, icon=TROPHY)
        body.append(svg)
        x += w + 8
    label = "Character sheet. Class: %s. Origin: %s. Current quest: %s. Loadout: %s" % (
        c["sheet"]["class"], c["sheet"]["origin"], c["sheet"]["quest"],
        ", ".join(i for g in c["loadout"].values() for i in g))
    return svg_doc(W, H, "".join(body), "".join(css), defs, label, accent=MAG)


# ----------------------------------------------------------------- quest log

def build_quest_header():
    H = 46
    body = header(W, "QUEST LOG", "SELECT A QUEST TO OPEN IT", num="03", accent=YEL)
    return svg_doc(W, H, body, "", "", "Quest log: featured projects", cut=12, accent=YEL, sweep=False)


def build_quest(i, q, total):
    H = 78
    body, css = [], []
    slot = 1.6
    period = slot * total
    body.append('<rect class="sel" width="%d" height="%d" fill="%s"/>' % (W, H, YEL))
    css.append(".sel{opacity:0;animation:sel %ss steps(1) infinite;animation-delay:%ss}"
               "@keyframes sel{0%%{opacity:.09}%s%%,100%%{opacity:0}}" % (fmt(period), fmt(i * slot), fmt(100.0 / total)))
    css.append(".cur{opacity:.0;animation:cur %ss steps(1) infinite;animation-delay:%ss}"
               "@keyframes cur{0%%{opacity:1}%s%%,100%%{opacity:0}}" % (fmt(period), fmt(i * slot), fmt(100.0 / total)))
    body.append(T("display", "%02d" % (i + 1), 30, 18, 2, DIM))
    body.append('<path class="cur" d="M74 18v16l12-8z" fill="%s"/>' % YEL)
    body.append(T("display", q["title"], 98, 16, 2, INK))
    body.append(T("term", q["desc"], 98, 47, 1, SOFT))
    x = W - 64
    for tag in reversed(q.get("tags", [])):
        w = measure("micro", tag, 2) + 16
        x -= w
        svg, _ = chip(tag, x, 12, CYAN)
        body.append(svg)
        x -= 8
    body.append('<g class="go">%s</g>' % T("display", ">>", W - 30, 46, 1.5, MAG, anchor="r"))
    css.append(".go{animation:go 1s steps(2) infinite}@keyframes go{50%{transform:translateX(4px)}}")
    body.append(T("micro", "OPEN", W - 30 - 34, 47, 2, DIM, anchor="r"))
    label = "%s: %s" % (q["title"], q["desc"])
    return svg_doc(W, H, "".join(body), "".join(css), "", label, cut=12, accent=DIM, sweep=False)


# --------------------------------------------------------- links and footer

def build_button(link):
    w, h = 300, 60
    colour = NAMED.get(link.get("color"), CYAN)
    body = ['<rect width="%d" height="%d" fill="%s" opacity=".1"/>' % (w, h, colour),
            '<rect class="shine" x="-80" width="60" height="%d" fill="#fff" opacity=".12" transform="skewX(-20)"/>' % h,
            T("display", "[", 24, 22, 2, DIM), T("display", "]", w - 24, 22, 2, DIM, anchor="r"),
            T("display", link["label"], w / 2.0, 22, 2, colour, anchor="c")]
    css = ".shine{animation:shine 4s linear infinite}@keyframes shine{0%{transform:translateX(0) skewX(-20deg)}30%,100%{transform:translateX(460px) skewX(-20deg)}}"
    return svg_doc(w, h, "".join(body), css, "", link["label"], cut=12, accent=colour, sweep=False)


def build_footer():
    H = 76
    body, css = [], []
    rnd = random.Random(3)
    wave = []
    for x in range(0, W, 6):
        hgt = 4 + int(10 * abs(math.sin(x / 37.0)) + rnd.random() * 6)
        wave.append('<rect class="wv" x="%d" y="%d" width="4" height="%d" fill="%s" opacity=".35" style="animation-delay:-%ss"/>' % (
            x, H - hgt, hgt, CYAN if (x // 6) % 7 else MAG, fmt((x / 6) * 0.06 % 1.8)))
    body.append("".join(wave))
    css.append(".wv{transform-box:fill-box;transform-origin:50% 100%;animation:wv 1.8s steps(6) infinite alternate}"
               "@keyframes wv{from{transform:scaleY(.3)}to{transform:scaleY(1.25)}}")
    svg, t, ex = typed("display", [("END OF TRANSMISSION", INK)], 30, 18, 2, 0.4, cps=30)
    body.append(svg)
    body.append('<rect class="blink" x="%s" y="16" width="14" height="18" fill="%s"/>' % (fmt(ex + 8), YEL))
    body.append(T("micro", "HAND-BUILT SVG  //  NO WIDGETS", W - 30, 21, 2, DIM, anchor="r"))
    return svg_doc(W, H, "".join(body), "".join(css), "", "End of transmission", cut=12, accent=DIM, sweep=False)


def sync_readme():
    """Rewrites the quest and link blocks of README.md from profile.json.
    Everything outside the marker comments is left alone."""
    path = os.path.join(ROOT, "README.md")
    if not os.path.exists(path):
        return
    text = open(path).read()
    login = CFG["login"]
    quests = "\n".join(
        '<a href="https://github.com/%s/%s"><img src="assets/quest-%d.svg" width="100%%" alt="%s: %s"></a>' % (
            login, q["repo"], i + 1, q["title"], q["desc"].replace('"', "&quot;"))
        for i, q in enumerate(CFG["quests"]))
    links = "\n".join(
        '<a href="%s"><img src="assets/btn-%s.svg" width="30%%" alt="%s"></a>' % (l["url"], l["id"], l["label"])
        for l in CFG["links"])
    for name, block in (("quests", quests), ("links", links)):
        start, end = "<!-- %s:start -->" % name, "<!-- %s:end -->" % name
        if start in text and end in text:
            head, rest = text.split(start, 1)
            text = head + start + "\n" + block + "\n" + end + rest.split(end, 1)[1]
    with open(path, "w") as f:
        f.write(text)


def main():
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    live = load_live()
    sizes = {
        "hero.svg": write("hero.svg", build_hero()),
        "sheet.svg": write("sheet.svg", build_sheet(live)),
        "city.svg": write("city.svg", build_city(live)),
        "quest-log.svg": write("quest-log.svg", build_quest_header()),
        "footer.svg": write("footer.svg", build_footer()),
    }
    quests = CFG["quests"]
    for i, q in enumerate(quests):
        sizes["quest-%d.svg" % (i + 1)] = write("quest-%d.svg" % (i + 1), build_quest(i, q, len(quests)))
    for link in CFG["links"]:
        sizes["btn-%s.svg" % link["id"]] = write("btn-%s.svg" % link["id"], build_button(link))
    sync_readme()
    for name, size in sizes.items():
        print("%-18s %6.1f KB" % (name, size / 1024.0))


if __name__ == "__main__":
    main()
