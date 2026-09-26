"""Validate the timeline and render the final (or preview) video.

Usage:
  python render.py --work work/ --check            # validate only (pace rules)
  python render.py --work work/ --preview          # fast low-res render -> work/preview.mp4
  python render.py --work work/                    # final render -> work/final.mp4
  python render.py --work work/ --preview --sheet  # also write work/qa_sheet.jpg (frames at every cue)

Inputs: work/cut.mkv, work/transcript_edited.json, work/timeline.json, sfx/*.wav
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from captions import CAPTION_DEFAULTS, anchor_xy, build_ass  # noqa: E402
from common import die, load, need, probe, run, save  # noqa: E402

RULES = {"sfx_min_gap": 3.0,          # s between two sound effects
         "zoom_min_len": 1.0,         # s, shorter punch-ins feel like glitches
         "zoom_max_scale": 1.35,
         "zoom_max_share": 0.45,      # max fraction of the video that is zoomed
         "anim_min_gap": 1.5,         # s between the end of one animation and the next
         "emphasis_per_10s": 3,       # highlighted words per 10 s of video
         "first_hook_by": 3.0}        # something (zoom/anim/sfx) should happen before this
SFX_LEAD = {"whoosh": 0.22, "pop": 0.0, "ding": 0.0, "click": 0.0, "riser": 1.20, "boom": 0.0}


def anim_box(a, meta, W, H):
    w, h = meta["width"], meta["height"]
    if a.get("x") is not None and a.get("y") is not None:
        return int(a["x"]), int(a["y"]), w, h
    cy = {"top": 0.14, "upper-third": 0.30, "center": 0.45, "lower-third": 0.60}[a.get("anchor", "upper-third")] * H
    cx = W * (0.47 if H > W else 0.5)
    return int(cx - w / 2), int(cy - h / 2), w, h


def validate(tl, tr, anims_meta, rules):
    errs, warns = [], []
    D, W, H = tr["duration"], tr["width"], tr["height"]
    word_ids = {w["i"] for w in tr["words"]}

    sfx = sorted(tl.get("sfx", []), key=lambda s: s["at"])
    for s in sfx:
        if not (0 <= s["at"] < D):
            errs.append(f"sfx at {s['at']} is outside the video (0-{D:.2f})")
    for a, b in zip(sfx, sfx[1:]):
        if b["at"] - a["at"] < rules["sfx_min_gap"]:
            errs.append(f"sfx at {a['at']} and {b['at']} are closer than {rules['sfx_min_gap']}s")

    zooms = sorted(tl.get("zooms", []), key=lambda z: z["start"])
    for z in zooms:
        if z["end"] - z["start"] < rules["zoom_min_len"]:
            errs.append(f"zoom {z['start']}-{z['end']} shorter than {rules['zoom_min_len']}s")
        if z.get("ramp", 0.7) < 0:
            errs.append(f"zoom {z['start']} ramp must be >= 0")
        if not (1.0 < z.get("scale", 1.15) <= rules["zoom_max_scale"]):
            errs.append(f"zoom {z['start']} scale must be in (1, {rules['zoom_max_scale']}]")
        if z["start"] < 0 or z["end"] > D + 0.05:
            errs.append(f"zoom {z['start']}-{z['end']} outside the video")
    for a, b in zip(zooms, zooms[1:]):
        if b["start"] < a["end"]:
            errs.append(f"zooms overlap: {a['start']}-{a['end']} and {b['start']}-{b['end']}")
    share = sum(z["end"] - z["start"] for z in zooms) / D if D else 0
    if share > rules["zoom_max_share"]:
        warns.append(f"{share:.0%} of the video is zoomed (> {rules['zoom_max_share']:.0%}); zooms lose impact")

    anims = sorted(tl.get("animations", []), key=lambda a: a["start"])
    cap = {**CAPTION_DEFAULTS, **tl.get("captions", {})}
    cap_y = anchor_xy(cap["position"], W, H)[1]
    band = int(min(W, H) * cap["size"] * 1.3)
    for a in anims:
        m = anims_meta[a["id"]]
        end = a["start"] + m["duration"]
        if a["start"] < 0 or end > D + 0.05:
            errs.append(f"animation {a['id']} ({a['start']}-{end:.2f}) outside the video")
        x, y, w, h = anim_box(a, m, W, H)
        if x < 0 or y < 0 or x + w > W or y + h > H:
            errs.append(f"animation {a['id']} box {x},{y},{w}x{h} leaves the frame")
        if cap["mode"] != "off" and not a.get("hide_captions") and y < cap_y + band and y + h > cap_y - band:
            warns.append(f"animation {a['id']} overlaps the caption band; move it or set hide_captions")
        if H > W and y + h > 0.80 * H:
            warns.append(f"animation {a['id']} enters the bottom 20% (platform UI zone)")
    for a, b in zip(anims, anims[1:]):
        if b["start"] < a["start"] + anims_meta[a["id"]]["duration"] + rules["anim_min_gap"]:
            errs.append(f"animations {a['id']} and {b['id']} are closer than {rules['anim_min_gap']}s")

    emph = tl.get("emphasis_words", [])
    bad = [i for i in emph if i not in word_ids]
    if bad:
        errs.append(f"emphasis_words not in edited transcript: {bad}")
    if D and len(emph) / D * 10 > rules["emphasis_per_10s"]:
        warns.append(f"{len(emph)} emphasis words in {D:.0f}s is dense (> {rules['emphasis_per_10s']}/10s)")

    firsts = [z["start"] for z in zooms] + [a["start"] for a in anims] + [s["at"] for s in sfx]
    if firsts and min(firsts) > rules["first_hook_by"]:
        warns.append(f"nothing happens visually before {min(firsts):.1f}s; consider a hook in the first 3s")
    return errs, warns


def face_center(video, samples=15):
    """Median face centre (normalized) using OpenCV's bundled Haar cascade; None if no face."""
    try:
        import cv2
    except ImportError:
        return None
    cap = cv2.VideoCapture(str(video))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    xs, ys = [], []
    for k in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (k + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = det.detectMultiScale(gray, 1.1, 6, minSize=(gray.shape[1] // 12, gray.shape[1] // 12))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            xs.append((x + w / 2) / gray.shape[1])
            ys.append((y + h / 2) / gray.shape[0])
    cap.release()
    if len(xs) < samples // 3:
        return None
    xs.sort()
    ys.sort()
    return xs[len(xs) // 2], ys[len(ys) // 2]


def zoom_expr(zooms, default_ramp=0.7):
    """FFmpeg expression for the zoom factor at time t: 1 outside zooms, eased (smoothstep)
    in over `ramp` s after start, held, eased out over `ramp` s before end. Gradual
    push-ins instead of hard cuts; "ramp": 0 restores the hard punch-in."""
    terms = []
    for z in zooms:
        a, b, s = z["start"], z["end"], z.get("scale", 1.15)
        r = min(max(z.get("ramp", default_ramp), 0.0), (b - a) / 2)
        if r < 1e-3:
            env = f"between(t,{a},{b - 0.001})"
        else:
            p_in, p_out = f"clip((t-{a})/{r:.3f},0,1)", f"clip(({b}-t)/{r:.3f},0,1)"
            env = f"({p_in})*({p_in})*(3-2*({p_in}))*({p_out})*({p_out})*(3-2*({p_out}))"
        terms.append(f"{s - 1:.4f}*{env}")
    return "(1+" + "+".join(terms) + ")"


def build_graph(tl, tr, anims_meta, sfx_dir, center, preview):
    W, H = tr["width"], tr["height"]
    inputs, fc = [], []
    v = "0:v"
    zooms = sorted(tl.get("zooms", []), key=lambda z: z["start"])
    if zooms:
        # Per-frame upscale by the eased factor, then crop back to W x H around the face
        # (face slightly above the crop centre). The crop offset follows the scaled size.
        s = zoom_expr(zooms)
        fx, fy = center
        fc.append(f"[{v}]scale=w='2*trunc({W}*{s}/2)':h='2*trunc({H}*{s}/2)':eval=frame:flags=bicubic,"
                  f"crop={W}:{H}:'min(max({fx}*iw-{W / 2},0),iw-{W})':'min(max({fy}*ih-{0.42 * H},0),ih-{H})',"
                  f"setsar=1[vz]")
        v = "vz"

    idx = 1
    for a in sorted(tl.get("animations", []), key=lambda a: a["start"]):
        m = anims_meta[a["id"]]
        x, y, _, _ = anim_box(a, m, W, H)
        inputs += ["-i", str(Path(a["file"]).resolve())]
        fc.append(f"[{idx}:v]format=rgba,setpts=PTS-STARTPTS+{a['start']}/TB[an{idx}]")
        fc.append(f"[{v}][an{idx}]overlay={x}:{y}:eof_action=pass:format=auto[va{idx}]")
        v = f"va{idx}"
        idx += 1

    fc.append(f"[{v}]ass=filename=captions.ass:fontsdir=fonts[vcap]")
    v = "vcap"
    if preview:
        fc.append(f"[{v}]scale=-2:{960 if H > W else 540}:flags=bilinear[vprev]")
        v = "vprev"
    fc.append(f"[{v}]format=yuv420p[vout]")

    alabels = ["[0:a]"]
    for s in sorted(tl.get("sfx", []), key=lambda s: s["at"]):
        f = Path(sfx_dir) / f"{s['sound']}.wav"
        if not f.exists():
            die(f"sfx '{s['sound']}' not found at {f} (run sfx_synth.py or add the wav)")
        start = max(0.0, s["at"] - SFX_LEAD.get(s["sound"], 0.0)) if s.get("align", "hit") == "hit" else s["at"]
        inputs += ["-i", str(f.resolve())]
        ms = int(start * 1000)
        fc.append(f"[{idx}:a]aresample=48000,adelay={ms}:all=1,volume={s.get('gain_db', -10)}dB[s{idx}]")
        alabels.append(f"[s{idx}]")
        idx += 1
    if len(alabels) > 1:
        fc.append(f"{''.join(alabels)}amix=inputs={len(alabels)}:normalize=0:duration=first:dropout_transition=0,"
                  f"alimiter=limit=0.89:level=false[aout]")
    else:
        fc.append("[0:a]anull[aout]")
    return inputs, fc


def qa_sheet(video, times, out):
    from PIL import Image, ImageDraw
    tmp = Path(out).parent / "qa_frames"
    tmp.mkdir(exist_ok=True)
    tiles = []
    for k, (t, label) in enumerate(times[:12]):
        p = tmp / f"{k:02d}.jpg"
        run(["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=-2:480", str(p)])
        im = Image.open(p).convert("RGB")
        ImageDraw.Draw(im).rectangle([0, 0, im.width, 26], fill=(0, 0, 0))
        ImageDraw.Draw(im).text((6, 6), f"{t:.2f}s  {label}", fill=(255, 255, 0))
        tiles.append(im)
    if not tiles:
        return
    cols = min(4, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].size
    sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % cols) * tw, (k // cols) * th))
    sheet.save(out, quality=85)
    print(f"OK: QA sheet {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work")
    ap.add_argument("--sfx", default="sfx")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--force", action="store_true", help="render even if pace rules fail")
    args = ap.parse_args()
    need("ffmpeg")
    work = Path(args.work).resolve()
    tr = load(work / "transcript_edited.json")
    tl = load(work / "timeline.json")
    rules = {**RULES, **tl.get("rules", {})}
    anims_meta = {}
    for a in tl.get("animations", []):
        if not Path(a["file"]).exists():
            die(f"animation file missing: {a['file']}")
        anims_meta[a["id"]] = probe(a["file"])
        a["duration"] = anims_meta[a["id"]]["duration"]  # captions.py needs it for hide_captions

    errs, warns = validate(tl, tr, anims_meta, rules)
    for w in warns:
        print(f"WARN: {w}")
    for e in errs:
        print(f"RULE: {e}")
    if args.check:
        print("CHECK OK" if not errs else f"CHECK FAILED ({len(errs)} rule violations)")
        sys.exit(1 if errs else 0)
    if errs and not args.force:
        die("fix the rule violations above (or pass --force)")

    center = tl.get("zoom_center")
    if center is None and tl.get("zooms"):
        center = face_center(work / "cut.mkv") or (0.5, 0.4)
        tl["zoom_center"] = [round(center[0], 3), round(center[1], 3)]
        save(tl, work / "timeline.json")
        print(f"zoom centre = {tl['zoom_center']}")
    (work / "captions.ass").write_text(build_ass(tr, tl), encoding="utf-8")

    inputs, fc = build_graph(tl, tr, anims_meta, Path(args.sfx).resolve(), center or (0.5, 0.4), args.preview)
    (work / "render_graph.txt").write_text(";\n".join(fc), encoding="utf-8")
    out = work / ("preview.mp4" if args.preview else "final.mp4")
    enc = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"] if args.preview
           else ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high"])
    (work / "fonts").mkdir(exist_ok=True)
    cmd = (["ffmpeg", "-y", "-i", str(work / "cut.mkv")] + inputs +
           ["-filter_complex_script", "render_graph.txt", "-map", "[vout]", "-map", "[aout]"] + enc +
           ["-r", str(tr["fps"]), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)])
    import subprocess
    p = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-4000:], file=sys.stderr)
        die("render failed (graph in work/render_graph.txt)")
    print(f"OK: {out} ({tr['duration']:.1f}s)")

    if args.sheet:
        times = [((z["start"] + z["end"]) / 2, f"zoom x{z.get('scale', 1.15)}") for z in tl.get("zooms", [])]
        times += [(a["start"] + anims_meta[a["id"]]["duration"] * 0.5, f"anim {a['id']}") for a in tl.get("animations", [])]
        times += [(tr["duration"] * f, "captions") for f in (0.1, 0.5)]
        qa_sheet(out, sorted(times), work / "qa_sheet.jpg")


if __name__ == "__main__":
    main()
