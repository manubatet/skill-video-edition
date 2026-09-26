"""v2 full-screen 2D scene (replaces the speaker from 3.28 s to 12.18 s, edited time).

Illustrates what she says: gradual exposure to a feared stimulus (a spider), with a
therapist accompanying, step by step, while an anxiety meter shows habituation waves
(each step raises anxiety less, and it always comes down). The speaker's words are
drawn at the bottom as phrase subtitles, like the original video's burned-in ones.
"""
import json
import math
import sys; sys.path.insert(0, "scripts")
from anim_kit import Anim, ease, lerp, load_style

S = load_style("work")
W, H = 848, 480
T0 = 3.28                       # edited-time start of this overlay
anim = Anim(w=W, h=H, duration=8.9)

GROUND = 338
STONES = [130, 280, 430, 580]
MOVES = [(4.3, 1), (5.7, 2), (7.2, 3)]          # (local start, target stone); each move 0.6 s
SPIDER = (735, 296)
SKIN, INK = "#F2C9A0", "#2B2B2B"
PERSON, THERAPIST, HAIR = "#FF8A3D", "#1FA39A", "#5A3A22"

# Phrase subtitles from the edited transcript (word-id ranges), local times.
words = {w["i"]: w for w in json.load(open("work/transcript_edited.json", encoding="utf-8"))["words"]}
CHUNKS = [(11, 16), (17, 21), (22, 27), (28, 30), (31, 33), (34, 39)]
SUBS = []
for k, (a, b) in enumerate(CHUNKS):
    txt = " ".join(words[i]["text"] for i in range(a, b + 1)).strip(" ,.").lower()
    start = words[a]["start"] - T0
    end = (words[CHUNKS[k + 1][0]]["start"] - T0) if k + 1 < len(CHUNKS) else 9.0
    SUBS.append((start, end, txt.replace(",", "")))


def spike(L, t0, h):
    if L <= t0:
        return 0.0
    x = L - t0
    return h * (1 - math.exp(-x / 0.15)) * math.exp(-x / 0.9)


def anxiety(L):
    base = 0.12 - 0.08 * ease.in_out_cubic(min(1, max(0, (L - 7.0) / 1.5)))  # calmer by the end
    lv = base + spike(L, 2.6, 1.2) + spike(L, 4.9, 0.95) + spike(L, 6.3, 0.7) + spike(L, 7.8, 0.3)
    return max(0.0, min(1.0, lv))


def person_x(L, lag=0.0):
    x = STONES[0]
    moving = False
    for t0, k in MOVES:
        p = (L - lag - t0) / 0.6
        if p <= 0:
            break
        moving = moving or p < 1
        x = lerp(STONES[k - 1], STONES[k], ease.in_out_cubic(min(1, p)))
    return x, moving


def meter_color(v):
    g, y, r = (46, 204, 113), (255, 212, 0), (255, 59, 59)
    a, b, f = (g, y, v / 0.5) if v < 0.5 else (y, r, (v - 0.5) / 0.5)
    return tuple(int(lerp(a[i], b[i], f)) for i in range(3)) + (255,)


def figure(c, cx, L, body, hair=None, anx=0.0, walking=False, face=1):
    fy = GROUND
    swing = math.sin(L * 14) * 7 if walking else 0
    bob = abs(math.sin(L * 14)) * 3 if walking else 0
    shake = math.sin(L * 45) * 2.5 * max(0, anx - 0.45) / 0.55
    cx += shake
    c.line([(cx - 8, fy - 40 - bob), (cx - 10 + swing, fy)], INK, width=8)
    c.line([(cx + 8, fy - 40 - bob), (cx + 10 - swing, fy)], INK, width=8)
    c.rect(cx - 20, fy - 102 - bob, 40, 66, body, radius=18)
    c.line([(cx - 18, fy - 90 - bob), (cx - 27, fy - 56 - bob)], body, width=8)
    hy = fy - 124 - bob
    if hair:
        c.circle(cx - 3 * face, hy - 4, 25, fill=hair)
    c.circle(cx, hy, 22, fill=SKIN)
    ex = 5 * face
    c.circle(cx + ex - 7, hy - 3, 2.8, fill=INK)
    c.circle(cx + ex + 7, hy - 3, 2.8, fill=INK)
    if anx < 0.4:
        c.arc(cx + ex, hy + 2, 8, 25, 155, INK, width=3)          # smile
    else:
        c.arc(cx + ex, hy + 13, 8, 205, 335, INK, width=3)        # worried
    if anx > 0.55:
        c.circle(cx - 24, hy - 12, 4.5, fill="#4FC3F7")            # sweat drop


def spider(c, L, scale_p):
    cx, cy = SPIDER
    with c.group(scale=max(0.02, scale_p), origin=(cx, GROUND)):
        for s in (-1, 1):
            for k in range(4):
                wig = math.sin(L * 7 + k * 1.3 + (s > 0)) * 3
                base = (cx + s * 12, cy - 4 + k * 5)
                knee = (cx + s * (40 + 5 * k), cy - 30 + k * 9 + wig)
                foot = (cx + s * (50 + 9 * k), GROUND - 2)
                c.line([base, knee, foot], "#2E2E3A", width=6)
        c.circle(cx + 8, cy, 30, fill="#2E2E3A")
        c.circle(cx - 24, cy + 8, 17, fill="#3A3A48")
        for ex in (-31, -19):
            c.circle(cx + ex, cy + 4, 5, fill="#FFFFFF")
            c.circle(cx + ex - 1.5, cy + 5, 2.4, fill=INK)


@anim.draw
def frame(c, L):
    fin = ease.out_cubic(c.progress(L, 0.0, 0.3))
    fout = 1 - ease.in_cubic(c.progress(L, 8.62, 0.28))
    with c.group(scale=1.06 - 0.06 * fin, alpha=fin * fout, origin=(W / 2, H / 2)):
        # background
        c.rect(0, 0, W, H, "#FFF4E0")
        c.circle(95, 70, 34, fill="#FFD166", alpha=0.9)
        c.rect(0, GROUND, W, H - GROUND, "#E9D8BC")
        c.rect(0, GROUND, W, 5, "#D8C4A2")
        # title
        tp = ease.out_back(c.progress(L, 0.25, 0.35))
        with c.group(scale=0.6 + 0.4 * tp, alpha=min(1, tp * 1.5), origin=(W / 2, 44)):
            c.text("EXPOSICIÓN GRADUAL", W / 2, 44, c.fit("EXPOSICIÓN GRADUAL", 560, 40), INK)
        # stones 0..3 (numbered 1..3 after the start one)
        for k, x in enumerate(STONES):
            sp = ease.out_back(c.progress(L, 0.9 + 0.18 * k, 0.3))
            if sp <= 0:
                continue
            with c.group(scale=sp, origin=(x, GROUND + 9)):
                c.rect(x - 52, GROUND + 1, 104, 18, "#BCA888", radius=9)
                if k:
                    c.text(str(k), x, GROUND + 44, 26, S["panel"], alpha=0.75)
        # anxiety meter
        mp = ease.out_cubic(c.progress(L, 2.3, 0.35))
        if mp > 0:
            v = anxiety(L)
            with c.group(alpha=mp, dy=(1 - mp) * -12):
                c.text("ANSIEDAD", 262, 97, 20, INK, anchor="rm")
                c.rect(274, 85, 320, 24, "#000000", radius=12, alpha=0.12)
                c.rect(274, 85, max(24, 320 * v), 24, meter_color(v), radius=12)
        # spider
        spider(c, L, ease.out_back(c.progress(L, 2.5, 0.35)))
        # therapist (appears on "acompañamos", follows 0.25 s behind)
        th = ease.out_back(c.progress(L, 3.65, 0.35))
        px, pmove = person_x(L)
        tx, tmove = person_x(L, lag=0.25)
        tx -= 72
        if th > 0:
            with c.group(scale=th, alpha=min(1, th * 1.5), origin=(tx, GROUND)):
                figure(c, tx, L, THERAPIST, hair=HAIR, anx=0.1, walking=tmove)
            if th >= 1 and px - tx < 95:  # supportive hand on the shoulder
                c.line([(tx + 16, GROUND - 90), (px - 16, GROUND - 86)], THERAPIST, width=8)
        # person
        figure(c, px, L, PERSON, anx=anxiety(L) if L > 2.5 else 0.1, walking=pmove)
        # final check
        cp = ease.out_back(c.progress(L, 8.05, 0.3))
        if cp > 0:
            with c.group(scale=cp, origin=(px, GROUND - 185)):
                c.circle(px, GROUND - 185, 22, fill=S["emphasis"])
                c.line([(px - 10, GROUND - 185), (px - 2, GROUND - 177), (px + 11, GROUND - 193)], "#FFFFFF", width=5)
        # subtitles (phrase style, like the original)
        for a, b, txt in SUBS:
            if a <= L < b:
                c.text(txt, W / 2, 432, c.fit(txt, 760, 30), "#FFFFFF", stroke=3, stroke_color="#000000")


anim.render("work/anims/b1.mov")
anim.sheet("work/anims/b1_sheet.png", times=(0.04, 0.2, 0.33, 0.55, 0.62, 0.76, 0.93))
