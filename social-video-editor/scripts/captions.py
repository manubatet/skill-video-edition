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
