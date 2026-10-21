"""Generate the project's icon files from one drawing (two circular arrows).

    python scripts/make_icons.py        (needs Pillow)

Writes packaging/ytm-sync.ico (the program and its shortcuts), docs/assets/logo.svg and logo.png
(README) and docs/assets/social-preview.png (1280x640, upload it in the repository's Settings >
Social preview). The arrows are the same glyph as the sidebar icon in app/src/css/icon.svg.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BG, FG = (92, 78, 214), (255, 255, 255)  # violet: deliberately not Spotify green or YouTube red
SCALE = 4  # draw big, shrink for smooth edges

# The glyph on a 24x24 grid: two arcs of a circle (centre 12,12, radius 8) and two arrow heads.
ARCS = [(-7, -150), (173, 30)]  # degrees, screen coordinates (y points down)
HEADS = [[(4, 5), (4, 8), (7, 8)], [(20, 19), (20, 16), (17, 16)]]
SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    f'<rect width="64" height="64" rx="14" fill="rgb{BG}"/>'
    '<g transform="translate(10.9 10.9) scale(1.76)" fill="none" stroke="#fff" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M20 11a8 8 0 0 0-14.9-3M4 5v3h3"/><path d="M4 13a8 8 0 0 0 14.9 3M20 19v-3h-3"/>'
    "</g></svg>\n"
)


def logo(size: int) -> Image.Image:
    big = size * SCALE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=BG)
    unit = big * 0.66 / 24
    off = big * 0.17

    def pt(x: float, y: float) -> tuple[float, float]:
        return off + x * unit, off + y * unit

    width = max(1, round(2 * unit))
    lines: list[list[tuple[float, float]]] = []
    for start, end in ARCS:
        steps = 90
        lines.append([
            pt(12 + 8 * math.cos(math.radians(start + (end - start) * i / steps)),
               12 + 8 * math.sin(math.radians(start + (end - start) * i / steps)))
            for i in range(steps + 1)
        ])
    lines += [[pt(x, y) for x, y in head] for head in HEADS]
    radius = width / 2
    for line in lines:
        for (x0, y0), (x1, y1) in zip(line, line[1:]):
            steps = max(1, int(math.hypot(x1 - x0, y1 - y0) / (radius / 3)))
            for i in range(steps + 1):
                x, y = x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=FG)
    return image.resize((size, size), Image.LANCZOS)


def social_preview() -> Image.Image:
    image = Image.new("RGB", (1280, 640), (30, 27, 46))
    image.paste(logo(300), (110, 170), logo(300))
    draw = ImageDraw.Draw(image)
    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    plain = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    title = ImageFont.truetype(bold, 110)
    tagline = ImageFont.truetype(plain, 38)
    draw.text((470, 215), "YTM Sync", font=title, fill=(255, 255, 255))
    draw.text((474, 355), "Mirror Spotify to YouTube Music,", font=tagline, fill=(200, 196, 230))
    draw.text((474, 405), "in the same order.", font=tagline, fill=(200, 196, 230))
    draw.text((474, 490), "A Spicetify custom app", font=ImageFont.truetype(plain, 30),
              fill=(150, 145, 190))
    return image


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    logo(256).save(ROOT / "packaging" / "ytm-sync.ico", sizes=[(s, s) for s in sizes])
    logo(512).save(ROOT / "docs" / "assets" / "logo.png")
    (ROOT / "docs" / "assets" / "logo.svg").write_text(SVG, encoding="utf-8")
    social_preview().save(ROOT / "docs" / "assets" / "social-preview.png")
    print("written: packaging/ytm-sync.ico, docs/assets/logo.{svg,png}, social-preview.png")


if __name__ == "__main__":
    main()
