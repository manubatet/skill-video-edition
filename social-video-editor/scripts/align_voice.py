"""Word timestamps for the voice-over clips, so render.py can caption them like the speech.

Usage (in the WhisperX environment, after voice_clone.py):
  python align_voice.py --work work/

The text is known, so this only runs forced alignment (wav2vec2, the same model transcribe.py
uses), no transcription. Writes work/voice/<id>.words.json for every voice-over in
work/voice/manifest.json; unchanged clips are skipped.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import die, fill_missing_times, load, save, wav_duration  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work")
    ap.add_argument("--language", default="es")
    args = ap.parse_args()
    work = Path(args.work)
    man_path = work / "voice" / "manifest.json"
    if not man_path.exists():
        die("no work/voice/manifest.json; run voice_clone.py first")
    todo = []
    for vid, m in load(man_path).items():
        if m["kind"] != "voiceover":
            continue
        out = work / "voice" / f"{vid}.words.json"
        if out.exists() and load(out).get("hash") == m["hash"]:
            print(f"  {vid}: unchanged")
            continue
        todo.append((vid, m, out))
    if not todo:
        print("OK: all voice-over captions up to date")
        return
    try:
        import whisperx
    except ImportError:
        die("WhisperX is not installed in this environment (run this with the transcribe.py environment)")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    model, meta = whisperx.load_align_model(language_code=args.language, device="cpu")
    for vid, m, out in todo:
        clip = work / "voice" / f"{vid}.wav"
        audio = whisperx.load_audio(str(clip))
        seg = [{"text": m["text"], "start": 0.0, "end": wav_duration(clip)}]
        res = whisperx.align(seg, model, meta, audio, "cpu", return_char_alignments=False)
        words = [{"text": w["word"], "start": w.get("start"), "end": w.get("end")}
                 for s in res["segments"] for w in s.get("words", [])]
        if not words:
            die(f"alignment produced no words for {vid}")
        fill_missing_times(words)
        save({"hash": m["hash"], "text": m["text"], "words": words}, out)
        print(f"  {vid}: {len(words)} words aligned")
    print("OK: voice-over captions ready")


if __name__ == "__main__":
    main()
