"""Compare this skill's VERSION with the one published on GitHub. Never fails the run.

Usage (from anywhere; it reads the VERSION next to SKILL.md):
  python <skill_dir>/scripts/check_update.py [--repo owner/repo]

Prints exactly one line:
  UP_TO_DATE 1.1.0
  UPDATE 1.1.0 -> 1.2.0
  UNKNOWN <reason>          (offline, no VERSION file, unreadable remote...)
VERSION holds a semantic version (MAJOR.MINOR.PATCH) that is bumped in every change to the skill,
so the comparison stays meaningful across merges (a commit hash cannot name its own commit).
"""
import argparse
import re
import urllib.request
from pathlib import Path

DEFAULT_REPO = "manubatet/skill-video-edition"


def parse(v):
    m = re.fullmatch(r"\s*v?(\d+)\.(\d+)\.(\d+)\s*", v or "")
    return tuple(int(x) for x in m.groups()) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo (update_repo in the user config)")
    ap.add_argument("--branch", default="main")
    args = ap.parse_args()
    vfile = Path(__file__).resolve().parent.parent / "VERSION"
    local = vfile.read_text(encoding="utf-8").strip() if vfile.exists() else ""
    if not parse(local):
        print(f"UNKNOWN local VERSION missing or not MAJOR.MINOR.PATCH ({local or 'no file'})")
        return
    url = f"https://raw.githubusercontent.com/{args.repo}/{args.branch}/social-video-editor/VERSION"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            remote = r.read().decode("utf-8").strip()
    except Exception as e:  # offline, sandbox without network, repo moved...
        print(f"UNKNOWN remote unreachable ({type(e).__name__})")
        return
    if not parse(remote):
        print(f"UNKNOWN remote VERSION unreadable ({remote[:20]!r})")
        return
    print(f"UPDATE {local} -> {remote}" if parse(remote) > parse(local) else f"UP_TO_DATE {local}")


if __name__ == "__main__":
    main()
