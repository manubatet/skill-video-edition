"""Tiny animation kit: the agent writes an animation as Python code, this renders it to a
transparent .mov (PNG codec, alpha) that render.py overlays on the video.

Example (work/anims/a1.py):
    import sys; sys.path.insert(0, "scripts")
    from anim_kit import Anim, ease, load_style
    S = load_style("work")
    anim = Anim(w=900, h=300, duration=1.8)

    @anim.draw
    def frame(c, t):
        p = ease.out_back(c.progress(t, 0.0, 0.35))          # entry 0..1
        out = 1 - ease.in_cubic(c.progress(t, 1.5, 0.3))     # exit 1..0
        with c.group(scale=0.6 + 0.4 * p, alpha=min(p, out), origin=(450, 150)):
            c.rect(40, 40, 820, 220, S["accent"], radius=40)
            c.text("3 CLAVES", 450, 150, 110, S["accent_text"])

    anim.render("work/anims/a1.mov")      # transparent video
    anim.sheet("work/anims/a1_sheet.png")  # 5 frames on a checkerboard, to inspect visually

Coordinates are output pixels inside the animation box (w x h); drawing is 2x
supersampled for smooth edges. The kit only uses Pillow + numpy + FFmpeg.
"""
import math
import subprocess
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STYLE_DEFAULTS = {"font": "Montserrat", "text": "#FFFFFF", "highlight": "#FFD400", "emphasis": "#00E676",
                  "outline": "#000000", "accent": "#FFD400", "accent_text": "#111111",
                  "panel": "#111111", "panel_text": "#FFFFFF", "danger": "#FF3B3B",
                  "anim_style": "bold"}


def load_style(work="work"):
    import json
    p = Path(work) / "timeline.json"
    st = dict(STYLE_DEFAULTS)
    if p.exists():
        st.update(json.loads(p.read_text(encoding="utf-8")).get("style", {}))
    return st


class ease:
    linear = staticmethod(lambda x: x)
    in_cubic = staticmethod(lambda x: x ** 3)
    out_cubic = staticmethod(lambda x: 1 - (1 - x) ** 3)
    in_out_cubic = staticmethod(lambda x: 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2)
    out_quint = staticmethod(lambda x: 1 - (1 - x) ** 5)

    @staticmethod
    def out_back(x, s=1.70158):
        return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2

    @staticmethod
    def out_elastic(x):
        if x in (0, 1):
            return x
        return 2 ** (-10 * x) * math.sin((x * 10 - 0.75) * (2 * math.pi) / 3) + 1


def lerp(a, b, p):
    return a + (b - a) * p


def rgba(color, alpha=1.0):
    if isinstance(color, tuple):
        return color[:3] + (int(255 * alpha),)
    h = color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * alpha))


@lru_cache(maxsize=None)
def font_path(family, weight="bold"):
    # 1) fonts dropped in work/fonts (same folder libass uses for captions)
    key = family.lower().replace(" ", "")
    local = sorted(p for p in Path("work/fonts").glob("*.[to]tf") if key in p.name.lower().replace(" ", "").replace("-", ""))
    if local:
        pref = [p for p in local if weight.lower() in p.name.lower()] or local
        return str(pref[0])
    # 2) system fonts via fontconfig
    for query in (f"{family}:{weight}", f"{family}", f"DejaVu Sans:{weight}"):
        try:
            p = subprocess.run(["fc-match", "-f", "%{file}", query], capture_output=True, text=True).stdout
            if p and Path(p).exists() and (family.lower().replace(" ", "") in p.lower().replace(" ", "")
                                           or query.startswith("DejaVu")):
                return p
        except FileNotFoundError:
            break
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if Path(p).exists():
            return p
    return None


@lru_cache(maxsize=256)
def _font(path, px):
    return ImageFont.truetype(path, px) if path else ImageFont.load_default()


class Canvas:
    def __init__(self, w, h, ss, style):
        self.w, self.h, self.ss, self.style = w, h, ss, style
        self._stack = [Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))]

    @staticmethod
    def progress(t, start, dur):
        return 0.0 if t <= start else 1.0 if dur <= 0 or t >= start + dur else (t - start) / dur

    @property
    def img(self):
        return self._stack[-1]

    def _s(self, v):
        return int(round(v * self.ss))

    def _layer(self):
        return Image.new("RGBA", self.img.size, (0, 0, 0, 0))

    def _put(self, layer):
        self._stack[-1] = Image.alpha_composite(self.img, layer)

    def rect(self, x, y, w, h, fill, radius=0, alpha=1.0, outline=None, width=0):
        L = self._layer()
        ImageDraw.Draw(L).rounded_rectangle([self._s(x), self._s(y), self._s(x + w), self._s(y + h)],
                                            radius=self._s(radius), fill=rgba(fill, alpha),
                                            outline=rgba(outline, alpha) if outline else None,
                                            width=self._s(width))
        self._put(L)

    def circle(self, cx, cy, r, fill=None, alpha=1.0, outline=None, width=0):
        L = self._layer()
        ImageDraw.Draw(L).ellipse([self._s(cx - r), self._s(cy - r), self._s(cx + r), self._s(cy + r)],
                                  fill=rgba(fill, alpha) if fill else None,
                                  outline=rgba(outline, alpha) if outline else None, width=self._s(width))
        self._put(L)

    def line(self, points, color, width=6, alpha=1.0):
        L = self._layer()
        pts = [(self._s(x), self._s(y)) for x, y in points]
        d = ImageDraw.Draw(L)
        d.line(pts, fill=rgba(color, alpha), width=self._s(width), joint="curve")
        r = self._s(width) / 2
        for px, py in (pts[0], pts[-1]):  # round caps
            d.ellipse([px - r, py - r, px + r, py + r], fill=rgba(color, alpha))
        self._put(L)

    def arc(self, cx, cy, r, start_deg, end_deg, color, width=10, alpha=1.0):
        L = self._layer()
        ImageDraw.Draw(L).arc([self._s(cx - r), self._s(cy - r), self._s(cx + r), self._s(cy + r)],
                              start_deg, end_deg, fill=rgba(color, alpha), width=self._s(width))
        self._put(L)

    def text(self, s, x, y, size, color, anchor="mm", alpha=1.0, weight="bold", family=None,
             stroke=0, stroke_color="#000000"):
        L = self._layer()
        f = _font(font_path(family or self.style["font"], weight), self._s(size))
        ImageDraw.Draw(L).text((self._s(x), self._s(y)), s, font=f, fill=rgba(color, alpha), anchor=anchor,
                               stroke_width=self._s(stroke), stroke_fill=rgba(stroke_color, alpha))
        self._put(L)

    def text_width(self, s, size, weight="bold", family=None):
        f = _font(font_path(family or self.style["font"], weight), self._s(size))
        return f.getlength(s) / self.ss

    def fit(self, s, max_w, size, weight="bold", family=None, min_size=12):
        """Largest font size <= size at which text s fits in max_w pixels. Always use it for
        dynamic text (numbers, user words) so nothing overflows its shape."""
        while size > min_size and self.text_width(s, size, weight, family) > max_w:
            size -= 2
        return size

    @contextmanager
    def group(self, scale=1.0, alpha=1.0, origin=None, dx=0, dy=0, rotate=0):
        """Draw children on their own layer, then scale/rotate/move/fade them as one."""
        self._stack.append(self._layer())
        yield self
        layer = self._stack.pop()
        ox, oy = origin if origin else (self.w / 2, self.h / 2)
        ox, oy = self._s(ox), self._s(oy)
        if rotate:
            layer = layer.rotate(rotate, resample=Image.BICUBIC, center=(ox, oy))
        if abs(scale - 1) > 1e-3 and scale > 0.01:
            W, H = layer.size
            sw, sh = max(1, int(W * scale)), max(1, int(H * scale))
            scaled = layer.convert("RGBa").resize((sw, sh), Image.BICUBIC).convert("RGBA")
            layer = self._layer()
            layer.paste(scaled, (int(ox - ox * scale), int(oy - oy * scale)))  # plain copy onto empty layer
        elif scale <= 0.01:
            return
        if dx or dy:
            moved = self._layer()
            moved.paste(layer, (self._s(dx), self._s(dy)))
            layer = moved
        if alpha < 1:
            a = layer.getchannel("A").point(lambda v: int(v * max(alpha, 0)))
            layer.putalpha(a)
        self._put(layer)


class Anim:
    def __init__(self, w, h, duration, fps=30, ss=2, style=None, work="work"):
        self.w, self.h, self.duration, self.fps, self.ss = int(w), int(h), duration, fps, ss
        self.style = style or load_style(work)
        self._fn = None

    def draw(self, fn):
        self._fn = fn
        return fn

    def frame_at(self, t):
        c = Canvas(self.w, self.h, self.ss, self.style)
        self._fn(c, t)
        img = c.img
        if self.ss != 1:
            img = img.convert("RGBa").resize((self.w, self.h), Image.LANCZOS).convert("RGBA")
        return img

    def render(self, out):
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        n = max(1, int(round(self.duration * self.fps)))
        p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                              "-s", f"{self.w}x{self.h}", "-r", str(self.fps), "-i", "-",
                              "-c:v", "png", "-pix_fmt", "rgba", str(out)], stdin=subprocess.PIPE)
        for k in range(n):
            p.stdin.write(self.frame_at(k / self.fps).tobytes())
        p.stdin.close()
        if p.wait() != 0:
            raise SystemExit(f"ffmpeg failed rendering {out}")
        print(f"OK: {out} ({self.w}x{self.h}, {self.duration}s, {n} frames)")

    def sheet(self, out, times=(0.08, 0.2, 0.45, 0.75, 0.97)):
        """Contact sheet on a checkerboard so transparency and timing can be inspected."""
        frames = [self.frame_at(f * self.duration) for f in times]
        scale = min(1.0, 360 / self.w)
        fw, fh = int(self.w * scale), int(self.h * scale)
        sheet = Image.new("RGBA", (fw * len(frames) + 10 * (len(frames) + 1), fh + 20), (40, 40, 40, 255))
        for k, fr in enumerate(frames):
            bg = Image.new("RGBA", (fw, fh), (90, 90, 90, 255))
            d = ImageDraw.Draw(bg)
            for yy in range(0, fh, 16):
                for xx in range(0, fw, 16):
                    if (xx // 16 + yy // 16) % 2:
                        d.rectangle([xx, yy, xx + 15, yy + 15], fill=(130, 130, 130, 255))
            bg.alpha_composite(fr.resize((fw, fh), Image.LANCZOS))
            sheet.paste(bg, (10 + k * (fw + 10), 10))
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        sheet.convert("RGB").save(out)
        print(f"OK: sheet {out}")
