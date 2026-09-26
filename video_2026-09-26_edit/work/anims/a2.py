import sys; sys.path.insert(0, "scripts")
from anim_kit import Anim, ease, load_style
S = load_style("work")
W, H = 320, 210
anim = Anim(w=W, h=H, duration=2.2)
STEPS = [(62, 28), (132, 52), (202, 76)]  # (x, height); each step 56 px wide
BASE = 118


@anim.draw
def frame(c, t):
    p = ease.out_back(c.progress(t, 0.0, 0.3))
    out = 1 - ease.in_cubic(c.progress(t, 1.95, 0.25))
    with c.group(scale=0.6 + 0.4 * p, alpha=min(1, p * 1.5) * out, origin=(160, 105)):
        c.rect(8, 8, 304, 194, S["panel"], radius=26, alpha=0.82)
        for k, (x, h) in enumerate(STEPS):
            g = ease.out_cubic(c.progress(t, 0.2 + 0.15 * k, 0.3))
            if g > 0:
                hh = h * g
                c.rect(x, BASE - hh, 56, hh, S["accent"], radius=6)
        # small dot climbing to the top step
        climb = ease.in_out_cubic(c.progress(t, 0.75, 0.6))
        k = min(2, int(climb * 3))
        x, h = STEPS[k]
        c.circle(x + 28, BASE - h - 14, 10, fill=S["text"], alpha=ease.out_cubic(c.progress(t, 0.7, 0.15)))
        c.text("EXPOSICIÓN", 160, 146, c.fit("EXPOSICIÓN", 270, 32), S["panel_text"])
        c.text("GRADUAL", 160, 180, c.fit("GRADUAL", 270, 32), S["accent"])

anim.render("work/anims/a2.mov"); anim.sheet("work/anims/a2_sheet.png")
