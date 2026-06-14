"""Text removal with LaMa — the "stage 3" the pro pipelines use for clean fills.

This is the actual big-lama model (the one manga-image-translator / MangaQuick
use), via simple-lama-inpainting. To stay fast on CPU and avoid feeding an
8000px strip through the network at once, we inpaint each bubble region as a
small padded crop and paste the result back.
"""

import torch  # noqa: F401 — keep torch's DLLs loaded first (Windows load order)

import cv2
import numpy as np
from PIL import Image
from simple_lama_inpainting import SimpleLama

_lama = None


def _get_lama() -> SimpleLama:
    global _lama
    if _lama is None:
        # Uses CUDA automatically on a GPU host (e.g. Colab); CPU otherwise.
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _lama = SimpleLama(device=device)
    return _lama


def lama_clean(
    img_rgb: np.ndarray,
    bubbles: list[dict],
    pad: int = 14,
    dilate: int = 6,
) -> np.ndarray:
    """Return a copy of img_rgb with the original text erased under each bubble.

    `bubbles` is the structure from detect.group_into_bubbles: each has a "box"
    and the list of text-line boxes used to build a tight inpainting mask.
    """
    h, w = img_rgb.shape[:2]
    out = img_rgb.copy()
    lama = _get_lama()
    kernel = np.ones((dilate, dilate), np.uint8)

    for bub in bubbles:
        bx0, by0, bx1, by1 = bub["box"]
        cx0, cy0 = max(0, bx0 - pad), max(0, by0 - pad)
        cx1, cy1 = min(w, bx1 + pad), min(h, by1 + pad)
        crop = out[cy0:cy1, cx0:cx1]
        if crop.size == 0:
            continue

        mask = np.zeros(crop.shape[:2], np.uint8)
        for lx0, ly0, lx1, ly1 in bub["lines"]:
            mask[ly0 - cy0 : ly1 - cy0, lx0 - cx0 : lx1 - cx0] = 255
        mask = cv2.dilate(mask, kernel, iterations=1)

        result = lama(Image.fromarray(crop), Image.fromarray(mask))
        result = np.asarray(result.convert("RGB"))[: crop.shape[0], : crop.shape[1]]
        out[cy0:cy1, cx0:cx1] = result

    return out
