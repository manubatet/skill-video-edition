"""User settings for the plugin: the same .social-video-editor.json the skill reads, plus local secrets.

Settings file (first match wins):
  $SVE_CONFIG                              explicit path
  ./.social-video-editor.json              the working directory (what the skill uses)
  ~/.config/social-video-editor/config.json

Secrets (API keys, tokens) never go in the settings file and are never returned to the model:
  environment variables (MISTRAL_API_KEY, HF_TOKEN; Claude Desktop sets them from its keychain)
  ~/.config/social-video-editor/secrets.json (chmod 600, outside every project and repo)
"""
import copy
import json
import os
import re
from pathlib import Path

HOME_DIR = Path(os.environ.get("SVE_HOME", Path.home() / ".config" / "social-video-editor")).expanduser()
SECRETS_FILE = HOME_DIR / "secrets.json"
SECRET_NAMES = ("MISTRAL_API_KEY", "HF_TOKEN")

PALETTES = {  # fondo, texto, principal, secundario, alerta (SKILL.md > Color palette presets)
    "energia": ["#111111", "#FFFFFF", "#FFD400", "#00E676", "#FF3B3B"],
    "calma": ["#1E3A4C", "#F7F5F0", "#5EC2B7", "#F4A261", "#E76F51"],
    "pop": ["#1A1033", "#FFFFFF", "#FF4FA3", "#7C5CFF", "#FFD23F"],
    "tierra": ["#2B2622", "#FAF6F0", "#D9B26F", "#8DB38B", "#C4553A"],
}
ROLES = ("fondo", "texto", "principal", "secundario", "alerta")

CHOICES = {
    "platform": ["reels", "tiktok", "shorts", "linkedin", "youtube"],
    "video_type": ["consejos", "educativo", "historia", "opinion", "entrevista", "promocion", "otro"],
    "captions.mode": ["karaoke", "word", "sentence", "off"],
    "captions.position": ["bottom", "middle", "top"],
    "effects": ["zooms", "sfx", "animations"],
    "anim_style": ["bold", "minimal", "flat2d", "neon"],
    "cuts.denoise": ["auto", "off", "light", "deepfilter"],
    "transcribe.model": ["large-v3", "medium", "small"],
    "voice.engine": ["voxcpm", "cosyvoice", "mistral"],
    "ask": ["missing", "always"],
}
LOCAL_ENGINES = ("voxcpm", "cosyvoice")

DEFAULTS = {
    "projects_dir": str(Path.home() / "Videos" / "social-video-editor"),
    "ask": "missing",
    "update_repo": "manubatet/skill-video-edition",
    "defaults": {
        "platform": "reels",
        "video_type": "consejos",
        "target_duration": None,
        "captions": {"mode": "karaoke", "position": "bottom", "y": None, "max_words": 3, "size": 0.07,
                     "uppercase": True},
        "effects": ["zooms", "sfx", "animations"],
        "anim_style": "bold",
        "palette": "energia",
        "font": "Montserrat",
        "loudness": -14,
        "cuts": {"max_gap": 0.40, "pad": 0.12, "denoise": "auto"},
        "extras": True,
        "notes": "",
    },
    "transcribe": {"model": "large-v3", "speakers": 1},
    "glossary": [],
    "speakers": {},
    "voice": {"enabled": False, "engine": "voxcpm", "steps": 25, "cfg_value": 2.0, "cosyvoice_dir": None,
              "cosyvoice_model": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512", "mistral_model": "voxtral-mini-tts-3-0",
              "mistral_key_env": "MISTRAL_API_KEY"},
    "runtime": {"ffmpeg_dir": None, "python_main": None, "python_whisperx": None, "python_voxcpm": None, "python_cosyvoice": None},
}


def config_path():
    if os.environ.get("SVE_CONFIG"):
        return Path(os.environ["SVE_CONFIG"]).expanduser()
    local = Path.cwd() / ".social-video-editor.json"
    if local.exists():
        return local
    return HOME_DIR / "config.json"


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_settings():
    p = config_path()
    raw = {}
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
    s = merge(DEFAULTS, raw)
    if "voice" in raw and "enabled" not in raw["voice"]:
        s["voice"]["enabled"] = True  # configs written by the skill before the plugin: voice was in use
    if os.environ.get("SVE_PROJECTS_DIR") and "projects_dir" not in raw:
        s["projects_dir"] = os.environ["SVE_PROJECTS_DIR"]
    return s


def projects_dir(s):
    p = Path(os.path.expanduser(s["projects_dir"]))
    return p if p.is_absolute() else (config_path().parent / p).resolve()


HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def norm_hex(v):
    m = HEX.match(str(v).strip())
    if not m:
        raise ValueError(f"invalid HEX colour: {v}")
    h = m.group(1)
    return "#" + (h if len(h) == 6 else "".join(c * 2 for c in h)).upper()


def validate(s):
    """Return a cleaned copy of the settings or raise ValueError with a readable message."""
    s = merge(DEFAULTS, s)
    d = s["defaults"]

    def pick(key, value):
        if value not in CHOICES[key]:
            raise ValueError(f"{key} must be one of {', '.join(CHOICES[key])}")
        return value

    s["ask"] = pick("ask", s["ask"])
    d["platform"] = pick("platform", d["platform"])
    d["video_type"] = pick("video_type", d["video_type"])
    d["captions"]["mode"] = pick("captions.mode", d["captions"]["mode"])
    d["captions"]["position"] = pick("captions.position", d["captions"]["position"])
    for e in d["effects"]:
        pick("effects", e)
    if d["anim_style"] not in CHOICES["anim_style"] and not str(d["anim_style"]).strip():
        raise ValueError("anim_style must be a preset or a free-text description")
    if isinstance(d["palette"], dict):
        d["palette"] = {r: norm_hex(d["palette"][r]) for r in ROLES}
    elif d["palette"] not in PALETTES:
        raise ValueError(f"palette must be one of {', '.join(PALETTES)} or 5 HEX colours")
    d["cuts"]["denoise"] = pick("cuts.denoise", d["cuts"]["denoise"])
    s["transcribe"]["model"] = pick("transcribe.model", s["transcribe"]["model"])
    s["voice"]["engine"] = pick("voice.engine", s["voice"]["engine"])
    for key, lo, hi in (("y", 0.05, 0.95), ("size", 0.03, 0.12)):
        v = d["captions"].get(key)
        if v is not None and not lo <= float(v) <= hi:
            raise ValueError(f"captions.{key} must be between {lo} and {hi}")
    if not 1 <= int(d["captions"]["max_words"]) <= 8:
        raise ValueError("captions.max_words must be between 1 and 8")
    if isinstance(s["glossary"], str):
        s["glossary"] = [g.strip() for g in s["glossary"].split(",") if g.strip()]
    if not str(s["projects_dir"]).strip():
        raise ValueError("projects_dir is required")
    for k in list(s):
        if k.lower().endswith(("key", "token", "secret")):
            raise ValueError(f"'{k}' looks like a secret; save it with the secret field, not in the settings")
    return s


def save_settings(s):
    s = validate(s)
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return s, p


# ---- secrets -------------------------------------------------------------------------------

def _read_secrets():
    try:
        return json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def get_secret(name):
    return (os.environ.get(name) or _read_secrets().get(name) or "").strip()


def secret_status():
    file = _read_secrets()
    return {n: ("env" if os.environ.get(n) else "file" if file.get(n) else None) for n in SECRET_NAMES}


def set_secret(name, value):
    if name not in SECRET_NAMES:
        raise ValueError(f"unknown secret {name}")
    data = _read_secrets()
    value = (value or "").strip()
    if value:
        data[name] = value
    else:
        data.pop(name, None)
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(SECRETS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.chmod(SECRETS_FILE, 0o600)


# ---- what the agent gets -------------------------------------------------------------------

def palette_colors(p):
    return dict(zip(ROLES, PALETTES[p])) if isinstance(p, str) else p


def timeline_defaults(s):
    """The style and captions blocks of timeline.json, ready to copy (SKILL.md > palette mapping)."""
    d = s["defaults"]
    c = palette_colors(d["palette"])
    style = {"font": d["font"], "text": c["texto"], "panel_text": c["texto"], "accent": c["principal"],
             "highlight": c["principal"], "emphasis": c["secundario"], "danger": c["alerta"],
             "panel": c["fondo"], "accent_text": c["fondo"], "outline": "#000000",
             "palette": d["palette"] if isinstance(d["palette"], str) else "custom", "anim_style": d["anim_style"]}
    cap = {k: v for k, v in d["captions"].items() if v is not None}
    return {"style": style, "captions": cap}


def edit_defaults(s):
    d = s["defaults"]
    return {**d["cuts"], "loudness": d["loudness"]}


def voice_settings(s):
    """Engine keys the plugin writes into edit.json "voice" before voice_clone.py runs."""
    v = s["voice"]
    keys = {"voxcpm": ("steps", "cfg_value"), "cosyvoice": ("cosyvoice_dir", "cosyvoice_model"),
            "mistral": ("mistral_model", "mistral_key_env")}[v["engine"]]
    return {"engine": v["engine"], **{k: v[k] for k in keys if v.get(k) is not None}}


def public_view(s):
    """Settings as the model and the UI see them: no secret values, only whether each one is set."""
    return {"settings": s, "config_path": str(config_path()), "projects_dir": str(projects_dir(s)),
            "secrets": secret_status(), "choices": CHOICES, "palettes": PALETTES}


def brief(s):
    """One paragraph per decision, in the words the skill's intake would have produced."""
    d = s["defaults"]
    cap = d["captions"]
    pal = d["palette"] if isinstance(d["palette"], str) else "custom " + ", ".join(d["palette"].values())
    v = s["voice"]
    if not v["enabled"]:
        voice = "voice cloning OFF (do not offer voice patches or voice-overs)"
    elif v["engine"] == "mistral":
        voice = ("voice cloning ON with Mistral Voxtral (cloud: only the ~10 s reference clip and the text of each "
                 "line are sent to api.mistral.ai; tell the user once before generating)")
    else:
        voice = f"voice cloning ON with {v['engine']} (local)"
    lines = [
        f"platform: {d['platform']}; video type: {d['video_type']}"
        + (f"; target length ~{d['target_duration']} s" if d.get("target_duration") else ""),
        "captions: OFF" if cap["mode"] == "off" else
        f"captions: {cap['mode']}, {cap['position']}" + (f" (y={cap['y']})" if cap.get("y") else "")
        + f", {cap['max_words']} words, size {cap['size']}, {'UPPERCASE' if cap.get('uppercase') else 'as spoken'}",
        "effects: " + (", ".join(d["effects"]) or "none"),
        f"animation style: {d['anim_style']}; palette: {pal}; font: {d['font']}; loudness: {d['loudness']} LUFS",
        f"cuts: max_gap {d['cuts']['max_gap']} s, pad {d['cuts']['pad']} s, denoise {d['cuts']['denoise']}",
        f"transcription: {s['transcribe']['model']}, speakers {s['transcribe']['speakers']}; glossary: "
        + (", ".join(s["glossary"]) or "none"),
        voice,
        "extras (title, description, hashtags, thumbnails): " + ("yes" if d.get("extras", True) else "no"),
    ]
    if d.get("notes"):
        lines.append(f"user notes: {d['notes']}")
    return "\n".join("- " + ln for ln in lines)
