"""The tools the plugin exposes. Every media step runs the skill's own scripts on this machine.

Nothing here uploads the video. The only outbound traffic is what the scripts already do: model
downloads from Hugging Face on first use and, when the user picks the Mistral voice engine, the
reference clip plus each line's text to api.mistral.ai.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import settings as cfg

HERE = Path(__file__).resolve().parent
UI_FILE = (HERE.parent / "ui" / "editor.html")


def skill_dir():
    for p in (os.environ.get("SVE_SKILL_DIR"), HERE.parent.parent / "social-video-editor", HERE.parent / "skill"):
        if p and (Path(p) / "SKILL.md").exists():
            return Path(p).resolve()
    raise RuntimeError("social-video-editor skill folder not found (set SVE_SKILL_DIR)")


class ToolError(Exception):
    pass


# ---- projects ------------------------------------------------------------------------------

SLUG = re.compile(r"[^a-z0-9]+")


def slug(name):
    import unicodedata
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return SLUG.sub("-", s).strip("-")[:60] or "video"


def project_path(s, name):
    root = cfg.projects_dir(s)
    p = (root / name).resolve()
    if p.parent != root.resolve() or name.startswith("_") or not p.is_dir():
        raise ToolError(f"unknown project '{name}' in {root} (create it with setup_project)")
    return p


STEP_FILES = [("transcript", "work/transcript.json"), ("edit", "work/edit.json"), ("cut", "work/cut.mkv"),
              ("timeline", "work/timeline.json"), ("preview", "work/preview.mp4"), ("final", "final/final.mp4")]


def project_status(p):
    done = {k: (p / f).exists() for k, f in STEP_FILES}
    nxt = next((k for k, _ in STEP_FILES if not done[k]), None)
    src = next((f.name for f in p.iterdir() if f.suffix.lower() in VIDEO_EXT), None)
    return {"name": p.name, "path": str(p), "source": src, "done": done, "next": nxt,
            "updated": max((p / f).stat().st_mtime for k, f in STEP_FILES if done[k]) if any(done.values()) else
            p.stat().st_mtime}


def list_projects(s):
    root = cfg.projects_dir(s)
    if not root.is_dir():
        return []
    ps = [project_status(p) for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))]
    return sorted(ps, key=lambda x: -x["updated"])


VIDEO_EXT = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}


def setup_project(s, video_path, name=None):
    src = Path(os.path.expanduser(video_path)).resolve()
    if not src.is_file() or src.suffix.lower() not in VIDEO_EXT:
        raise ToolError(f"video not found or not a video file: {src}")
    root = cfg.projects_dir(s)
    name = slug(name or src.stem)
    p = root / name
    link = p / src.name
    if p.exists() and not (link.exists() and link.resolve() == src):
        raise ToolError(f"a project called '{name}' already exists for another video; pass a different name")
    shared = root / "_shared"
    for d in ("models", "envs", "voices", "fonts", "sfx", "anims"):
        (shared / d).mkdir(parents=True, exist_ok=True)
    for d in ("work/anims", "work/voice", "work/logs", "final"):
        (p / d).mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(src)  # never move or copy the user's original
    shutil.copytree(skill_dir() / "scripts", p / "scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    fonts = p / "work" / "fonts"
    if not fonts.exists():
        fonts.symlink_to(shared / "fonts")
    return project_status(p)


# ---- environment ---------------------------------------------------------------------------

def python_for(s, env):
    """Interpreter for an environment: runtime override, then <projects>/_shared/envs/<env>, then this one."""
    override = s["runtime"].get(f"python_{env}")
    if override:
        return override
    shared = cfg.projects_dir(s) / "_shared" / "envs"
    names = {"main": ("whisperx", ".venv"), "whisperx": ("whisperx", ".venv"),
             "voxcpm": ("voxcpm", ".venv-voice"), "cosyvoice": ("cosyvoice",)}[env]
    for n in names:
        for b in ("bin/python", "Scripts/python.exe"):
            if (shared / n / b).exists():
                return str(shared / n / b)
    return sys.executable if env == "main" else None


FFMPEG_DIRS = ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin", "/opt/homebrew/bin",
               "/usr/local/bin", "/usr/bin")
_FFMPEG_DIR = {}


def ffmpeg_dir(s):
    """Folder of the first FFmpeg built with libass (captions need it); Homebrew's plain ffmpeg lacks it."""
    want = s["runtime"].get("ffmpeg_dir")
    if want:
        return want
    if "dir" not in _FFMPEG_DIR:
        found = shutil.which("ffmpeg")
        cands = ([str(Path(found).parent)] if found else []) + [d for d in FFMPEG_DIRS if Path(d, "ffmpeg").exists()]
        _FFMPEG_DIR["dir"] = next((d for d in cands if re.search(r"\sass\s", _probe(
            [str(Path(d, "ffmpeg")), "-hide_banner", "-filters"])[1])), cands[0] if cands else None)
    return _FFMPEG_DIR["dir"]


def ffmpeg(s):
    d = ffmpeg_dir(s)
    return str(Path(d, "ffmpeg")) if d else "ffmpeg"


def _probe(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout + p.stderr)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def check_environment(s):
    out = {}
    ok, txt = _probe([ffmpeg(s), "-hide_banner", "-filters"])
    out["ffmpeg"] = ok
    out["ffmpeg_path"] = ffmpeg(s)
    out["ffmpeg_libass"] = ok and bool(re.search(r"\sass\s", txt))
    out["ffmpeg_loudnorm"] = ok and "loudnorm" in txt
    for env, mod in (("main", "numpy, PIL, cv2"), ("whisperx", "whisperx"), ("voxcpm", "voxcpm"),
                     ("cosyvoice", "torch")):
        py = python_for(s, env)
        out[f"python_{env}"] = py
        out[f"{env}_ok"] = bool(py) and _probe([py, "-c", f"import {mod}"], 120)[0]
    out["secrets"] = cfg.secret_status()
    v = s["voice"]
    problems = []
    if not out["ffmpeg_libass"]:
        problems.append("FFmpeg with libass is missing (macOS: brew install ffmpeg-full; Debian/Ubuntu: "
                        "apt install ffmpeg), or set runtime.ffmpeg_dir in the settings")
    if not out["main_ok"]:
        problems.append(f"the main Python ({out['python_main']}) lacks numpy, pillow or opencv-python-headless")
    if not out["whisperx_ok"]:
        problems.append("WhisperX is not installed: create <projects>/_shared/envs/whisperx and pip install whisperx")
    if v["enabled"] and v["engine"] in cfg.LOCAL_ENGINES and not out[f"{v['engine']}_ok"]:
        problems.append(f"voice engine {v['engine']} is not installed in <projects>/_shared/envs/{v['engine']}")
    if v["enabled"] and v["engine"] == "mistral" and not out["secrets"]["MISTRAL_API_KEY"]:
        problems.append("Mistral is the voice engine but no API key is saved (settings UI > Voz)")
    out["problems"] = problems
    out["ready"] = not problems
    return out


# ---- jobs ----------------------------------------------------------------------------------

JOBS = {}
JOBS_LOCK = threading.Lock()
STEPS = {
    # step: (env, script, args builder)
    "sfx": ("main", "sfx_synth.py"),
    "transcribe": ("whisperx", "transcribe.py"),
    "build_edit": ("main", "build_edit.py"),
    "voice_clone": (None, "voice_clone.py"),
    "align_voice": ("whisperx", "align_voice.py"),
    "animation": ("main", None),
    "check": ("main", "render.py"),
    "preview": ("main", "render.py"),
    "final": ("main", "render.py"),
}


def _env(s):
    e = dict(os.environ)
    if ffmpeg_dir(s):
        e["PATH"] = ffmpeg_dir(s) + os.pathsep + e.get("PATH", "")
    e["HF_HOME"] = str(cfg.projects_dir(s) / "_shared" / "models")
    e["PYTHONUNBUFFERED"] = "1"
    e.setdefault("TOKENIZERS_PARALLELISM", "false")
    for n in cfg.SECRET_NAMES:
        val = cfg.get_secret(n)
        if val:
            e[n] = val
    key_env = s["voice"].get("mistral_key_env") or "MISTRAL_API_KEY"
    if key_env != "MISTRAL_API_KEY" and e.get("MISTRAL_API_KEY"):
        e.setdefault(key_env, e["MISTRAL_API_KEY"])
    return e


def _apply_voice_settings(s, p):
    """The engine picked in the UI wins over edit.json; consent, ref and seeds stay the agent's."""
    v = s["voice"]
    if not v["enabled"]:
        raise ToolError("voice cloning is turned off in the settings; the user can enable it in the UI (Voz)")
    if v["engine"] == "mistral" and not cfg.get_secret("MISTRAL_API_KEY"):
        raise ToolError("no Mistral API key saved; ask the user to add it in the settings UI (never in chat)")
    path = p / "work" / "edit.json"
    edit = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    edit["voice"] = {**edit.get("voice", {}), **cfg.voice_settings(s)}
    path.write_text(json.dumps(edit, ensure_ascii=False, indent=2), encoding="utf-8")
    return v["engine"]


def build_command(s, p, step, opts):
    env, script = STEPS[step]
    sc = p / "scripts"
    if step == "voice_clone":
        env = _apply_voice_settings(s, p)
        env = env if env in cfg.LOCAL_ENGINES else "main"
    py = python_for(s, env)
    if not py:
        raise ToolError(f"no Python environment for '{env}' (expected {cfg.projects_dir(s)}/_shared/envs/{env}); "
                        "run check_environment and follow SKILL.md > Setup")
    sfx_dir = cfg.projects_dir(s) / "_shared" / "sfx"
    if step == "sfx":
        return [py, str(sc / script), "--out", str(sfx_dir)]
    if step == "transcribe":
        src = project_status(p)["source"]
        if not src:
            raise ToolError("the project has no source video")
        cmd = [py, str(sc / script), src, "--out", "work", "--model", s["transcribe"]["model"]]
        if s["glossary"]:
            cmd += ["--glossary", ", ".join(s["glossary"])]
        if int(s["transcribe"].get("speakers") or 0) > 1:
            cmd += ["--speakers", str(s["transcribe"]["speakers"])]
        return cmd
    if step in ("build_edit", "align_voice"):
        return [py, str(sc / script), "--work", "work"]
    if step == "voice_clone":
        return [py, str(sc / script), "--work", "work"] + (["--force"] if opts.get("force") else [])
    if step == "animation":
        aid = str(opts.get("id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]+", aid) or not (p / "work" / "anims" / f"{aid}.py").exists():
            raise ToolError(f"work/anims/{aid}.py not found; write it with write_project_file first")
        return [py, str(p / "work" / "anims" / f"{aid}.py")]
    if not sfx_dir.joinpath("whoosh.wav").exists():
        subprocess.run([python_for(s, "main"), str(sc / "sfx_synth.py"), "--out", str(sfx_dir)], cwd=p,
                       capture_output=True, env=_env(s))
    cmd = [py, str(sc / script), "--work", "work", "--sfx", str(sfx_dir)]
    return cmd + {"check": ["--check"], "preview": ["--preview", "--sheet"], "final": []}[step]


def start_job(s, project, step, opts=None):
    if step not in STEPS:
        raise ToolError(f"step must be one of {', '.join(STEPS)}")
    p = project_path(s, project)
    with JOBS_LOCK:
        busy = [j for j in JOBS.values() if j["project"] == project and j["proc"].poll() is None]
    if busy:
        raise ToolError(f"'{busy[0]['step']}' is still running for this project (job {busy[0]['id']})")
    cmd = build_command(s, p, step, opts or {})
    log = p / "work" / "logs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{step}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log, "w", encoding="utf-8")
    fh.write("$ " + " ".join(cmd) + "\n\n")
    fh.flush()
    proc = subprocess.Popen(cmd, cwd=p, env=_env(s), stdout=fh, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL)
    job = {"id": uuid.uuid4().hex[:8], "project": project, "step": step, "proc": proc, "log": log, "fh": fh,
           "started": time.time()}
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    return job_status(job["id"], wait=3)


def _finish(job):
    if job["step"] == "final" and job["proc"].returncode == 0:
        p = job["log"].parents[2]
        shutil.copy2(p / "work" / "final.mp4", p / "final" / "final.mp4")


def job_status(job_id, wait=0, lines=40):
    job = JOBS.get(job_id)
    if not job:
        raise ToolError(f"unknown job {job_id} (jobs live as long as the plugin process)")
    deadline = time.time() + max(0, min(float(wait or 0), 55))
    while job["proc"].poll() is None and time.time() < deadline:
        time.sleep(0.5)
    rc = job["proc"].poll()
    if rc is not None and not job["fh"].closed:
        job["fh"].close()
        _finish(job)
    tail = job["log"].read_text(encoding="utf-8", errors="replace").splitlines()[-int(lines):]
    state = "running" if rc is None else "done" if rc == 0 else "failed"
    return {"job": job_id, "project": job["project"], "step": job["step"], "state": state, "exit_code": rc,
            "elapsed_s": round(time.time() - job["started"], 1), "log": str(job["log"]), "tail": "\n".join(tail)}


def running_jobs():
    with JOBS_LOCK:
        jobs = list(JOBS.values())
    return [job_status(j["id"], lines=3) for j in jobs if j["proc"].poll() is None]


# ---- files the agent reads and writes ------------------------------------------------------

WRITABLE = [re.compile(r) for r in (r"work/edit\.json", r"work/timeline\.json", r"work/transcript\.json",
                                    r"work/anims/[A-Za-z0-9_-]+\.py", r"final/extras\.md")]
TEXT_EXT = {".json", ".txt", ".py", ".md", ".ass", ".log"}


def _inside(p, rel):
    f = (p / rel).resolve()
    if p.resolve() not in f.parents:
        raise ToolError("path must stay inside the project")
    return f


def read_project_file(s, project, path, max_chars=60000):
    p = project_path(s, project)
    f = _inside(p, path)
    if not f.is_file() or f.suffix.lower() not in TEXT_EXT:
        raise ToolError(f"{path} is not a readable text file in the project")
    txt = f.read_text(encoding="utf-8", errors="replace")
    return txt if len(txt) <= max_chars else txt[:max_chars] + f"\n… [truncated, {len(txt)} chars]"


def write_project_file(s, project, path, content):
    p = project_path(s, project)
    rel = path.replace("\\", "/").lstrip("./")
    if not any(r.fullmatch(rel) for r in WRITABLE):
        raise ToolError("only work/edit.json, work/timeline.json, work/transcript.json, work/anims/<id>.py and "
                        "final/extras.md can be written")
    if rel.endswith(".json"):
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            raise ToolError(f"invalid JSON: {e}")
    f = _inside(p, rel)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return {"written": rel, "bytes": len(content.encode())}


def view_image(s, project, path=None, video=None, time_s=None, max_width=1280):
    """An image (QA sheet, animation sheet) or a frame of a project video, scaled down, as JPEG."""
    p = project_path(s, project)
    if path:
        src = _inside(p, path)
        if not src.is_file():
            raise ToolError(f"{path} not found")
        pre = []
    else:
        videos = {"source": p / (project_status(p)["source"] or "-"), "cut": p / "work" / "cut.mkv",
                  "preview": p / "work" / "preview.mp4", "final": p / "final" / "final.mp4"}
        src = videos.get(video or "source")
        if not src or not src.exists():
            raise ToolError(f"video '{video}' does not exist yet (one of {', '.join(videos)})")
        pre = ["-ss", f"{float(time_s or 0):.3f}"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "img.jpg"
        r = subprocess.run([ffmpeg(s), "-y", "-loglevel", "error", *pre, "-i", str(src), "-frames:v", "1", "-vf",
                            f"scale='min({int(max_width)},iw)':-2", "-q:v", "4", str(out)], capture_output=True,
                           text=True)
        if r.returncode or not out.exists():
            raise ToolError("could not read the image: " + r.stderr[-400:])
        return base64.b64encode(out.read_bytes()).decode()


def media_file(s, project, which):
    """Absolute path of a project video for the local settings page player."""
    p = project_path(s, project)
    f = {"preview": p / "work" / "preview.mp4", "final": p / "final" / "final.mp4",
         "qa": p / "work" / "qa_sheet.jpg"}.get(which)
    if not f or not f.exists():
        raise ToolError("not available yet")
    return f
