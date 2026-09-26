---
name: "social-video-editor"
description: "Edit a Spanish talking-head video for social media with open-source tools (WhisperX, FFmpeg, Pillow). Transcribes, cuts retakes and silences, adds captions, zooms, SFX and coded animations."
---

# Social Video Editor (Spanish, v1)

Turns a raw Spanish talking-head video into a social-ready edit: retakes and dead air removed, clean loud audio, burned-in captions with highlighted keywords, gradual (eased) push-in zooms, sparse sound effects and custom animations that Claude writes as code.

Appendix A holds the PRD (the why and the scope). Appendix B holds the scripts. This section holds the procedure.

## Core principles

1. **Claude decides, scripts execute.** Claude only writes JSON decision files and animation code. Deterministic scripts do all the media work. Never hand-edit video with ad-hoc FFmpeg commands when a script covers the step.
2. **Two decision files are the contract.**
   - `work/edit.json` holds what to cut, in source time.
   - `work/timeline.json` holds what to add, in edited time.
   Any change is an edit to one of these files followed by a re-run. Never re-run transcription to change an edit.
3. **Cut first, decorate second.** Cuts shift every timestamp. All effect timings refer to `transcript_edited.json`, which exists only after `build_edit.py` has run.
4. **Word ids are stable.** Every word keeps its original id `i` through the pipeline. Refer to words by id, never by list position.
5. **Pace is a rule, not a vibe.** `render.py --check` enforces density rules. Fix violations by removing effects, not with `--force`.
6. **Never remove filler words** ("eh", "este", "o sea", "pues", "bueno"). They are part of the speaker's voice. Only retakes, stutters, and pauses longer than `max_gap` are cut.

## Setup (once per machine)

The pipeline needs Python 3.9+, FFmpeg built with libass, and a machine that can download the Whisper models from Hugging Face. A GPU is optional: CPU with int8 works but is slower. On Apple Silicon, WhisperX runs on CPU.

1. Create a project folder next to the video: `<video-name>_edit/`. Every command below runs from inside that folder.
2. Write every file from Appendix B, **verbatim**, into `<project>/scripts/`.
3. Install and check the dependencies:
   ```bash
   pip install whisperx numpy pillow opencv-python-headless   # add --break-system-packages if pip asks
   ffmpeg -hide_banner -filters | grep -E " ass | loudnorm "     # both lines must appear
   python scripts/sfx_synth.py --out sfx                        # builds the default SFX library
   ```
4. Optional installs:
   - **Speaker diarization.** Create a free Hugging Face token and accept the terms of `pyannote/speaker-diarization-community-1`. Then pass `--hf-token` or set `HF_TOKEN`.
   - **Better denoising.** `pip install deepfilternet`, then set `"denoise": "deepfilter"`.
   - **Caption font.** Put a bold TTF (default: Montserrat ExtraBold, OFL license) in `work/fonts/`. Set `style.font` to the font's family name. Without it, captions fall back to a system font.
   - **Better SFX.** Any `.wav` placed in `sfx/` with the same name (for example a CC0 `whoosh.wav` from Freesound) replaces the synthesized one.

If a model download is blocked (sandboxed or offline machine), say so plainly. Ask the user to run the transcription step on their own machine, or to provide the `transcript.json`.

## Intake: two quick rounds

Ask with AskUserQuestion. The recommended option comes first. If nobody answers, use the defaults and state them. AskUserQuestion takes at most 4 questions and 4 options per question, and it always adds a free-text "Other". So the intake runs in two calls, back to back, before any heavy work starts.

### Round 1: what to add

1. **Captions**: Karaoke, 3 words with the current word highlighted (recommended) / One word at a time / Phrases / No captions.
2. **Caption position**: Bottom, above the platform UI (recommended) / Middle / Top.
3. **Effects**: a **multi-select** question (`multiSelect: true`), never single choice. Options: Punch-in zooms / Sound effects / Animations. Word the question so it is obvious that several can be ticked and that anything else can be written in the free-text "Other" field. For example: "¿Qué efectos quieres? Marca todos los que quieras. Si quieres añadir algo más (una escena animada a pantalla completa, un estilo concreto, algo a evitar…), escríbelo en 'Other'." If nobody answers, all three are on.
4. **Speakers**: One person (recommended) / Two / Three or more. Skip this question when a Hugging Face token is available: detect speakers instead and only confirm the result.

In the same message, also invite:
- a **glossary**: names, brands and anglicisms Whisper might misspell. Pass it to `--glossary`.
- **anything else to add**: an open line such as "¿Hay algo más que quieras añadir o que deba tener en cuenta?". Treat whatever comes back, here or in "Other", as a requirement. Plan it in the proposal table (Checkpoint 1) like any other effect.

### Round 2: style guide (right after round 1)
Ask this round when captions or animations are on. Skip it only when both are off.

5. **Animation style**: ask only if Animations was selected. Single choice. The question text must invite a custom style in "Other", for example: "¿Qué estilo quieres para las animaciones? Si ninguno encaja, descríbelo en 'Other' (referencias, marcas, cuentas que te gusten…)." Offer the four presets from *Animation style presets*, with the one that best fits the video's tone first as "(Recommended)":
   - **Tarjetas bold**: pills sólidas, rebote, tipografía gruesa en mayúsculas.
   - **Minimal limpio**: líneas finas, fundidos y deslizamientos suaves, sin rebote.
   - **Flat 2D ilustrado**: iconos y personajes simples de colores planos.
   - **Neón tech**: fondo oscuro, bordes brillantes, entradas rápidas.
6. **Color palette (style guide)**: single choice. Offer the four presets from *Color palette presets*. Put the five HEX codes in each option's `description`, so the user sees the actual colours. Put the preset that best fits the video's topic first as "(Recommended)". The question text must explain the "Other" format, for example: "¿Qué paleta de colores usamos? Si tienes la tuya, escribe en 'Other' hasta 5 colores HEX en este orden: fondo, texto, principal, secundario, alerta (p. ej. #1E3A4C, #F7F5F0, #5EC2B7, #F4A261, #E76F51)."

Custom answers:
- **Custom style:** a free-text style becomes `style.anim_style`, holding the user's description. Derive its motion and shape rules from the nearest preset and state them at Checkpoint 1.
- **Custom palette:** for HEX codes, accept `#RGB`, `#RRGGBB` or codes without `#`, separated by commas or spaces. Map them in order to the five roles.
  - With fewer than 5 colours, fill the missing roles from the closest preset.
  - With more than 5 colours, use the first 5 and say so.
  - With an invalid code, ask again only for that value.
  - Colour names ("azul marino") are also accepted: convert them to HEX and show the codes you chose.

## Workflow

### 1. Transcribe
```bash
python scripts/transcribe.py INPUT.mp4 --out work --glossary "Nombre, Marca" [--speakers N] [--hf-token T]
```
This writes `work/transcript.json`, with word-level `start`, `end`, `score` and `speaker`, plus `work/transcript.txt`. Words with a score below 0.4 are likely mistranscriptions. Check them first.

### 2. Checkpoint 1: transcript, cut plan and effects proposal (one message)
Read `transcript.json` and propose the cuts, following the rules in *Editorial rules > Retakes*. Before writing the message, extract one or two frames (`ffmpeg -ss T -i INPUT -frames:v 1 f.jpg`) and look at them. You need them to spot things that change the plan: burned-in subtitles or titles, landscape framing, and where the free space for animations is.

Show the user three things:
- the transcript, with suspicious words marked;
- the proposed removals as a short list, for example "S3 removed: retake of S4" or "w120–w123 removed: stutter 'la la'";
- the **effects proposal table**. This is required whenever animations are enabled, and it goes in this first message, not later. Use exactly these columns, one row per animation:

| # | Momento | Frase | Animación | Por qué |
|---|---|---|---|---|
| a1 | 0,1 s → 1,6 s | "**Sí**, se puede superar" | **Sello de check**: círculo verde con rebote, ✓ que se dibuja trazo a trazo, "SÍ" debajo | Gancho: responde a la pregunta en el primer segundo |

  Column rules:
  - **Momento** is in source seconds at this stage; say that times shift slightly after the cuts.
  - **Frase** quotes the words it illustrates, with the key word in bold.
  - **Animación** names the pattern in bold, then describes motion, text and colours in one line.
  - **Por qué** ties it to the sentence's role (hook, data, key claim, cta…).

  Under the table add:
  - one line on **where** the animations sit (the free area of the frame and the box size), and why it avoids the face and any burned-in text;
  - one line on the **look**: the chosen palette (key and its 5 HEX codes), the `anim_style` row, the font and the entry/hold/exit timing;
  - when zooms or emphasis words are on, a short list of the sentences that get a zoom and the words that get highlighted.

  Offer optional extras as a separate "Opcional" line instead of silently adding them.

Ask them to correct wrong words, confirm the cuts and approve or change the table. After the cuts, carry the approved rows into `timeline.json` with edited times. If the user asks to see the plan again, re-show it in the same table.

To apply text fixes, edit the `text` of words in `work/transcript.json` with a small Python snippet. Keep word count and timings unchanged. If a fix merges or splits words, adjust only the text and keep the original number of word entries. Then write `work/edit.json` (schema in `build_edit.py`'s docstring).

### 3. Cut and clean
```bash
python scripts/build_edit.py --work work
```
This writes `work/cut.mkv` (cuts, light denoise, two-pass loudness normalization to -14 LUFS), `work/segments.json` and `work/transcript_edited.json/.txt`. Report the before and after duration.

### 4. Classify and plan effects
Read `transcript_edited.json`. Then write `work/timeline.json` (schema below), following *Editorial rules* and the table approved at Checkpoint 1. Include the `classification` array: it documents the reasoning and makes later changes easy to discuss. If an approved row cannot be placed as agreed (for example two animations now violate `anim_min_gap`), show the updated table and say what changed.

### 5. Code the animations
For each entry in `animations`, write `work/anims/<id>.py` using `anim_kit` (see *Animation guide*). Run it. Then **open the generated `<id>_sheet.png` with Read and inspect it** before continuing. Fix overflowing text, clipped shapes, unreadable contrast and timing that looks wrong.

### 6. Validate and preview
```bash
python scripts/render.py --work work --check
python scripts/render.py --work work --preview --sheet
```
Open `work/qa_sheet.jpg` with Read. It holds one frame per zoom and animation, plus caption samples. Check the QA list below. Fix any problem, then re-render.

### 7. Checkpoint 2: preview
Send `work/preview.mp4` and a three-line summary of what was added. Apply feedback by editing `timeline.json` or `edit.json`. Re-run `build_edit.py` only if the cuts changed.

### 8. Final render and extras
```bash
python scripts/render.py --work work
```
Deliver `work/final.mp4`. Also give the extras in the reply, derived from the transcript:
- a title (up to 60 characters);
- a description (2–3 lines, Spanish);
- 5–8 hashtags;
- the 2–3 best thumbnail moments. Extract candidate frames with `ffmpeg -ss T -i work/final.mp4 -frames:v 1 thumb_T.jpg`, look at them, and pick expressive faces at high-importance sentences.

## timeline.json schema (all times in edited seconds)

```json
{
  "style": {"font": "Montserrat", "text": "#FFFFFF", "highlight": "#FFD400", "emphasis": "#00E676",
            "outline": "#000000", "accent": "#FFD400", "accent_text": "#111111",
            "panel": "#111111", "panel_text": "#FFFFFF", "danger": "#FF3B3B",
            "palette": "energia", "anim_style": "bold"},
  "captions": {"mode": "karaoke", "position": "bottom", "uppercase": true, "max_words": 3, "size": 0.07},
  "classification": [{"sentence": 0, "role": "hook", "importance": "high", "why": "promete 3 claves"}],
  "emphasis_words": [6, 7, 32],
  "zooms": [{"start": 4.72, "end": 6.58, "scale": 1.15, "ramp": 0.7}],
  "sfx": [{"at": 5.0, "sound": "whoosh", "gain_db": -10}],
  "animations": [{"id": "a1", "file": "work/anims/a1.mov", "start": 2.15, "anchor": "upper-third",
                  "hide_captions": false}],
  "zoom_center": null,
  "rules": {}
}
```

Field notes:
- **`captions.mode`**: `karaoke` | `word` | `sentence` | `off`.
- **`captions.position`**: `bottom` | `middle` | `top`. Positions already respect the TikTok and Reels safe zones for vertical video.
- **`sfx.at`**: the moment the sound should *land*. `render.py` subtracts each sound's lead time automatically, for example 0.22 s for `whoosh` and 1.2 s for `riser`. Set `"align": "start"` to disable this.
- **Available sounds**: `whoosh` (transitions, new point), `pop` (a word or card appears), `ding` (number or result), `click` (list item), `riser` (build-up before a reveal), `boom` (big claim, use at most once per video).
- **`animations.anchor`**: `top` | `upper-third` | `center` | `lower-third`. Alternatively give explicit `x` and `y` in pixels for the top-left corner. Use `hide_captions: true` when an animation replaces the captions for its duration.
- **`zooms`**: every zoom is a **gradual push-in**, never a hard cut. The scale eases in (smoothstep) over `ramp` seconds from `start`, holds, then eases back out over `ramp` seconds before `end`. The default `ramp` is **0.7 s**, capped at half the zoom length. Keep the default; lower it (0.35) only when the user asks for a snappier style. `"ramp": 0` gives the old hard punch-in, so use it only when the user asks for jump-cut style. Because the ramp eats into the zoom, start it about `ramp`/2 (≈0.3 s) before the key word, so the zoom is fully in when the word lands. Make zooms at least 1.4 s long, so both full ramps fit. Shorter ones never reach full scale and read as a quick breathe-in.
- **`zoom_center`**: leave it `null`. It is detected from the face, falling back to `[0.5, 0.4]`. Set it by hand when the source has burned-in text that the zoom would cut in half. Choose a centre whose crop either keeps that text whole or leaves it out entirely.
- **`rules`**: overrides the density limits in `render.py` (`RULES`). Change a limit only when the user asks for a denser or calmer style.

## Editorial rules

**Retakes.** A retake is the same idea started twice. Keep the **last complete take**, because speakers usually improve on the repeat.
- Remove the earlier attempt(s) with `remove_sentences`, or with `remove_words` when only the start of a sentence is repeated.
- Stutters ("la la constancia") are removed with a `remove_words` range covering the duplicate word(s).
- Explicit restart markers ("perdón", "espera", "vuelvo a empezar", "corta") are always removed, together with the failed attempt before them.
- When unsure, keep the material and flag it at Checkpoint 1.

**Classification.** Give every sentence a `role` and an `importance`.

| Role | Typical signals (Spanish) | Treatment |
|---|---|---|
| hook | first 1–2 sentences, promise, question | an animation or zoom before 3 s, plus `pop` or `whoosh` |
| list / structure | "tres claves", "primero", "la segunda" | keyword card animation + `whoosh` or `click` |
| data | numbers, %, money, dates | counter animation + `ding`; the number is an emphasis word |
| punchline / key claim | contrast ("pero", "en realidad"), strong verbs | zoom 1.25–1.3 + 1–2 emphasis words |
| explanation | supporting detail | zoom 1.15 or nothing (alternate framing) |
| story | anecdote, "un día…" | calm: captions only, maybe a gentle 1.1 zoom |
| cta | "sígueme", "comenta", "guarda" | small card animation at the end |

**Pacing.**
- Change framing (zoom on or off) roughly every 4–8 s. A long unbroken shot longer than 10 s is the most common sign that an edit feels slow.
- Emphasis words: at most 1 per sentence. Always content words (numbers, nouns, verbs), never articles or connectors.
- Something must happen in the first 3 s.
- Fewer, well-timed effects beat many. When in doubt, leave it out.

**Timing.**
- Start zooms at the **start of a word**, ideally the first word of the sentence, and end them at a sentence boundary. Zooms ease in and out (`ramp`), so they read as a camera push, not a cut.
- Animations start about 0.1 s before the word they illustrate. Sounds land on the word, or on the animation's entry.
- Spanish specifics: Whisper's `¿`, `¡` and accents stay in the captions. Numbers often lack timestamps; they are interpolated, so check them in the QA sheet.

## Animation guide (Claude writes code)

Each animation is one Python file using `scripts/anim_kit.py`. It renders to a transparent `.mov` that is overlaid on the video. The API:
- `Anim(w, h, duration, fps=30)`: sets the size of the animation box, not the full frame. Keep boxes small; typical sizes are 600–900 × 200–450 px for a 1080-wide video.
- `@anim.draw def frame(c, t)`: `t` is in seconds.
- Primitives: `c.rect`, `c.circle`, `c.line`, `c.arc`, `c.text`.
- `c.group(scale, alpha, origin, dx, dy, rotate)` animates several elements as one unit.
- `c.progress(t, start, dur)` returns a local 0–1 progress value, to pass through `ease.*` (`out_back`, `out_cubic`, `in_cubic`, `in_out_cubic`, `out_quint`, `out_elastic`).
- `c.fit(text, max_w, size)`: **always** use it for text that must fit a shape.
- `anim.render(path)` and `anim.sheet(path)`.

Design rules:
- Duration 1.2–2.5 s, with three phases: **entry** 0.25–0.4 s (`out_back` for pop, `out_cubic` for slide), **hold**, **exit** 0.2–0.3 s (`in_cubic` fade or shrink).
- At most 4 words of text, drawn large. Motion supports the speech; it never competes with it.
- Colors come only from `load_style()`: tokens `accent`, `accent_text`, `panel`, `panel_text`, `text`, `emphasis`, `highlight`, `danger`. Never hard-code a HEX in an animation. This is what lets the palette chosen at intake restyle everything without code changes.
- Motion and shape follow `style.anim_style` (see *Animation style presets* below).
- No emoji or bitmap logos (fonts render them unreliably). Draw simple icons from primitives: a check mark is a `line`, a progress ring is an `arc`, an arrow is a `line` with a head.
- Proven patterns:
  - keyword card (pill plus word, pop-in);
  - number counter (count up with `out_quint`, ring or bar filling);
  - list reveal (items slide in, staggered by 0.15 s);
  - before/after split;
  - check or cross stamp;
  - progress bar.

Example: a working keyword card.

```python
import sys; sys.path.insert(0, "scripts")
from anim_kit import Anim, ease, load_style
S = load_style("work")
anim = Anim(w=820, h=300, duration=1.8)

@anim.draw
def frame(c, t):
    p = ease.out_back(c.progress(t, 0.0, 0.35))
    out = 1 - ease.in_cubic(c.progress(t, 1.5, 0.3))
    with c.group(scale=0.5 + 0.5 * p, alpha=min(1, p * 1.5) * out, origin=(410, 150)):
        c.rect(30, 45, 760, 210, S["accent"], radius=48)
        c.text("3 CLAVES", 410, 150, c.fit("3 CLAVES", 680, 118), S["accent_text"])

anim.render("work/anims/a1.mov"); anim.sheet("work/anims/a1_sheet.png")
```

## Animation style presets

The intake answer is stored in `style.anim_style`. Every animation in the video follows the same row. The proven patterns above work in every style; only their motion and shapes change.

| Preset (`anim_style`) | Entry / exit | Shapes | Text | Idle motion |
|---|---|---|---|---|
| `bold`: Tarjetas bold (default) | `out_back` pop 0.3 s from scale 0.5; exit `in_cubic` shrink and fade 0.25 s | solid `accent` pills or `panel` at alpha 0.85, radius 40–48 | ExtraBold, UPPERCASE, as large as fits | none; the hold is still |
| `minimal`: Minimal limpio | `out_cubic` fade plus 12–20 px slide, 0.4 s; no overshoot; exit a plain fade 0.3 s | thin lines (width 3–4) and outlines, `panel` alpha ≤ 0.6 or no panel, radius 10–14 | regular or bold weight, sentence case, 20–30 % smaller than bold | none |
| `flat2d`: Flat 2D ilustrado | `out_back` with a small overshoot, 0.35 s; elements stagger by 0.1–0.15 s | icons and characters built from primitives, flat fills, no outlines, soft background shapes | bold, sentence case, short labels | gentle wiggle or bob (1–3 px, `sin(t·k)`), blinking eyes, walk cycles; best for full-screen scenes |
| `neon`: Neón tech | fast `out_quint` slide 0.2 s from off-box; exit a fast slide out | dark `panel` alpha 0.9; `accent` outline width 3 plus glow (2–3 wider outlines at alpha 0.25 → 0.08) | ExtraBold UPPERCASE, `accent` or `text` colour | subtle glow pulse (alpha ±0.1 at 1–2 Hz) |

For a free-text style, pick the nearest row and adapt it. At Checkpoint 1, name the row and write one line on what you changed.

## Color palette presets

Each palette has 5 colours with fixed roles: **fondo** (dark base), **texto** (light), **principal**, **secundario**, **alerta**. They map to the `style` tokens like this:
- `panel` and `accent_text` = fondo;
- `text` and `panel_text` = texto;
- `accent` and `highlight` = principal;
- `emphasis` = secundario;
- `danger` = alerta;
- `outline` = `#000000`, always, so captions stay readable on any footage.

Also set `style.palette` to the preset's key, or to `"custom"`.

| Key | Option label | fondo | texto | principal | secundario | alerta | Fits |
|---|---|---|---|---|---|---|---|
| `energia` | Energía (amarillo) | `#111111` | `#FFFFFF` | `#FFD400` | `#00E676` | `#FF3B3B` | tips, motivación, negocio; the default |
| `calma` | Calma (salud) | `#1E3A4C` | `#F7F5F0` | `#5EC2B7` | `#F4A261` | `#E76F51` | salud, psicología, bienestar, educación |
| `pop` | Pop (rosa y violeta) | `#1A1033` | `#FFFFFF` | `#FF4FA3` | `#7C5CFF` | `#FFD23F` | lifestyle, moda, belleza, entretenimiento |
| `tierra` | Tierra (elegante) | `#2B2622` | `#FAF6F0` | `#D9B26F` | `#8DB38B` | `#C4553A` | gastronomía, viajes, marca personal premium |

All four keep at least 3:1 WCAG contrast for every role on `fondo`, and at least 4.5:1 for texto and principal. With a custom palette:
- Check the same contrasts.
- If principal on fondo is below 3:1, use texto as `accent_text` instead of fondo, and tell the user.
- If texto on fondo is below 4.5:1, warn the user and propose the nearest fix.

## QA checklist (preview and QA sheet)

- Captions are readable and never cover the face or an animation. Keywords are highlighted.
- Zoomed frames keep the face whole, with no forehead cut off, and are not blurry. If they are blurry, lower the scale.
- Zooms push in and out smoothly in the preview, with no visible jump. A zoom that looks like a cut has `ramp` 0 or is too short for its ramp.
- Animations sit inside the frame and outside the bottom 20% on vertical video, with no text overflow.
- `render.py --check` passes with no RULE lines. WARN lines are either fixed or deliberately accepted.
- Cuts sound natural: no clipped word starts. If a word start is clipped, raise `pad` to 0.15–0.2 s.
- Audio and video have equal durations (`ffprobe` both streams).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Words cut off at the edges of cuts | raise `pad` in `edit.json`; lower it (0.08) if the edit feels slow |
| Edit feels choppy | raise `max_gap` to 0.6 |
| Wrong names in captions | `--glossary`, or fix the word texts at Checkpoint 1 |
| Captions use the wrong font | the font file is missing from `work/fonts/`, or `style.font` doesn't match its family name (`fc-scan file.ttf`) |
| Zoom crops the face | set `zoom_center` manually to `[x, y]` (normalized face position) |
| Audio pumps or sounds robotic | `"denoise": "off"` |

## Roadmap hooks (don't build unless asked)

v2 items, in the PRD, fit into the existing contracts without rewrites:
- **Style guide** → `timeline.style` (palette and animation-style presets exist; a full brand guide would extend them).
- **Templates** → preset `timeline.rules` and effect toggles.
- **Format / auto-reframe** → a crop pass in `build_edit.py`.
- **Combining videos** → multiple sources in `segments.json`.
- **Music with ducking** → one more audio input in `render.py`.

---

## Appendix A — PRD

**Product.** A Claude skill that edits Spanish talking-head videos into social-ready clips using only Claude plus open-source tools.

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
4. It is 100% open-source tooling plus Claude, and runs locally.

**Non-goals (v1).** Filler-word removal (explicitly rejected). Multi-camera editing. Background music. Auto-reframing between aspect ratios. Combining videos. Stock B-roll. Languages other than Spanish.

**User flow.** Upload video → two short question rounds (effects, then style guide: animation style and colour palette) → transcript and cut review → preview with QA → final video plus title, description, hashtags and thumbnail picks.

**Functional requirements (v1).**

| ID | Requirement |
|---|---|
| F1 | Transcription with word-level timestamps (WhisperX large-v3, Spanish alignment model), with glossary biasing |
| F2 | Optional speaker diarization (pyannote); otherwise the user states the speaker count |
| F3 | Retake and stutter removal decided by Claude; silence trimming by a word-gap threshold with padding; frame-accurate cuts |
| F4 | Audio: light denoise (FFmpeg afftdn, optional DeepFilterNet), two-pass loudness normalization to -14 LUFS, micro-fades at every cut, limiter after SFX |
| F5 | Captions: karaoke, word or phrase modes; 3 positions with platform safe zones; keyword highlighting; per-speaker colors |
| F6 | Sentence classification (role, importance) driving zooms, SFX and animations |
| F7 | Gradual push-in zooms (eased in and out, per-frame scale and crop) centered on the detected face (OpenCV) |
| F8 | SFX from a procedurally synthesized royalty-free library, with automatic lead-time alignment; user files can override it |
| F9 | Animations coded by Claude per video (Pillow-based kit, rendered as transparent overlays), with a self-review contact sheet |
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
video ─► transcribe.py ─► transcript.json ──(Claude: retakes)──► edit.json
      ─► build_edit.py ─► cut.mkv + transcript_edited.json
      ──(Claude: classify, plan)──► timeline.json ──(Claude: code)──► anims/*.py ─► *.mov
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

---

## Appendix B — Scripts

Write each file verbatim to `scripts/<name>`. They depend only on Python's standard library, numpy, Pillow, OpenCV and FFmpeg. `transcribe.py` also needs WhisperX.

### scripts/common.py

```python
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
```

### scripts/transcribe.py

```python
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
```

### scripts/build_edit.py

```python
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
```

### scripts/captions.py

```python
"""Build an ASS subtitle file (burned in later by libass) from the edited transcript + timeline.

Modes (timeline.captions.mode):
  word      one word at a time, big, with a pop-in
  karaoke   short groups (max_words), the word being spoken is highlighted
  sentence  phrase chunks (max_words_sentence), no per-word highlight
  off       no captions
Emphasis words (timeline.emphasis_words, original word ids) are always drawn in the
emphasis colour and slightly larger, in every mode.

Usage (normally called by render.py):  python captions.py --work work/
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import load  # noqa: E402

CAPTION_DEFAULTS = {"mode": "karaoke", "position": "bottom", "uppercase": True, "max_words": 3,
                    "max_words_sentence": 7, "size": 0.07, "pop": True}
STYLE_DEFAULTS = {"font": "Montserrat", "bold": True, "text": "#FFFFFF", "highlight": "#FFD400",
                  "emphasis": "#00E676", "outline": "#000000", "outline_ratio": 0.09,
                  "speaker_colors": ["#FFFFFF", "#8FD3FF", "#FFB3C7", "#C9F7A5"]}


def ass_color(hex_rgb, alpha=0):
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ts(t):
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    cs = int(round((s - int(s)) * 100))
    s = int(s)
    if cs == 100:
        s, cs = s + 1, 0
    return f"{int(h)}:{int(m):02d}:{s:02d}.{cs:02d}"


def clean(text, upper):
    text = re.sub(r"[,.;:…]+$", "", text.strip())
    text = text.replace("\\", "").replace("{", "(").replace("}", ")")
    return text.upper() if upper else text


def anchor_xy(position, w, h):
    vertical = h > w
    x = int(w * (0.47 if vertical else 0.5))  # vertical: nudge left of TikTok/Reels side buttons
    y = {"bottom": 0.72 if vertical else 0.88,
         "middle": 0.56,
         "top": 0.20 if vertical else 0.12}[position]
    return x, int(h * y)


def group_words(words, max_words, sentence_mode=False):
    groups, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        brk = (nxt is None or len(cur) >= max_words
               or nxt["sentence"] != w["sentence"]
               or nxt.get("speaker") != w.get("speaker")
               or nxt["start"] - w["end"] > 0.35
               or (re.search(r"[.?!…]$", w["text"]) is not None)
               or (not sentence_mode and sum(len(x["text"]) for x in cur) > 16))
        if brk:
            groups.append(cur)
            cur = []
    return groups


def build_ass(transcript, timeline):
    cap = {**CAPTION_DEFAULTS, **timeline.get("captions", {})}
    st = {**STYLE_DEFAULTS, **timeline.get("style", {})}
    w, h = transcript["width"], transcript["height"]
    size = int(min(w, h) * cap["size"])
    outline = max(2, int(size * st["outline_ratio"]))
    emph = set(timeline.get("emphasis_words", []))
    speakers = transcript.get("speakers") or []
    multi = len(speakers) > 1
    spk_color = {s: st["speaker_colors"][k % len(st["speaker_colors"])] for k, s in enumerate(speakers)}
    hide = [(a["start"], a["start"] + a.get("duration", 0)) for a in timeline.get("animations", [])
            if a.get("hide_captions")]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{st['font']},{size},{ass_color(st['text'])},{ass_color(st['highlight'])},{ass_color(st['outline'])},{ass_color('#000000', 0x80)},{-1 if st['bold'] else 0},0,0,0,100,100,0,0,1,{outline},{max(1, outline // 3)},5,{int(w*0.1)},{int(w*0.1)},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    if cap["mode"] == "off":
        return header
    words = transcript["words"]
    x, y = anchor_xy(cap["position"], w, h)
    pos = f"\\pos({x},{y})"
    pop = "\\fscx82\\fscy82\\t(0,90,\\fscx100\\fscy100)" if cap["pop"] else ""

    def word_tag(wd, current=False):
        txt = clean(wd["text"], cap["uppercase"])
        if not txt:
            return ""
        if wd["i"] in emph:
            return f"{{\\c{ass_color(st['emphasis'])}\\fscx115\\fscy115}}{txt}{{\\r}}"
        if current:
            return f"{{\\c{ass_color(st['highlight'])}}}{txt}{{\\r}}"
        if multi and wd.get("speaker") in spk_color:
            return f"{{\\c{ass_color(spk_color[wd['speaker']])}}}{txt}{{\\r}}"
        return txt

    events = []
    mw = 1 if cap["mode"] == "word" else cap["max_words"] if cap["mode"] == "karaoke" else cap["max_words_sentence"]
    groups = group_words(words, mw, sentence_mode=cap["mode"] == "sentence")
    for gi, g in enumerate(groups):
        g_start = g[0]["start"]
        nxt_start = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else g[-1]["end"] + 0.5
        g_end = min(g[-1]["end"] + 0.25, nxt_start)
        if cap["mode"] == "karaoke" and len(g) > 1:
            for k, wd in enumerate(g):
                a = g_start if k == 0 else wd["start"]
                b = g[k + 1]["start"] if k + 1 < len(g) else g_end
                body = " ".join(filter(None, (word_tag(x, current=(j == k)) for j, x in enumerate(g))))
                events.append((a, b, f"{{{pos}{pop if k == 0 else ''}}}{body}"))
        else:
            body = " ".join(filter(None, (word_tag(x) for x in g)))
            events.append((g_start, g_end, f"{{{pos}{pop}}}{body}"))

    lines = []
    for a, b, text in events:
        mid = (a + b) / 2
        if any(s <= mid <= e for s, e in hide) or b - a < 0.02:
            continue
        lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Cap,,0,0,0,,{text}")
    return header + "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work")
    args = ap.parse_args()
    work = Path(args.work)
    ass = build_ass(load(work / "transcript_edited.json"), load(work / "timeline.json"))
    (work / "captions.ass").write_text(ass, encoding="utf-8")
    print(f"OK: wrote {work/'captions.ass'}")


if __name__ == "__main__":
    main()
```

### scripts/anim_kit.py

```python
"""Tiny animation kit: Claude writes an animation as Python code, this renders it to a
transparent .mov (PNG codec, alpha) that render.py overlays on the video.

Example (work/anims/a1.py):
    import sys; sys.path.insert(0, "scripts")
    from anim_kit import Anim, ease, load_style
    S = load_style("work")
    anim = Anim(w=900, h=300, duration=1.8)

    @anim.draw
    def frame(c, t):
        p = ease.out_back(c.progress(t, 0.0, 0.35))          # entry 0..1
        out = 1 - ease.in_cubic(c.progress(t, 1.5, 0.3))     # exit 1..0
        with c.group(scale=0.6 + 0.4 * p, alpha=min(p, out), origin=(450, 150)):
            c.rect(40, 40, 820, 220, S["accent"], radius=40)
            c.text("3 CLAVES", 450, 150, 110, S["accent_text"])

    anim.render("work/anims/a1.mov")      # transparent video
    anim.sheet("work/anims/a1_sheet.png")  # 5 frames on a checkerboard, to inspect with Read

Coordinates are output pixels inside the animation box (w x h); drawing is 2x
supersampled for smooth edges. The kit only uses Pillow + numpy + FFmpeg.
"""
import math
import subprocess
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STYLE_DEFAULTS = {"font": "Montserrat", "text": "#FFFFFF", "highlight": "#FFD400", "emphasis": "#00E676",
                  "outline": "#000000", "accent": "#FFD400", "accent_text": "#111111",
                  "panel": "#111111", "panel_text": "#FFFFFF", "danger": "#FF3B3B",
                  "anim_style": "bold"}


def load_style(work="work"):
    import json
    p = Path(work) / "timeline.json"
    st = dict(STYLE_DEFAULTS)
    if p.exists():
        st.update(json.loads(p.read_text(encoding="utf-8")).get("style", {}))
    return st


class ease:
    linear = staticmethod(lambda x: x)
    in_cubic = staticmethod(lambda x: x ** 3)
    out_cubic = staticmethod(lambda x: 1 - (1 - x) ** 3)
    in_out_cubic = staticmethod(lambda x: 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2)
    out_quint = staticmethod(lambda x: 1 - (1 - x) ** 5)

    @staticmethod
    def out_back(x, s=1.70158):
        return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2

    @staticmethod
    def out_elastic(x):
        if x in (0, 1):
            return x
        return 2 ** (-10 * x) * math.sin((x * 10 - 0.75) * (2 * math.pi) / 3) + 1


def lerp(a, b, p):
    return a + (b - a) * p


def rgba(color, alpha=1.0):
    if isinstance(color, tuple):
        return color[:3] + (int(255 * alpha),)
    h = color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * alpha))


@lru_cache(maxsize=None)
def font_path(family, weight="bold"):
    # 1) fonts dropped in work/fonts (same folder libass uses for captions)
    key = family.lower().replace(" ", "")
    local = sorted(p for p in Path("work/fonts").glob("*.[to]tf") if key in p.name.lower().replace(" ", "").replace("-", ""))
    if local:
        pref = [p for p in local if weight.lower() in p.name.lower()] or local
        return str(pref[0])
    # 2) system fonts via fontconfig
    for query in (f"{family}:{weight}", f"{family}", f"DejaVu Sans:{weight}"):
        try:
            p = subprocess.run(["fc-match", "-f", "%{file}", query], capture_output=True, text=True).stdout
            if p and Path(p).exists() and (family.lower().replace(" ", "") in p.lower().replace(" ", "")
                                           or query.startswith("DejaVu")):
                return p
        except FileNotFoundError:
            break
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if Path(p).exists():
            return p
    return None


@lru_cache(maxsize=256)
def _font(path, px):
    return ImageFont.truetype(path, px) if path else ImageFont.load_default()


class Canvas:
    def __init__(self, w, h, ss, style):
        self.w, self.h, self.ss, self.style = w, h, ss, style
        self._stack = [Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))]

    @staticmethod
    def progress(t, start, dur):
        return 0.0 if t <= start else 1.0 if dur <= 0 or t >= start + dur else (t - start) / dur

    @property
    def img(self):
        return self._stack[-1]

    def _s(self, v):
        return int(round(v * self.ss))

    def _layer(self):
        return Image.new("RGBA", self.img.size, (0, 0, 0, 0))

    def _put(self, layer):
        self._stack[-1] = Image.alpha_composite(self.img, layer)

    def rect(self, x, y, w, h, fill, radius=0, alpha=1.0, outline=None, width=0):
        L = self._layer()
        ImageDraw.Draw(L).rounded_rectangle([self._s(x), self._s(y), self._s(x + w), self._s(y + h)],
                                            radius=self._s(radius), fill=rgba(fill, alpha),
                                            outline=rgba(outline, alpha) if outline else None,
                                            width=self._s(width))
        self._put(L)

    def circle(self, cx, cy, r, fill=None, alpha=1.0, outline=None, width=0):
        L = self._layer()
        ImageDraw.Draw(L).ellipse([self._s(cx - r), self._s(cy - r), self._s(cx + r), self._s(cy + r)],
                                  fill=rgba(fill, alpha) if fill else None,
                                  outline=rgba(outline, alpha) if outline else None, width=self._s(width))
        self._put(L)

    def line(self, points, color, width=6, alpha=1.0):
        L = self._layer()
        pts = [(self._s(x), self._s(y)) for x, y in points]
        d = ImageDraw.Draw(L)
        d.line(pts, fill=rgba(color, alpha), width=self._s(width), joint="curve")
        r = self._s(width) / 2
        for px, py in (pts[0], pts[-1]):  # round caps
            d.ellipse([px - r, py - r, px + r, py + r], fill=rgba(color, alpha))
        self._put(L)

    def arc(self, cx, cy, r, start_deg, end_deg, color, width=10, alpha=1.0):
        L = self._layer()
        ImageDraw.Draw(L).arc([self._s(cx - r), self._s(cy - r), self._s(cx + r), self._s(cy + r)],
                              start_deg, end_deg, fill=rgba(color, alpha), width=self._s(width))
        self._put(L)

    def text(self, s, x, y, size, color, anchor="mm", alpha=1.0, weight="bold", family=None,
             stroke=0, stroke_color="#000000"):
        L = self._layer()
        f = _font(font_path(family or self.style["font"], weight), self._s(size))
        ImageDraw.Draw(L).text((self._s(x), self._s(y)), s, font=f, fill=rgba(color, alpha), anchor=anchor,
                               stroke_width=self._s(stroke), stroke_fill=rgba(stroke_color, alpha))
        self._put(L)

    def text_width(self, s, size, weight="bold", family=None):
        f = _font(font_path(family or self.style["font"], weight), self._s(size))
        return f.getlength(s) / self.ss

    def fit(self, s, max_w, size, weight="bold", family=None, min_size=12):
        """Largest font size <= size at which text s fits in max_w pixels. Always use it for
        dynamic text (numbers, user words) so nothing overflows its shape."""
        while size > min_size and self.text_width(s, size, weight, family) > max_w:
            size -= 2
        return size

    @contextmanager
    def group(self, scale=1.0, alpha=1.0, origin=None, dx=0, dy=0, rotate=0):
        """Draw children on their own layer, then scale/rotate/move/fade them as one."""
        self._stack.append(self._layer())
        yield self
        layer = self._stack.pop()
        ox, oy = origin if origin else (self.w / 2, self.h / 2)
        ox, oy = self._s(ox), self._s(oy)
        if rotate:
            layer = layer.rotate(rotate, resample=Image.BICUBIC, center=(ox, oy))
        if abs(scale - 1) > 1e-3 and scale > 0.01:
            W, H = layer.size
            sw, sh = max(1, int(W * scale)), max(1, int(H * scale))
            scaled = layer.convert("RGBa").resize((sw, sh), Image.BICUBIC).convert("RGBA")
            layer = self._layer()
            layer.paste(scaled, (int(ox - ox * scale), int(oy - oy * scale)))  # plain copy onto empty layer
        elif scale <= 0.01:
            return
        if dx or dy:
            moved = self._layer()
            moved.paste(layer, (self._s(dx), self._s(dy)))
            layer = moved
        if alpha < 1:
            a = layer.getchannel("A").point(lambda v: int(v * max(alpha, 0)))
            layer.putalpha(a)
        self._put(layer)


class Anim:
    def __init__(self, w, h, duration, fps=30, ss=2, style=None, work="work"):
        self.w, self.h, self.duration, self.fps, self.ss = int(w), int(h), duration, fps, ss
        self.style = style or load_style(work)
        self._fn = None

    def draw(self, fn):
        self._fn = fn
        return fn

    def frame_at(self, t):
        c = Canvas(self.w, self.h, self.ss, self.style)
        self._fn(c, t)
        img = c.img
        if self.ss != 1:
            img = img.convert("RGBa").resize((self.w, self.h), Image.LANCZOS).convert("RGBA")
        return img

    def render(self, out):
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        n = max(1, int(round(self.duration * self.fps)))
        p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                              "-s", f"{self.w}x{self.h}", "-r", str(self.fps), "-i", "-",
                              "-c:v", "png", "-pix_fmt", "rgba", str(out)], stdin=subprocess.PIPE)
        for k in range(n):
            p.stdin.write(self.frame_at(k / self.fps).tobytes())
        p.stdin.close()
        if p.wait() != 0:
            raise SystemExit(f"ffmpeg failed rendering {out}")
        print(f"OK: {out} ({self.w}x{self.h}, {self.duration}s, {n} frames)")

    def sheet(self, out, times=(0.08, 0.2, 0.45, 0.75, 0.97)):
        """Contact sheet on a checkerboard so transparency and timing can be inspected."""
        frames = [self.frame_at(f * self.duration) for f in times]
        scale = min(1.0, 360 / self.w)
        fw, fh = int(self.w * scale), int(self.h * scale)
        sheet = Image.new("RGBA", (fw * len(frames) + 10 * (len(frames) + 1), fh + 20), (40, 40, 40, 255))
        for k, fr in enumerate(frames):
            bg = Image.new("RGBA", (fw, fh), (90, 90, 90, 255))
            d = ImageDraw.Draw(bg)
            for yy in range(0, fh, 16):
                for xx in range(0, fw, 16):
                    if (xx // 16 + yy // 16) % 2:
                        d.rectangle([xx, yy, xx + 15, yy + 15], fill=(130, 130, 130, 255))
            bg.alpha_composite(fr.resize((fw, fh), Image.LANCZOS))
            sheet.paste(bg, (10 + k * (fw + 10), 10))
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        sheet.convert("RGB").save(out)
        print(f"OK: sheet {out}")
```

### scripts/sfx_synth.py

```python
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
```

### scripts/render.py

```python
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
```