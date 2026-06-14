"""Dedicated text detection — the "stage 1" the pro pipelines use a real model for.

manga-image-translator / MangaQuick / Koharu all run a purpose-built text
detector (DBNet / Comic-Text-Detector) instead of asking an LLM where the text
is. We use PaddleOCR's DBNet detector (the repo's "Paddle" option): it returns
tight text-line boxes that give us both an accurate inpainting mask and clean
crops to translate.

Two Windows-specific gotchas, handled here:
  * torch must be imported before paddle so its DLLs resolve first;
  * paddlepaddle 2.6.x + enable_mkldnn=False, or the bundled det model hits a
    OneDNN fused-conv crash.
"""

import torch  # noqa: F401 — must import before paddle to fix Windows DLL load order

import numpy as np
from paddleocr import PaddleOCR

_ocr = None


def _gpu_available() -> bool:
    """True only if paddle is built with CUDA and a device is actually present."""
    try:
        import paddle
        return paddle.device.cuda.device_count() > 0
    except Exception:
        return False


def _get_ocr() -> PaddleOCR:
    global _ocr
    if _ocr is None:
        # On a GPU host install paddlepaddle-gpu and this lights up automatically;
        # on CPU it stays False and mkldnn-off keeps the bundled det model stable.
        _ocr = PaddleOCR(
            lang="en",
            use_gpu=_gpu_available(),
            enable_mkldnn=False,
            use_angle_cls=False,
            show_log=False,
        )
    return _ocr


def _iou_overlap(a, b) -> float:
    """Fraction of the smaller box covered by the intersection."""
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(1, min(area_a, area_b))


def _dedup(boxes: list[list[int]]) -> list[list[int]]:
    """Merge near-duplicate boxes produced in tile overlap zones."""
    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    out: list[list[int]] = []
    for b in boxes:
        merged = False
        for o in out:
            if _iou_overlap(b, o) > 0.5:
                o[0], o[1] = min(o[0], b[0]), min(o[1], b[1])
                o[2], o[3] = max(o[2], b[2]), max(o[3], b[3])
                merged = True
                break
        if not merged:
            out.append(list(b))
    return out


def detect_boxes(img_rgb: np.ndarray, tile_h: int = 900, overlap: int = 150) -> list[list[int]]:
    """Tiled DBNet detection. Returns axis-aligned [x0,y0,x1,y1] boxes in full coords.

    Tall manhwa strips are tiled so each tile is detected near native resolution
    (DBNet downscales its input, so detecting a whole 8000px strip at once would
    shrink the text to nothing).
    """
    h, w = img_rgb.shape[:2]
    bgr = img_rgb[:, :, ::-1]  # PaddleOCR expects BGR ndarrays
    ocr = _get_ocr()
    boxes: list[list[int]] = []

    y = 0
    while True:
        y_end = min(h, y + tile_h)
        res = ocr.ocr(bgr[y:y_end], det=True, rec=False, cls=False)
        polys = res[0] if res and res[0] else []
        for p in polys:
            arr = np.asarray(p, dtype=np.float32)
            x0, x1 = int(arr[:, 0].min()), int(arr[:, 0].max())
            y0, y1 = int(arr[:, 1].min() + y), int(arr[:, 1].max() + y)
            boxes.append([x0, y0, x1, y1])
        if y_end >= h:
            break
        y = y_end - overlap

    return _dedup(boxes)


def group_into_bubbles(boxes: list[list[int]]) -> list[dict]:
    """Cluster text-line boxes into bubbles so each is translated as one unit.

    Lines are merged when they overlap horizontally and sit within ~1.6 line
    heights of each other vertically — i.e. stacked lines of the same bubble.
    Returns [{"box": [x0,y0,x1,y1], "lines": [...]}].
    """
    n = len(boxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            # horizontal overlap
            ox = min(a[2], b[2]) - max(a[0], b[0])
            if ox <= 0:
                continue
            line_h = min(a[3] - a[1], b[3] - b[1])
            # vertical gap between the two boxes
            gap = max(a[1], b[1]) - min(a[3], b[3])
            if gap <= line_h * 1.6:
                union(i, j)

    clusters: dict[int, list[list[int]]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(boxes[i])

    bubbles = []
    for lines in clusters.values():
        x0 = min(l[0] for l in lines)
        y0 = min(l[1] for l in lines)
        x1 = max(l[2] for l in lines)
        y1 = max(l[3] for l in lines)
        bubbles.append({"box": [x0, y0, x1, y1], "lines": lines})
    bubbles.sort(key=lambda b: (b["box"][1], b["box"][0]))  # reading order, top→bottom
    return bubbles
