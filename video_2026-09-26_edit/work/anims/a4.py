import sys; sys.path.insert(0, "scripts")
from anim_kit import Anim, ease, load_style
S = load_style("work")
W, H = 320, 210
anim = Anim(w=W, h=H, duration=1.4)
X0, X1, Y, BH = 30, 236, 118, 30


@anim.draw
def frame(c, t):
    p = ease.out_back(c.progress(t, 0.0, 0.25))
    out = 1 - ease.in_cubic(c.progress(t, 1.18, 0.22))
    with c.group(scale=0.6 + 0.4 * p, alpha=min(1, p * 1.5) * out, origin=(160, 105)):
        c.rect(8, 8, 304, 194, S["panel"], radius=26, alpha=0.82)
        c.text("POCO A POCO", 160, 66, c.fit("POCO A POCO", 270, 36), S["panel_text"])
        c.rect(X0, Y, X1 - X0, BH, "#FFFFFF", radius=15, alpha=0.18)
        fill = sum(ease.out_cubic(c.progress(t, 0.15 + 0.25 * k, 0.2)) for k in range(3)) / 3
        if fill > 0.02:
            c.rect(X0, Y, max(BH, (X1 - X0) * fill), BH, S["accent"], radius=15)
        for k in (1, 2):  # step dividers
            x = X0 + (X1 - X0) * k / 3
            c.line([(x, Y + 4), (x, Y + BH - 4)], S["panel"], width=3, alpha=0.6)
        cp = ease.out_back(c.progress(t, 0.85, 0.22))
        if cp > 0:
            with c.group(scale=cp, origin=(270, Y + BH / 2)):
                c.circle(270, Y + BH / 2, 24, fill=S["emphasis"])
                c.line([(259, Y + 15), (267, Y + 23), (282, Y + 7)], "#FFFFFF", width=6)

anim.render("work/anims/a4.mov"); anim.sheet("work/anims/a4_sheet.png")
