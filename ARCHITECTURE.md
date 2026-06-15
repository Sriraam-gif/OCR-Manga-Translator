# Architecture

How this repo is structured and how a request flows end to end — written so
someone seeing the repo for the first time can follow along. For a quick start
see [`README.md`](README.md); for how to work on the code (setup, Windows
gotchas) see [`AGENTS.md`](AGENTS.md); for limitations see
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).

---

## What it does

You give it a manga (Japanese) or manhwa (Korean) **panel image**, and it returns
a **finished, translated image**: the original text is erased from the artwork and
natural English is typeset back into the speech bubbles — the way a hand
scanlation looks, not a caption beside the picture.

You can feed it panels three ways:

1. **Web UI** — upload a single panel (`http://localhost:5173`).
2. **Chrome extension** — a "Translate this page" button that translates panels
   on whatever chapter page you're reading (the recommended way to do real
   chapters — see [The browser extension](#the-browser-extension)).
3. **CLI** — `test_translate.py` for a quick backend smoke test.

---

## The big idea (why this isn't just another translator)

Every open-source manga translator (manga-image-translator, MangaQuick, Koharu)
runs the **same 5-stage pipeline**: detect text → OCR → remove text → translate →
typeset. We deliberately copied that pipeline because it's the proven way to get a
clean erase-and-replace result.

The one place we differ — and the whole reason this project exists — is the
**translation step**. The other tools send **one bubble at a time** to a stateless
API (Google/DeepL), which loses all context. We use an **LLM (Claude)** and send
the **whole page at once**, which lets us do things a bubble-by-bubble translator
structurally cannot:

- **Whole-page context** — pronouns, speaker turns, and tone stay consistent
  because Claude sees the entire scene.
- **Chapter-consistent glossary** — Claude returns the character names / recurring
  terms it used; the chapter flow threads them into later pages so names never
  drift.
- **Tone control** — `natural` / `literal` / `localized`, plus a keep-honorifics
  toggle.
- **One model, many languages** — Claude reads Japanese, Korean, Spanish, etc.
  with no per-language OCR model.

So: **detector + inpainter = parity with the field; LLM translation = our edge.**

---

## High-level architecture

```
  ┌──────────────────────────┐      ┌──────────────────────────┐
  │  Web UI (React + Vite)   │      │  Chrome extension (MV3)  │
  │  localhost:5173          │      │  reads panels from the   │
  │  upload a panel          │      │  tab you're viewing      │
  └─────────────┬────────────┘      └─────────────┬────────────┘
                │  POST /translate-image           │  POST /translate-image
                │  (Vite dev proxy)                │  (direct, CORS-enabled)
                ▼                                  ▼
  ┌───────────────────────────────────────────────────────────────┐
  │  Backend (FastAPI + Uvicorn)   http://127.0.0.1:8000           │
  │    main.py   ── /health  /translate-image  /translate-chapter  │
  │                     │                                          │
  │                     ▼                                          │
  │    translate.py  (orchestrator)                               │
  │        detect.py   DBNet (PaddleOCR)  → find + group text     │
  │        translate   Claude (LLM)       → whole-page translate  │
  │        inpaint.py  LaMa (big-lama)    → erase original text   │
  │        render.py   Pillow             → typeset English in    │
  │                                                              │
  │    scraper.py  (Playwright) — used only by /translate-chapter │
  └───────────────────────────────────────────────────────────────┘
```

Both front-ends hit the **same backend**. The web UI goes through Vite's dev proxy
(so the browser sees a same-origin call); the extension calls the backend directly
and relies on the backend's permissive CORS. The heavy compute lives entirely in
the backend.

---

## The pipeline (the heart of it)

`translate.py` orchestrates four stages on each panel:

```
panel image
  → detect.py    DBNet (PaddleOCR) finds tight text-line boxes, groups them into bubbles
  → translate    full page + every bubble crop → Claude (claude-sonnet-4-6) → English
                 [LLM does OCR + translation only — never used to locate text]
  → inpaint.py   LaMa (big-lama) erases the original text from each translated bubble
  → render.py    Pillow typesets the English into each bubble with a fitted comic font
  → finished translated PNG (returned as a data URL)
```

A key detail in the orchestration: **only boxes that come back with a real
translation are erased and typeset.** If Claude returns empty text for a box (a
caption it skipped, or a spurious/false detection), that region is left as the
original art — otherwise we'd erase it and leave a blank white rectangle.

---

## Repository layout

```
OCR Manga Translator/
├── backend/
│   ├── main.py            # FastAPI app: 3 endpoints, CORS, model warm-start
│   ├── translate.py       # pipeline orchestrator + Claude translation step
│   ├── detect.py          # DBNet text detection (PaddleOCR) + bubble grouping
│   ├── inpaint.py         # LaMa text removal (simple-lama-inpainting)
│   ├── render.py          # typesetting: draw English into bubbles (Pillow)
│   ├── scraper.py         # Playwright: chapter URL -> list of panel image URLs
│   ├── test_translate.py  # CLI smoke test (POST one image, write the result)
│   ├── requirements.txt   # Python deps
│   ├── .env.example       # template — copy to .env and add your key
│   ├── .env               # ANTHROPIC_API_KEY (gitignored)
│   └── venv/              # virtualenv (gitignored)
├── frontend/
│   └── src/
│       ├── App.jsx                    # top-level state + fetch + layout
│       ├── components/
│       │   ├── UrlInput.jsx           # chapter-URL field + Translate button
│       │   ├── ImageUpload.jsx        # single-panel upload
│       │   └── PanelResult.jsx        # one panel: rendered image (or overlay)
│       ├── main.jsx                   # React entry point
│       └── index.css                  # Tailwind directives
│   └── vite.config.js                # dev proxy; VITE_BACKEND_URL override
├── extension/             # Chrome extension (MV3) — "Translate this page"
│   ├── manifest.json
│   ├── popup.html / popup.js
│   └── README.md
├── colab_gpu.ipynb        # run the backend on a free Colab GPU (optional)
├── start.ps1              # one command: launch backend + frontend
├── README.md              # front door / quickstart
├── ARCHITECTURE.md        # this file
├── AGENTS.md              # how to work on the code (setup, gotchas)
├── KNOWN_ISSUES.md        # failure modes & limitations
├── CLAUDE.md              # project guide + original build spec
├── eval/                  # Phase 2 — NOT built yet (translation-quality scoring)
└── .gitignore
```

---

## Backend components

### `main.py` — HTTP layer

Defines the FastAPI app and three endpoints, owns transport concerns (request
parsing, image downloading, error handling), and delegates the real work to
`translate.py` / `scraper.py`. It also:

- **Enables permissive CORS** so the browser extension (and any local frontend)
  can call the API. This is a self-hosted local tool, so allow-all is fine.
- **Warms the models at startup** in a background thread (`lifespan`), so
  `/health` answers in ~1s while PaddleOCR + LaMa load, and the first real
  translation isn't a cold ~60s wait.

| Endpoint | Method | Input | Output |
|---|---|---|---|
| `/health` | GET | — | `{"status": "ok"}` |
| `/translate-image` | POST | multipart `file` + optional `tone`, `keep_honorifics` form fields | `{regions, rendered_image, glossary}` |
| `/translate-chapter` | POST | JSON `{url, tone?, keep_honorifics?}` | `{panels: [{image_url, regions, rendered_image, glossary}, ...]}` |

`/translate-image` runs the heavy, blocking pipeline via `run_in_threadpool` so the
async event loop stays responsive. `/translate-chapter` is a plain `def` (FastAPI
runs it in a worker thread) because it calls the **synchronous** Playwright API and
the blocking torch/paddle pipeline, and threads a **glossary** from each panel into
the next for chapter-wide name consistency.

### `translate.py` — `translate_image(image_bytes, options, glossary) -> dict`

The orchestrator, and where our differentiator lives.

1. **Detect.** `detect.detect_boxes` + `detect.group_into_bubbles` find and group
   the text.
2. **Translate (Claude, whole-page).** `_translate_bubbles` sends **one** request
   containing the **full page** (downscaled for context) **plus every bubble
   crop** (full-res, for legible OCR), and asks Claude to translate the page as a
   coherent scene. A JSON-schema structured output returns one
   `{index, original_text, translated_text}` per bubble **and** a `glossary` of
   names/terms. Tone and honorific handling come from `options`; an incoming
   `glossary` is injected so earlier pages' choices are reused.
3. **Filter.** Keep only bubbles with a non-empty translation (see the blank-box
   note above).
4. **Inpaint (LaMa).** `inpaint.lama_clean` erases the original text from the kept
   bubbles.
5. **Typeset (Pillow).** `render.typeset` draws the English into each box.

Returns `{regions, rendered_image, glossary}`. The Anthropic client reads the key
from `backend/.env` at import time. Model is `claude-sonnet-4-6` (`MODEL`).

### `detect.py` — `detect_boxes()` + `group_into_bubbles()`

DBNet text detection via PaddleOCR. Tall manhwa strips are **tiled** vertically so
each tile is detected near native resolution (DBNet downscales its input, so
detecting an 8000px strip at once would shrink the text to nothing). Returns tight
text-line boxes, deduplicated across tile overlaps, then clusters lines into
bubbles (union-find on horizontal overlap + vertical proximity) so each bubble is
translated as one unit.

**Device-aware:** detection runs on GPU when `paddlepaddle-gpu` is installed and a
CUDA device is present (`use_gpu`), otherwise CPU. Two Windows gotchas are handled
here: `import torch` **before** paddle (DLL load order), and
`paddlepaddle==2.6.2` + `enable_mkldnn=False` (newer paddle crashes on the bundled
det model's fused-conv ops).

### `inpaint.py` — `lama_clean(img, bubbles) -> img`

Runs the real **big-lama** model (via `simple-lama-inpainting`) to erase text. To
stay fast and avoid feeding a whole 8000px strip through at once, it inpaints each
bubble as a small padded crop (mask built from the bubble's text-line boxes,
slightly dilated) and pastes the result back. **Device-aware:** uses CUDA
automatically when available, CPU otherwise.

### `render.py` — `typeset(img, items) -> png bytes`

Draws each translated string into its (already-cleaned) bubble box: greedy
word-wrap, font auto-sized down to fit and capped at a modest page-relative size so
text looks typeset rather than ballooning, black/white text chosen by background
luminance, with a thin contrasting outline (standard scanlation look).

### `scraper.py` — `get_panel_image_urls(chapter_url) -> list[str]`

Launches headless Chromium via Playwright, loads the chapter page, scrolls to
trigger lazy-loaded images, and collects every `<img>` whose natural size is at
least 400×400px (the panel heuristic). Returns absolute, de-duplicated URLs in page
order. **Note:** anti-bot (Cloudflare) blocks this on the tested sites — the
extension is the practical way to get real panels (see below).

---

## The browser extension

Lives in [`extension/`](extension/) (Chrome MV3). It solves the scraper's
Cloudflare problem by never scraping: it reads the panel images out of the tab
**you already opened** (so you've already passed any Cloudflare/login wall).

Flow when you click **Translate this page** (`popup.js`):

```
1. inject collectPanels() into the active tab  → tag + list every <img> ≥ 400px
2. for each panel:
     fetch the image bytes        (extension host_permissions bypass page CORS)
     POST it to BACKEND/translate-image
     inject replacePanel()        → swap the panel's src for the translated image
3. show progress in the popup
```

The backend URL defaults to `http://localhost:8000` (editable in the popup, e.g.
to point at a Colab GPU tunnel). Because the heavy pipeline can't run in a browser,
the extension still needs the **local backend running** — same model as every
self-hosted translator. Setup: [`extension/README.md`](extension/README.md).

**Scraper vs. extension:** both feed images into the same backend. The scraper is a
server-side robot that re-opens the URL and gets blocked at the door; the extension
reads the page you already opened. Only the image-fetching front-end differs.

---

## Frontend components

- **`ImageUpload.jsx`** — single-panel file picker + Translate button (the working
  path today).
- **`UrlInput.jsx`** — chapter-URL field + Translate button (subject to the
  Cloudflare limitation).
- **`PanelResult.jsx`** — renders one panel: if the backend returned a
  `rendered_image` (the finished, typeset panel) it shows that directly; otherwise
  it falls back to a CSS overlay of `regions` on the original image.
- **`App.jsx`** — holds app state (`loading`, `panels`, `error`), makes the fetch
  calls, and lays out the input on top with results below. Handles loading, error,
  and "no panels found" states.

---

## Request flows

### Single image (`POST /translate-image`) — the main flow

```
client uploads image (+ optional tone / keep_honorifics)
   → main.py reads bytes → run_in_threadpool(translate_image)
   → detect (DBNet) → translate whole-page (Claude) → filter empties
   → inpaint kept bubbles (LaMa) → typeset (Pillow)
   → {regions, rendered_image, glossary}
```

~30s/panel on CPU (the first call also loads the detector + LaMa). Used by both the
web UI upload and the Chrome extension.

### Full chapter (`POST /translate-chapter`)

```
App fetch POST /translate-chapter {url, tone?, keep_honorifics?}
   → scraper.py: Playwright loads page, scrolls, returns panel image URLs
   → glossary = {}
   → for each URL:
         httpx.get(url, UA + Referer)                  # download panel bytes
         translate_image(bytes, options, glossary)     # full pipeline
         glossary = result.glossary                    # carry names/terms forward
         append {image_url, regions, rendered_image, glossary}
         # per-panel error: log + skip, don't fail the chapter
   → {"panels": [...]}
```

Panels run **sequentially**, threading the glossary so names stay consistent across
the chapter. Scraping itself is currently Cloudflare-blocked — use the extension.

---

## Data shapes

```jsonc
// translate_image() / POST /translate-image
{
  "regions": [
    {
      "original_text": "...",
      "translated_text": "...",
      "box": { "x": 0.2, "y": 0.1, "width": 0.3, "height": 0.05 }  // fractions of image size
    }
  ],
  "rendered_image": "data:image/png;base64,...",   // finished, typeset panel
  "glossary": { "원문이름": "English Name" }          // names/terms Claude used
}

// POST /translate-chapter
{
  "panels": [
    { "image_url": "https://.../panel1.jpg", "regions": [...], "rendered_image": "data:...", "glossary": {...} }
  ]
}
```

---

## Running it (local, CPU)

One command from the repo root:

```powershell
./start.ps1      # opens backend + frontend in two windows
```

Or manually:

```bash
# Terminal A — backend  (avoid --reload: it reloads the heavy models each change)
cd backend
PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe -m uvicorn main:app --port 8000

# Terminal B — frontend
cd frontend
npm run dev
```

Open the Vite URL it prints and upload a panel. The **first** request loads
PaddleOCR + LaMa (and downloads `big-lama.pt` once); subsequent panels are
~30s each on CPU. Backend-only smoke test:

```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe test_translate.py some_panel.jpg out.png
```

See [`AGENTS.md`](AGENTS.md) for first-time setup and the Windows torch/paddle
gotchas.

---

## Running on a GPU (optional, ~4x faster)

Detection + LaMa are the slow part on CPU and both GPU-accelerate; the Claude call
is remote and unaffected. On a GPU a panel drops from ~30s to ~8s. The code is
**device-aware**, so the *same backend* runs on GPU with no changes:

- `inpaint.py` uses CUDA torch automatically when present.
- `detect.py` uses GPU when `paddlepaddle-gpu` is installed (CPU fallback
  otherwise).

This machine has no NVIDIA GPU, so the practical path is the **free Colab T4**:
[`colab_gpu.ipynb`](colab_gpu.ipynb) clones the repo, installs GPU deps, and serves
the backend on a public Cloudflare tunnel URL. Point the frontend at it with
`VITE_BACKEND_URL`, or paste the URL into the extension's backend field. Colab
sessions are ephemeral (~12h max) — a dev/demo accelerator, not 24/7 hosting.

---

## Configuration

- **`backend/.env`** — `ANTHROPIC_API_KEY=...`. Gitignored; copy from
  `.env.example`. Each user needs their **own** key (calls cost money). Translation
  401s until a real key is set.
- **Model** — `claude-sonnet-4-6`, hardcoded as `MODEL` in `translate.py`.
- **Tone / honorifics** — `tone` (`natural`/`literal`/`localized`) and
  `keep_honorifics` per request (defaults: `natural`, keep).
- **Panel size threshold** — 400px in `scraper.py` and the extension's
  `collectPanels`. Lower if a site's panels are smaller.
- **Frontend backend target** — `VITE_BACKEND_URL` (defaults to
  `http://127.0.0.1:8000`); set it to a Colab tunnel URL to run on GPU.
- **CORS** — backend allows all origins (local tool) so the extension can call it.

---

## Tech choices worth knowing

- **LLM translation, whole-page context.** The project's edge: Claude translates
  the whole page at once (context, glossary, tone), unlike the bubble-by-bubble
  API calls the other tools use.
- **Dedicated detector, not VLM-as-detector.** An LLM reads/translates well but
  returns fuzzy/incomplete bounding boxes; detection uses a real DBNet model and
  Claude is reserved for translation — same division of labour as
  manga-image-translator / MangaQuick / Koharu.
- **LaMa for text removal, not white boxes.** Inpainting erases text so the bubble
  art shows through, run per-bubble-crop to keep inference fast.
- **Only erase what we translate.** Boxes with empty translations keep the original
  art, so we never leave blank white rectangles.
- **Tile tall strips for detection.** DBNet downscales its input; a single 8000px
  manhwa strip would lose all text, so we detect in overlapping tiles.
- **Device-aware, warm-started backend.** Same code runs CPU or GPU; models load at
  startup so the first request isn't a cold wait.
- **Windows torch+paddle coexistence.** `import torch` first (DLL load order) and
  pin `paddlepaddle==2.6.2` with mkldnn disabled — newer paddle crashes on the
  bundled detection model.
- **Structured outputs over prompt-and-parse.** The JSON schema is enforced by the
  API, so the translation step never guesses whether the model returned valid JSON.
- **Extension over scraping for real chapters.** Reading images from your logged-in
  tab sidesteps Cloudflare entirely; the scraper is kept but limited.
- **Per-panel error isolation.** Chapter translation never fails wholesale on one
  bad image.

---

## Not built yet — Phase 2 (eval pipeline)

The `eval/` folder is planned but empty. Per `CLAUDE.md`, Phase 2 measures
translation quality and compares prompt strategies (a reference dataset, a second
prompt variant, a `score.py` computing BLEU/ChrF with `sacrebleu`, and a results
summary). It's the natural next step — and especially valuable here because it
would *prove* the whole-page-context translation beats bubble-by-bubble.

For current limitations and per-site scraping notes, see
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).
