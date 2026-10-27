#!/usr/bin/env python3
"""Social Video Editor: local MCP server for Claude and ChatGPT. Standard library only.

  python main.py                 stdio (Claude Code, Claude Desktop, Codex)
  python main.py --http [PORT]   Streamable HTTP on 127.0.0.1 (ChatGPT through a tunnel, MCP inspectors)

Both modes also serve the settings page on http://127.0.0.1:<port>/?token=... The same page is
rendered inside the chat as an MCP App (Claude) or an Apps SDK widget (ChatGPT). All media work
happens on this machine; see tools.py for the only outbound traffic.
"""
import json
import mimetypes
import os
import secrets
import socket
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
# GUI hosts (Claude Desktop) start servers with a bare PATH; FFmpeg and Homebrew live here
for _d in ("/opt/homebrew/bin", "/usr/local/bin"):
    if Path(_d).is_dir() and _d not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + _d
import settings as cfg  # noqa: E402
import tools  # noqa: E402
from tools import ToolError  # noqa: E402

NAME, VERSION = "social-video-editor", "1.5.0"
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = """Edits Spanish talking-head videos for social media on the user's own machine.
1. Start every edit with open_settings (pass the video path if you know it), before reading the video, opening
   links, checking the environment or anything else: the user reviews this run's options (captions, effects,
   style, palette, voice engine…) there instead of answering the intake questions. Ask any question the request
   itself raises (which part of the video, how long, a linked article's role…) in the same turn.
2. The settings page opens in the user's browser. Show them its link from the open_settings result as a
   clickable Markdown link, read get_skill_guide if the social-video-editor skill is not loaded, then call
   wait_for_settings until it returns confirmed. Then call get_settings and say in one line what you are using.
   If the user asks to change an option in chat, use save_settings.
3. Use these tools instead of a shell: setup_project, run_step (+ job_status for long steps),
   read_project_file / write_project_file for the decision files and animations, view_image to look at
   frames and QA sheets. Keep the skill's two checkpoints (cut plan + effects table, then the preview).
4. Never ask the user to paste an API key in chat; keys are entered in the settings page and never reach you."""

STATE = {"token": None, "ui_url": None, "ui_server": None, "http": False}
RUN = {"event": threading.Event(), "video_path": None, "pending": False, "waiting": 0}  # "Guardar y editar"


def token():
    if STATE["token"]:
        return STATE["token"]
    f = cfg.HOME_DIR / "token"
    t = os.environ.get("SVE_TOKEN") or (f.read_text().strip() if f.exists() else "")
    if not t:
        t = secrets.token_urlsafe(18)
        cfg.HOME_DIR.mkdir(parents=True, exist_ok=True)
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(t)
    STATE["token"] = t
    return t


# ---- tool registry -------------------------------------------------------------------------

def schema(props=None, required=()):
    return {"type": "object", "properties": props or {}, "required": list(required), "additionalProperties": False}


PROJECT = {"type": "string", "description": "project folder name (from setup_project or list_projects)"}
RO = {"readOnlyHint": True, "openWorldHint": False}

TOOLS = [
    ("open_settings", "Open the settings page (video type, captions, effects, style, palette, voice engine, "
     "Mistral key, projects folder…) in the user's browser and return its link. Call it first on every edit, "
     "before any other tool, so the user reviews this run's options, and whenever they want to see or change "
     "them. Show the user the link, then call wait_for_settings.",
     schema({"video_path": {"type": "string", "description": "optional: the video the user wants to edit"},
             "open_browser": {"type": "boolean", "description": "open the local page in the user's browser"},
             "reload": {"type": "boolean", "description": "set only by the settings UI when it loads"}}),
     RO),
    ("wait_for_settings", "After open_settings opened the browser: wait until the user presses \"Guardar y "
     "editar\" in the settings page. wait_s (≤55) blocks; call again while confirmed is false. Returns the video "
     "path the user entered.", schema({"wait_s": {"type": "number"}}), RO),
    ("get_settings", "The user's saved choices as a brief, plus ready-to-copy timeline.json style/captions and "
     "edit.json cut defaults. Use it instead of the intake questions.", schema(), RO),
    ("save_settings", "Save the full settings object (as returned by get_settings.settings, modified). Only when "
     "the user asks to change an option in chat; the UI saves by itself.",
     schema({"settings": {"type": "object"}}, ["settings"]), {"openWorldHint": False}),
    ("get_skill_guide", "The full editing procedure (SKILL.md): rules, JSON schemas, animation API. Read it once "
     "per conversation if the skill is not already loaded. Optionally pass a heading to get one section.",
     schema({"section": {"type": "string"}}), RO),
    ("check_environment", "Check FFmpeg (libass), the Python environments (main, WhisperX, voice engines) and "
     "saved keys on this machine. Returns problems with fixes.", schema(), RO),
    ("list_projects", "Projects in the projects folder with the steps already done.", schema(), RO),
    ("setup_project", "Create a project for a video on this machine: links the video (never moves it), copies "
     "the scripts and creates work/ and final/. Returns the project name to use with the other tools.",
     schema({"video_path": {"type": "string", "description": "absolute path of the source video"},
             "name": {"type": "string", "description": "optional project name"}}, ["video_path"]),
     {"openWorldHint": False}),
    ("run_step", "Run one pipeline step locally in the background and return a job: transcribe, build_edit, "
     "voice_clone (engine from settings), align_voice, animation (needs id: renders work/anims/<id>.py), check, "
     "preview (also writes the QA sheet), final (copies to final/final.mp4), sfx. Poll with job_status.",
     schema({"project": PROJECT, "step": {"type": "string", "enum": list(tools.STEPS)},
             "id": {"type": "string", "description": "animation id for step=animation"},
             "force": {"type": "boolean", "description": "voice_clone: regenerate every line"}},
            ["project", "step"]), {"openWorldHint": False}),
    ("job_status", "State and log tail of a job. wait_s (≤55) blocks until it finishes or the time is up.",
     schema({"job_id": {"type": "string"}, "wait_s": {"type": "number"}}, ["job_id"]), RO),
    ("read_project_file", "Read a text file of a project (transcript.json, transcript_edited.txt, timeline.json, "
     "logs…). Paths are relative to the project folder.",
     schema({"project": PROJECT, "path": {"type": "string"}}, ["project", "path"]), RO),
    ("write_project_file", "Write a decision file or an animation: work/edit.json, work/timeline.json, "
     "work/transcript.json (text fixes), work/anims/<id>.py, final/extras.md.",
     schema({"project": PROJECT, "path": {"type": "string"}, "content": {"type": "string"}},
            ["project", "path", "content"]), {"openWorldHint": False}),
    ("view_image", "Look at an image of the project (work/qa_sheet.jpg, work/anims/<id>_sheet.png) or at one "
     "frame of a video (video = source | cut | preview | final, time_s in that video's seconds).",
     schema({"project": PROJECT, "path": {"type": "string"},
             "video": {"type": "string", "enum": ["source", "cut", "preview", "final"]},
             "time_s": {"type": "number"}}, ["project"]), RO),
]
TOOL_INDEX = {t[0]: t for t in TOOLS}
# Calls only the local page (browser -> 127.0.0.1) can make. They are not MCP tools: a key never travels through
# the chat host or reaches the model, and only the user can start a run.
LOCAL_ONLY = ("save_secret", "test_secret", "confirm_settings")


def text(t):
    return {"type": "text", "text": t}


def result(msg, data=None, extra=None):
    r = {"content": [text(msg)] + (extra or [])}
    if data is not None:
        r["structuredContent"] = data
    return r


def settings_payload(s, video_path=None):
    view = cfg.public_view(s)
    view["projects"] = tools.list_projects(s)
    view["jobs"] = tools.running_jobs()
    view["ui_url"] = ensure_ui_server()
    view["video_path"] = video_path
    view["run_pending"] = RUN["pending"]
    view["skill_version"] = (tools.skill_dir() / "VERSION").read_text().strip()
    return view


def section(md, heading):
    lines, out, level = md.splitlines(), [], None
    for ln in lines:
        if ln.startswith("#"):
            lv = len(ln) - len(ln.lstrip("#"))
            if level is not None and lv <= level:
                break
            if level is None and heading.lower() in ln.lower():
                level = lv
        if level is not None:
            out.append(ln)
    return "\n".join(out)


def call_tool(name, a):
    s = cfg.load_settings()
    if name == "open_settings":
        if not a.get("reload"):  # a new run; the page's own load (reload) keeps the run it belongs to
            RUN["event"].clear()
            RUN.update(video_path=a.get("video_path"), pending=True)
        data = settings_payload(s, RUN["video_path"])
        opened = a.get("open_browser", True) and webbrowser.open(data["ui_url"])
        return result(f"Settings page{' opened in the browser' if opened else ''}. Show the user this link (it only "
                      f"works on their computer): [Abrir los ajustes]({data['ui_url']})\n"
                      f"Current settings:\n{cfg.brief(s)}\n"
                      "Call wait_for_settings until the user presses \"Guardar y editar\", then get_settings.", data)
    if name == "confirm_settings":
        RUN.update(video_path=(a.get("video_path") or "").strip() or None, pending=False)
        RUN["event"].set()
        return result("Run confirmed.", {"confirmed": True, "agent_waiting": RUN["waiting"] > 0})
    if name == "wait_for_settings":
        RUN["waiting"] += 1
        try:
            done = RUN["event"].wait(max(0, min(float(a.get("wait_s", 50)), 55)))
        finally:
            RUN["waiting"] -= 1
        if not done:
            return result("Still waiting for the user to press \"Guardar y editar\". Call wait_for_settings again.",
                          {"confirmed": False})
        vp = RUN["video_path"]
        return result("The user confirmed this run's settings" + (f" for {vp}" if vp else "")
                      + ". Call get_settings and start.\n" + cfg.brief(cfg.load_settings()),
                      {"confirmed": True, "video_path": vp})
    if name == "get_settings":
        data = {"brief": cfg.brief(s), "timeline_defaults": cfg.timeline_defaults(s),
                "edit_defaults": cfg.edit_defaults(s), "projects_dir": str(cfg.projects_dir(s)),
                "settings": s, "secrets": cfg.secret_status(), "config_path": str(cfg.config_path())}
        return result("User settings (from the settings UI):\n" + data["brief"] + "\n\ntimeline.json defaults: "
                      + json.dumps(data["timeline_defaults"], ensure_ascii=False) + "\nedit.json defaults: "
                      + json.dumps(data["edit_defaults"]), data)
    if name == "save_settings":
        saved, path = cfg.save_settings(a["settings"])
        return result(f"Saved to {path}.\n{cfg.brief(saved)}", settings_payload(saved))
    if name == "save_secret":
        cfg.set_secret(a["name"], a.get("value", ""))
        saved = bool(a.get("value", "").strip())
        return result(f"{a['name']} {'saved' if saved else 'removed'}.", {"secrets": cfg.secret_status()})
    if name == "test_secret":
        good, why = cfg.test_secret(a["name"])
        return result(why, {"ok": good, "secrets": cfg.secret_status()})
    if name == "get_skill_guide":
        md = (tools.skill_dir() / "SKILL.md").read_text(encoding="utf-8")
        if a.get("section"):
            md = section(md, a["section"]) or f"No section matching '{a['section']}'."
        return result(md + "\n\n(Plugin mode: run the commands above with run_step, not a shell.)")
    if name == "check_environment":
        env = tools.check_environment(s)
        msg = "Ready." if env["ready"] else "Problems:\n- " + "\n- ".join(env["problems"])
        return result(msg, env)
    if name == "list_projects":
        ps = tools.list_projects(s)
        lines = [f"- {p['name']}: next step {p['next'] or 'done'}" for p in ps]
        return result("\n".join(lines) or f"No projects yet in {cfg.projects_dir(s)}.", {"projects": ps})
    if name == "setup_project":
        st = tools.setup_project(s, a["video_path"], a.get("name"))
        return result(f"Project '{st['name']}' ready at {st['path']}. Next: run_step transcribe.", st)
    if name == "run_step":
        st = tools.start_job(s, a["project"], a["step"], {k: a[k] for k in ("id", "force") if k in a})
        return result(_job_text(st), st)
    if name == "job_status":
        st = tools.job_status(a["job_id"], a.get("wait_s", 0))
        return result(_job_text(st), st)
    if name == "read_project_file":
        return result(tools.read_project_file(s, a["project"], a["path"]))
    if name == "write_project_file":
        st = tools.write_project_file(s, a["project"], a["path"], a["content"])
        return result(f"Wrote {st['written']} ({st['bytes']} bytes).", st)
    if name == "view_image":
        b64 = tools.view_image(s, a["project"], a.get("path"), a.get("video"), a.get("time_s"))
        what = a.get("path") or f"{a.get('video', 'source')} @ {a.get('time_s', 0)}s"
        return result(f"Image: {what}", None, [{"type": "image", "data": b64, "mimeType": "image/jpeg"}])
    raise ToolError(f"unknown tool {name}")


def _job_text(st):
    head = f"job {st['job']} · {st['step']} · {st['state']} · {st['elapsed_s']} s"
    if st["state"] == "running":
        head += " (call job_status with wait_s=50 to keep waiting)"
    return head + "\n" + st["tail"][-3000:]


def safe_call(name, args, local=False):
    if name not in TOOL_INDEX and not (local and name in LOCAL_ONLY):
        return {"content": [text(f"unknown tool {name}")], "isError": True}
    try:
        return call_tool(name, args or {})
    except (ToolError, ValueError, KeyError, OSError, RuntimeError) as e:
        return {"content": [text(f"Error: {e}")], "isError": True}


# ---- JSON-RPC ------------------------------------------------------------------------------

def handle(msg):
    """One JSON-RPC message in, one response (or None for notifications) out."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method is None:
        return None  # a response to something we never send
    if mid is None:
        return None  # notifications: initialized, cancelled, roots changed…

    def ok(r):
        return {"jsonrpc": "2.0", "id": mid, "result": r}

    if method == "initialize":
        want = params.get("protocolVersion")
        return ok({"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[1],
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": NAME, "title": "Social Video Editor", "version": VERSION},
                   "instructions": INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [{"name": n, "title": n.replace("_", " ").capitalize(), "description": d,
                              "inputSchema": sc, "annotations": ann}
                             for n, d, sc, ann in TOOLS]})
    if method == "tools/call":
        return ok(safe_call(params.get("name"), params.get("arguments")))
    if method in ("prompts/list",):
        return ok({"prompts": []})
    if method == "logging/setLevel":
        return ok({})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def handle_body(body):
    try:
        msg = json.loads(body)
    except json.JSONDecodeError:
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
    if isinstance(msg, list):
        out = [r for r in (handle(m) for m in msg) if r]
        return out or None
    return handle(msg)


# ---- HTTP: settings page, its API, media and the MCP endpoint -------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "sve/" + VERSION

    def log_message(self, *a):
        pass

    def _authed(self, q):
        t = (q.get("token") or [""])[0] or self.headers.get("X-SVE-Token", "")
        return secrets.compare_digest(t, token())

    def _send(self, code, body=b"", ctype="application/json", headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.startswith("/mcp"):
            return self._send(405, b"", headers={"Allow": "POST"})
        if not self._authed(q):
            return self._send(403, b"Forbidden: open the link given by the open_settings tool.", "text/plain")
        if u.path == "/":
            html = tools.UI_FILE.read_text(encoding="utf-8").replace(
                "/*SVE_BOOT*/", "window.SVE_BOOT = " + json.dumps({"mode": "standalone", "token": token()}) + ";")
            return self._send(200, html.encode(), "text/html; charset=utf-8",
                              {"Content-Security-Policy": "default-src 'self' 'unsafe-inline' data: blob:"})
        if u.path.startswith("/media/"):
            _, _, project, which = u.path.split("/", 3)
            try:
                f = tools.media_file(cfg.load_settings(), unquote(project), which)
            except ToolError as e:
                return self._send(404, str(e).encode(), "text/plain")
            return self._file(f)
        self._send(404, b"not found", "text/plain")

    do_HEAD = do_GET

    def _file(self, f):
        size = f.stat().st_size
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range", "")
        start, end = 0, size - 1
        if rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else max(0, size - int(b))
            end = min(int(b), size - 1) if a and b else end
        length = end - start + 1
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(f, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                chunk = fh.read(min(1 << 16, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if u.path.rstrip("/") in (f"/mcp/{token()}", "/mcp"):
            if u.path.rstrip("/") == "/mcp" and not self._authed(q):
                return self._send(401, b'{"error":"use the /mcp/<token> URL"}')
            r = handle_body(body)
            return self._send(202) if r is None else self._json(200, r)
        if u.path == "/api/call":
            if not self._authed(q) or self.headers.get("Origin") not in (None, self._origin()):
                return self._send(403, b'{"error":"forbidden"}')
            try:
                req = json.loads(body)
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad json"})
            return self._json(200, safe_call(req.get("name"), req.get("arguments"), local=self._direct()))
        self._send(404, b"not found", "text/plain")

    def _direct(self):
        """True for a browser on this machine; False through a tunnel (ChatGPT mode), which adds proxy headers."""
        host = self.headers.get("Host", "").rsplit(":", 1)[0]
        proxied = any(self.headers.get(h) for h in ("X-Forwarded-For", "Forwarded", "Cf-Connecting-Ip", "X-Real-Ip"))
        return host in ("127.0.0.1", "localhost") and not proxied

    def _origin(self):
        return f"http://{self.headers.get('Host', '')}"


def _bind(port):
    for p in (port, 0):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), Handler)
        except OSError:
            continue
    raise RuntimeError("cannot open a local port")


def ensure_ui_server(port=None):
    if STATE["ui_server"] is None:
        srv = _bind(int(port or os.environ.get("SVE_UI_PORT", 8765)))
        STATE["ui_server"] = srv
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        STATE["ui_url"] = f"http://127.0.0.1:{srv.server_address[1]}/?token={token()}"
    return STATE["ui_url"]


# ---- entry points --------------------------------------------------------------------------

def serve_stdio():
    lock = threading.Lock()

    def reply(line):
        try:
            r = handle_body(line)
        except Exception:  # never let one bad request kill the server
            traceback.print_exc(file=sys.stderr)
            return
        if r is not None:
            with lock:
                sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")
                sys.stdout.flush()

    workers = []
    for line in sys.stdin:
        if line.strip():
            workers = [w for w in workers if w.is_alive()]
            workers.append(threading.Thread(target=reply, args=(line,), daemon=True))
            workers[-1].start()
    for w in workers:  # stdin closed: answer what is in flight before exiting
        w.join(60)


def serve_http(port):
    STATE["http"] = True
    url = ensure_ui_server(port)
    p = STATE["ui_server"].server_address[1]
    print(f"Social Video Editor MCP server (local)\n  MCP endpoint: http://127.0.0.1:{p}/mcp/{token()}\n"
          f"  Settings page: {url}\nExpose the MCP endpoint to ChatGPT through an HTTPS tunnel "
          f"(see plugin/README.md). Ctrl+C to stop.", file=sys.stderr)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


def main():
    args = sys.argv[1:]
    if args and args[0] == "--http":
        serve_http(int(args[1]) if len(args) > 1 else int(os.environ.get("SVE_UI_PORT", 8765)))
    elif args and args[0] in ("-h", "--help"):
        print(__doc__)
    else:
        socket.setdefaulttimeout(None)
        serve_stdio()


if __name__ == "__main__":
    main()
