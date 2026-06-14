"""Typesetting — the "stage 5" the pro pipelines do after inpainting.

The image arrives already cleaned by LaMa (inpaint.py); this module only draws
the English back in. Each bubble gets a comic font fitted to its box with a
contrasting outline, the standard scanlation look.
"""

import io
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Comic-ish fonts to try, in order; falls back to PIL's bundled font.
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/comicbd.ttf",
    "C:/Windows/Fonts/comic.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_FONT_PATH = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), None)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    if _FONT_PATH:
        return ImageFont.truetype(_FONT_PATH, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    """Greedy word-wrap to fit max_w pixels."""
    words = text.split()
    if not words:
        return [""]
    lines, line = [], words[0]
    for word in words[1:]:
        if draw.textlength(f"{line} {word}", font=font) <= max_w:
            line = f"{line} {word}"
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def _fit(draw, text, box_w, box_h, max_size):
    """Largest font (up to max_size) whose wrapped text fits the box."""
    for size in range(min(max_size, max(8, int(box_h))), 7, -1):
        font = _load_font(size)
        lines = _wrap(draw, text, font, box_w)
        line_h = (font.getbbox("Ag")[3] - font.getbbox("Ag")[1]) * 1.18
        widest = max((draw.textlength(ln, font=font) for ln in lines), default=0)
        if line_h * len(lines) <= box_h and widest <= box_w:
            return font, lines, line_h
    font = _load_font(8)
    return font, _wrap(draw, text, font, box_w), 10


def typeset(img_rgb: np.ndarray, items: list[dict]) -> bytes:
    """Draw translated text into each box on the cleaned image; return PNG bytes.

    `items` = [{"box": [x0,y0,x1,y1] (pixels), "text": str}].
    """
    out = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(out)
    # Consistent, modest point size scaled to page width (~2.2% ≈ 16px on 720px).
    max_font = max(11, round(out.width * 0.022))

    for item in items:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        x0, y0, x1, y1 = item["box"]
        pad = max(2, round((x1 - x0) * 0.06))
        box_w, box_h = (x1 - x0) - 2 * pad, (y1 - y0) - 2 * pad
        if box_w < 4 or box_h < 4:
            continue

        # Light vs dark background → black text w/ white outline, or vice versa.
        patch = img_rgb[y0:y1, x0:x1]
        bright = patch.mean() if patch.size else 255
        fill = (20, 20, 20) if bright > 110 else (245, 245, 245)
        stroke = (255, 255, 255) if bright > 110 else (0, 0, 0)

        font, lines, line_h = _fit(draw, text, box_w, box_h, max_font)
        cy = y0 + pad + (box_h - line_h * len(lines)) / 2
        sw = 1 if font.size <= 22 else 2
        for ln in lines:
            cx = x0 + pad + (box_w - draw.textlength(ln, font=font)) / 2
            draw.text((cx, cy), ln, font=font, fill=fill,
                      stroke_width=sw, stroke_fill=stroke)
            cy += line_h

    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
