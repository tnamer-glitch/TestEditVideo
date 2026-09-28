"""Edit klip UGC gaya "Vox" (explainer kolaj): latar kertas, kad foto,
tajuk serif dengan sapuan highlighter kuning, bulatan marker merah,
punch-in zoom, grain filem dan bunyi 'whoosh'.

Guna:  python3 edit_vox.py [vox_config.json]
"""
import json
import math
import os
import subprocess
import sys
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
FF = imageio_ffmpeg.get_ffmpeg_exe()

SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
HAND = "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf"

PAPER = (243, 237, 224)
INK = (22, 22, 22)
YELLOW = (255, 221, 0)
RED = (226, 45, 38)

# Kad video
CARD_W, CARD_H, BORDER = 740, 1316, 14
CARD_CX, CARD_CY = W // 2, 1040
CARD_ROT = -1.2


# ---------------------------------------------------------------- utils
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


_fonts = {}


def font(path, size):
    if (path, size) not in _fonts:
        _fonts[(path, size)] = ImageFont.truetype(path, size)
    return _fonts[(path, size)]


def probe_duration(path):
    out = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    h, m, s = out.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def make_paper(seed=3):
    rng = np.random.default_rng(seed)
    base = np.ones((H, W, 3)) * np.array(PAPER)
    low = Image.fromarray((rng.random((48, 27)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    base += (np.asarray(low, float)[..., None] / 255 - 0.5) * 14
    base += rng.normal(0, 4, (H, W, 1))
    # vignette
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)
    base *= (1 - 0.18 * clamp_arr(d - 0.25))[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    # garis halus gaya kertas nota
    d2 = ImageDraw.Draw(img)
    for y in range(0, H, 64):
        d2.line((0, y, W, y), fill=(210, 200, 185, 255), width=1)
    return img


def clamp_arr(a):
    return np.clip(a, 0, 1)


def make_grain(n=6, seed=9):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        g = rng.normal(128, 40, (H // 2, W // 2)).clip(0, 255).astype(np.uint8)
        g = Image.fromarray(g).resize((W, H), Image.NEAREST)
        a = Image.new("L", (W, H), 20)
        out.append(Image.merge("RGBA", (g, g, g, a)))
    return out


def rough_rect(d, box, fill, seed):
    """Segi empat bertepi kasar (macam sapuan marker)."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = box
    pts = []
    n = max(4, int((x1 - x0) / 40))
    for i in range(n + 1):
        pts.append((x0 + (x1 - x0) * i / n, y0 + rng.uniform(-5, 5)))
    for i in range(n + 1):
        pts.append((x1 - (x1 - x0) * i / n, y1 + rng.uniform(-5, 5)))
    d.polygon(pts, fill=fill)


# ---------------------------------------------------------------- elemen teks
def kicker(frame, text, t, start, y=150):
    """Label kecil huruf besar + garis merah (gaya bab Vox)."""
    p = ease((t - start) / 0.4)
    if p <= 0:
        return
    f = font(SANS_B, 34)
    spaced = " ".join(text.upper())
    tw = f.getlength(spaced)
    x0 = (W - tw) / 2
    d = ImageDraw.Draw(frame)
    d.line((x0, y + 52, x0 + tw * p, y + 52), fill=RED, width=6)
    col = INK + (int(255 * p),)
    d.text((x0, y), spaced, font=f, fill=col)


def headline(frame, lines, t, start, y=215, size=74, hl_idx=None, seed=1):
    """Tajuk serif; baris hl_idx dapat sapuan highlighter animasi."""
    f = font(SERIF_B, size)
    d = ImageDraw.Draw(frame)
    lh = int(size * 1.25)
    for i, ln in enumerate(lines):
        st = start + i * 0.25
        p = ease((t - st) / 0.35)
        if p <= 0:
            continue
        tw = f.getlength(ln)
        x = (W - tw) / 2
        yy = y + i * lh + int((1 - p) * 20)
        if hl_idx is not None and i in (hl_idx if isinstance(hl_idx, (list, tuple)) else [hl_idx]):
            hp = ease((t - st - 0.15) / 0.4)
            if hp > 0:
                rough_rect(d, (x - 18, yy + size * 0.18, x - 18 + (tw + 36) * hp, yy + size * 1.12), YELLOW + (255,), seed + i)
        d.text((x, yy), ln, font=f, fill=INK + (int(255 * p),))


def sticky(frame, text, t, start, end, cx, cy, rot=4, w=430):
    if not (start <= t < end):
        return
    p = ease((t - start) / 0.3)
    f = font(HAND, 46)
    words, lines, cur = text.split(), [], ""
    for wd in words:
        tr = (cur + " " + wd).strip()
        if f.getlength(tr) <= w - 60 or not cur:
            cur = tr
        else:
            lines.append(cur)
            cur = wd
    lines.append(cur)
    h = 60 + len(lines) * 56
    note = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", note.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((26, 30, w + 26, h + 30), fill=(0, 0, 0, 90))
    note.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(note)
    d.rectangle((16, 16, w + 16, h + 16), fill=(255, 236, 110, 255))
    d.rectangle((w / 2 - 50, 6, w / 2 + 70, 34), fill=(255, 255, 255, 150))  # pita
    for i, ln in enumerate(lines):
        d.text((46, 44 + i * 56), ln, font=f, fill=INK)
    sc = 0.6 + 0.4 * p
    note = note.rotate(rot, expand=True, resample=Image.BICUBIC)
    note = note.resize((int(note.width * sc), int(note.height * sc)), Image.LANCZOS)
    a = min(p, clamp((end - t) / 0.2))
    note.putalpha(note.getchannel("A").point(lambda v: int(v * a)))
    frame.alpha_composite(note, (int(cx - note.width / 2), int(cy - note.height / 2)))


def marker_circle(frame, cx, cy, rx, ry, t, start, end):
    if not (start <= t < end):
        return
    p = ease_io((t - start) / 0.5)
    d = ImageDraw.Draw(frame)
    pts = []
    total = 2 * math.pi * 1.12 * p
    steps = max(2, int(80 * p))
    for i in range(steps + 1):
        a = -2.2 + total * i / steps
        wob = 1 + 0.04 * math.sin(a * 3)
        pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a)))
    d.line(pts, fill=RED + (255,), width=10, joint="curve")


def arrow_label(frame, text, x0, y0, x1, y1, t, start, end):
    """Anak panah marker dari label (x0,y0) ke sasaran (x1,y1)."""
    if not (start <= t < end):
        return
    p = ease((t - start) / 0.4)
    d = ImageDraw.Draw(frame)
    xe, ye = x0 + (x1 - x0) * p, y0 + (y1 - y0) * p
    # lengkung sedikit
    mx, my = (x0 + xe) / 2 + 40, (y0 + ye) / 2 + 30
    pts = [((1 - s) ** 2 * x0 + 2 * (1 - s) * s * mx + s * s * xe,
            (1 - s) ** 2 * y0 + 2 * (1 - s) * s * my + s * s * ye) for s in np.linspace(0, 1, 30)]
    d.line(pts, fill=RED + (255,), width=8, joint="curve")
    if p > 0.95:
        ang = math.atan2(ye - pts[-4][1], xe - pts[-4][0])
        for da in (2.6, -2.6):
            d.line((xe, ye, xe + 40 * math.cos(ang + da), ye + 40 * math.sin(ang + da)), fill=RED + (255,), width=8)
    f = font(HAND, 50)
    tw = f.getlength(text)
    lp = ease((t - start - 0.25) / 0.3)
    if lp > 0:
        bx = min(max(20, x0 - tw / 2), W - tw - 40)
        rough_rect(d, (bx - 14, y0 + 8, bx + tw + 14, y0 + 72), (255, 255, 255, int(235 * lp)), 7)
        d.text((bx, y0 + 12), text, font=f, fill=RED + (int(255 * lp),))


def stamp(frame, text, cx, cy, t, start, end, rot=-12):
    if not (start <= t < end):
        return
    p = (t - start) / 0.25
    if p <= 0:
        return
    sc = 1.8 - 0.8 * ease(p)
    f = font(SANS_B, 40)
    tw = int(f.getlength(text))
    lyr = Image.new("RGBA", (tw + 60, 100), (0, 0, 0, 0))
    d = ImageDraw.Draw(lyr)
    d.rounded_rectangle((6, 6, tw + 54, 94), radius=14, outline=RED + (255,), width=7)
    d.text((30, 24), text, font=f, fill=RED + (255,))
    lyr = lyr.rotate(rot, expand=True, resample=Image.BICUBIC)
    lyr = lyr.resize((int(lyr.width * sc), int(lyr.height * sc)), Image.LANCZOS)
    a = clamp(p) * clamp((end - t) / 0.2) * 0.92
    lyr.putalpha(lyr.getchannel("A").point(lambda v: int(v * a)))
    frame.alpha_composite(lyr, (int(cx - lyr.width / 2), int(cy - lyr.height / 2)))


def strips(frame, items, t, start, end, y0=1180):
    """Senarai bernombor atas jalur kertas koyak."""
    if not (start <= t < end):
        return
    fa = clamp((end - t) / 0.2)
    fnum, ftxt = font(SERIF_B, 58), font(SERIF_B, 48)
    for i, it in enumerate(items):
        p = ease((t - start - i * 0.7) / 0.35)
        if p <= 0:
            continue
        num = f"{i + 1:02d}"
        tw = ftxt.getlength(it) + fnum.getlength(num) + 110
        lyr = Image.new("RGBA", (int(tw) + 60, 130), (0, 0, 0, 0))
        d = ImageDraw.Draw(lyr)
        rough_rect(d, (20, 22, tw + 30, 112), (0, 0, 0, 70), 20 + i)
        rough_rect(d, (10, 10, tw + 20, 100), (252, 250, 244, 255), 30 + i)
        d.text((34, 20), num, font=fnum, fill=RED)
        d.text((34 + fnum.getlength(num) + 30, 30), it, font=ftxt, fill=INK)
        lyr = lyr.rotate((-1.5, 1.2, -0.8)[i % 3], expand=True, resample=Image.BICUBIC)
        lyr.putalpha(lyr.getchannel("A").point(lambda v: int(v * p * fa)))
        x = int(90 + (1 - p) * -300) if i % 2 == 0 else int(W - lyr.width - 90 + (1 - p) * 300)
        frame.alpha_composite(lyr, (x, y0 + i * 150))


# ---------------------------------------------------------------- kad video
def card_shadow():
    cw, ch = CARD_W + 2 * BORDER, CARD_H + 2 * BORDER
    sh = Image.new("RGBA", (cw + 120, ch + 120), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((70, 76, cw + 60, ch + 66), fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    return sh.rotate(CARD_ROT, expand=True, resample=Image.BICUBIC)


def zoom_at(t, zooms):
    """Pulangkan (zoom, px, py) untuk masa t berdasarkan senarai punch-in."""
    z, px, py = 1.0 + 0.05 * t / 17, 0.5, 0.42
    for zm in zooms:
        s, e, amt = zm["start"], zm["end"], zm["zoom"]
        if s <= t < e + 0.4:
            k = ease((t - s) / 0.35) if t < e else 1 - ease_io((t - e) / 0.4)
            z = z + (amt - z) * k
            px, py = zm["x"], zm["y"]
    return z, px, py


def card_frame(src, t, zooms):
    z, px, py = zoom_at(t, zooms)
    cw, chh = W / z, H / z
    left, top = px * (W - cw), py * (H - chh)
    img = src.crop((int(left), int(top), int(left + cw), int(top + chh))).resize((CARD_W, CARD_H), Image.BILINEAR)
    card = Image.new("RGBA", (CARD_W + 2 * BORDER, CARD_H + 2 * BORDER), (252, 251, 247, 255))
    card.paste(img, (BORDER, BORDER))
    return card.rotate(CARD_ROT, expand=True, resample=Image.BICUBIC)


def card_to_screen(nx, ny):
    """Titik ternormal dalam video (selepas zoom tetap di px,py) -> koordinat skrin."""
    x = CARD_CX - CARD_W / 2 + nx * CARD_W
    y = CARD_CY - CARD_H / 2 + ny * CARD_H
    a = math.radians(-CARD_ROT)
    dx, dy = x - CARD_CX, y - CARD_CY
    return CARD_CX + dx * math.cos(a) - dy * math.sin(a), CARD_CY + dx * math.sin(a) + dy * math.cos(a)


# ---------------------------------------------------------------- babak
def draw_beats(frame, cfg, t):
    for b in cfg["beats"]:
        if not (b["start"] <= t < b["end"]):
            continue
        # kicker & headline pudar keluar hujung babak
        layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        kicker(layer, b["kicker"], t, b["start"])
        headline(layer, b["headline"], t, b["start"] + 0.15, hl_idx=b.get("highlight"), seed=int(b["start"] * 10))
        fo = clamp((b["end"] - t) / 0.2)
        if fo < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * fo)))
        frame.alpha_composite(layer)
    for n in cfg.get("stickies", []):
        sticky(frame, n["text"], t, n["start"], n["end"], n["x"], n["y"], n.get("rot", 4))
    for c in cfg.get("circles", []):
        cx, cy = card_to_screen(c["x"], c["y"])
        marker_circle(frame, cx, cy, c["rx"], c["ry"], t, c["start"], c["end"])
    for a in cfg.get("arrows", []):
        tx, ty = card_to_screen(a["to_x"], a["to_y"])
        arrow_label(frame, a["text"], a["from_x"], a["from_y"], tx, ty, t, a["start"], a["end"])
    for s in cfg.get("stamps", []):
        stamp(frame, s["text"], s["x"], s["y"], t, s["start"], s["end"])
    for l in cfg.get("lists", []):
        strips(frame, l["items"], t, l["start"], l["end"], l.get("y", 1180))


def end_card(paper, ec, t):
    f = paper.copy()
    d = ImageDraw.Draw(f)
    kicker(f, ec["kicker"], t, 0.0, y=560)
    headline(f, [ec["product_name"]], t, 0.1, y=640, size=110)
    headline(f, ec["lines"], t, 0.5, y=830, size=66, hl_idx=len(ec["lines"]) - 1, seed=77)
    p = ease((t - 1.1) / 0.3)
    if p > 0:
        fb = font(SANS_B, 58)
        tw = fb.getlength(ec["button"])
        sc = 1 + 0.035 * math.sin(max(0, t - 1.4) * 6)
        bw, bh = (tw + 110) * sc, 130 * sc
        x0, y0 = (W - bw) / 2, 1110 + (1 - p) * 40
        d.rectangle((x0 + 10, y0 + 12, x0 + bw + 10, y0 + bh + 12), fill=(0, 0, 0, int(90 * p)))
        d.rectangle((x0, y0, x0 + bw, y0 + bh), fill=INK + (int(255 * p),))
        d.text((x0 + (bw - tw) / 2, y0 + (bh - 70) / 2), ec["button"], font=fb, fill=YELLOW + (int(255 * p),))
    np_ = ease((t - 1.5) / 0.3)
    if np_ > 0:
        fn = font(HAND, 48)
        tw = fn.getlength(ec["note"])
        d.text(((W - tw) / 2, 1300), ec["note"], font=fn, fill=RED + (int(255 * np_),))
    return f


def comment_card(name, text, likes, seed):
    """Kad komen gaya media sosial (nama dipendekkan untuk privasi)."""
    fn, ft, fs = font(SANS_B, 38), font(SANS, 42), font(SANS_B, 30)
    words, lines, cur = text.split(), [], ""
    for wd in words:
        tr = (cur + " " + wd).strip()
        if ft.getlength(tr) <= 640 or not cur:
            cur = tr
        else:
            lines.append(cur)
            cur = wd
    lines.append(cur)
    bw = int(max(fn.getlength(name), max(ft.getlength(l) for l in lines))) + 70
    bh = 80 + len(lines) * 54
    cw, ch = bw + 150, bh + 80
    lyr = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(lyr)
    rough_rect(d, (8, 8, cw - 8, ch - 8), (0, 0, 0, 50), seed)
    d.rectangle((0, 0, cw - 16, ch - 16), fill=(255, 255, 255, 255))
    hue = [(233, 120, 150), (120, 150, 220), (240, 170, 80), (130, 190, 140)][seed % 4]
    d.ellipse((20, 22, 104, 106), fill=hue)
    ini = name[0].upper()
    d.text((62 - font(SANS_B, 44).getlength(ini) / 2, 36), ini, font=font(SANS_B, 44), fill=WHITE_T)
    d.rounded_rectangle((122, 16, 122 + bw, 16 + bh), radius=34, fill=(240, 242, 245))
    d.text((150, 30), name, font=fn, fill=INK)
    for i, ln in enumerate(lines):
        d.text((150, 80 + i * 54), ln, font=ft, fill=(40, 40, 40))
    d.text((150, bh + 26), "Suka    Balas", font=fs, fill=(101, 103, 107))
    if likes:
        lx = 122 + bw - 70
        d.ellipse((lx, bh + 24, lx + 36, bh + 60), fill=(24, 119, 242))
        d.text((lx + 44, bh + 26), str(likes), font=fs, fill=(101, 103, 107))
    return lyr


WHITE_T = (255, 255, 255)


def testimonial_section(paper, ts, t):
    f = paper.copy()
    kicker(f, ts["kicker"], t, 0.0)
    headline(f, ts["headline"], t, 0.15, hl_idx=ts.get("highlight"), seed=55)
    y = 560
    for i, c in enumerate(ts["comments"]):
        st = 0.6 + i * 0.7
        p = ease((t - st) / 0.35)
        card = comment_card(c["name"], c["text"], c.get("likes", 1), i)
        if p > 0:
            rot = (-1.5, 1.2, -0.8, 1.0)[i % 4]
            lyr = card.rotate(rot, expand=True, resample=Image.BICUBIC)
            lyr.putalpha(lyr.getchannel("A").point(lambda v: int(v * p)))
            x = (W - lyr.width) // 2 + int((1 - p) * (220 if i % 2 else -220))
            f.alpha_composite(lyr, (x, y))
            if c.get("circle"):
                cx, cy = W / 2, y + lyr.height / 2
                marker_circle(f, cx, cy, lyr.width / 2 + 30, lyr.height / 2 + 34, t, st + 0.5, 99)
        y += card.height + 60
    if ts.get("stamp"):
        stamp(f, ts["stamp"], W // 2, min(y + 70, 1660), t, 0.6 + len(ts["comments"]) * 0.7, 99, rot=-6)
    return f


_photos = {}


def proof_section(paper, pf, t):
    """Gambar testimoni sebagai foto kolaj + nota sticky."""
    f = paper.copy()
    kicker(f, pf["kicker"], t, 0.0)
    headline(f, pf["headline"], t, 0.15, hl_idx=pf.get("highlight"), seed=66)
    if pf["image"] not in _photos:
        sz = 860
        img = Image.open(pf["image"]).convert("RGBA").resize((sz, sz), Image.LANCZOS)
        card = Image.new("RGBA", (sz + 36, sz + 36), (252, 251, 247, 255))
        card.paste(img, (18, 18))
        sh = Image.new("RGBA", (sz + 140, sz + 140), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle((60, 70, sz + 96, sz + 106), fill=(0, 0, 0, 120))
        sh = sh.filter(ImageFilter.GaussianBlur(20)).rotate(1.8, expand=True, resample=Image.BICUBIC)
        _photos[pf["image"]] = (card.rotate(1.8, expand=True, resample=Image.BICUBIC), sh)
    card, sh = _photos[pf["image"]]
    p = ease((t - 0.3) / 0.45)
    if p > 0:
        sc = 1.08 - 0.08 * p
        c2 = card.resize((int(card.width * sc), int(card.height * sc)), Image.BILINEAR)
        c2.putalpha(c2.getchannel("A").point(lambda v: int(v * p)))
        cy = 960
        f.alpha_composite(sh, ((W - sh.width) // 2 + 8, cy - sh.height // 2 + 14))
        f.alpha_composite(c2, ((W - c2.width) // 2, cy - c2.height // 2))
    for n in pf.get("notes", []):
        sticky(f, n["text"], t, n["start"], 99, n["x"], n["y"], n.get("rot", -4), n.get("w", 430))
    return f


def swipe_in(prev, new, t, dur=0.3):
    if t >= dur or prev is None:
        return new
    off = int(W * (1 - ease(t / dur)))
    base = prev.copy()
    base.alpha_composite(new.crop((0, 0, W - off, H)), (off, 0))
    return base


def disclaimer(frame, text):
    f = font(SANS, 26)
    tw = f.getlength(text)
    if tw > W - 80:
        mid = len(text) // 2
        cut = text.rfind(" ", 0, mid + 10)
        lines = [text[:cut], text[cut + 1:]]
    else:
        lines = [text]
    d = ImageDraw.Draw(frame)
    for i, ln in enumerate(lines):
        lw = f.getlength(ln)
        d.text(((W - lw) / 2, H - 100 + i * 34), ln, font=f, fill=(90, 84, 76, 255))


# ---------------------------------------------------------------- audio
def whoosh_track(times, total, path, sr=44100):
    rng = np.random.default_rng(5)
    out = np.zeros(int(total * sr) + sr)
    L = int(0.28 * sr)
    for tm in times:
        n = rng.normal(0, 1, L)
        k = np.ones(18) / 18
        n = np.convolve(n, k, "same")
        n = n - np.convolve(n, np.ones(120) / 120, "same")  # buang frekuensi rendah
        env = np.sin(np.linspace(0, math.pi, L)) ** 2
        s = int(tm * sr)
        out[s:s + L] += n * env * 0.35
    out = np.clip(out, -1, 1)
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- main
def main(cfg_path):
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    src, out = cfg["input"], cfg["output"]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    clip_dur = probe_duration(src)
    ec = cfg["end_card"]
    ts = cfg.get("testimonials")
    pf = cfg.get("proof")
    ts_dur = ts["duration"] if ts else 0.0
    pf_dur = pf["duration"] if pf else 0.0
    total = clip_dur + ts_dur + pf_dur + ec["duration"]

    paper = make_paper()
    grain = make_grain()
    shadow = card_shadow()

    vf = ("hflip," if cfg.get("mirror") else "") + f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}"
    dec = subprocess.Popen([FF, "-loglevel", "error", "-i", src, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    tmp_video = out + ".video.mp4"
    enc = subprocess.Popen(
        [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", tmp_video],
        stdin=subprocess.PIPE)

    fsize, i, last = W * H * 3, 0, None
    while True:
        raw = dec.stdout.read(fsize)
        if len(raw) < fsize:
            break
        t = i / FPS
        src_img = Image.frombytes("RGB", (W, H), raw)
        frame = paper.copy()
        card = card_frame(src_img, t, cfg.get("zooms", []))
        # kad masuk dengan sedikit 'drop' pada awal
        p = ease(t / 0.4)
        oy = int((1 - p) * 120)
        frame.alpha_composite(shadow, (CARD_CX - shadow.width // 2 + 6, CARD_CY - shadow.height // 2 + 10 + oy))
        frame.alpha_composite(card, (CARD_CX - card.width // 2, CARD_CY - card.height // 2 + oy))
        draw_beats(frame, cfg, t)
        disclaimer(frame, cfg["disclaimer"])
        frame.alpha_composite(grain[i % len(grain)])
        enc.stdin.write(frame.convert("RGB").tobytes())
        last = frame
        i += 1
        if i % FPS == 0:
            print(f"\rklip {t:.0f}s", end="", flush=True)

    # Seksyen selepas klip: testimoni (jika ada) kemudian end card, masuk dengan 'swipe' kertas
    sections = []
    if ts:
        sections.append((ts["duration"], lambda t: testimonial_section(paper, ts, t)))
    if pf:
        sections.append((pf["duration"], lambda t: proof_section(paper, pf, t)))
    sections.append((ec["duration"], lambda t: end_card(paper, ec, t)))
    for dur, fn in sections:
        prev = last
        for k in range(int(dur * FPS)):
            t = k / FPS
            f = swipe_in(prev, fn(t), t)
            disclaimer(f, cfg["disclaimer"])
            f.alpha_composite(grain[i % len(grain)])
            enc.stdin.write(f.convert("RGB").tobytes())
            last = f
            i += 1
    enc.stdin.close()
    enc.wait()
    dec.wait()

    # SFX whoosh pada setiap kemasukan teks
    times = sorted({b["start"] for b in cfg["beats"]} | {n["start"] for n in cfg.get("stickies", [])}
                   | {l["start"] for l in cfg.get("lists", [])} | {clip_dur, clip_dur + ts_dur, clip_dur + ts_dur + pf_dur}
                   | ({clip_dur + ts_dur + n["start"] for n in pf.get("notes", [])} if pf else set())
                   | ({clip_dur + 0.6 + j * 0.7 for j in range(len(ts["comments"]))} if ts else set()))
    sfx = out + ".sfx.wav"
    whoosh_track(times, total, sfx)
    subprocess.run(
        [FF, "-y", "-loglevel", "error", "-i", tmp_video, "-i", src, "-i", sfx,
         "-filter_complex",
         f"[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100,afade=t=out:st={clip_dur - 0.4}:d=0.4,"
         f"apad=whole_dur={total:.3f}[v];[2:a]aresample=44100,volume=0.5[s];"
         f"[v][s]amix=inputs=2:duration=first:normalize=0[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
         "-t", f"{total:.3f}", "-movflags", "+faststart", out],
        check=True)
    os.remove(tmp_video)
    os.remove(sfx)
    print(f"\nSiap: {out} ({total:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "vox_config.json")
