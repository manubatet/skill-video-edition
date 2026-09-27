# Social Video Editor — PRD

**Product.** An Agent Skill that edits Spanish talking-head videos into social-ready clips using only an LLM agent (Claude, ChatGPT, Codex) plus open-source tools.

**Problem.** Editing a 1–3 minute talking-head clip by hand means several separate chores, which together take 30–90 minutes per video:
- removing retakes and dead air;
- captioning;
- adding zooms and effects.

Existing auto-editors are closed SaaS products, work poorly in Spanish, and decorate blindly: effects go on every sentence regardless of meaning.

**Users.** Spanish-speaking creators and small teams publishing short videos (Reels, TikTok, Shorts, LinkedIn) from a single camera.

**Goals (v1).**
1. A raw video becomes an edited video with at most 2 human checkpoints: transcript and cuts, then preview.
2. Effects are chosen from the *meaning* of the speech, not at random.
3. The pipeline is reproducible and editable: every decision lives in a JSON file, so changing one cue never requires redoing the whole edit.
4. It is 100% open-source tooling plus any skills-capable LLM agent, and runs locally.

**Non-goals (v1).** Filler-word removal (explicitly rejected). Multi-camera editing. Background music. Auto-reframing between aspect ratios. Combining videos. Stock B-roll. Languages other than Spanish.

**User flow.** Upload video → two short question rounds (effects, then style guide: animation style and colour palette) → transcript and cut review → preview with QA → final video plus title, description, hashtags and thumbnail picks.

**Functional requirements (v1).**

| ID | Requirement |
|---|---|
| F1 | Transcription with word-level timestamps (WhisperX large-v3, Spanish alignment model), with glossary biasing |
| F2 | Optional speaker diarization (pyannote); otherwise the user states the speaker count |
| F3 | Retake and stutter removal decided by the agent; silence trimming by a word-gap threshold with padding; frame-accurate cuts |
| F4 | Audio: light denoise (FFmpeg afftdn, optional DeepFilterNet), two-pass loudness normalization to -14 LUFS, micro-fades at every cut, limiter after SFX |
| F5 | Captions: karaoke, word or phrase modes; 3 positions with platform safe zones; keyword highlighting; per-speaker colors |
| F6 | Sentence classification (role, importance) driving zooms, SFX and animations |
| F7 | Gradual push-in zooms (eased in and out, per-frame scale and crop) centered on the detected face (OpenCV) |
| F8 | SFX from a procedurally synthesized royalty-free library, with automatic lead-time alignment; user files can override it |
| F9 | Animations coded by the agent per video (Pillow-based kit, rendered as transparent overlays), with a self-review contact sheet |
| F10 | Density-rule validator (`--check`) that blocks over-decorated timelines |
| F11 | Fast preview plus a QA frame sheet; final H.264/AAC MP4 with faststart |
| F12 | Title, description, hashtags and thumbnail suggestions |

**Non-functional requirements.**
- Deterministic rendering: the same JSON gives the same video.
- Runs on CPU; a GPU is optional.
- No proprietary runtime dependencies.
- Rendering a 60 s 1080×1920 video takes under 3 minutes on a laptop CPU, excluding transcription.
- All intermediate files are human-readable (JSON, TXT, ASS).

**Architecture.**
```
video ─► transcribe.py ─► transcript.json ──(agent: retakes)──► edit.json
      ─► build_edit.py ─► cut.mkv + transcript_edited.json
      ──(agent: classify, plan)──► timeline.json ──(agent: code)──► anims/*.py ─► *.mov
      ─► render.py (validate ─► zooms ─► overlays ─► ASS captions ─► SFX mix ─► limiter) ─► preview / final
```

**Tech stack (all open source).**

| Component | Tool | License |
|---|---|---|
| Transcription and alignment | WhisperX, faster-whisper, wav2vec2 | BSD-2 / MIT |
| Speaker diarization | pyannote | MIT |
| Cuts, audio processing, rendering, captions | FFmpeg and libass | LGPL/GPL, ISC |
| Face detection | OpenCV | Apache-2.0 |
| Animation rendering | Pillow and numpy | MIT-CMU, BSD |
| SFX synthesis | numpy | BSD |
| Optional denoising | DeepFilterNet | MIT/Apache |
| Font | Montserrat | OFL |

**Success metrics.**
- Editing time under 10 minutes of human attention per video.
- At most 1 preview iteration on average.
- Fewer than 2% of words need correction after glossary use.
- Zero rule violations shipped.
- Qualitative: the user would publish the output without opening a manual editor.

**Risks and mitigations.**

| Risk | Mitigation |
|---|---|
| Whisper errors on names | Glossary, plus Checkpoint 1 |
| Over-decoration | Density rules and classification-driven placement |
| Clipped words at cuts | Padding plus frame-snapped cuts |
| Coded animations look amateur | Proven pattern list, style tokens, mandatory contact-sheet review |
| Model download blocked in sandboxes | Run transcription locally |
| Synthesized SFX sound basic | Drop-in replacement with CC0 files |

**Roadmap.**
- **v1.5:** animation pattern library (reusable parametrized files); B-roll suggestions.
- **v2:**
  - output formats and auto-reframe (MediaPipe face tracking);
  - video templates (animations only; animations plus emphasis; SFX on/off);
  - a style guide driving captions and animations;
  - combining two videos;
  - background music with ducking and beat-synced cuts (librosa);
  - clip extraction from long videos;
  - English subtitles.

**Open questions.**
- Should the style guide be a JSON token file or a Design System artifact?
- Is a Revideo-based renderer worth adopting if animations become the core of the product?
- Which platform presets beyond vertical safe zones are needed (LinkedIn 1:1, YouTube 16:9)?
