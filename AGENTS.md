# AGENTS.md

Working guide for contributors and AI coding agents. For *what* the project is,
read [`README.md`](README.md); for *how it's designed*, read
[`ARCHITECTURE.md`](ARCHITECTURE.md). This file is the *how to work on it*.

---

## The mental model

The backend is a 4-stage pipeline. Keep the stages decoupled — each is one file:

```
detect.py   →   translate.py   →   inpaint.py   →   render.py
(find text)     (Claude: words)    (LaMa: erase)    (PIL: draw)
```

`translate.py` is the **orchestrator**: it calls detect → Claude → inpaint →
render and returns `{regions, rendered_image}`. The LLM does the *language* step
only; it is never used to locate text. Don't reintroduce "ask Claude for bounding
boxes" — that was tried and produced fuzzy/incomplete boxes.

---

## Setup

```bash
cd backend
py -3.11 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium      # scraping only
# put ANTHROPIC_API_KEY in backend/.env
```

The venv interpreter is `backend/venv/Scripts/python.exe`. Use it directly in
scripts/tests rather than relying on an activated shell.

---

## Critical environment gotchas (Windows, CPU)

These are load-bearing. Breaking them gives confusing crashes:

1. **Import `torch` before paddle.** `detect.py` and `inpaint.py` both do
   `import torch` at the very top. On Windows, if paddle (or anything) loads
   first, torch fails with `WinError 127 ... shm.dll`. Keep torch first.
2. **`paddlepaddle==2.6.2`, not 3.x.** Newer paddle crashes on PaddleOCR's
   bundled detection model with `OneDnnContext does not have the input Filter`
   (a fused-conv op mismatch). The detector is created with `enable_mkldnn=False`.
3. **One OpenCV only.** `opencv-python` (full), pinned to `4.11.0.86`. Do **not**
   let `opencv-python-headless` or `opencv-contrib-python` get co-installed —
   duplicate `cv2` installs corrupt the module. If `cv2` import breaks, uninstall
   all three and reinstall just `opencv-python==4.11.0.86`.
4. **Version-pin warnings from pip are mostly cosmetic.** `simple-lama-inpainting`
   pins old numpy/pillow; the runtime works fine with the newer ones we have.
   Don't "fix" them by downgrading — you'll break paddle.

If you change deps, re-test imports in this order: `torch`, `cv2`, `paddleocr`,
`simple_lama_inpainting`.

---

## Running & restarting the backend

From the repo root, **`./start.ps1`** launches the backend and frontend together.
To run the backend alone (e.g. while iterating on the pipeline):

```bash
cd backend
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m uvicorn main:app --port 8000
```

- **Avoid `--reload`.** It reloads the heavy models on every code change and has
  been flaky on this setup. Restart manually instead.
- To restart: kill whatever holds port 8000, then start fresh.
  ```powershell
  (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess | % { Stop-Process -Id $_ -Force }
  ```
- The **first request** loads PaddleOCR + LaMa (and downloads `big-lama.pt`
  ~196MB to `~/.cache/torch/hub` once). Expect a slow first call, then ~30s/panel.
- `PYTHONIOENCODING=utf-8` matters only for *printing* CJK to the Windows console
  (original-text logs). It does not affect translation.

---

## Testing changes

There are no unit tests yet; verify against a real panel.

```bash
# translate one image through the running server, write the result to a PNG
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe test_translate.py input.jpg out.png
```

`test_translate.py` prints the bubble count + translations and writes the rendered
image. Open the PNG and check, in order:

- original text fully **erased** (no leftover glyphs, no white smears),
- English sits **inside** the bubbles, sized to fit,
- **every** bubble translated, including duplicated close-ups.

When tuning, keep a known-good reference image around and compare side by side.

---

## Where to change what

| You want to… | Edit | Notes |
|---|---|---|
| Improve which text gets found / how lines group into bubbles | `detect.py` | `detect_boxes` (tiling, thresholds), `group_into_bubbles` (clustering) |
| Change the translation prompt / model / batching | `translate.py` | `_build_prompt`, `_TONE_GUIDE`, `MODEL`, `_translate_bubbles` |
| Cleaner text removal | `inpaint.py` | mask dilation, per-crop padding |
| Font, size, outline, color of typeset text | `render.py` | `_FONT_CANDIDATES`, `_fit`, `max_font`, stroke |
| HTTP endpoints / request handling | `main.py` | heavy work runs via `run_in_threadpool`; CORS + model warm-start live here |
| Translate panels on any website | `extension/` | MV3 popup posts page images to the backend; works around the blocked scraper |
| GPU vs CPU device selection | `detect.py` / `inpaint.py` | auto-CUDA, CPU fallback; run on a free GPU via `colab_gpu.ipynb` |
| Panel scraping | `scraper.py` | Cloudflare-blocked; prefer the extension |

Data contract between backend and frontend:
`{ "regions": [{original_text, translated_text, box:{x,y,width,height}}], "rendered_image": "data:image/png;base64,...", "glossary": {term: translation} }`.
`PanelResult.jsx` shows `rendered_image` if present, else falls back to a CSS
overlay of `regions`.

**Context-aware translation.** `translate.py` sends the whole page (downscaled,
`_context_b64`) plus every bubble crop in one Claude request and asks for the page
as a *coherent scene* — so pronouns, speaker turns, names, and tone stay consistent
across bubbles, which bubble-by-bubble tools can't do. Claude also returns a
`glossary` (character names / recurring terms); `/translate-chapter` threads it
panel→panel so names stay stable across a chapter. Requests accept
`tone` (`natural`/`literal`/`localized`) and `keep_honorifics` — defaults
`natural` + keep. These are the project's main differentiator; preserve the
full-page-context behavior when editing the prompt.

---

## Conventions

- **Keep stages single-purpose and small.** Match the existing comment density —
  each file has a short module docstring explaining its role in the pipeline.
- **Don't refactor unrelated code** while making a change.
- **Performance is CPU-bound by design.** Before adding work per panel, remember
  it multiplies across a whole chapter. Inpaint per-bubble-crop, not whole-image.
- Project model is `claude-sonnet-4-6` (set in the original spec). Don't change it
  without reason.

---

## Known sharp edges

- **Scraping is Cloudflare-blocked** on the sites tested — the chapter-URL flow
  returns no panels. The working paths are single-image upload and the **Chrome
  extension** (reads panels from your logged-in tab; see [`extension/`](extension/)).
- **Site watermarks** baked into scans get detected and translated like dialogue —
  no filter yet.
- **Sound-effects baked into the art** (not in bubbles) are intentionally not
  translated.
- ~30s/panel on CPU; a long chapter is slow because panels run sequentially. For
  ~4x speed run the backend on a free GPU via `colab_gpu.ipynb`.

See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for the full list.
