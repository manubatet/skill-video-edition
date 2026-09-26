"""Generate a small royalty-free SFX library procedurally (numpy only, no samples).

Usage: python sfx_synth.py --out sfx/
Sounds and their 'lead' (seconds from file start to the audible hit; start the cue
this much BEFORE the moment it should land):
  whoosh 0.22 | pop 0.0 | ding 0.0 | click 0.0 | riser 1.20 | boom 0.0
Any .wav you drop in sfx/ with the same name (e.g. a CC0 file from Freesound) overrides these.
"""
import argparse
import json
import wave
from pathlib import Path

import numpy as np

SR = 48000
LEAD = {"whoosh": 0.22, "pop": 0.0, "ding": 0.0, "click": 0.0, "riser": 1.20, "boom": 0.0}
rng = np.random.default_rng(7)


def t_axis(d):
    return np.arange(int(SR * d)) / SR


def lowpass(x, cutoff):
    """One-pole low-pass with a per-sample (time-varying) cutoff in Hz."""
    cutoff = np.broadcast_to(cutoff, x.shape)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.zeros_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def whoosh():
    d = 0.55
    t = t_axis(d)
    env = np.exp(-((t - LEAD["whoosh"]) ** 2) / (2 * 0.09 ** 2))
    cutoff = 400 + 5000 * env
    n = lowpass(rng.standard_normal(len(t)), cutoff)
    n -= lowpass(n, 150)  # remove rumble
    return n * env


def pop():
    t = t_axis(0.09)
    f = 900 * np.exp(-t * 35) + 180
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45)


def ding():
    t = t_axis(1.4)
    tone = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((1318.5, 1.0), (2637, 0.35), (3955, 0.12)))
    return tone * np.exp(-t * 3.2) * np.minimum(1, t / 0.004)


def click():
    t = t_axis(0.025)
    n = rng.standard_normal(len(t))
    return (n - lowpass(n, 2000)) * np.exp(-t * 300)


def riser():
    d = LEAD["riser"] + 0.05
    t = t_axis(d)
    env = (t / d) ** 2.5
    f = 200 + 1400 * (t / d) ** 2
    tone = 0.4 * np.sin(2 * np.pi * np.cumsum(f) / SR)
    noise = lowpass(rng.standard_normal(len(t)), 500 + 7000 * (t / d) ** 2)
    out = (tone + noise) * env
    out[-int(0.05 * SR):] *= np.linspace(1, 0, int(0.05 * SR))
    return out


def boom():
    t = t_axis(1.2)
    f = 90 * np.exp(-t * 4) + 38
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.5)
    thump = lowpass(rng.standard_normal(len(t)), 300) * np.exp(-t * 18) * 2
    return sub + thump


def write(x, path, peak_db=-3.0):
    x = x / (np.max(np.abs(x)) + 1e-9) * 10 ** (peak_db / 20)
    fade = int(0.003 * SR)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="sfx")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in {"whoosh": whoosh, "pop": pop, "ding": ding, "click": click, "riser": riser, "boom": boom}.items():
        p = out / f"{name}.wav"
        if p.exists():
            print(f"keep existing {p}")
            continue
        write(fn(), p)
        print(f"OK: {p}")
    (out / "lead.json").write_text(json.dumps(LEAD, indent=2))


if __name__ == "__main__":
    main()
