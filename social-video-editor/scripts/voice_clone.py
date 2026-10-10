"""Generate speech in the speaker's own voice (zero-shot cloning from a short reference).

Usage (in the environment of the chosen engine):
  python voice_clone.py --work work/ [--force] [--device cuda|mps|cpu]

Engines (edit.json "voice.engine"):
  voxcpm      VoxCPM2 (Apache-2.0, local, 48 kHz). Best Spain-Spanish accent in our tests. Default.
  chatterbox  Chatterbox Multilingual (MIT, local). Lighter; tends towards a Latin American accent.
  elevenlabs  ElevenLabs API (paid, cloud). Key from the env var in voice.api_key_env; the cloned
              voice id is cached next to the reference (elevenlabs.json) and reused.

Reads the lines to generate from the two decision files (the text lives there, nowhere else):
  work/edit.json      "voice": {...settings...}, "voice_patches": [{"id": "p1", "words": [120, 123], "text": "..."}]
  work/timeline.json  "voiceover": [{"id": "v1", "at": 12.3, "text": "..."}]
Settings (edit.json "voice", all optional except consent):
  {
    "consent": true,          # REQUIRED: the user confirmed the voice is theirs or they have permission
    "ref": [31.2, 43.0],      # source seconds of clean speech to clone from; null = pick automatically
    "ref_file": null,         # or a saved reference wav (e.g. _shared/voices/<speaker>/ref.wav);
                              # its transcript goes in ref.txt next to it (voxcpm needs it)
    "engine": "voxcpm",       # voxcpm | chatterbox | elevenlabs
    "exaggeration": 0.5,      # chatterbox: 0.25-1.0, higher = more expressive
    "cfg_weight": 0.5,        # chatterbox: 0.3-0.7, lower = slower, more deliberate delivery
    "api_key_env": "ELEVENLABS_API_KEY",   # elevenlabs: env var holding the key (never the key itself)
    "elevenlabs_model": "eleven_multilingual_v2",
    "seed": 7
  }
Writes work/voice/ref.wav, work/voice/<id>.wav (48 kHz mono, edges trimmed, level matched to the
reference) and work/voice/manifest.json. Unchanged lines are not regenerated; --force redoes all.
build_edit.py splices the patches into the source audio; render.py mixes the voice-overs.
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import die, load, need, run, save, wav_duration  # noqa: E402

VOICE_DEFAULTS = {"consent": False, "ref": None, "ref_file": None, "engine": "voxcpm", "exaggeration": 0.5,
                  "cfg_weight": 0.5, "api_key_env": "ELEVENLABS_API_KEY",
                  "elevenlabs_model": "eleven_multilingual_v2", "seed": 7}
ENGINE_SETTINGS = {"voxcpm": ("seed",), "chatterbox": ("exaggeration", "cfg_weight", "seed"),
                   "elevenlabs": ("elevenlabs_model", "seed")}
REF_MIN, REF_IDEAL, REF_MAX = 5.0, 8.0, 15.0  # seconds of reference speech
ELEVENLABS_API = "https://api.elevenlabs.io/v1"
SR = 48000


def read_wav(path):
    with wave.open(str(path), "rb") as f:
        sr, n, ch = f.getframerate(), f.getnframes(), f.getnchannels()
        x = np.frombuffer(f.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    return (x.reshape(-1, ch).mean(axis=1) if ch > 1 else x), sr


def write_wav(path, x, sr):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(pcm.tobytes())


def active_rms(x, sr, floor_db=-40):
    """RMS over 20 ms frames louder than floor_db below the peak frame (ignores pauses)."""
    n = max(1, int(sr * 0.02))
    frames = x[: len(x) // n * n].reshape(-1, n)
    if not len(frames):
        return 1e-6
    rms = np.sqrt((frames ** 2).mean(axis=1)) + 1e-9
    loud = rms[rms > rms.max() * 10 ** (floor_db / 20)]
    return float(np.sqrt((loud ** 2).mean()))


def trim_edges(x, sr, floor_db=-40, margin=0.03):
    n = max(1, int(sr * 0.01))
    frames = x[: len(x) // n * n].reshape(-1, n)
    rms = np.sqrt((frames ** 2).mean(axis=1)) + 1e-9
    on = np.where(rms > rms.max() * 10 ** (floor_db / 20))[0]
    if not len(on):
        return x
    m = int(margin * sr)
    return x[max(0, on[0] * n - m): min(len(x), (on[-1] + 1) * n + m)]


def pick_ref(t, excluded):
    """Best window of continuous, confidently transcribed speech (REF_IDEAL-REF_MAX s)."""
    words = [w for w in t["words"] if w.get("start") is not None]
    best, best_key = None, None
    for a in range(len(words)):
        if words[a]["i"] in excluded:
            continue
        scores = []
        for b in range(a, len(words)):
            w = words[b]
            if w["i"] in excluded or (b > a and w["start"] - words[b - 1]["end"] > 0.6):
                break
            if w["end"] - words[a]["start"] > REF_MAX:
                break
            scores.append(w.get("score", 0.5) or 0.5)
            dur = w["end"] - words[a]["start"]
            if dur >= REF_MIN:
                key = (dur >= REF_IDEAL, sum(scores) / len(scores), dur)
                if best_key is None or key > best_key:
                    best, best_key = (words[a]["start"], w["end"]), key
    return best


def build_ref(t, cfg, edit, work):
    ref = work / "voice" / "ref.wav"
    ref.parent.mkdir(parents=True, exist_ok=True)
    if cfg["ref_file"]:
        if not Path(cfg["ref_file"]).exists():
            die(f"voice.ref_file not found: {cfg['ref_file']}")
        run(["ffmpeg", "-y", "-i", str(cfg["ref_file"]), "-vn", "-ac", "1", "-ar", str(SR), str(ref)])
        txt = Path(cfg["ref_file"]).with_suffix(".txt")
        return ref, str(cfg["ref_file"]), txt.read_text(encoding="utf-8").strip() if txt.exists() else None
    excluded = set()
    for p in edit.get("voice_patches", []):
        excluded.update(range(p["words"][0], p["words"][1] + 1))
    for a, b in edit.get("remove_words", []):
        excluded.update(range(a, b + 1))
    for sid in edit.get("remove_sentences", []):
        s = next((s for s in t["sentences"] if s["id"] == sid), None)
        if s:
            excluded.update(s["words"])
    patched = set()
    for p in edit.get("voice_patches", []):
        patched.update(range(p["words"][0], p["words"][1] + 1))
    # prefer speech that stays in the edit; fall back to cut material (the voice is the same)
    span = cfg["ref"] or pick_ref(t, excluded) or pick_ref(t, patched)
    if not span:
        die(f"no {REF_MIN:.0f}+ s stretch of clean continuous speech found; set voice.ref = [start, end] by hand")
    a, b = max(0.0, span[0] - 0.1), min(t["duration"], span[1] + 0.1)
    run(["ffmpeg", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", t["source"], "-vn", "-ac", "1",
         "-ar", str(SR), "-af", "highpass=f=70,afftdn=nf=-25", str(ref)])
    text = " ".join(w["text"] for w in t["words"]
                    if w.get("start") is not None and w["start"] >= a - 0.05 and w["end"] <= b + 0.05)
    return ref, [round(a, 3), round(b, 3)], text


def pick_device(requested):
    import torch
    if requested:
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_chatterbox(device, ref, ref_text, cfg, work):
    try:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    except ImportError:
        die('Chatterbox is not installed. Run: pip install chatterbox-tts "setuptools<80"')
    try:
        model = ChatterboxMultilingualTTS.from_pretrained(device=device)
    except Exception as e:  # MPS support varies by torch build; CPU always works
        if device == "cpu":
            raise
        print(f"WARNING: could not load on {device} ({e}); falling back to cpu")
        model, device = ChatterboxMultilingualTTS.from_pretrained(device="cpu"), "cpu"

    def synth(text):
        import torch
        torch.manual_seed(cfg["seed"])
        wav = model.generate(text, language_id="es", audio_prompt_path=str(ref),
                             exaggeration=cfg["exaggeration"], cfg_weight=cfg["cfg_weight"])
        return wav.squeeze().detach().cpu().numpy().astype(np.float32), model.sr
    return synth, f"Chatterbox Multilingual on {device}"


def load_voxcpm(device, ref, ref_text, cfg, work):
    try:
        from voxcpm import VoxCPM
    except ImportError:
        die("VoxCPM is not installed. Run: pip install voxcpm soundfile")
    if not ref_text:
        die("voxcpm needs the reference transcript: put it in ref.txt next to voice.ref_file")
    model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)

    def synth(text):
        import torch
        torch.manual_seed(cfg["seed"])
        wav = model.generate(text=text, prompt_wav_path=str(ref), prompt_text=ref_text,
                             reference_wav_path=str(ref))
        return np.asarray(wav, dtype=np.float32).squeeze(), model.tts_model.sample_rate
    return synth, "VoxCPM2"


def _el_request(url, key, body, content_type):
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"xi-api-key": key, "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        die(f"ElevenLabs API error {e.code}: {e.read().decode(errors='replace')[:500]}")


def load_elevenlabs(device, ref, ref_text, cfg, work):
    key = os.environ.get(cfg["api_key_env"], "").strip()
    if not key:
        die(f"set the ElevenLabs API key in the environment variable {cfg['api_key_env']} (never in a file "
            "that goes to git)")
    api = ELEVENLABS_API
    # cache the cloned voice next to a saved reference (reused across projects), else in work/voice
    cache = Path(cfg["ref_file"]).with_name("elevenlabs.json") if cfg["ref_file"] else work / "voice" / "elevenlabs.json"
    ref_hash = hashlib.sha1(Path(ref).read_bytes()).hexdigest()[:12]
    cached = load(cache) if cache.exists() else {}
    voice_id = cfg.get("elevenlabs_voice_id") or (cached.get("voice_id") if cached.get("ref_hash") == ref_hash else None)
    if not voice_id:
        b = uuid.uuid4().hex
        parts = [f'--{b}\r\nContent-Disposition: form-data; name="name"\r\n\r\n{work.resolve().parent.name}\r\n'.encode(),
                 f'--{b}\r\nContent-Disposition: form-data; name="files"; filename="ref.wav"\r\n'
                 f"Content-Type: audio/wav\r\n\r\n".encode() + Path(ref).read_bytes() + b"\r\n",
                 f"--{b}--\r\n".encode()]
        out = json.loads(_el_request(f"{api}/voices/add", key, b"".join(parts), f"multipart/form-data; boundary={b}"))
        voice_id = out["voice_id"]
        save({"voice_id": voice_id, "ref_hash": ref_hash}, cache)
        print(f"ElevenLabs: cloned voice {voice_id} (cached in {cache})")

    def synth(text):
        body = json.dumps({"text": text, "model_id": cfg["elevenlabs_model"], "seed": cfg["seed"],
                           "voice_settings": {"stability": 0.5, "similarity_boost": 0.85}}).encode()
        mp3 = _el_request(f"{api}/text-to-speech/{voice_id}?output_format=mp3_44100_128", key, body, "application/json")
        tmp = work / "voice" / "_el.mp3"
        tmp.write_bytes(mp3)
        wav = tmp.with_suffix(".wav")
        run(["ffmpeg", "-y", "-i", str(tmp), "-ac", "1", "-ar", str(SR), str(wav)])
        x, sr = read_wav(wav)
        tmp.unlink()
        wav.unlink()
        return x, sr
    return synth, f"ElevenLabs {cfg['elevenlabs_model']} (voice {voice_id})"


ENGINES = {"voxcpm": load_voxcpm, "chatterbox": load_chatterbox, "elevenlabs": load_elevenlabs}


def resample(x, sr_in, sr_out):
    if sr_in == sr_out:
        return x
    n = int(round(len(x) * sr_out / sr_in))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work")
    ap.add_argument("--force", action="store_true", help="regenerate every line")
    ap.add_argument("--device", default=None, help="cuda | mps | cpu (default: best available)")
    args = ap.parse_args()
    need("ffmpeg")
    work = Path(args.work)
    t = load(work / "transcript.json")
    edit_path, tl_path = work / "edit.json", work / "timeline.json"
    edit = load(edit_path) if edit_path.exists() else {}
    tl = load(tl_path) if tl_path.exists() else {}
    cfg = {**VOICE_DEFAULTS, **edit.get("voice", {})}
    if cfg["consent"] is not True:
        die('voice cloning needs "voice": {"consent": true} in edit.json. Set it only after the user confirms '
            "the voice is their own or they have the speaker's permission.")

    lines = [("patch", p) for p in edit.get("voice_patches", [])] + [("voiceover", v) for v in tl.get("voiceover", [])]
    if not lines:
        die("nothing to generate: add voice_patches to edit.json or voiceover to timeline.json")
    seen = set()
    for kind, ln in lines:
        if not ln.get("id") or not ln.get("text", "").strip():
            die(f"every {kind} needs an id and a text: {ln}")
        if ln["id"] in seen:
            die(f"duplicate voice id '{ln['id']}' (ids are shared by patches and voice-overs)")
        seen.add(ln["id"])

    if cfg["engine"] not in ENGINES:
        die(f"voice.engine must be one of {', '.join(ENGINES)}")
    ref, ref_span, ref_text = build_ref(t, cfg, edit, work)
    ref_x, ref_sr = read_wav(ref)
    target_rms = active_rms(ref_x, ref_sr)
    settings = {"engine": cfg["engine"], **{k: cfg[k] for k in ENGINE_SETTINGS[cfg["engine"]]}}
    man_path = work / "voice" / "manifest.json"
    manifest = load(man_path) if man_path.exists() else {}
    where = ref_span if isinstance(ref_span, str) else f"source {ref_span[0]:.2f}-{ref_span[1]:.2f}s"
    print(f"reference: {where} ({wav_duration(ref):.1f}s) -> {ref}")

    synth, done = None, 0
    for kind, ln in lines:
        key = json.dumps([ln["text"].strip(), settings, ref_span], ensure_ascii=False)
        h = hashlib.sha1(key.encode()).hexdigest()[:12]
        out = work / "voice" / f"{ln['id']}.wav"
        if not args.force and out.exists() and manifest.get(ln["id"], {}).get("hash") == h:
            print(f"  {ln['id']}: unchanged ({manifest[ln['id']]['duration']:.2f}s)")
            continue
        if synth is None:
            device = pick_device(args.device) if cfg["engine"] != "elevenlabs" else None
            synth, label = ENGINES[cfg["engine"]](device, ref, ref_text, cfg, work)
            print(f"model: {label}")
        x, sr = synth(ln["text"].strip())
        x = trim_edges(resample(x, sr, SR), SR)
        x = x * min(target_rms / active_rms(x, SR), 10 ** (24 / 20))
        x = x / max(1.0, float(np.abs(x).max()) / 0.98)
        write_wav(out, x, SR)
        manifest[ln["id"]] = {"kind": kind, "text": ln["text"].strip(), "hash": h, "duration": round(len(x) / SR, 3)}
        done += 1
        print(f"  {ln['id']}: {kind} {len(x) / SR:.2f}s  \"{ln['text'].strip()}\"")
    for k in [k for k in manifest if k not in seen]:
        del manifest[k]
    save(manifest, man_path)
    print(f"OK: {done} generated, {len(lines) - done} unchanged. Listen to work/voice/*.wav before using them.")


if __name__ == "__main__":
    main()
