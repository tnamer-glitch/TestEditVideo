"""Tambah suara latar (TTS luar talian) pada video yang tiada suara.

Setiap baris skrip dijana dengan model Piper (sherpa-onnx), dilaraskan supaya
muat dalam slotnya, kemudian diletakkan pada masa `start`. Bunyi asal video
dikekalkan perlahan di belakang.

Guna:  python3 add_voiceover.py [voiceover_config.json]
Model: https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-id_ID-news_tts-medium.tar.bz2
"""
import json
import os
import subprocess
import sys
import wave

import imageio_ffmpeg
import numpy as np
import sherpa_onnx

FF = imageio_ffmpeg.get_ffmpeg_exe()
SR = 44100


def load_tts(model_dir):
    name = next(f for f in os.listdir(model_dir) if f.endswith(".onnx"))
    vits = sherpa_onnx.OfflineTtsVitsModelConfig(
        model=os.path.join(model_dir, name), tokens=os.path.join(model_dir, "tokens.txt"),
        data_dir=os.path.join(model_dir, "espeak-ng-data"))
    return sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=4)))


def resample(x, sr_in, sr_out):
    n = int(len(x) * sr_out / sr_in)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def main(cfg_path):
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    tts = load_tts(cfg["model"])
    speed = cfg.get("speed", 1.0)
    lines = cfg["lines"]
    track = np.zeros(int(SR * (lines[-1]["start"] + 30)))
    for i, ln in enumerate(lines):
        # slot = sehingga baris seterusnya (atau 'end' jika diberi)
        slot = ln.get("end", lines[i + 1]["start"] if i + 1 < len(lines) else 1e9) - ln["start"] - 0.15
        sp = ln.get("speed", speed)
        a = tts.generate(ln["text"], sid=0, speed=sp)
        dur = len(a.samples) / a.sample_rate
        if dur > slot:  # terlalu panjang: jana semula lebih laju
            sp *= dur / slot
            a = tts.generate(ln["text"], sid=0, speed=sp)
            dur = len(a.samples) / a.sample_rate
        print(f"{ln['start']:5.1f}s  {dur:4.1f}s  x{sp:.2f}  {ln['text']}")
        x = resample(np.asarray(a.samples, float), a.sample_rate, SR)
        s0 = int(ln["start"] * SR)
        track[s0:s0 + len(x)] += x
    track = track[:int(SR * (max(l["start"] for l in lines) + 12))]
    vo = cfg["output"] + ".vo.wav"
    with wave.open(vo, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((np.clip(track, -1, 1) * 32767).astype(np.int16).tobytes())

    bg = cfg.get("original_volume", 0.3)
    subprocess.run(
        [FF, "-y", "-loglevel", "error", "-i", cfg["input"], "-i", vo, "-filter_complex",
         f"[0:a]volume={bg},aresample={SR}[b];"
         f"[1:a]highpass=f=70,acompressor=threshold=-18dB:ratio=3:attack=5:release=80,"
         f"loudnorm=I=-15:TP=-1.5:LRA=9,aresample={SR}[v];"
         f"[b][v]amix=inputs=2:duration=first:normalize=0[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", cfg["output"]],
        check=True)
    os.remove(vo)
    print(f"Siap: {cfg['output']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "voiceover_config.json")
