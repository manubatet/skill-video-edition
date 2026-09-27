# skill-video-edition

**Social Video Editor** es un *Agent Skill* que convierte un vídeo en bruto de una persona hablando a cámara, en español, en un clip listo para Reels, TikTok, Shorts o LinkedIn. Solo usa herramientas de código abierto (WhisperX, FFmpeg, Pillow, OpenCV). Funciona con **Claude** (Claude Code y claude.ai), **ChatGPT** y **Codex**, porque sigue el formato abierto de skills: una carpeta con un `SKILL.md`, scripts y referencias.

## Qué hace

- **Transcribe** con marcas de tiempo por palabra (WhisperX large-v3 y alineación en español). Admite un glosario de nombres y marcas.
- **Corta** repeticiones de toma, tartamudeos y silencios largos. **Nunca** quita las muletillas, porque forman parte de la voz de quien habla.
- **Limpia el audio**: reducción de ruido suave y normalización a -14 LUFS en dos pasadas.
- **Subtítulos** incrustados en tres modos (karaoke, palabra a palabra o frases) y tres posiciones, respetando las zonas seguras de TikTok y Reels. Las palabras clave se resaltan.
- **Zooms graduales**: acercamientos suaves centrados en la cara que tardan 0,7 s en entrar y en salir, en lugar de cortes.
- **Efectos de sonido** sintetizados, libres de derechos y colocados con moderación.
- **Animaciones programadas**: el agente escribe cada animación en Python y se superpone con transparencia. Pueden ser tarjetas, contadores, sellos, barras de progreso o escenas 2D a pantalla completa.
- **Guía de estilo**: 4 estilos de animación y 4 paletas de 5 colores con contraste verificado, o colores propios en HEX.
- **Control de ritmo**: un validador bloquea las líneas de tiempo sobrecargadas.
- **Extras**: propuesta de título, descripción, hashtags y miniaturas.

### Cómo trabaja

Cada decisión vive en un JSON editable. Cambiar un detalle nunca obliga a rehacer la edición entera.

```
vídeo ─► transcribe.py ─► transcript.json ──(agente: cortes)──► edit.json
      ─► build_edit.py ─► cut.mkv + transcript_edited.json
      ──(agente: clasifica y planifica)──► timeline.json ──(agente: programa)──► anims/*.py ─► *.mov
      ─► render.py (valida ─► zooms ─► animaciones ─► subtítulos ─► SFX ─► limitador) ─► preview / final
```

**Dos momentos de revisión** con el usuario:
1. Transcripción, cortes y **tabla de propuesta de animaciones**, con las columnas Momento, Frase, Animación y Por qué.
2. Vista previa.

## Estructura del repositorio

```
social-video-editor/          ← el skill (lo que se instala)
├── SKILL.md                  ← procedimiento para el agente
├── scripts/                  ← pipeline determinista (Python + FFmpeg)
│   ├── transcribe.py  build_edit.py  captions.py  render.py
│   └── anim_kit.py  sfx_synth.py  common.py
├── references/PRD.md         ← producto: objetivos, requisitos, roadmap
└── agents/openai.yaml        ← metadatos opcionales para ChatGPT / Codex
.claude/skills/social-video-editor  → enlace para Claude Code
.agents/skills/social-video-editor  → enlace para Codex
```

## Instalación

| Agente | Cómo |
|---|---|
| **Claude Code** | Abre este repo: el skill se detecta en `.claude/skills/`. Para usarlo en cualquier proyecto, copia `social-video-editor/` a `~/.claude/skills/`. |
| **claude.ai** | Comprime la carpeta (`zip -r social-video-editor.zip social-video-editor`) y súbela en *Settings → Capabilities → Skills*. |
| **Codex (CLI / IDE)** | Abre este repo: el skill se detecta en `.agents/skills/`. Para uso personal, copia la carpeta a `~/.agents/skills/`. |
| **ChatGPT** | Sube el mismo `.zip` desde el selector de Skills. `agents/openai.yaml` aporta el nombre, la descripción y el prompt por defecto. |

Después, sube tu vídeo y pide algo como *"edita este vídeo para redes"*, o invoca el skill por su nombre (`/social-video-editor` en Claude Code).

## Requisitos

- Python 3.9 o superior y **FFmpeg compilado con libass** (`ffmpeg -filters | grep " ass "`).
- `pip install whisperx numpy pillow opencv-python-headless`
  - En el Python de sistema de Debian/Ubuntu, instala dentro de un entorno virtual (`python3 -m venv .venv`).
  - Sin GPU, añade `--extra-index-url https://download.pytorch.org/whl/cpu`.
- Acceso a Hugging Face para descargar los modelos de Whisper la primera vez.
- Opcional:
  - token de Hugging Face (detección de hablantes);
  - DeepFilterNet (mejor reducción de ruido);
  - Montserrat ExtraBold en `work/fonts/`.

La GPU es opcional: en CPU funciona con int8, aunque más despacio.

## Entornos sin red (ChatGPT, sandboxes)

El skill detecta el entorno y se adapta:

1. **Completo** (shell, red y FFmpeg): ejecuta todo el proceso.
2. **Sandbox sin red**:
   - la transcripción no puede descargar modelos, así que el agente pide ejecutar `transcribe.py` en local y subir `transcript.json`;
   - si el sandbox tiene FFmpeg con libass, el resto sigue ahí; si no, el agente entrega los JSON, las animaciones y los comandos para ejecutarlos en local.
3. **Solo chat**: el agente actúa como editor. Escribe las decisiones y el código, y tú ejecutas los scripts y le devuelves la hoja de control y la vista previa.

## Uso manual de los scripts

Se ejecutan desde la carpeta del proyecto, con `scripts/` copiada dentro:

```bash
python scripts/sfx_synth.py --out sfx
python scripts/transcribe.py video.mp4 --out work --glossary "Nombre, Marca"
# escribe work/edit.json (qué cortar)
python scripts/build_edit.py --work work
# escribe work/timeline.json (qué añadir) y work/anims/*.py
python scripts/render.py --work work --check
python scripts/render.py --work work --preview --sheet
python scripts/render.py --work work
```

Los esquemas de `edit.json` y `timeline.json` están documentados en `social-video-editor/SKILL.md` y en el docstring de `build_edit.py`.

## Próximos pasos

**Validación**
- [ ] Probar el skill de principio a fin en **ChatGPT** y en **Codex**:
  - la instalación del `.zip`;
  - las preguntas sin herramienta de opciones;
  - el perfil sin red.
- [ ] Añadir tests automáticos de los scripts, sobre un vídeo sintético corto:
  - `build_edit.py`: cortes y re-temporización;
  - `captions.py`: agrupado y colores;
  - `render.py --check`: reglas de ritmo;
  - el cálculo de la expresión de zoom.
- [ ] CI que ejecute esos tests y publique el `.zip` del skill en cada *release*.

**Funcionalidad (v1.5)**
- [ ] Biblioteca de patrones de animación reutilizables, con parámetros (tarjeta, contador, lista, sello, barra), para cada estilo de animación.
- [ ] Añadir "Escena 2D a pantalla completa" como opción de efecto en la primera ronda de preguntas.
- [ ] Sugerencias de B-roll a partir de la transcripción.
- [ ] Detectar subtítulos o títulos ya incrustados en el vídeo y adaptar automáticamente los subtítulos, los zooms y la colocación de las animaciones.

**Funcionalidad (v2)**
- [ ] Formatos de salida y reencuadre automático (16:9 → 9:16) siguiendo la cara.
- [ ] Plantillas de edición (solo animaciones, animaciones y énfasis, con o sin SFX).
- [ ] Guía de estilo de marca completa (tipografías, logos, animaciones propias) sobre las paletas actuales.
- [ ] Combinar varios vídeos en una sola edición.
- [ ] Música de fondo que baje de volumen cuando se habla (*ducking*) y cortes al ritmo, con librosa.
- [ ] Extraer clips de vídeos largos.
- [ ] Subtítulos en inglés y soporte para otros idiomas.

## Licencias de terceros

Todas las herramientas son de código abierto: WhisperX y faster-whisper (BSD-2/MIT), pyannote (MIT), FFmpeg y libass (LGPL/GPL, ISC), OpenCV (Apache-2.0), Pillow y numpy (MIT-CMU/BSD). La fuente Montserrat usa la licencia OFL.
