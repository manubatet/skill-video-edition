"""Apply cut decisions (retakes, removed words, silences), clean audio, re-time the transcript.

Usage:
  python build_edit.py --work work/ [--edit work/edit.json]

Reads  work/transcript.json and work/edit.json (all fields optional):
  {
    "remove_sentences": [3, 7],        # sentence ids (retakes, off-topic)
    "remove_words": [[120, 131]],      # inclusive ranges of word ids (false starts)
    "max_gap": 0.40,                   # pauses longer than this are cut (s)
    "pad": 0.12,                       # breathing room kept around speech (s)
    "denoise": "light",                # off | light (FFmpeg afftdn) | deepfilter (DeepFilterNet CLI)
    "loudness": -14                    # integrated LUFS target
  }
Writes work/segments.json, work/transcript_edited.json, work/transcript_edited.txt, work/cut.mkv
All word ids stay the ORIGINAL ids, so later steps can reference them safely.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import die, load, need, run, save, write_readable  # noqa: E402

DEFAULTS = {"remove_sentences": [], "remove_words": [], "max_gap": 0.40, "pad": 0.12,
            "denoise": "light", "loudness": -14}


def plan_segments(t, cfg):
    words = t["words"]
    removed = set()
    for sid in cfg["remove_sentences"]:
        s = next((s for s in t["sentences"] if s["id"] == sid), None)
        if s is None:
            die(f"remove_sentences: sentence {sid} does not exist")
        removed.update(s["words"])
    for a, b in cfg["remove_words"]:
        removed.update(range(a, b + 1))
    kept = [w for w in words if w["i"] not in removed]
    if not kept:
        die("Every word was removed; nothing left to render.")

    groups, cur = [], [kept[0]]
    for prev, w in zip(kept, kept[1:]):
        contiguous = w["i"] == prev["i"] + 1
        if contiguous and (w["start"] - prev["end"]) <= cfg["max_gap"]:
            cur.append(w)
        else:
            groups.append(cur)
            cur = [w]
    groups.append(cur)

    fps, dur, pad = t["fps"], t["duration"], cfg["pad"]
    segs = []
    for g in groups:
        first, last = g[0], g[-1]
        start = first["start"] - pad
        if first["i"] > 0:
            before = words[first["i"] - 1]
            limit = before["end"] + 0.01 if before["i"] in removed else (before["end"] + first["start"]) / 2
            start = max(start, limit)
        end = last["end"] + pad
        if last["i"] + 1 < len(words):
            after = words[last["i"] + 1]
            limit = after["start"] - 0.01 if after["i"] in removed else (last["end"] + after["start"]) / 2
            end = min(end, limit)
        # snap to the frame grid so audio and video cut at identical instants (no drift)
        start = max(0.0, round(start * fps) / fps)
        end = min(dur, round(end * fps) / fps)
        if end - start >= 1.0 / fps:
            segs.append({"src_start": round(start, 4), "src_end": round(end, 4), "words": [w["i"] for w in g]})

    merged = [segs[0]]
    for s in segs[1:]:  # join segments that touch after snapping
        if s["src_start"] - merged[-1]["src_end"] < 0.5 / fps:
            merged[-1]["src_end"] = s["src_end"]
            merged[-1]["words"] += s["words"]
        else:
            merged.append(s)
    off = 0.0
    for s in merged:
        s["out_start"] = round(off, 4)
        off += s["src_end"] - s["src_start"]
        s["out_end"] = round(off, 4)
    return merged, removed


def retime(t, segs):
    words_by_id = {w["i"]: w for w in t["words"]}
    new_words = []
    for s in segs:
        for i in s["words"]:
            w = dict(words_by_id[i])
            w["start"] = round(s["out_start"] + w["start"] - s["src_start"], 3)
            w["end"] = round(min(s["out_start"] + w["end"] - s["src_start"], s["out_end"]), 3)
            new_words.append(w)
    kept_ids = {w["i"] for w in new_words}
    idx = {w["i"]: k for k, w in enumerate(new_words)}
    sentences = []
    for s in t["sentences"]:
        ids = [i for i in s["words"] if i in kept_ids]
        if not ids:
            continue
        ws = [new_words[idx[i]] for i in ids]
        sentences.append({**s, "words": ids, "text": " ".join(w["text"] for w in ws),
                          "start": ws[0]["start"], "end": ws[-1]["end"]})
    duration = segs[-1]["out_end"]
    return {**t, "duration": round(duration, 3), "edited": True, "sentences": sentences, "words": new_words}


def denoise_source(src, mode, work):
    """Return (path, extra_filter) for the audio to cut from."""
    if mode == "off":
        return src, ""
    if mode == "deepfilter":
        if not shutil.which("deepFilter"):
            print("WARNING: deepFilter CLI not found (pip install deepfilternet); falling back to 'light'")
            return src, "afftdn=nf=-25,"
        wav = work / "src_audio.wav"
        run(["ffmpeg", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "48000", str(wav)])
        run(["deepFilter", str(wav), "-o", str(work / "df")])
        out = next((work / "df").glob("*.wav"), None)
        if out is None:
            die("DeepFilterNet produced no output")
        return out, ""
    return src, "afftdn=nf=-25,"  # light: gentle broadband noise reduction


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work")
    ap.add_argument("--edit", default=None)
    args = ap.parse_args()
    need("ffmpeg")
    work = Path(args.work)
    t = load(work / "transcript.json")
    if not t.get("has_audio", True):
        die("the source video has no audio track")
    edit_path = Path(args.edit) if args.edit else work / "edit.json"
    cfg = {**DEFAULTS, **(load(edit_path) if edit_path.exists() else {})}

    segs, removed = plan_segments(t, cfg)
    save({"segments": segs, "config": cfg}, work / "segments.json")
    edited = retime(t, segs)
    save(edited, work / "transcript_edited.json")
    write_readable(edited, work / "transcript_edited.txt")

    audio_src, afilter = denoise_source(Path(t["source"]), cfg["denoise"], work)
    fc, labels = [], []
    for k, s in enumerate(segs):
        a, b = s["src_start"], s["src_end"]
        d = b - a
        fade = min(0.012, d / 4)
        fc.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{k}]")
        fc.append(f"[1:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,"
                  f"afade=t=in:d={fade:.3f},afade=t=out:st={d - fade:.3f}:d={fade:.3f}[a{k}]")
        labels.append(f"[v{k}][a{k}]")
    fc.append(f"{''.join(labels)}concat=n={len(segs)}:v=1:a=1[vc][ac0]")
    fc.append(f"[ac0]{afilter}aresample=48000[ac]")
    raw = work / "cut_raw.mkv"
    graph = work / "cut_graph.txt"
    graph.write_text(";\n".join(fc), encoding="utf-8")
    run(["ffmpeg", "-y", "-i", t["source"], "-i", str(audio_src), "-filter_complex_script", str(graph),
         "-map", "[vc]", "-map", "[ac]", "-c:v", "libx264", "-crf", "14", "-preset", "fast",
         "-pix_fmt", "yuv420p", "-fps_mode", "cfr", "-r", str(t["fps"]), "-c:a", "pcm_s16le", str(raw)])

    # Two-pass loudness normalization (EBU R128) to the platform target.
    lufs = cfg["loudness"]
    p = run(["ffmpeg", "-i", str(raw), "-vn", "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json",
             "-f", "null", "-"])
    m = json.loads(p.stderr[p.stderr.rindex("{"):p.stderr.rindex("}") + 1])
    ln = (f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run(["ffmpeg", "-y", "-i", str(raw), "-c:v", "copy", "-af", f"{ln},aresample=48000",
         "-c:a", "pcm_s16le", str(work / "cut.mkv")])
    raw.unlink(missing_ok=True)

    saved = t["duration"] - edited["duration"]
    print(f"OK: {len(segs)} segments, removed {len(removed)} words, "
          f"{t['duration']:.1f}s -> {edited['duration']:.1f}s (-{saved:.1f}s). "
          f"Input loudness {m['input_i']} LUFS -> {lufs}. Wrote {work/'cut.mkv'}")


if __name__ == "__main__":
    main()
