# Plugin para Claude y ChatGPT

El plugin convierte el skill en una app con **pantalla de ajustes**. Ahí eliges todas las opciones: tipo de vídeo y plataforma, subtítulos sí o no (y cómo), efectos, estilo de animación, paleta, cortes, transcripción, motor de voz, clave de Mistral y carpeta de proyectos. El agente las lee en lugar de preguntarte, y edita el vídeo **en tu ordenador**.

```
Claude / ChatGPT ──MCP──► plugin/server (Python, en tu ordenador) ──► scripts del skill (WhisperX, FFmpeg, Pillow)
        ▲                         │
        └── pantalla de ajustes ◄─┘  (dentro del chat, o en http://127.0.0.1:8765)
```

## Qué sale de tu ordenador

- **El vídeo, nunca.** Se transcribe, se corta, se anima y se renderiza en local.
- **Al chat** van los textos que el agente necesita para decidir: la transcripción, los JSON de decisiones y los fotogramas o la hoja de control que pide ver (`view_image`).
- **Hugging Face**: los modelos se descargan la primera vez, en `<proyectos>/_shared/models`.
- **Mistral**, solo si eliges *Mistral Voxtral* como motor de voz: se envían el fragmento de referencia (unos 10 s de voz) y el texto de cada frase. Con VoxCPM2 o CosyVoice 3, la voz también se genera en local.

Las claves (Mistral, Hugging Face) se guardan en `~/.config/social-video-editor/secrets.json` (permisos 600), fuera de cualquier proyecto o repositorio. En Claude Desktop también puedes ponerlas en el llavero del sistema desde los ajustes de la extensión. Nunca llegan al modelo: las herramientas solo dicen si están configuradas.

## Instalación

Requisitos: los del skill (Python 3.9+, FFmpeg con libass, WhisperX; ver el README principal). El servidor solo usa la biblioteca estándar de Python, así que no hay que instalar nada más para él. En macOS, el `ffmpeg` de Homebrew no trae libass: instala `ffmpeg-full` (`brew install ffmpeg-full`). El plugin lo encuentra solo.

### Claude Code

```bash
claude plugin marketplace add manubatet/skill-video-edition
claude plugin install social-video-editor@skill-video-edition
```

Instala el skill y el servidor. Claude Code no muestra interfaces dentro del chat, así que `open_settings` abre la pantalla de ajustes en tu navegador (página local con un token, solo accesible desde tu ordenador). Los ajustes se guardan en `.social-video-editor.json` si existe en la carpeta del proyecto (el mismo archivo que usa el skill) o, si no, en `~/.config/social-video-editor/config.json`.

### Claude Desktop

```bash
./plugin/build.sh          # crea dist/social-video-editor.mcpb
```

Abre `dist/social-video-editor.mcpb` con Claude Desktop (o arrástralo a *Ajustes → Extensiones*). La extensión pide la carpeta de proyectos y, opcionalmente, la clave de Mistral y el token de Hugging Face. La pantalla de ajustes completa aparece **dentro del chat** cuando pides "abre los ajustes del editor de vídeo" o empiezas una edición sin ajustes guardados.

El bundle trae el procedimiento del skill: el agente lo lee con `get_skill_guide`. Para tenerlo también como skill, sube `dist/social-video-editor-skill.zip` en *Ajustes → Capacidades → Skills*.

### ChatGPT

ChatGPT se conecta a servidores MCP por HTTPS, así que el servidor corre en tu ordenador y un túnel lo publica. El vídeo sigue sin salir: por el túnel solo pasan las llamadas a las herramientas.

1. Arranca el servidor en modo HTTP:
   ```bash
   python3 plugin/server/main.py --http 8765
   ```
   Imprime la URL del endpoint MCP, que incluye un token secreto: `http://127.0.0.1:8765/mcp/<token>`.
2. Publícalo con un túnel HTTPS, por ejemplo:
   ```bash
   cloudflared tunnel --url http://127.0.0.1:8765
   ```
3. En ChatGPT, activa el *modo desarrollador* (*Settings → Apps & Connectors → Advanced*), crea una app nueva y pega `https://<tu-túnel>/mcp/<token>`, sin autenticación. **Trata esa URL como una contraseña**: quien la tenga puede usar las herramientas.
4. En el chat, pide "abre los ajustes del editor de vídeo". La pantalla aparece dentro de ChatGPT. Para la clave de Mistral, el botón abre la página local en tu navegador, porque lo que escribes dentro de ChatGPT pasa por sus servidores.

Cierra el túnel cuando termines.

### Codex

```bash
codex mcp add social-video-editor -- python3 /ruta/al/repo/plugin/server/main.py
```

El skill ya se detecta en `.agents/skills/`.

## Herramientas

| Herramienta | Para qué |
|---|---|
| `open_settings` | Muestra la pantalla de ajustes (en el chat, o en el navegador si el host no tiene interfaz) |
| `get_settings` | Los ajustes como resumen, más los bloques `style`/`captions` de `timeline.json` y los valores de corte de `edit.json`, listos para copiar |
| `save_settings` | Guarda los ajustes si pides un cambio en el chat |
| `save_secret` | Guarda una clave en local (solo la pantalla de ajustes) |
| `get_skill_guide` | El `SKILL.md` completo o una sección |
| `check_environment` | Revisa FFmpeg con libass, los entornos de Python y las claves |
| `setup_project`, `list_projects` | Proyectos en la carpeta de proyectos |
| `run_step`, `job_status` | Ejecuta en segundo plano `transcribe`, `build_edit`, `voice_clone`, `align_voice`, `animation`, `check`, `preview`, `final` y `sfx` |
| `read_project_file`, `write_project_file` | Lee archivos del proyecto y escribe solo los de decisión (`edit.json`, `timeline.json`, `transcript.json`, `anims/<id>.py`, `extras.md`) |
| `view_image` | Un fotograma de cualquier versión del vídeo, o la hoja de control |

## Entornos de Python

Cada paso usa su entorno, igual que el skill: `<proyectos>/_shared/envs/whisperx` (transcripción, cortes y render), `envs/voxcpm` y `envs/cosyvoice` (voz). Si están en otro sitio, indica su `python` en *Proyectos → Avanzado*. Mistral no necesita entorno propio.

## Desarrollo

- `plugin/server/main.py`: protocolo MCP (stdio y HTTP), página local y registro de herramientas.
- `plugin/server/tools.py`: proyectos, entornos, trabajos y archivos.
- `plugin/server/settings.py`: ajustes, validación, claves y el resumen para el agente.
- `plugin/ui/editor.html`: la pantalla de ajustes. Un solo archivo que funciona como MCP App (Claude), widget del Apps SDK (ChatGPT) y página local.
- `plugin/claude-desktop/manifest.json` y `plugin/build.sh`: el bundle `.mcpb`.
- `.claude-plugin/`: manifiesto del plugin y marketplace de Claude Code.

Prueba rápida sin cliente: `python3 plugin/server/main.py --http` y abre la URL de la página de ajustes que imprime.
