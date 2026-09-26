import sys; sys.path.insert(0, "scripts")
from anim_kit import Anim, ease, load_style
S = load_style("work")
W, H = 320, 210
anim = Anim(w=W, h=H, duration=2.1)


@anim.draw
def frame(c, t):
    p = ease.out_back(c.progress(t, 0.0, 0.3))
    out = 1 - ease.in_cubic(c.progress(t, 1.85, 0.25))
    with c.group(scale=0.6 + 0.4 * p, alpha=min(1, p * 1.5) * out, origin=(160, 105)):
        c.rect(8, 8, 304, 194, S["panel"], radius=26, alpha=0.82)
        # cross stamp: lands at 0.95 s, shrinking from 1.6x to 1x; text dims under it
        sp = ease.out_back(c.progress(t, 0.95, 0.25))
        dim = 1 - 0.45 * min(1, max(0, sp))
        c.text("PENSAMIENTOS", 160, 82, c.fit("PENSAMIENTOS", 270, 34), S["panel_text"], alpha=dim)
        c.text("NEGATIVOS", 160, 126, c.fit("NEGATIVOS", 270, 34), S["panel_text"], alpha=dim)
        if sp > 0:
            with c.group(scale=1.6 - 0.6 * sp, alpha=min(1, sp * 2) * 0.92, origin=(160, 104)):
                c.line([(95, 45), (225, 163)], S["danger"], width=13)
                c.line([(225, 45), (95, 163)], S["danger"], width=13)

anim.render("work/anims/a3.mov"); anim.sheet("work/anims/a3_sheet.png")
