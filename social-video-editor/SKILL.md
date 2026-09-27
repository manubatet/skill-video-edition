---
name: social-video-editor
description: "Edit a Spanish talking-head video for social media (Reels, TikTok, Shorts, LinkedIn) with open-source tools (WhisperX, FFmpeg, Pillow). Use when the user uploads or points to a talking-head video and asks to edit it, cut retakes or silences, add captions/subtitles, zooms, sound effects or animations. Works in any agent that supports Agent Skills (Claude, ChatGPT, Codex)."
---

# Social Video Editor (Spanish, v1)

Turns a raw Spanish talking-head video into a social-ready edit:
- retakes and dead air removed;
- clean, loud audio;
- burned-in captions with highlighted keywords;
- gradual (eased) push-in zooms;
- sparse sound effects;
- custom animations that the agent writes as code.

This skill follows the open Agent Skills format, so the same folder works in Claude (Claude Code, claude.ai), ChatGPT and Codex. What it contains:
- `SKILL.md`: the procedure;
- `scripts/`: the deterministic media pipeline;
- `references/PRD.md`: the why and the scope;
- `agents/openai.yaml`: display metadata for ChatGPT and Codex.

In this file, "the agent" means whichever assistant is running the skill.

## Core principles

1. **The agent decides, scripts execute.** The agent only writes JSON decision files and animation code. Deterministic scripts do all the media work. Never hand-edit video with ad-hoc FFmpeg commands when a script covers the step.
2. **Two decision files are the contract.**
   - `work/edit.json` holds what to cut, in source time.
   - `work/timeline.json` holds what to add, in edited time.
   Any change is an edit to one of these files followed by a re-run. Never re-run transcription to change an edit.
3. **Cut first, decorate second.** Cuts shift every timestamp. All effect timings refer to `transcript_edited.json`, which exists only after `build_edit.py` has run.
4. **Word ids are stable.** Every word keeps its original id `i` through the pipeline. Refer to words by id, never by list position.
5. **Pace is a rule, not a vibe.** `render.py --check` enforces density rules. Fix violations by removing effects, not with `--force`.
6. **Never remove filler words** ("eh", "este", "o sea", "pues", "bueno"). They are part of the speaker's voice. Only retakes, stutters, and pauses longer than `max_gap` are cut.

## Agent capabilities (portable across Claude, ChatGPT, Codex)

The procedure needs four abilities. Each can be done in more than one way, depending on the host.

| Ability | Use when available | Fallback |
|---|---|---|
| **Ask structured questions** | a question/choice tool, e.g. `AskUserQuestion` in Claude Code (max 4 questions × 4 options, adds "Other" automatically, supports `multiSelect`) | one chat message with numbered questions and lettered options. Mark multi-select questions "(puedes elegir varias)". End each question with "Otro: …" for free text. Give the recommended option first. |
| **Run code** | a shell / terminal (Claude Code, Codex, ChatGPT with a terminal or code execution) | give the user the exact commands to run locally, then continue from the files they send back (see *Runtime profiles*) |
| **Look at images** | open the PNG/JPG with the image-viewing tool (for example `Read` in Claude Code, or open the image in ChatGPT's sandbox) | ask the user to look at the QA sheet and report problems |
| **Deliver files** | the platform's file-sharing or download mechanism | tell the user the path of the file |

Never skip a checkpoint because a tool is missing. Use the fallback instead.

## Check for updates (once per run)

Before Setup, do one simple, non-blocking check:

```bash
LOCAL=$(cat VERSION 2>/dev/null || echo unknown)
REMOTE=$(curl -s --max-time 3 https://api.github.com/repos/manubatet/skill-video-edition/commits/main | grep -m1 '"sha"' | cut -d'"' -f4 | cut -c1-7)
echo "local=$LOCAL remote=${REMOTE:-unreachable}"
```

- No network, or `curl` fails: skip silently and continue. This never blocks the run.
- `REMOTE` differs from `LOCAL`: say so in one line, for example "Tu skill social-video-editor no está actualizada (local `81108d2`, remoto `a1b2c3d`). Actualízala desde https://github.com/manubatet/skill-video-edition (`git pull` si trabajas dentro del repo, o vuelve a copiar/descargar la carpeta `social-video-editor/` si la usas suelta)." Then continue normally; do not wait for the user to update.
- If this skill folder is itself a checkout of that repo (`.git` present and `git remote -v` shows `skill-video-edition`), prefer `git fetch origin -q && git rev-list --count HEAD..origin/main` — a non-zero count means updates are available, and `git pull --ff-only` applies them.

## Runtime profiles

Check the environment first with one command:
`ffmpeg -hide_banner -filters | grep -E " ass | loudnorm "; python -c "import whisperx" && echo whisperx-ok; curl -sI https://huggingface.co | head -1`

Then pick the profile that matches:

1. **Full.** Shell, network and FFmpeg with libass. This is typical of Claude Code, Codex CLI/IDE and a local terminal. Run everything as written.
2. **Sandbox without network.** This covers the hosted code execution in ChatGPT or claude.ai when outbound network is off. `pip install` and Whisper model downloads fail there, and FFmpeg may be missing or built without libass.
   - Say this plainly.
   - Ask the user to run `transcribe.py` on their machine and upload `work/transcript.json`; give them the Setup and step 1 commands.
   - If FFmpeg with libass is present in the sandbox, continue from step 2 there. If it is not, write `edit.json`, `timeline.json` and `anims/*.py`, then hand over the remaining commands (steps 3, 5, 6 and 8) as a copy-paste block for the user to run locally.
   - Keep uploads small: ask for the video compressed if the platform rejects its size.
3. **Chat only.** No code execution. Work as the editor:
   - read the `transcript.json` the user uploads;
   - write the decision files and animation code in the chat;
   - have the user run the scripts and send back `qa_sheet.jpg` and `preview.mp4` for the checkpoints.

## Setup (once per machine)

The pipeline needs Python 3.9+, FFmpeg built with libass, and a machine that can download the Whisper models from Hugging Face. A GPU is optional: CPU with int8 works but is slower. On Apple Silicon, WhisperX runs on CPU.

1. **Project management: one folder per project.** Create a project folder named `<video-name>_edit/` **inside the current working directory** (where the agent is running), not next to the source video if that file lives elsewhere (Downloads, a temp upload path, etc.) — copy or symlink the video into the project folder instead. This folder holds everything for that project: the video, `scripts/`, `work/` (transcript, edit decisions, timeline, renders) and any extras. Every command below runs from inside that folder. If a folder with that name already exists for a different video, ask the user for a project name rather than overwriting it. Never mix two projects' `work/` in the same folder.
2. Copy this skill's `scripts/` folder (next to this `SKILL.md`) into `<project>/scripts/`. Do not rewrite the scripts.
3. Install and check the dependencies:
   ```bash
   pip install whisperx numpy pillow opencv-python-headless   # add --break-system-packages if pip asks, or use a venv
   ffmpeg -hide_banner -filters | grep -E " ass | loudnorm "     # both lines must appear
   python scripts/sfx_synth.py --out sfx                        # builds the default SFX library
   ```
   If `pip` fails building `antlr4-python3-runtime` on Debian/Ubuntu's system Python, install into a virtualenv (`python3 -m venv .venv`). On CPU-only machines, add `--extra-index-url https://download.pytorch.org/whl/cpu` to avoid the large CUDA wheels.
4. Optional installs:
   - **Speaker diarization.** Create a free Hugging Face token and accept the terms of `pyannote/speaker-diarization-community-1`. Then pass `--hf-token` or set `HF_TOKEN`.
   - **Better denoising.** `pip install deepfilternet`, then set `"denoise": "deepfilter"`.
   - **Caption font.** Put a bold TTF (default: Montserrat ExtraBold, OFL license) in `work/fonts/`. Set `style.font` to the font's family name. Without it, captions fall back to a system font.
   - **Better SFX.** Any `.wav` placed in `sfx/` with the same name (for example a CC0 `whoosh.wav` from Freesound) replaces the synthesized one.

If a model download is blocked (sandboxed or offline machine), switch to runtime profile 2.

## Intake: two quick rounds

Ask using the *Ask structured questions* ability. The recommended option comes first. If nobody answers, use the defaults and state them. With a question tool that caps questions per call (Claude Code: 4 questions × 4 options, plus an automatic "Other"), run the intake as two calls back to back. In a plain chat message, send round 1, wait for the answer, then send round 2. Either way, ask before any heavy work starts. Wherever this section says "Other", the chat fallback is the "Otro: …" line.

### Round 1: what to add

1. **Captions**: Karaoke, 3 words with the current word highlighted (recommended) / One word at a time / Phrases / No captions.
2. **Caption position**: Bottom, above the platform UI (recommended) / Middle / Top.
3. **Effects**: a **multi-select** question, never single choice. With a question tool, set its multi-select flag (`multiSelect: true` in Claude Code). In chat, write "(puedes elegir varias)". Options: Punch-in zooms / Sound effects / Animations. Word the question so it is obvious that several can be ticked and that anything else can be written in the free-text "Other" field. For example: "¿Qué efectos quieres? Marca todos los que quieras. Si quieres añadir algo más (una escena animada a pantalla completa, un estilo concreto, algo a evitar…), escríbelo en 'Other'." If nobody answers, all three are on.
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
| a1 | 2,1 s → 3,9 s | "Hoy te doy **tres claves** para…" | **Tarjeta de palabra**: pill del color principal con rebote, "3 CLAVES" en mayúsculas | Gancho: anuncia la estructura del vídeo en los primeros 3 s |

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
For each entry in `animations`, write `work/anims/<id>.py` using `anim_kit` (see *Animation guide*). Run it. Then **open the generated `<id>_sheet.png` and look at it** (*Look at images*) before continuing. Fix overflowing text, clipped shapes, unreadable contrast and timing that looks wrong.

### 6. Validate and preview
```bash
python scripts/render.py --work work --check
python scripts/render.py --work work --preview --sheet
```
Open `work/qa_sheet.jpg` and look at it (*Look at images*). It holds one frame per zoom and animation, plus caption samples. Check the QA list below. Fix any problem, then re-render.

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

## Animation guide (the agent writes code)

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
