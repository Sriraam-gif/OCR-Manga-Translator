"""Pipeline orchestration, mirroring the established manga-translator repos.

  detect (DBNet)  →  group into bubbles  →  translate (Claude, LLM only)
                  →  inpaint (LaMa)       →  typeset (PIL)

Claude is used for the language step only — a dedicated detector finds the text
and LaMa erases it, exactly as manga-image-translator / MangaQuick do.
"""

import base64
import io
import json
import logging

import numpy as np
from anthropic import Anthropic
from dotenv import load_dotenv
from PIL import Image

import detect
import inpaint
import render

load_dotenv()
logger = logging.getLogger("manga-translator")

MODEL = "claude-sonnet-4-6"  # per project spec

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "original_text": {"type": "string"},
                    "translated_text": {"type": "string"},
                },
                "required": ["index", "original_text", "translated_text"],
                "additionalProperties": False,
            },
        },
        # Character names and recurring terms Claude settled on, so the chapter
        # loop can feed them back into later panels for consistency.
        "glossary": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "translation": {"type": "string"},
                },
                "required": ["term", "translation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["translations", "glossary"],
    "additionalProperties": False,
}

# Tone presets selectable per request. Default is "natural".
_TONE_GUIDE = {
    "natural": (
        "Translate into natural, conversational English that a professional "
        "scanlation would use — readable and idiomatic, matching each speaker's "
        "register (rough, polite, childish, formal)."
    ),
    "literal": (
        "Translate faithfully and close to the source wording. Preserve sentence "
        "structure and nuance even if slightly stiff; do not localize idioms."
    ),
    "localized": (
        "Localize freely for an English-speaking reader: rework idioms, jokes, and "
        "cultural references into natural English equivalents while keeping intent."
    ),
}


def _build_prompt(options: dict, glossary: dict[str, str]) -> str:
    tone = _TONE_GUIDE.get(options.get("tone", "natural"), _TONE_GUIDE["natural"])
    honorifics = (
        "Keep Japanese/Korean honorifics and suffixes (-san, -chan, -nim, oppa, etc.)."
        if options.get("keep_honorifics", True)
        else "Drop honorifics and suffixes; use plain English names and address."
    )
    glossary_block = ""
    if glossary:
        pairs = "; ".join(f"{k} = {v}" for k, v in glossary.items())
        glossary_block = (
            "\n\nUse these established translations for consistency with earlier "
            f"pages (do not change them): {pairs}."
        )
    return (
        "The first image is the FULL manga/manhwa page, for context. The images "
        "after it are cropped text regions from that page, labelled 'Bubble 1', "
        "'Bubble 2', and so on (the crops may not be in reading order).\n\n"
        "Treat the page as one coherent scene, not isolated lines. Use the full "
        "page to infer reading direction (manga is right-to-left, manhwa is "
        "left-to-right/top-to-bottom), who is speaking, and how lines connect, so "
        "pronouns, names, tone, and running jokes stay consistent across bubbles.\n\n"
        f"{tone} {honorifics}{glossary_block}\n\n"
        "Return exactly one entry per labelled bubble, giving its index (1-based), "
        "the original_text you read, and the translated_text. If a bubble has no "
        "readable text, return empty strings for that entry. Also return a "
        "'glossary' of the character names and recurring terms you used (term = "
        "the source name/word, translation = the English you chose), so later "
        "pages can stay consistent."
    )

_client = Anthropic()


def _png_b64(img_rgb: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(img_rgb).save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _context_b64(img_rgb: np.ndarray, max_side: int = 1568) -> str:
    """Downscaled full page for layout context. Long manhwa strips exceed the
    API's 8000px limit and waste tokens; legible text comes from the crops."""
    im = Image.fromarray(img_rgb)
    scale = max_side / max(im.size)
    if scale < 1:
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _translate_bubbles(
    img_rgb: np.ndarray,
    bubbles: list[dict],
    options: dict,
    glossary: dict[str, str],
) -> tuple[list[dict], dict[str, str]]:
    """One Claude request: full page + every bubble crop, translated as a scene.

    Returns (translations aligned to bubbles, glossary updated with new terms).
    """
    h, w = img_rgb.shape[:2]
    # Full page first, for cross-bubble context.
    content: list[dict] = [
        {"type": "text", "text": "Full page (context):"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": _context_b64(img_rgb)},
        },
    ]
    for i, bub in enumerate(bubbles):
        x0, y0, x1, y1 = bub["box"]
        crop = img_rgb[max(0, y0 - 6):min(h, y1 + 6), max(0, x0 - 6):min(w, x1 + 6)]
        content.append({"type": "text", "text": f"Bubble {i + 1}:"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": _png_b64(crop)},
        })
    content.append({"type": "text", "text": _build_prompt(options, glossary)})

    response = _client.messages.create(
        model=MODEL,
        max_tokens=4096,
        output_config={"format": {"type": "json_schema", "schema": _RESPONSE_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    data = json.loads(response.content[0].text)

    # Align by 1-based index; fall back to positional order.
    by_index = {t.get("index"): t for t in data.get("translations", [])}
    out = []
    for i in range(len(bubbles)):
        out.append(by_index.get(i + 1) or {"original_text": "", "translated_text": ""})

    # Carry forward newly established terms (existing entries win — don't drift).
    updated = dict(glossary)
    for g in data.get("glossary", []):
        term, tr = g.get("term", "").strip(), g.get("translation", "").strip()
        if term and tr and term not in updated:
            updated[term] = tr
    return out, updated


def translate_image(
    image_bytes: bytes,
    options: dict | None = None,
    glossary: dict[str, str] | None = None,
) -> dict:
    """Full pipeline. Returns {regions, rendered_image, glossary} for one panel.

    `options`: {"tone": "natural"|"literal"|"localized", "keep_honorifics": bool}.
    `glossary`: established term→translation map carried across a chapter.
    """
    options = options or {}
    glossary = glossary or {}

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img)
    h, w = arr.shape[:2]

    boxes = detect.detect_boxes(arr)
    bubbles = detect.group_into_bubbles(boxes)
    logger.info("Detected %d text lines in %d bubbles", len(boxes), len(bubbles))

    if not bubbles:
        return {
            "regions": [],
            "rendered_image": f"data:image/png;base64,{_png_b64(arr)}",
            "glossary": glossary,
        }

    translations, glossary = _translate_bubbles(arr, bubbles, options, glossary)

    # Only touch boxes we actually have a translation for. Erasing a box whose
    # translation came back empty (a skipped caption or a spurious detection)
    # would leave a blank white rectangle, so we keep those as the original art.
    translated = [
        (bub, tr)
        for bub, tr in zip(bubbles, translations)
        if (tr.get("translated_text") or "").strip()
    ]

    if not translated:
        return {
            "regions": [],
            "rendered_image": f"data:image/png;base64,{_png_b64(arr)}",
            "glossary": glossary,
        }

    cleaned = inpaint.lama_clean(arr, [bub for bub, _ in translated])

    items, regions = [], []
    for bub, tr in translated:
        x0, y0, x1, y1 = bub["box"]
        items.append({"box": [x0, y0, x1, y1], "text": tr["translated_text"]})
        regions.append({
            "original_text": tr.get("original_text", ""),
            "translated_text": tr["translated_text"],
            "box": {"x": x0 / w, "y": y0 / h, "width": (x1 - x0) / w, "height": (y1 - y0) / h},
        })

    png = render.typeset(cleaned, items)
    return {
        "regions": regions,
        "rendered_image": f"data:image/png;base64,{base64.standard_b64encode(png).decode('ascii')}",
        "glossary": glossary,
    }
