# Architecture

How this repo is structured and how a request flows end to end. For the original
build spec see `CLAUDE.md`; for limitations see `KNOWN_ISSUES.md`.

---

## What it does

A web app where you paste a manga/manhwa chapter URL (or upload a single panel).
The app finds the text in each panel, translates it to English, **erases the
original text from the art, and typesets the English back into the bubbles** —
returning a finished, translated image.

It uses the same 5-stage pipeline as the established open-source translators
(manga-image-translator, MangaQuick, Koharu): a **dedicated text detector**, a
**translation model**, an **inpainter** to remove the original text, and a
**typesetter** to draw the new text. Claude is used for the *translation* step
only — not as the detector.

- **Manga** (Japanese) reads right-to-left; **manhwa** (Korean) reads
  left-to-right. Detected bubbles are ordered top-to-bottom for translation.

---

## High-level architecture

```
┌─────────────────────────────┐         ┌──────────────────────────────────────┐
│  Frontend (React + Vite)    │         │  Backend (FastAPI + Uvicorn)         │
│  http://localhost:5173      │         │  http://127.0.0.1:8000               │
│                             │         │                                      │
│  App.jsx                    │  POST   │  main.py                             │
│   ├─ UrlInput.jsx ──────────┼────────▶│   ├─ POST /translate-chapter        │
│   └─ PanelResult.jsx        │ /trans- │   ├─ POST /translate-image          │
│                             │ late-*  │   └─ GET  /health                   │
└─────────────────────────────┘         │            │            │            │
        ▲   Vite dev proxy forwards      │            ▼            ▼            │
        │   /translate-* to :8000        │      scraper.py    translate.py     │
        │   (no CORS in dev)             │       (Playwright)  (orchestrator)  │
        └────────────────────────────────         │                │           │
                                                   ▼                ▼           │
                                          headless Chromium   pipeline:         │
                                          loads chapter page   detect.py  (DBNet)
                                                               translate  (Claude)
                                                               inpaint.py (LaMa) │
                                                               render.py  (typeset)
                                          └─────────────────────────────────────┘
```

The translation pipeline (`translate.py`) chains four stages:

```
panel image
  → detect.py    DBNet (PaddleOCR) finds tight text-line boxes, grouped into bubbles
  → translate.py each bubble crop → Claude (claude-sonnet-4-6) → English  [LLM = translate only]
  → inpaint.py   LaMa (big-lama) erases the original text from each bubble crop
  → render.py    PIL typesets the English into each bubble with a fitted comic font
  → finished translated PNG (returned as a data URL)
```

Two processes during development: the Vite dev server (frontend) and Uvicorn
(backend). The browser only ever talks to the Vite origin; Vite proxies the
`/translate-*` calls to the backend so there are no CORS issues.

---

## Repository layout

```
OCR Manga Translator/
├── backend/
│   ├── main.py            # FastAPI app + the 3 HTTP endpoints
│   ├── translate.py       # pipeline orchestrator + Claude translation step
│   ├── detect.py          # DBNet text detection (PaddleOCR) + bubble grouping
│   ├── inpaint.py         # LaMa text removal (simple-lama-inpainting)
│   ├── render.py          # typesetting: draw English into bubbles (PIL)
│   ├── scraper.py         # Playwright: chapter URL -> list of panel image URLs
│   ├── requirements.txt   # Python deps
│   ├── .env               # ANTHROPIC_API_KEY (gitignored; ships as a placeholder)
│   └── venv/              # virtualenv (gitignored)
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # top-level state + fetch + layout
│   │   ├── components/
│   │   │   ├── UrlInput.jsx         # URL field + Translate button
│   │   │   └── PanelResult.jsx      # one panel: image + translated/original text
│   │   ├── main.jsx                 # React entry point
│   │   └── index.css                # Tailwind directives
│   ├── vite.config.js              # dev-server proxy to the backend
│   ├── tailwind.config.js
│   └── package.json
├── eval/                  # Phase 2 — NOT built yet (translation-quality scoring)
├── CLAUDE.md              # the original build spec
├── KNOWN_ISSUES.md        # failure modes & limitations
├── ARCHITECTURE.md        # this file
└── .gitignore
```

---

## Backend components

### `main.py` — HTTP layer

Defines the FastAPI app and three endpoints. It owns transport concerns
(request parsing, image downloading, error handling) and delegates the real work
to `scraper.py` and `translate.py`.

| Endpoint | Method | Input | Output |
|---|---|---|---|
| `/health` | GET | — | `{"status": "ok"}` |
| `/translate-image` | POST | multipart file upload | `{"regions": [...], "rendered_image": "data:image/png;base64,..."}` |
| `/translate-chapter` | POST | JSON `{"url": "..."}` | `{"panels": [{image_url, regions, rendered_image}, ...]}` |

`/translate-image` reads the upload, then runs the (heavy, blocking) pipeline via
`run_in_threadpool` so the async event loop stays responsive. `/translate-chapter`
is a plain `def`, so FastAPI runs the whole thing in a worker thread — it calls
the **synchronous** Playwright API and the blocking pipeline (torch/paddle), which
can't run on the asyncio event loop thread.

Image downloads in `/translate-chapter` send a browser-like `User-Agent` and the
chapter URL as `Referer`, because many image CDNs reject requests without them.

### `scraper.py` — `get_panel_image_urls(chapter_url) -> list[str]`

Launches headless Chromium via Playwright, loads the chapter page, scrolls to the
bottom to trigger lazy-loaded images, then collects every `<img>` whose rendered
natural size is at least 400×400px (the panel heuristic). Returns absolute,
de-duplicated URLs in page order. `currentSrc` is read so `srcset`/lazy
attributes resolve correctly.

### `detect.py` — `detect_boxes()` + `group_into_bubbles()`

DBNet text detection via PaddleOCR (the repo's "Paddle" detector option). Tall
manhwa strips are **tiled** vertically so each tile is detected near native
resolution (DBNet downscales its input, so detecting an 8000px strip at once
would shrink the text to nothing). Returns tight text-line boxes, deduplicated
across tile overlaps, then clusters lines into bubbles (union-find on horizontal
overlap + vertical proximity) so each bubble is translated as one unit.

Two Windows gotchas are handled here: `import torch` **before** paddle (DLL load
order), and `paddlepaddle==2.6.2` + `enable_mkldnn=False` (newer paddle hits a
OneDNN fused-conv crash on the bundled det model).

### `translate.py` — `translate_image(image_bytes) -> dict`

The orchestrator. Detects bubbles, then:

1. **Translate (Claude only).** All bubble crops are sent in **one** request to
   `claude-sonnet-4-6` with a JSON-schema structured output, returning one
   `{original_text, translated_text}` per bubble. Claude does OCR+translation of
   the crops — it is *not* used to locate text.
2. **Inpaint (LaMa).** `inpaint.lama_clean` erases the original text.
3. **Typeset (PIL).** `render.typeset` draws the English into each bubble box.

Returns `{regions, rendered_image}` — `regions` is the structured data (original,
translated, fractional box per bubble); `rendered_image` is the finished PNG as a
data URL. The Anthropic client reads the key from `backend/.env` at import time.

### `inpaint.py` — `lama_clean(img, bubbles) -> img`

Runs the real **big-lama** model (via `simple-lama-inpainting`) to erase text.
To stay fast on CPU and avoid feeding a whole 8000px strip through the network,
it inpaints each bubble as a small padded crop (mask built from the bubble's
text-line boxes, slightly dilated) and pastes the result back.

### `render.py` — `typeset(img, items) -> png bytes`

Draws each translated string into its (already-cleaned) bubble box: greedy
word-wrap, font auto-sized down to fit, capped at a modest page-relative size so
text looks typeset rather than ballooning, black/white chosen by background
luminance, with a thin contrasting outline (standard scanlation look).

---

## Frontend components

- **`UrlInput.jsx`** — controlled text input + a Translate button. On submit it
  passes the trimmed URL up to `App`. The button shows a loading state and is
  disabled while a request is in flight.
- **`PanelResult.jsx`** — renders one panel. If the backend returned a
  `rendered_image` (the finished, typeset panel), it shows that directly;
  otherwise it falls back to a CSS overlay of the `regions` on the original image.
- **`App.jsx`** — holds the app state (`loading`, `panels`, `error`), does the
  `fetch('/translate-chapter', ...)` call, and lays out the input on top with the
  list of `PanelResult`s below. Handles three UI states: loading, error, and
  "no panels found".

---

## Request flows

### Single image (`POST /translate-image`)

```
client uploads image file
   → main.py reads the bytes → run_in_threadpool(translate_image)
   → detect (DBNet) → translate (Claude) → inpaint (LaMa) → typeset (PIL)
   → returns {regions, rendered_image}
```

This is now a first-class flow: the single-image upload in the UI uses it to
translate a panel without scraping. ~30s/image on CPU (first call also loads the
detector + LaMa models).

### Full chapter (`POST /translate-chapter`) — the main user flow

```
UrlInput submit  → App fetch POST /translate-chapter {url}
   → (Vite proxy) → main.py
        → scraper.py: Playwright loads page, scrolls, returns panel image URLs
        → for each URL:
              httpx.get(url, UA + Referer)        # download panel bytes
              translate.py.translate_image(bytes) # full detect→translate→inpaint→typeset
              append {image_url, regions, rendered_image}
              # on any per-panel error: log + skip, don't fail the chapter
   → {"panels": [...]}
   → App renders one PanelResult per panel
```

Panels are processed **sequentially**, each running the full pipeline (~30s/page
on CPU). A bad panel (failed download, unsupported format) is logged and skipped
so one failure doesn't sink the whole chapter. Note: scraping itself is currently
blocked by Cloudflare on the tested sites — see `KNOWN_ISSUES.md`.

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
  "rendered_image": "data:image/png;base64,..."   // finished, typeset panel
}

// POST /translate-chapter
{
  "panels": [
    { "image_url": "https://.../panel1.jpg", "regions": [ ... ], "rendered_image": "data:..." }
  ]
}
```

---

## Configuration

- **`backend/.env`** — `ANTHROPIC_API_KEY=...`. Gitignored; ships as a
  placeholder (`your_key_here`). Translation calls 401 until you set a real key.
- **Model** — `claude-sonnet-4-6`, hardcoded as `MODEL` in `translate.py`.
- **Panel size threshold** — `min_width`/`min_height` (default 400) in
  `get_panel_image_urls`. Lower it if a site's panels are smaller than expected.
- **Vite proxy** — `vite.config.js` forwards `/translate-chapter` and
  `/translate-image` to `http://127.0.0.1:8000`.

---

## Running it

```bash
# Terminal A — backend  (avoid --reload: it reloads the heavy models each change)
cd backend
PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe -m uvicorn main:app --port 8000

# Terminal B — frontend
cd frontend
npm run dev
```

Open the Vite URL it prints; upload a panel image (or paste a chapter URL). The
**first** request loads PaddleOCR + LaMa (and downloads `big-lama.pt` once), so it
is slow; subsequent requests are ~30s/panel on CPU.

Backend-only smoke test of a single image (writes the rendered result to a PNG):
```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe test_translate.py some_panel.jpg out.png
```

See [`AGENTS.md`](AGENTS.md) for setup, the Windows torch/paddle gotchas, and how
to restart the server.

---

## Tech choices worth knowing

- **Dedicated detector, not VLM-as-detector.** An LLM can read and translate text
  well, but asking it for pixel-accurate bounding boxes is unreliable (it misses
  duplicated/busy regions and returns fuzzy boxes). So detection uses a real
  DBNet model and Claude is reserved for translation — the same division of
  labour as manga-image-translator / MangaQuick / Koharu.
- **LaMa for text removal, not white boxes.** Inpainting erases the original text
  so the bubble background/art shows through, instead of pasting opaque
  rectangles. We run it per-bubble-crop to keep CPU inference fast.
- **Tile tall strips for detection.** DBNet downscales its input; a single
  8000px manhwa strip would lose all text, so we detect in overlapping tiles.
- **Windows torch+paddle coexistence.** `import torch` first (DLL load order) and
  pin `paddlepaddle==2.6.2` with mkldnn disabled — newer paddle crashes on the
  bundled detection model's fused-conv ops.
- **Structured outputs over prompt-and-parse.** The schema is enforced by the
  API, so the translation step never has to guess whether the model returned
  valid JSON.
- **Sync `/translate-chapter` endpoint.** Deliberate — lets us use sync Playwright
  and the blocking Anthropic SDK in FastAPI's threadpool without async/sync
  juggling.
- **Pinned `create-vite@5` + Tailwind v3.** Node 19 on this machine is EOL; the
  latest of both require Node 20+. Bump these if you upgrade Node.
- **Per-panel error isolation.** Chapter translation never fails wholesale on a
  single bad image.

---

## Not built yet — Phase 2 (eval pipeline)

The `eval/` folder is planned but empty. Per `CLAUDE.md`, Phase 2 measures
translation quality and compares prompt strategies (a reference dataset, a second
prompt variant via a `prompt_version` parameter on `translate_image`, a
`score.py` that computes BLEU/ChrF with `sacrebleu`, and a results summary). It's
intentionally deferred until Phase 1 is confirmed working end-to-end.
```

For current limitations and per-site scraping notes, see `KNOWN_ISSUES.md`.
