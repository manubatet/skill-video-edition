import sys; sys.path.insert(0, "scripts")
from anim_kit import Anim, ease, load_style
S = load_style("work")
W, H = 320, 210
anim = Anim(w=W, h=H, duration=1.55)
CHECK = [(126, 88), (150, 112), (196, 64)]


def partial(points, p):
    """Polyline drawn up to fraction p of its total length."""
    segs = list(zip(points, points[1:]))
    lens = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in segs]
    left = p * sum(lens)
    out = [points[0]]
    for (a, b), L in zip(segs, lens):
        if left >= L:
            out.append(b); left -= L
        else:
            f = left / L if L else 0
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)); break
    return out


@anim.draw
def frame(c, t):
    out = 1 - ease.in_cubic(c.progress(t, 1.3, 0.25))
    p = ease.out_back(c.progress(t, 0.0, 0.3))
    with c.group(scale=0.4 + 0.6 * p, alpha=min(1, p * 1.5) * out, origin=(160, 88)):
        c.circle(160, 88, 66, fill="#000000", alpha=0.35)
        c.circle(160, 88, 62, fill=S["emphasis"])
        d = ease.out_cubic(c.progress(t, 0.2, 0.35))
        if d > 0:
            c.line(partial(CHECK, d), "#FFFFFF", width=14)
    tp = ease.out_cubic(c.progress(t, 0.3, 0.25))
    with c.group(alpha=tp * out, dy=(1 - tp) * 14):
        c.text("SÍ", 160, 182, c.fit("SÍ", 280, 46), S["text"], stroke=4, stroke_color=S["outline"])

anim.render("work/anims/a1.mov"); anim.sheet("work/anims/a1_sheet.png")
