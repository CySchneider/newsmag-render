#!/usr/bin/env python3
"""Newsmag Story-Video: N Schlagzeilen-PNGs (1080x1920, 3–8 Stück) + Schluss-Slide + News-Beat -> MP4 im Stil von Cys Filmora-Export.
python3 makevideo.py <ordner mit newsmag-morning-1..N.png und newsmag-end.png> <beat.m4a> <out.mp4>
(Alt: ohne newsmag-end.png gilt die letzte newsmag-morning-*.png als Schluss-Slide.)
Seit 10.10.2026 variable Anzahl: Schnitte bleiben auf dem Beat; für mehr als 6 Schlagzeilen wird ein Takt (2 Schläge) der Musik
wiederholt, für weniger ausgelassen; der Schluss (Schluss-Slide + Ausklang) ist immer gleich.
Schnitte auf dem Beat (aus dem Filmora-Export gemessen), Glitch-Übergang (Bewegungsunschärfe, RGB-Versatz,
Aufhellen raus / Farbblitz + vertikale Unschärfe rein), Schrift sonst ruhig, leichte Lichtreflexe als Layer."""
import sys, subprocess, math
import numpy as np
from PIL import Image

src, beat, out = sys.argv[1:4]
FPS, W, H = 30, 1080, 1920
BEAT = [0.0, 2.4, 4.4333, 6.4667, 8.4667, 10.4667, 12.4667, 16.4]   # Original: Start jedes Slides + Ende (gemessen)
TOUT, TIN = 0.20, 0.20                                             # Dauer Übergang raus / rein
import os, glob
files = sorted(glob.glob(f"{src}/newsmag-morning-*.png"), key=lambda f: int(f.rsplit("-", 1)[1].split(".")[0]))
end_png = f"{src}/newsmag-end.png" if os.path.exists(f"{src}/newsmag-end.png") else files.pop()
N = len(files)
if not 1 <= N <= 10: sys.exit(f"{N} Schlagzeilen – erwartet 3 bis 8")
BAR = BEAT[3] - BEAT[2]                                            # Länge eines Slides auf dem Beat (≈ 2.03 s)
# Musik-Stücke (Start, Ende) im Original: Anfang bis Slide N (max. 6), dann Takte 3–4 wiederholen, dann der Ausklang
segs = [(0.0, BEAT[min(N, 6)])] + [(BEAT[2], BEAT[3])] * max(0, N - 6) + [(BEAT[6], BEAT[7])]
TOTAL = sum(b - a for a, b in segs)
# Starts der Schlagzeilen-Slides: bis 6 exakt wie im Original, weitere je ein Takt länger; dann Schluss-Slide und Ende
CUTS = BEAT[:min(N, 6)] + [BEAT[6] + BAR * k for k in range(N - 6)] + [TOTAL - (BEAT[7] - BEAT[6]), TOTAL]
slides = [np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) for f in files + [end_png]]
LAST = len(slides) - 1
rng = np.random.default_rng(7)
# Lichtflecken: grosse weiche Kreise, sehr schwach, langsam treibend
yy, xx = np.mgrid[0:H:4, 0:W:4]  # in Viertelauflösung rechnen
blobs = [dict(x=rng.uniform(0, W), y=rng.uniform(0, H), r=rng.uniform(120, 260), vx=rng.uniform(-40, 40), vy=rng.uniform(-30, 30), a=rng.uniform(.03, .06)) for _ in range(5)]

def bokeh(t):
    m = np.zeros_like(xx, dtype=np.float32)
    for b in blobs:
        cx, cy = (b["x"] + b["vx"] * t) % W, (b["y"] + b["vy"] * t) % H
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        m += b["a"] * np.clip(1 - d / b["r"], 0, 1) ** 2
    m = np.asarray(Image.fromarray(m).resize((W, H), Image.BILINEAR))
    return m[..., None]

def zoom(img, s):
    if abs(s - 1) < 1e-3: return img
    pil = Image.fromarray(img.astype(np.uint8)); w, h = int(W * s), int(H * s)
    big = pil.resize((w, h), Image.BICUBIC); l, t = (w - W) // 2, (h - H) // 2
    return np.asarray(big.crop((l, t, l + W, t + H)), dtype=np.float32)

def mblur(img, n, axis):
    if n < 2: return img
    acc = np.zeros_like(img); k = max(2, min(10, n // 4))
    for i in range(k):
        acc += np.roll(img, int(-n / 2 + n * i / (k - 1)), axis=axis)
    return acc / k

def rgbsplit(img, px):
    if px < 1: return img
    o = img.copy(); o[..., 0] = np.roll(img[..., 0], px, 1); o[..., 2] = np.roll(img[..., 2], -px, 1); return o

def frame(t):
    i = max(j for j in range(len(slides)) if CUTS[j] <= t)
    start, end = CUTS[i], CUTS[i + 1]
    img = slides[i].copy()                                                # Schrift steht ruhig (kein Zoom)
    if i < LAST and t > end - TOUT:                                          # raus: aufhellen, wischen, RGB
        p = (t - (end - TOUT)) / TOUT
        img = img * (1 - .45 * p) + np.array([40, 52, 78], np.float32) * .45 * p
        img = rgbsplit(mblur(img, int(70 * p), 1), int(14 * p))
    if i > 0 and t < start + TIN:                                         # rein: Farbblitz, vertikal, Zoom
        q = 1 - (t - start) / TIN
        img = rgbsplit(mblur(img, int(60 * q), 0), int(10 * q))
        mean = img.mean(axis=2, keepdims=True); img = mean + (img - mean) * (1 + .5 * q)  # Sättigung
    img = img + (255 - img) * bokeh(t)                                    # Lichtflecken (Screen)
    return np.clip(img, 0, 255).astype(np.uint8)

n = int(round(CUTS[-1] * FPS))
af = "".join(f"[1:a]atrim={a:.4f}:{b:.4f},asetpts=PTS-STARTPTS[s{k}];" for k, (a, b) in enumerate(segs)) + \
     "".join(f"[s{k}]" for k in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1[a]"
ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                       "-i", beat, "-filter_complex", af, "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
for f in range(n):
    ff.stdin.write(frame(f / FPS).tobytes())
ff.stdin.close(); ff.wait()
print(out, n, "frames,", N, "Schlagzeilen")
