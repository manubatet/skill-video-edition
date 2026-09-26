"""Shared helpers for the social-video-editor pipeline."""
import json
import subprocess
import shutil
import sys
from pathlib import Path


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def need(binary):
    if not shutil.which(binary):
        die(f"'{binary}' not found in PATH. Install it first (see SKILL.md > Setup).")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def run(cmd, quiet=True):
    """Run a command; on failure print the tail of stderr and exit."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print("COMMAND FAILED:\n" + " ".join(map(str, cmd))[:2000], file=sys.stderr)
        print(p.stderr[-4000:], file=sys.stderr)
        sys.exit(p.returncode)
    if not quiet:
        print(p.stdout)
    return p


def probe(path):
    """Return width, height, fps, duration and whether the file has audio."""
    need("ffprobe")
    p = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    info = json.loads(p.stdout)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        die(f"{path} has no video stream")
    num, den = v.get("avg_frame_rate", "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    w, h = int(v["width"]), int(v["height"])
    # Respect rotation metadata from phones (portrait videos stored as landscape).
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = abs(int(sd["rotation"]))
    if rot in (90, 270):
        w, h = h, w
    return {
        "width": w,
        "height": h,
        "fps": round(fps, 3),
        "duration": float(info["format"]["duration"]),
        "has_audio": a is not None,
    }


def fmt(t):
    m, s = divmod(max(t, 0), 60)
    return f"{int(m):02d}:{s:05.2f}"


def fill_missing_times(words):
    """WhisperX leaves some tokens (often numbers like '2026' or '%') without
    timestamps. Interpolate them from neighbours so every word has start/end."""
    n = len(words)
    for i, w in enumerate(words):
        if w.get("start") is not None and w.get("end") is not None:
            continue
        prev_end = next((words[j]["end"] for j in range(i - 1, -1, -1) if words[j].get("end") is not None), None)
        nxt = next((j for j in range(i + 1, n) if words[j].get("start") is not None), None)
        next_start = words[nxt]["start"] if nxt is not None else None
        if prev_end is None and next_start is None:
            w["start"], w["end"] = 0.0, 0.3
            continue
        if prev_end is None:
            prev_end = max(next_start - 0.3, 0)
        if next_start is None:
            next_start = prev_end + 0.3
        # share the gap between the consecutive untimed words
        k = i
        while k < n and words[k].get("start") is None:
            k += 1
        count = k - i
        step = max(next_start - prev_end, 0.05 * count) / count
        for off in range(count):
            words[i + off]["start"] = round(prev_end + off * step, 3)
            words[i + off]["end"] = round(prev_end + (off + 1) * step, 3)
            words[i + off]["interpolated"] = True
    return words


def write_readable(transcript, path):
    """Human-readable transcript: one numbered sentence per line."""
    lines = []
    for s in transcript["sentences"]:
        spk = f" {s['speaker']}" if s.get("speaker") else ""
        w0, w1 = s["words"][0], s["words"][-1]
        lines.append(f"[S{s['id']} {fmt(s['start'])}-{fmt(s['end'])}{spk} | w{w0}-w{w1}] {s['text']}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def rebuild_sentence_text(transcript):
    for s in transcript["sentences"]:
        ws = [transcript["words"][i] for i in s["words"]]
        s["text"] = " ".join(w["text"] for w in ws)
        s["start"], s["end"] = ws[0]["start"], ws[-1]["end"]
    return transcript
