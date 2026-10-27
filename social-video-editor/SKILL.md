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
- custom animations that the agent writes as code;
- optional voice cloning to fix a flubbed phrase or add a short voice-over in the speaker's own voice.

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

## Plugin mode (MCP tools)

When the `social-video-editor` MCP tools are available (the Claude or ChatGPT plugin, see `plugin/README.md` in the repository), the user has already chosen the options in its settings UI. Use the tools instead of the intake and the shell:

- **Settings, at the start of every edit.** The settings UI replaces the *Intake* questions. Call `open_settings` with the video path before `setup_project`, so the user reviews this run's options (the saved values are filled in).
  - If the UI is shown in the chat, end your turn and wait: the user's "Guardar y editar" sends a message.
  - If it opened in the browser (Claude Code, Codex), call `wait_for_settings` with `wait_s: 50` until it returns `confirmed`. It also returns the video path the user entered.
  - Then call `get_settings` and say in one line what you are using, as in *User config*. Copy its `timeline_defaults` (the `style` and `captions` blocks) into `timeline.json` and its `edit_defaults` into `edit.json`. Respect `effects` (zooms, sfx, animations), the caption mode (`off` = no captions), the platform, the video type and the user's notes.
  - Ask in chat only what the settings don't cover (the glossary for this video, the cut plan, consent). If the user asks to change an option in chat, use `save_settings`.
- **Setup.** `check_environment` replaces the runtime check, and `setup_project` replaces Setup steps 1–2 (it links the video and copies the scripts).
- **Commands.** Each command in *Workflow* is one `run_step`: `transcribe`, `build_edit`, `voice_clone`, `align_voice`, `animation` (with `id`), `check`, `preview` (also writes the QA sheet) and `final` (also copies it to `final/`). Steps run in the background: call `job_status` with `wait_s: 50` until the state is `done` or `failed`, and read the log tail.
- **Files.** Write `edit.json`, `timeline.json`, transcript text fixes, `anims/<id>.py` and `final/extras.md` with `write_project_file`. Read anything in the project with `read_project_file`.
- **Images.** `view_image` is the *Look at images* ability: the QA sheet, the animation sheets and any frame of the source, cut, preview or final video.
- **Voice.** The engine comes from the settings, and `run_step voice_clone` writes it into `edit.json`. If voice cloning is off, don't offer voice patches or voice-overs. With `mistral`, tell the user once, before the first generation, that the reference clip and each line's text go to Mistral.
- **Keys.** Never ask for an API key in chat. If one is missing, ask the user to add it in the settings UI.

The checkpoints, editorial rules and QA checklist stay exactly the same.

## Check for updates (once per run)

Before Setup, run one quick, non-blocking check. `<skill_dir>` is the folder that contains this `SKILL.md`; pass `--repo` only when the user config sets `update_repo`:

```bash
python <skill_dir>/scripts/check_update.py [--repo owner/repo]
```

It compares the local `VERSION` (a semantic version, `MAJOR.MINOR.PATCH`) with the one published on the repository's `main`, waits at most 3 s, and prints one line:
- `UP_TO_DATE …` or `UNKNOWN …` (offline, sandbox without network, no `VERSION`): say nothing and continue. This never blocks the run.
- `UPDATE 1.1.0 -> 1.2.0`: say so in one line, then continue normally without waiting, for example "Hay una versión nueva del skill social-video-editor (tienes la 1.1.0, la última es la 1.2.0). Actualízala desde https://github.com/manubatet/skill-video-edition (`git pull` si trabajas dentro del repo, o vuelve a copiar/descargar la carpeta `social-video-editor/` si la usas suelta)."
- If this skill folder is itself a checkout of that repo (`.git` present and `git remote -v` shows `skill-video-edition`), `git pull --ff-only` applies the update.

## User config (`.social-video-editor.json`)

Read this file from the current working directory at the start of every run, before the update check. It holds the user's standing answers, so the intake only asks what is new for this video. The template is `config.example.json` next to this `SKILL.md`.

| Key | Holds | Replaces |
|---|---|---|
| `projects_dir` | where projects and `_shared/` live | Setup step 1 question |
| `ask` | `"missing"` (default): ask only what the config doesn't answer. `"always"`: ask everything, with the config's answers as the recommended options | — |
| `update_repo` | `owner/repo` for the update check | the repository hard-coded below |
| `defaults.captions`, `.effects`, `.anim_style`, `.palette`, `.font`, `.loudness` | the house style: `palette` is a preset key or `{"fondo", "texto", "principal", "secundario", "alerta"}` in HEX | intake questions 1–3, 5 and 6 |
| `glossary` | names and brands for `--glossary` (merged with any new ones) | the glossary invite |
| `speakers.<id>` | `name` and `title` for lower thirds, `voice_ref` (saved reference wav), `consent` (who allowed what, and when) | re-asking the name and title, picking a voice reference, and the consent question when the use matches |
| `voice` | `enabled`, `engine` (`voxcpm` \| `cosyvoice` \| `mistral`), `steps`, `cfg_value`, `cosyvoice_dir`, `cosyvoice_model`, `mistral_model`, `mistral_key_env` | the engine settings |
| `defaults.platform`, `.video_type`, `.target_duration`, `.cuts`, `.extras`, `.notes`, `transcribe`, `runtime` | written by the plugin's settings UI: target platform, kind of video, cut defaults (`max_gap`, `pad`, `denoise`), whether to write the extras, free-text notes, Whisper model and speaker count, and paths to FFmpeg and each Python environment | the remaining intake questions |

Rules:
- **Say what you are reusing.** When the config answers intake questions, skip them, and say so in one line so the user can override, for example: "Uso tu configuración: karaoke al 64 %, flat 2D, paleta Calma, voz VoxCPM2. Dime si cambias algo."
- **Offer to save.** At the end of a run, if the user answered questions the config doesn't cover (a new speaker, a custom palette, a projects folder), offer to save those answers. Write the file only after they agree.
- **Never store secrets.** Credentials (API keys, tokens) never go in this file or in any project file. The config holds only the *name* of the environment variable (`api_key_env`). The key lives in the user's shell profile, the system keychain or a git-ignored `.env`. If the variable is missing, tell the user how to set it; never ask them to paste the key in chat.
- The file is personal: keep it out of git (add it to `.gitignore`).

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

1. **Projects folder (ask once, then reuse).** If the user config has `projects_dir`, use it without asking. Otherwise ask the user where to keep their video projects. Recommend `Projects/` inside the current working directory, and accept any path they give. Explain that this folder will hold the finished videos and everything worth reusing: model weights, Python environments, voices, fonts, SFX and animations. Save the answer as `{"projects_dir": "<path>"}` in `.social-video-editor.json`. If the working directory is a git repository, add the projects folder to `.gitignore`, because media and weights never go to git. Layout:
   ```
   <projects_dir>/
   ├── _shared/                  reused by every project
   │   ├── models/               HF_HOME: Whisper, alignment and TTS weights, downloaded once
   │   ├── envs/                 .venv (WhisperX) and .venv-voice (TTS)
   │   ├── voices/<speaker>/     ref.wav + ref.txt + consent.txt, to clone the same speaker again
   │   ├── fonts/  sfx/          caption fonts and the SFX library
   │   └── anims/                animations worth reusing (copy the .py and re-run it with the new style)
   └── <video-name>/             one folder per video
       ├── <source video>        a copy or a symlink, never moved from where the user keeps it
       ├── scripts/              this skill's scripts
       ├── work/                 transcript, edit.json, timeline.json, anims/, voice/, previews
       └── final/                final.mp4 + extras.md (title, description, hashtags, thumbnails)
   ```
   Before running any script, `export HF_HOME=<projects_dir>/_shared/models`, so model downloads land in `_shared/` and are reused. Run Python from `_shared/envs/`. Link `work/fonts` to `_shared/fonts`, and pass `--sfx <projects_dir>/_shared/sfx` to `render.py`. Every command below runs from inside the project folder. If a folder with that name already exists for a different video, ask for a project name rather than overwriting it. Never mix two projects' `work/` in the same folder.
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
   - **Voice cloning.** VoxCPM2 (Apache-2.0): `pip install voxcpm soundfile` in its own venv (`_shared/envs/voxcpm`), with Python 3.10–3.12; its `torch` can clash with WhisperX's, so keep the two environments apart. The first run downloads the model (about 4 GB) from Hugging Face. It runs on CUDA, Apple MPS or CPU. Install it only when the user wants a voice fix or narration.
     CosyVoice 3 (optional): `git clone --recursive https://github.com/FunAudioLLM/CosyVoice <projects_dir>/_shared/engines/CosyVoice`, then in a new venv (`_shared/envs/cosyvoice`, Python 3.10–3.11): `pip install "setuptools<80" numpy==1.26.4 cython`, `pip install --no-build-isolation openai-whisper==20231117 pyworld==0.3.4`, `pip install -r <repo>/requirements.txt`. The Linux-only extras (deepspeed, TensorRT) are skipped automatically on macOS.

If a model download is blocked (sandboxed or offline machine), switch to runtime profile 2.

## Intake: two quick rounds

Skip every question the user config already answers (see *User config*), and state the reused answers in one line. Ask using the *Ask structured questions* ability. The recommended option comes first. If nobody answers, use the defaults and state them. With a question tool that caps questions per call (Claude Code: 4 questions × 4 options, plus an automatic "Other"), run the intake as two calls back to back. In a plain chat message, send round 1, wait for the answer, then send round 2. Either way, ask before any heavy work starts. Wherever this section says "Other", the chat fallback is the "Otro: …" line.

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
6. **Color palette (style guide)**: single choice. Offer the four presets from *Color palette presets* that best fit the video's topic (AskUserQuestion takes at most 4 options). Put the five HEX codes in each option's `description`, so the user sees the actual colours. Put the preset that best fits the video's topic first as "(Recommended)". The question text must explain the "Other" format, for example: "¿Qué paleta de colores usamos? Si tienes la tuya, escribe en 'Other' hasta 5 colores HEX en este orden: fondo, texto, principal, secundario, alerta (p. ej. #1E3A4C, #F7F5F0, #5EC2B7, #F4A261, #E76F51)."

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

  Offer optional extras as a separate "Opcional" line instead of silently adding them. When a phrase is mispronounced, wrong or flubbed and there is no clean take to keep, offer a **voice patch** there (see *Voice cloning*), quoting the words and the proposed replacement text.

Ask them to correct wrong words, confirm the cuts and approve or change the table. After the cuts, carry the approved rows into `timeline.json` with edited times. If the user asks to see the plan again, re-show it in the same table.

To apply text fixes, edit the `text` of words in `work/transcript.json` with a small Python snippet. Keep word count and timings unchanged. If a fix merges or splits words, adjust only the text and keep the original number of word entries. Then write `work/edit.json` (schema in `build_edit.py`'s docstring).

### 2b. Voice patches (only if approved at Checkpoint 1)
Add `voice` and `voice_patches` to `work/edit.json` and run `python scripts/voice_clone.py --work work`, then listen to the clips (see *Voice cloning*). Do this before step 3, because `build_edit.py` splices the clips in.

### 3. Cut and clean
```bash
python scripts/build_edit.py --work work
```
This writes `work/cut.mkv` (cuts, denoise only if the pauses are noisy, two-pass loudness normalization to -14 LUFS), `work/segments.json` and `work/transcript_edited.json/.txt`. Report the before and after duration.

### 4. Classify and plan effects
Read `transcript_edited.json`. Then write `work/timeline.json` (schema below), following *Editorial rules* and the table approved at Checkpoint 1. Include the `classification` array: it documents the reasoning and makes later changes easy to discuss. If an approved row cannot be placed as agreed (for example two animations now violate `anim_min_gap`), show the updated table and say what changed. If the plan has `voiceover` entries, run `voice_clone.py` again now: it only generates the new lines. Then run `python scripts/align_voice.py --work work` in the WhisperX environment, so the voice-overs get captions.

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
Copy `work/final.mp4` to `final/` and deliver it from there. Also give the extras in the reply, and save them to `final/extras.md`. Derive them from the transcript:
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
  "voiceover": [{"id": "v1", "at": 18.2, "text": "Y guarda este vídeo para luego.", "duck_db": -24, "gain_db": 0}],
  "extend": 0,
  "zoom_center": null,
  "rules": {}
}
```

Field notes:
- **`captions.mode`**: `karaoke` | `word` | `sentence` | `off`.
- **`captions.position`**: `bottom` | `middle` | `top`. Positions already respect the TikTok and Reels safe zones for vertical video. For an in-between height, set `captions.y` (0–1 of the frame height, e.g. 0.64 for "middle, a bit lower"); it overrides `position`. Keep it above 0.80 on vertical video.
- **`sfx.at`**: the moment the sound should *land*. `render.py` subtracts each sound's lead time automatically, for example 0.22 s for `whoosh` and 1.2 s for `riser`. Set `"align": "start"` to disable this.
- **Available sounds**: `whoosh` (transitions, new point), `pop` (a word or card appears), `ding` (number or result), `click` (list item), `riser` (build-up before a reveal), `boom` (big claim, use at most once per video).
- **`animations.anchor`**: `top` | `upper-third` | `center` | `lower-third`. Alternatively give explicit `x` and `y` in pixels for the top-left corner. Use `hide_captions: true` when an animation replaces the captions for its duration.
- **`zooms`**: every zoom is a **gradual push-in**, never a hard cut. The scale eases in (smoothstep) over `ramp` seconds from `start`, holds, then eases back out over `ramp` seconds before `end`. The default `ramp` is **0.7 s**, capped at half the zoom length. Keep the default; lower it (0.35) only when the user asks for a snappier style. `"ramp": 0` gives the old hard punch-in, so use it only when the user asks for jump-cut style. Because the ramp eats into the zoom, start it about `ramp`/2 (≈0.3 s) before the key word, so the zoom is fully in when the word lands. Make zooms at least 1.4 s long, so both full ramps fit. Shorter ones never reach full scale and read as a quick breathe-in.
- **`zoom_center`**: leave it `null`. It is detected from the face, falling back to `[0.5, 0.4]`. Set it by hand when the source has burned-in text that the zoom would cut in half. Choose a centre whose crop either keeps that text whole or leaves it out entirely.
- **`voiceover`**: a line in the speaker's cloned voice, starting at `at`. The speech track is ducked by `duck_db` (default -24; -60 mutes it) while it plays. The clip must already exist (`voice_clone.py`), and it must end inside the video. It is captioned like the speech once `align_voice.py` has aligned its words; speech under a muted voice-over (`duck_db` ≤ -40) is left out of the captions. See *Voice cloning*.
- **`extend`**: seconds added after the end of the cut (the last frame is held and silence is padded) for full-screen animated scenes narrated by `voiceover`, for example a segment that explains an article after the speaker's real intro. Cover the whole extension with opaque full-screen animations (box = frame size, `x: 0, y: 0`); scenes may run back to back, so set `rules.anim_min_gap` to 0 (full-frame boxes skip the caption-band and UI-zone warnings). Keep the caption band free in the scene design, because captions are drawn on top.
- **`rules`**: overrides the density limits in `render.py` (`RULES`). Change a limit only when the user asks for a denser or calmer style.

## Voice cloning (optional)

`scripts/voice_clone.py` generates Spanish speech in the speaker's own voice, zero-shot from about 10 s of their speech, with one of these engines (`voice.engine`):

| Engine | Where it runs | Notes |
|---|---|---|
| `voxcpm` | local, VoxCPM2, Apache-2.0, 48 kHz | Won a blind test against Qwen3-TTS and Chatterbox on accent fidelity (it keeps a Spain-Spanish accent) and naturalness. Needs the reference transcript (`ref.txt` next to `ref_file`, or taken from the transcript for a `ref` span). `pip install voxcpm soundfile`. |
| `cosyvoice` | local, CosyVoice 3 (0.5B), Apache-2.0, 24 kHz | Lighter alternative with very natural prosody. Needs the reference transcript (`ref.txt`), a clone of the CosyVoice repo (`voice.cosyvoice_dir`) and its own environment (see Setup). `voice.cosyvoice_model` is the Hugging Face id or a local folder with the weights. |
| `mistral` | Mistral API, Voxtral TTS, pay per use | No local install. The reference clip and each line's text are sent to api.mistral.ai with every request (nothing is stored there); the video stays local. The key goes in the env var named by `voice.mistral_key_env` (default `MISTRAL_API_KEY`), never in a file that goes to git. |
| `elevenlabs` | ElevenLabs API, paid | **Disabled for now** (do not offer it). The code stays in `voice_clone.py` (`DISABLED_ENGINES`) for when it is enabled again. |

Run `voice_clone.py` with the Python environment of the chosen engine (`_shared/envs/<engine>`). It has two uses, and nothing else:
- **Voice patch** (`edit.json` → `voice_patches`, source time): replaces the audio of a word range, for example a mispronounced name or a wrong figure. The clip is fitted to the original span: sped up by at most ×1.2, or padded with room tone if it is shorter. So no timestamp moves and the video frames stay. Then fix those words' text in `transcript.json` as usual, so the captions match.
- **Voice-over** (`timeline.json` → `voiceover`, edited time): a new line laid over the edit, typically over a full-screen animation or a scene where the face is covered. The speech underneath is ducked. With `extend`, a series of voice-overs can narrate full-screen scenes after the real footage, for example adapting an article the user provides. Keep each line under about 250 characters (one idea per scene); long lines degrade.

Rules:
1. **Consent first.** Clone only the voice of the person in the video, and only when the user confirms it is their own voice or that they have that person's permission. Ask explicitly before the first use. Record it as `"voice": {"consent": true}` in `edit.json` and in `speakers.<id>.consent` of the user config; the script refuses to run without it. Never clone a voice from any other recording.
2. **Lip sync.** A patch changes the sound but not the mouth. Use it for one to four words, ideally where the change is hard to see (similar mouth shapes, a zoom, an animation or B-roll covering the face). For longer changes, prefer cutting or a re-recording, and say so.
3. **Keep the text short and natural.** Write it the way the speaker talks, with the same register. Write numbers as words ("veinticinco por ciento"). A patch must be about as long as the words it replaces. If the script says the clip is too long, shorten the text or widen the word range.
4. **Listen before using.** After each run, play `work/voice/<id>.wav` (or have the user play it) and check the pronunciation, especially names and anglicisms. Transcribe the clips back with Whisper and compare them with the text: a changed word ("hacer" for "nacer") is a mispronunciation. If a clip sounds wrong, give that line its own `"seed"` (re-rolls only that take) or rephrase it, then re-run. Unchanged lines are not regenerated.
5. **Reference.** Never run a denoiser on a reference: the model clones its artifacts as a metallic, robotic timbre. By default the script picks the best 8–15 s of continuous, clean speech that is not cut or patched. If that stretch has music, noise or another voice, set `voice.ref` to `[start, end]` in source seconds.
6. **No dubbing or translation.** This skill does not translate or re-voice whole videos.
7. **Narrated scenes.** When the voice-over says new things (not a fix), show the script to the user at Checkpoint 1 and get it approved before generating. Adapt source material to the speaker's register and to social media: short sentences, second person, one idea per line, and a closing CTA. Never invent claims that are not in the source.

`edit.json` example:
```json
{"voice": {"consent": true, "ref": null, "engine": "voxcpm", "steps": 25, "seed": 7},
 "voice_patches": [{"id": "p1", "words": [120, 122], "text": "el veinticinco por ciento"}]}
```
Ids are shared by patches and voice-overs, so they must be unique across both files. The clips go to `work/voice/`.

**Reusing a voice.** After a speaker's first project, save the reference to `_shared/voices/<speaker>/`: `ref.wav` (copy `work/voice/ref.wav`), `ref.txt` (its transcript) and `consent.txt` (who gave permission, and when). In later projects, set `"voice": {"consent": true, "ref_file": "<projects_dir>/_shared/voices/<speaker>/ref.wav"}`, so the same voice is used without picking a reference again. Ask about consent again if the use is different from the one recorded.

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
- Primitives: `c.rect`, `c.circle`, `c.line`, `c.arc`, `c.polygon`, `c.text`.
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
| `oceano` | Océano (corporativo) | `#0B2545` | `#F4F7FB` | `#4CC9F0` | `#FFB703` | `#FF5D73` | empresa, finanzas, tecnología |
| `noche` | Noche (tech) | `#0D0D14` | `#F2F2F7` | `#00E5FF` | `#C77DFF` | `#FF2E63` | tech, gaming, IA |
| `bosque` | Bosque (natural) | `#16261D` | `#F3F1E7` | `#9BD770` | `#F2C14E` | `#E4572E` | sostenibilidad, deporte, naturaleza |

All presets keep at least 3:1 WCAG contrast for every role on `fondo`, and at least 4.5:1 for texto and principal. With a custom palette:
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
- Voice patches and voice-overs match the speaker's level and tone, and do not stand out at the joins. Any lip-sync mismatch is hidden or minimal.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Words cut off at the edges of cuts | raise `pad` in `edit.json`; lower it (0.08) if the edit feels slow |
| Edit feels choppy | raise `max_gap` to 0.6 |
| Wrong names in captions | `--glossary`, or fix the word texts at Checkpoint 1 |
| Captions use the wrong font | the font file is missing from `work/fonts/`, or `style.font` doesn't match its family name (`fc-scan file.ttf`) |
| Zoom crops the face | set `zoom_center` manually to `[x, y]` (normalized face position) |
| Audio pumps or sounds robotic | `"denoise": "off"` (the default `auto` only denoises when the pauses are noisy, above -50 dBFS) |
| Cloned voice doesn't sound like the speaker | set `voice.ref` (or `ref_file`) to a cleaner 10–15 s stretch whose `ref.txt` matches it exactly |
| Cloned voice sounds robotic or metallic | the reference was denoised (rebuild it with only `highpass=f=60`); with `voxcpm`, raise `voice.steps` to 25–30 |
| Cloned voice is rushed, flat or odd | re-roll that line with its own `"seed"`; adjust `cfg_value` (1.5 looser, 2.5 more literal); pick a reference with the delivery you want, since the voice copies its energy and pace |
| `filter_complex_script` not recognized | FFmpeg 8+ removed it; the scripts detect the version, so recopy `scripts/` from the skill |

## Roadmap hooks (don't build unless asked)

v2 items, in the PRD, fit into the existing contracts without rewrites:
- **Style guide** → `timeline.style` (palette and animation-style presets exist; a full brand guide would extend them).
- **Templates** → preset `timeline.rules` and effect toggles.
- **Format / auto-reframe** → a crop pass in `build_edit.py`.
- **Combining videos** → multiple sources in `segments.json`.
- **Music with ducking** → one more audio input in `render.py`.
