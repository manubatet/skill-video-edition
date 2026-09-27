"""Transcribe a Spanish video with WhisperX: word-level timestamps + optional diarization.

Usage:
  python transcribe.py INPUT.mp4 --out work/ [--model large-v3] [--glossary "Término1, Marca2"]
                       [--speakers N] [--hf-token TOKEN]

Writes work/transcript.json (machine) and work/transcript.txt (for review).
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import die, fill_missing_times, need, probe, save, write_readable  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default="work")
    ap.add_argument("--model", default="large-v3", help="large-v3 (best), medium, small (fast CPU drafts)")
    ap.add_argument("--language", default="es")
    ap.add_argument("--glossary", default="", help="comma-separated proper nouns / brands / anglicisms")
    ap.add_argument("--speakers", type=int, default=0, help="known speaker count (0 = detect if token given)")
    ap.add_argument("--hf-token", default=os.environ.get("HF_TOKEN", ""), help="Hugging Face token for pyannote diarization")
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()

    need("ffmpeg")
    try:
        import torch
        import whisperx
    except ImportError:
        die("WhisperX is not installed. Run: pip install whisperx")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    meta = probe(args.input)
    print(f"device={device} compute={compute_type} model={args.model} duration={meta['duration']:.1f}s")

    asr_options = {}
    if args.glossary.strip():
        # The prompt biases spelling of names; hotwords boosts them further.
        asr_options["initial_prompt"] = f"Vocabulario: {args.glossary.strip()}."
        asr_options["hotwords"] = args.glossary.strip()

    model = whisperx.load_model(args.model, device, compute_type=compute_type,
                                language=args.language, asr_options=asr_options or None)
    audio = whisperx.load_audio(args.input)
    result = model.transcribe(audio, batch_size=args.batch_size, language=args.language)

    align_model, align_meta = whisperx.load_align_model(language_code=args.language, device=device)
    result = whisperx.align(result["segments"], align_model, align_meta, audio, device,
                            return_char_alignments=False)

    diarized = False
    if args.hf_token and args.speakers != 1:
        try:
            from whisperx.diarize import DiarizationPipeline
            try:
                dp = DiarizationPipeline(token=args.hf_token, device=device)
            except TypeError:  # older WhisperX versions
                dp = DiarizationPipeline(use_auth_token=args.hf_token, device=device)
            kw = {"num_speakers": args.speakers} if args.speakers > 1 else {}
            dia = dp(audio, **kw)
            if isinstance(dia, tuple):
                dia = dia[0]
            result = whisperx.assign_word_speakers(dia, result)
            diarized = True
        except Exception as e:  # diarization is optional; never block the edit on it
            print(f"WARNING: diarization failed ({e}); continuing without speakers")

    words, sentences = [], []
    for seg in result["segments"]:
        seg_words = seg.get("words") or []
        if not seg_words:
            continue
        idx = []
        for w in seg_words:
            text = (w.get("word") or "").strip()
            if not text:
                continue
            words.append({
                "i": len(words),
                "text": text,
                "start": w.get("start"),
                "end": w.get("end"),
                "score": round(w["score"], 3) if w.get("score") is not None else None,
                "speaker": w.get("speaker") or seg.get("speaker"),
                "sentence": len(sentences),
            })
            idx.append(len(words) - 1)
        if idx:
            sentences.append({"id": len(sentences), "words": idx, "speaker": seg.get("speaker")})

    fill_missing_times(words)
    for s in sentences:
        ws = [words[i] for i in s["words"]]
        s["text"] = " ".join(w["text"] for w in ws)
        s["start"], s["end"] = ws[0]["start"], ws[-1]["end"]

    speakers = sorted({w["speaker"] for w in words if w.get("speaker")})
    transcript = {
        "source": str(Path(args.input).resolve()),
        "language": args.language,
        "model": args.model,
        "diarized": diarized,
        "speakers": speakers,
        **meta,
        "sentences": sentences,
        "words": words,
    }
    out = Path(args.out)
    save(transcript, out / "transcript.json")
    write_readable(transcript, out / "transcript.txt")
    low = sum(1 for w in words if (w.get("score") or 1) < 0.4)
    print(f"OK: {len(sentences)} sentences, {len(words)} words, speakers={speakers or 'n/a'}, "
          f"low-confidence words={low}. Wrote {out/'transcript.json'} and {out/'transcript.txt'}")


if __name__ == "__main__":
    main()
