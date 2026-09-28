"""Jana video iklan 9:16 (1080x1920) untuk produk kurus.

Guna:  python3 make_video.py [config.json] [output.mp4]
Perlu: pip install pillow numpy imageio-ffmpeg
"""
import json
import math
import subprocess
import sys
from functools import lru_cache

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Palet warna
PLUM_TOP, PLUM_BOT = (46, 16, 58), (104, 30, 74)
FRESH_TOP, FRESH_BOT = (255, 244, 236), (255, 214, 206)
PINK = (255, 92, 138)
GOLD = (255, 200, 87)
WHITE = (255, 255, 255)
DARK = (48, 20, 56)
RED = (235, 70, 90)
GREEN = (40, 180, 120)
WA_GREEN = (37, 211, 102)


# ---------------------------------------------------------------- helpers
def ease_out_cubic(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_out_back(x):
    x = min(max(x, 0.0), 1.0)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


@lru_cache(maxsize=None)
def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fnt.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


@lru_cache(maxsize=None)
def text_layer(text, path, size, fill, max_w=940, align="center", shadow=True):
    """Render teks (boleh berbilang baris) ke lapisan RGBA."""
    fnt = font(path, size)
    lines = wrap(text, fnt, max_w)
    line_h = int(size * 1.22)
    widths = [int(fnt.getlength(l)) for l in lines]
    lw, lh = max(widths) + 40, line_h * len(lines) + 40
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
        d = ImageDraw.Draw(sh)
        for i, l in enumerate(lines):
            x = (lw - widths[i]) // 2 if align == "center" else 20
            d.text((x + 4, 24 + i * line_h), l, font=fnt, fill=(0, 0, 0, 110))
        layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(layer)
    for i, l in enumerate(lines):
        x = (lw - widths[i]) // 2 if align == "center" else 20
        d.text((x, 20 + i * line_h), l, font=fnt, fill=fill)
    return layer


def with_alpha(layer, a):
    if a >= 0.999:
        return layer
    out = layer.copy()
    out.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
    return out


def place(frame, layer, cx, cy, t, start, dur=0.5, kind="fade_up", anchor="center"):
    """Letak lapisan pada frame dengan animasi masuk."""
    p = (t - start) / dur
    if p <= 0:
        return
    a = ease_out_cubic(p)
    dx = dy = 0
    scale = 1.0
    if kind == "fade_up":
        dy = int((1 - a) * 60)
    elif kind == "slide_left":
        dx = int((1 - a) * 220)
    elif kind == "pop":
        scale = max(0.01, ease_out_back(p) * 1.0)
    lyr = layer
    if scale != 1.0:
        lyr = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))), Image.LANCZOS)
    lyr = with_alpha(lyr, a)
    x = cx - lyr.width // 2 if anchor == "center" else cx
    y = cy - lyr.height // 2
    frame.alpha_composite(lyr, (int(x + dx), int(y + dy)))


@lru_cache(maxsize=None)
def gradient(top, bot):
    ys = np.linspace(0, 1, H)[:, None, None]
    arr = (np.array(top) * (1 - ys) + np.array(bot) * ys).astype(np.uint8)
    arr = np.repeat(arr, W, axis=1)
    alpha = np.full((H, W, 1), 255, np.uint8)
    return Image.fromarray(np.concatenate([arr, alpha], axis=2), "RGBA")


def bokeh(frame, t, color, seed, n=9):
    rng = np.random.default_rng(seed)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(n):
        bx, by = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.uniform(60, 190)
        sp = rng.uniform(0.2, 0.6)
        x = bx + math.sin(t * sp + i) * 50
        y = (by - t * 40 * sp) % (H + 400) - 200
        d.ellipse((x - r, y - r, x + r, y + r), fill=color + (int(rng.uniform(18, 40)),))
    frame.alpha_composite(layer.filter(ImageFilter.GaussianBlur(30)))


def icon(kind, size=84):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = {"x": RED, "check": GREEN, "star": GOLD}[kind]
    d.ellipse((0, 0, size - 1, size - 1), fill=col + (255,))
    w = max(6, size // 10)
    m = size * 0.3
    if kind == "x":
        d.line((m, m, size - m, size - m), fill=WHITE, width=w)
        d.line((m, size - m, size - m, m), fill=WHITE, width=w)
    elif kind == "check":
        d.line((size * 0.26, size * 0.52, size * 0.43, size * 0.68), fill=WHITE, width=w)
        d.line((size * 0.43, size * 0.68, size * 0.75, size * 0.34), fill=WHITE, width=w)
    else:
        cx = cy = size / 2
        pts = []
        for k in range(10):
            ang = -math.pi / 2 + k * math.pi / 5
            r = size * (0.32 if k % 2 == 0 else 0.14)
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        d.polygon(pts, fill=WHITE)
    return img


def list_item(text, kind, color, card):
    """Kad senarai: ikon + teks."""
    txt = text_layer(text, FONT_BOLD, 50, color, max_w=720, align="left", shadow=False)
    ic = icon(kind)
    cw, ch = 900, max(150, txt.height + 50)
    layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=36, fill=card)
    layer.alpha_composite(ic, (40, (ch - ic.height) // 2))
    layer.alpha_composite(txt, (140, (ch - txt.height) // 2))
    return layer


def product_jar(name):
    """Ilustrasi balang produk ringkas dengan label nama."""
    w, h = 420, 560
    img = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((50, 150, w + 50, h + 60), radius=60, fill=(0, 0, 0, 90))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(20)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((70, 30, w + 10, 150), radius=28, fill=DARK)  # penutup
    d.rounded_rectangle((40, 120, w + 40, h + 40), radius=60, fill=WHITE)  # badan
    d.rounded_rectangle((40, 250, w + 40, 470), radius=0, fill=PINK)  # label
    d.rounded_rectangle((70, 140, 110, 420), radius=20, fill=(255, 255, 255, 140))
    lbl = text_layer(name, FONT_BOLD, 50, WHITE, max_w=w - 80, shadow=False)
    if lbl.width > w:
        lbl = lbl.resize((w, int(lbl.height * w / lbl.width)), Image.LANCZOS)
    img.alpha_composite(lbl, (40 + (w - lbl.width) // 2, 360 - lbl.height // 2))
    return img


def pill(text, bg, fg, size=58, pad_x=70, pad_y=34):
    txt = text_layer(text, FONT_BOLD, size, fg, shadow=False)
    w, h = txt.width + pad_x * 2 - 40, txt.height + pad_y * 2 - 40
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg)
    layer.alpha_composite(txt, ((w - txt.width) // 2, (h - txt.height) // 2))
    return layer


# ---------------------------------------------------------------- scenes
def scene_hook(c, t):
    f = gradient(PLUM_TOP, PLUM_BOT).copy()
    bokeh(f, t, PINK, 1)
    place(f, text_layer(c["hook_small"], FONT_REG, 70, WHITE), W // 2, 760, t, 0.2, 0.6)
    big = text_layer(c["hook_big"], FONT_BOLD, 120, GOLD)
    shake = int(math.sin(t * 40) * 6) if 1.2 < t < 1.6 else 0
    place(f, big, W // 2 + shake, 960, t, 1.0, 0.5, "pop")
    return f


def scene_pain(c, t):
    f = gradient(PLUM_TOP, PLUM_BOT).copy()
    bokeh(f, t, PINK, 2)
    place(f, text_layer(c["pain_title"], FONT_BOLD, 80, WHITE), W // 2, 520, t, 0.1)
    for i, p in enumerate(c["pains"]):
        item = list_item(p, "x", DARK, (255, 255, 255, 235))
        place(f, item, W // 2, 820 + i * 230, t, 0.8 + i * 1.2, 0.5, "slide_left")
    return f


def scene_agitate(c, t):
    f = gradient(PLUM_TOP, PLUM_BOT).copy()
    bokeh(f, t, GOLD, 3)
    place(f, text_layer(c["agitate_big"], FONT_BOLD, 104, WHITE), W // 2, 820, t, 0.1, 0.6, "pop")
    place(f, text_layer(c["agitate_small"], FONT_REG, 58, (255, 225, 235), max_w=880), W // 2, 1080, t, 1.0, 0.6)
    return f


def scene_solution(c, t):
    f = gradient(FRESH_TOP, FRESH_BOT).copy()
    bokeh(f, t, PINK, 4)
    place(f, text_layer("Kenalkan", FONT_REG, 60, DARK, shadow=False), W // 2, 250, t, 0.0, 0.5)
    jar = product_jar(c["product_name"])
    bob = int(math.sin(t * 2.2) * 10)
    place(f, jar, W // 2, 640 + bob, t, 0.3, 0.7, "pop")
    place(f, text_layer(c["tagline"], FONT_BOLD, 62, PINK, shadow=False), W // 2, 1010, t, 1.0)
    for i, b in enumerate(c["benefits"]):
        item = list_item(b, "check", DARK, (255, 255, 255, 230))
        place(f, item, W // 2, 1210 + i * 190, t, 1.7 + i * 0.9, 0.5, "slide_left")
    return f


def scene_desire(c, t):
    f = gradient(FRESH_TOP, FRESH_BOT).copy()
    bokeh(f, t, GOLD, 5)
    place(f, text_layer(c["desire_title"], FONT_BOLD, 96, PINK, shadow=False), W // 2, 560, t, 0.1, 0.6)
    for i, dsr in enumerate(c["desires"]):
        item = list_item(dsr, "star", DARK, (255, 255, 255, 230))
        place(f, item, W // 2, 840 + i * 220, t, 0.8 + i * 1.0, 0.5, "fade_up")
    return f


def scene_cta(c, t):
    f = gradient(PLUM_TOP, PLUM_BOT).copy()
    bokeh(f, t, PINK, 6)
    place(f, text_layer(c["cta_title"], FONT_BOLD, 80, WHITE), W // 2, 640, t, 0.1)
    btn = pill(c["cta_button"], WA_GREEN, WHITE, size=66)
    if t > 1.2:
        s = 1 + 0.05 * math.sin((t - 1.2) * 6)
        btn = btn.resize((int(btn.width * s), int(btn.height * s)), Image.LANCZOS)
    place(f, btn, W // 2, 950, t, 0.6, 0.5, "pop")
    place(f, text_layer(c["whatsapp"], FONT_BOLD, 76, GOLD), W // 2, 1110, t, 1.0)
    place(f, text_layer(c["cta_note"], FONT_REG, 50, (255, 225, 235)), W // 2, 1230, t, 1.4)
    return f


# (fungsi, tempoh saat, tunjuk penafian?)
SCENES = [
    (scene_hook, 3.5, False),
    (scene_pain, 5.5, False),
    (scene_agitate, 4.0, False),
    (scene_solution, 6.5, True),
    (scene_desire, 5.0, True),
    (scene_cta, 5.0, True),
]
XFADE = 0.35


def overlay(f, c, t_global, total, disclaimer):
    d = ImageDraw.Draw(f)
    # bar kemajuan di atas
    d.rounded_rectangle((60, 70, W - 60, 80), radius=5, fill=(255, 255, 255, 70))
    d.rounded_rectangle((60, 70, 60 + int((W - 120) * t_global / total), 80), radius=5, fill=PINK)
    if disclaimer:
        lyr = text_layer(c["disclaimer"], FONT_REG, 28, (120, 90, 120) if f.getpixel((W // 2, H - 60))[0] > 200 else (230, 200, 220), max_w=960, shadow=False)
        f.alpha_composite(lyr, ((W - lyr.width) // 2, H - 60 - lyr.height))


def render(cfg, out):
    total = sum(d for _, d, _ in SCENES)
    n = int(total * FPS)
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-f", "lavfi", "-t", str(total), "-i", "anullsrc=r=44100:cl=stereo",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", "-movflags", "+faststart", out,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    starts, acc = [], 0.0
    for _, d, _ in SCENES:
        starts.append(acc)
        acc += d
    for i in range(n):
        tg = i / FPS
        k = max(j for j, s in enumerate(starts) if s <= tg)
        fn, dur, disc = SCENES[k]
        tl = tg - starts[k]
        frame = fn(cfg, tl)
        rem = dur - tl
        if rem < XFADE and k + 1 < len(SCENES):
            nxt = SCENES[k + 1][0](cfg, 0.0)
            frame = Image.blend(frame, nxt, 1 - rem / XFADE)
        overlay(frame, cfg, tg, total, disc)
        proc.stdin.write(frame.convert("RGB").tobytes())
        if i % FPS == 0:
            print(f"\r{i}/{n} frame", end="", flush=True)
    proc.stdin.close()
    proc.wait()
    print(f"\nSiap: {out} ({total:.1f}s)")


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "output/video-produk-kurus.mp4"
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    import os
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    render(cfg, out)
