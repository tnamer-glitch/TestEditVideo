"""Edit klip UGC (telefon) jadi video iklan: teks overlay + end card CTA.

Guna:  python3 edit_video.py [edit_config.json]
Perlu: pip install pillow numpy imageio-ffmpeg
"""
import json
import math
import os
import subprocess
import sys

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from make_video import (
    DARK, FONT_BOLD, FONT_REG, GOLD, PINK, PLUM_BOT, PLUM_TOP, WA_GREEN, WHITE,
    bokeh, ease_out_cubic, gradient, icon, pill, place, text_layer, with_alpha,
)

W, H, FPS = 1080, 1920, 30
FF = imageio_ffmpeg.get_ffmpeg_exe()


def probe_duration(path):
    out = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    hms = out.split("Duration: ")[1].split(",")[0]
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def box(text, highlight=False, size=64):
    """Kotak kapsyen gaya TikTok."""
    fg, bg = (WHITE, PINK + (255,)) if highlight else (DARK, (255, 255, 255, 240))
    txt = text_layer(text, FONT_BOLD, size, fg, max_w=860, shadow=False)
    w, h = txt.width + 30, txt.height
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, w - 1, h - 1), radius=28, fill=bg)
    layer.alpha_composite(txt, ((w - txt.width) // 2, 0))
    return layer


def product_tag(name, sub, badge):
    title = text_layer(name, FONT_BOLD, 96, WHITE)
    subt = text_layer(sub, FONT_BOLD, 46, GOLD, max_w=880)
    bdg = pill(badge, GOLD, DARK, size=38, pad_x=44, pad_y=26)
    w = max(title.width, subt.width) + 60
    h = bdg.height + title.height + subt.height + 10
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, bdg.height // 2, w - 1, h - 1), radius=40, fill=PINK + (235,))
    layer.alpha_composite(bdg, ((w - bdg.width) // 2, 0))
    layer.alpha_composite(title, ((w - title.width) // 2, bdg.height - 10))
    layer.alpha_composite(subt, ((w - subt.width) // 2, bdg.height + title.height - 30))
    return layer


def bullet(text, kind):
    txt = text_layer(text, FONT_BOLD, 48, DARK, max_w=800, align="left", shadow=False)
    ic = icon(kind, 76)
    cw, ch = 940, max(130, txt.height + 30)
    layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=34, fill=(255, 255, 255, 240))
    layer.alpha_composite(ic, (34, (ch - ic.height) // 2))
    layer.alpha_composite(txt, (126, (ch - txt.height) // 2))
    return layer


_cache = {}


def cached(key, fn):
    if key not in _cache:
        _cache[key] = fn()
    return _cache[key]


def draw_overlays(frame, ov_list, t):
    for i, ov in enumerate(ov_list):
        s, e = ov["start"], ov["end"]
        if not (s <= t < e):
            continue
        fade_out = min(1.0, (e - t) / 0.2)
        kind = ov["type"]
        if kind == "caption":
            lyr = cached(i, lambda: box(ov["text"], ov.get("highlight", False)))
            tmp = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            place(tmp, lyr, W // 2, ov["y"], t, s, 0.35, "pop")
            frame.alpha_composite(with_alpha(tmp, fade_out))
        elif kind == "product":
            lyr = cached(i, lambda: product_tag(ov["name"], ov["sub"], ov["badge"]))
            tmp = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            place(tmp, lyr, W // 2, ov["y"], t, s, 0.5, "pop")
            frame.alpha_composite(with_alpha(tmp, fade_out))
        elif kind == "bullets":
            tmp = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            for j, it in enumerate(ov["items"]):
                lyr = cached((i, j), lambda: bullet(it, ov.get("icon", "check")))
                place(tmp, lyr, W // 2, ov["y"] + j * 160, t, s + j * 0.8, 0.45, "slide_left")
            frame.alpha_composite(with_alpha(tmp, fade_out))


def end_card(ec, t):
    f = gradient(PLUM_TOP, PLUM_BOT).copy()
    bokeh(f, t, PINK, 7)
    place(f, text_layer(ec["product_name"], FONT_BOLD, 110, GOLD), W // 2, 560, t, 0.0, 0.5, "pop")
    place(f, text_layer(ec["title"], FONT_BOLD, 72, WHITE), W // 2, 780, t, 0.3)
    btn = pill(ec["button"], WA_GREEN, WHITE, size=60)
    if t > 1.0:
        sc = 1 + 0.05 * math.sin((t - 1.0) * 6)
        btn = btn.resize((int(btn.width * sc), int(btn.height * sc)), Image.LANCZOS)
    place(f, btn, W // 2, 1040, t, 0.6, 0.5, "pop")
    place(f, text_layer(ec["note"], FONT_REG, 50, (255, 225, 235)), W // 2, 1200, t, 1.0)
    return f


_photo = {}


def photo_card(path, size):
    if (path, size) not in _photo:
        img = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size - 1), radius=36, fill=255)
        card = Image.new("RGBA", (size + 20, size + 20), (0, 0, 0, 0))
        ImageDraw.Draw(card).rounded_rectangle((0, 0, size + 19, size + 19), radius=44, fill=GOLD + (255,))
        img.putalpha(m)
        card.alpha_composite(img, (10, 10))
        _photo[(path, size)] = card
    return _photo[(path, size)]


def comment_bubble(name, text):
    fn, ft = ImageFont.truetype(FONT_BOLD, 34), ImageFont.truetype(FONT_REG, 40)
    tw = int(max(fn.getlength(name), ft.getlength(text))) + 60
    layer = Image.new("RGBA", (tw + 110, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((0, 30, 84, 114), fill=PINK)
    d.text((42 - fn.getlength(name[0]) / 2, 50), name[0], font=ImageFont.truetype(FONT_BOLD, 40), fill=WHITE)
    d.rounded_rectangle((100, 0, tw + 100, 146), radius=36, fill=(255, 255, 255, 245))
    d.text((130, 22), name, font=fn, fill=DARK)
    d.text((130, 74), text, font=ft, fill=(40, 40, 40))
    return layer


def testimonial_section(ts, t):
    f = gradient(PLUM_TOP, PLUM_BOT).copy()
    bokeh(f, t, GOLD, 8)
    place(f, text_layer(ts["title"], FONT_BOLD, 76, GOLD), W // 2, 230, t, 0.0, 0.4, "pop")
    place(f, photo_card(ts["image"], 820), W // 2, 790, t, 0.3, 0.5, "pop")
    for j, c in enumerate(ts["comments"]):
        place(f, comment_bubble(c["name"], c["text"]), W // 2, 1340 + j * 180, t, 1.4 + j * 0.8, 0.45, "slide_left")
    return f


def disclaimer(frame, text, dark_bg):
    col = (235, 215, 228) if dark_bg else WHITE
    lyr = text_layer(text, FONT_REG, 28, col, max_w=960, shadow=True)
    frame.alpha_composite(lyr, ((W - lyr.width) // 2, H - 70 - lyr.height))


def progress(frame, t, total):
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((60, 70, W - 60, 80), radius=5, fill=(255, 255, 255, 90))
    d.rounded_rectangle((60, 70, 60 + int((W - 120) * min(t / total, 1)), 80), radius=5, fill=PINK)


def main(cfg_path):
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    src, out = cfg["input"], cfg["output"]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    clip_dur = probe_duration(src)
    ec = cfg["end_card"]
    ts = cfg.get("testimonials")
    total = clip_dur + (ts["duration"] if ts else 0) + ec["duration"]

    vf = ("hflip," if cfg.get("mirror") else "") + \
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}"
    dec = subprocess.Popen(
        [FF, "-loglevel", "error", "-i", src, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    tmp_video = out + ".video.mp4"
    enc = subprocess.Popen(
        [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", tmp_video],
        stdin=subprocess.PIPE)

    fsize = W * H * 3
    i = 0
    while True:
        raw = dec.stdout.read(fsize)
        if len(raw) < fsize:
            break
        t = i / FPS
        frame = Image.frombytes("RGB", (W, H), raw).convert("RGBA")
        draw_overlays(frame, cfg["overlays"], t)
        progress(frame, t, total)
        disclaimer(frame, cfg["disclaimer"], False)
        enc.stdin.write(frame.convert("RGB").tobytes())
        i += 1
        if i % FPS == 0:
            print(f"\rklip {t:.0f}s", end="", flush=True)
    last = frame
    sections = []
    if ts:
        sections.append((ts["duration"], lambda t: testimonial_section(ts, t)))
    sections.append((ec["duration"], lambda t: end_card(ec, t)))
    for dur, fn in sections:
        prev = last
        for k in range(int(dur * FPS)):
            t = k / FPS
            f = fn(t)
            if t < 0.35:  # crossfade dari seksyen sebelumnya
                f = Image.blend(prev, f, ease_out_cubic(t / 0.35))
            progress(f, i / FPS, total)
            disclaimer(f, cfg["disclaimer"], True)
            enc.stdin.write(f.convert("RGB").tobytes())
            last = f
            i += 1
    enc.stdin.close()
    enc.wait()
    dec.wait()

    # Audio asal: kuatkan (loudnorm) + senyap untuk end card
    subprocess.run(
        [FF, "-y", "-loglevel", "error", "-i", tmp_video, "-i", src,
         "-map", "0:v", "-map", "1:a",
         "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={clip_dur - 0.4}:d=0.4,apad=whole_dur={total:.3f}",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart", out],
        check=True)
    os.remove(tmp_video)
    print(f"\nSiap: {out} ({total:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "edit_config.json")
