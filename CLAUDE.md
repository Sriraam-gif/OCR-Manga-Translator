# CLAUDE.md — Project guide

> **New here? Start with [`README.md`](README.md).** To just *use* it, see
> [`USAGE.md`](USAGE.md) (step-by-step first-time guide); for internals see
> [`ARCHITECTURE.md`](ARCHITECTURE.md); for how to work on the code (setup,
> Windows gotchas, testing) see [`AGENTS.md`](AGENTS.md); for limitations see
> [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).

## Current state (what's actually built)

Phase 1 is built and working, but the **architecture evolved past the original
spec below**. Instead of a single Claude Vision call per panel, the app now runs
the same 4-stage pipeline the established open-source translators use, and Claude
is used for the **translation step only**:

```
detect.py (DBNet/PaddleOCR)  →  translate.py (Claude claude-sonnet-4-6)
                             →  inpaint.py (LaMa)  →  render.py (typeset, PIL)
```

The output is a **finished translated image**: the original text is erased from
the art and the English is typeset into the bubbles (not shown as a caption).

Our differentiator is the **translation step**: unlike the bubble-by-bubble
DeepL/Google calls the other tools use, we send the **whole page** to Claude for
context-aware translation, a **chapter-consistent glossary** (names/terms threaded
across panels), and a **tone dial** (natural / literal / localized + honorifics).

- ✅ Single-image translation, end to end, quality on par with hand-scanlation.
- ✅ Context-aware translation: whole-page context, glossary, tone control.
- ✅ **Chrome extension** (`extension/`) — translate panels on any site; the
  practical way to do real chapters (works around the blocked scraper).
- ⚠️ Chapter-URL scraper still Cloudflare-blocked — use the extension instead.
- ⬜ Phase 2 eval pipeline (`eval/`) not built yet.
- Runs CPU-only by default, ~30s/panel; optional free GPU via `colab_gpu.ipynb`
  (~8s/panel). Heavy deps: PyTorch + PaddlePaddle + LaMa. Device-aware (auto-CUDA).

### Working style for this repo

On clear/greenfield specs, prefer decisive action: give a short verdict and
build, rather than over-asking or proposing heavy review pipelines. Use the
`andrej-karpathy` skill when developing code. **Before touching the backend
pipeline, read the "Critical environment gotchas" in [`AGENTS.md`](AGENTS.md)** —
the torch/paddle import order and version pins are load-bearing.

---

# IMPLEMENTATION_PLAN.md (original build spec — historical)
## Manga/Manhwa OCR Translator — Build Spec for Claude Code

> This is the original from-scratch plan the project was built against. It is kept
> for context; the implemented architecture differs (see "Current state" above —
> notably a dedicated detector + LaMa inpainting replaced the single Vision call,
> and translation is rendered onto the image rather than shown beside it).

---

## Project goal

Build a web app where a user pastes a URL to a manga/manhwa chapter page. The app
scrapes the panel images from that page, sends each image to the Claude Vision API
to read and translate any text in it, and displays the original image alongside
the translated text. Manga(Japanese) is read right to left whereas Manhwa(Korean) are read from left to right.

Build this in the order specified below. Do not skip ahead to later steps until
the current step's acceptance criteria are met.

---

## Tech stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn
- **AI model:** Anthropic Claude Vision API (model: `claude-sonnet-4-6`)
- **Scraping:** Playwright (Python)
- **Frontend:** React + Vite + Tailwind CSS
- **Config:** `.env` file for `ANTHROPIC_API_KEY` (use `python-dotenv`)

---

## Folder structure

```
manga-translator/
├── backend/
│   ├── main.py              # FastAPI app entrypoint
│   ├── translate.py         # Claude Vision call logic
│   ├── scraper.py            # Playwright scraping logic
│   ├── requirements.txt
│   └── .env                  # ANTHROPIC_API_KEY=... (gitignored)
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── UrlInput.jsx
│   │   │   └── PanelResult.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── eval/                      # Phase 2 — built later
│   ├── dataset/
│   ├── score.py
│   └── results/
├── .gitignore
└── CLAUDE.md
```

---

## Build order

### Step 1 — Project scaffolding

- Create the folder structure above.
- Initialize `backend/` with a virtual environment and `requirements.txt`
  containing: `fastapi`, `uvicorn`, `anthropic`, `python-dotenv`, `playwright`,
  `pillow`.
- Initialize `frontend/` with `npm create vite@latest` (React template), then
  add Tailwind CSS.
- Create `.gitignore` covering `.env`, `node_modules/`, `__pycache__/`, `venv/`.
- Create an empty `.env` file in `backend/` with a placeholder:
  `ANTHROPIC_API_KEY=your_key_here`

**Acceptance criteria:** `uvicorn main:app --reload` runs a bare FastAPI app
returning `{"status": "ok"}` on `GET /health`. `npm run dev` serves a blank
Vite + React page.

---

### Step 2 — Single-image translation endpoint

- In `translate.py`, write a function `translate_image(image_bytes: bytes) -> dict`
  that:
  - Sends the image to the Claude Vision API (`claude-sonnet-4-6`) as a base64-encoded
    image input.
  - Uses a prompt instructing the model to: (1) read all visible text in the image
    (preserving reading order for manga, which may be right-to-left), and (2)
    translate it to natural English.
  - Requests a structured JSON response: `{"original_text": "...", "translated_text": "..."}`.
  - Parses and returns this dict.
- In `main.py`, add `POST /translate-image` which accepts an uploaded image file
  (multipart/form-data) and returns the result of `translate_image`.

**Acceptance criteria:** Using a tool like `curl` or Postman, upload a single
manga panel image (test with 1-2 sample images saved locally) to
`/translate-image` and receive back a JSON object with `original_text` and
`translated_text` fields containing plausible content.

---

### Step 3 — Chapter scraping

- In `scraper.py`, write a function `get_panel_image_urls(chapter_url: str) -> list[str]`
  using Playwright that:
  - Loads the given URL in a headless browser.
  - Finds all `<img>` elements that look like manga panels (large images in the
    main content area — heuristics may be needed depending on the target site;
    start with a generic "all images above a minimum width/height" filter).
  - Returns a list of absolute image URLs in page order.
- In `main.py`, add `POST /translate-chapter` which:
  - Accepts `{"url": "..."}` in the request body.
  - Calls `get_panel_image_urls`.
  - For each image URL, downloads the image bytes and calls `translate_image`.
  - Returns `{"panels": [{"image_url": "...", "original_text": "...", "translated_text": "..."}, ...]}`.

**Acceptance criteria:** Calling `/translate-chapter` with a real manga chapter
URL returns a list of panels, each with original and translated text. Handle and
log errors per-panel without failing the whole request (e.g., if one image fails
to download, skip it and continue).

---

### Step 4 — Frontend

- `UrlInput.jsx`: a text input + "Translate" button. On submit, calls
  `POST /translate-chapter` on the backend and shows a loading state.
- `PanelResult.jsx`: given one panel object, displays the panel image with the
  translated text shown below or overlaid on it.
- `App.jsx`: ties these together — input at top, list of `PanelResult` components
  below once results arrive.
- Configure Vite's dev server to proxy `/translate-chapter` and `/translate-image`
  to the FastAPI backend (avoid CORS issues during development).

**Acceptance criteria:** Pasting a real chapter URL into the UI and clicking
"Translate" displays each panel image with its translated text below it, without
needing to use `curl` or Postman.

---

### Step 5 — End-to-end testing

- Test with 2-3 different real manga/manhwa chapter URLs from different sites.
- Note and document any failure patterns (e.g., site-specific image detection
  issues, garbled OCR on stylized fonts, very long chapters timing out).
- Add basic error handling in the UI for failed requests (show an error message
  instead of a blank screen).

**Acceptance criteria:** The app works end-to-end on at least 2 real chapter
URLs, and known failure modes are documented in a `KNOWN_ISSUES.md` file.

---

## Phase 2 — Evaluation pipeline (build after Phase 1 is fully working)

This phase measures translation quality and compares prompt strategies. It lives
in the `eval/` folder and does not modify the running app.

### Step 6 — Build a reference dataset

- Manually select 20-30 manga panel images with visible dialogue.
- Save them in `eval/dataset/images/`.
- Create `eval/dataset/references.json`:
  `[{"image": "panel_001.jpg", "reference": "<human-written correct translation>"}, ...]`

### Step 7 — Add a second prompt variant

- In `translate.py`, refactor `translate_image` to accept a `prompt_version`
  parameter (`"v1"` = original prompt, `"v2"` = a refined prompt that adds
  context, e.g., "this is informal manga dialogue between characters; preserve
  tone and keep it natural in English").

### Step 8 — Scoring script

- `eval/score.py`:
  - Reads `references.json`.
  - For each image, calls `translate_image` with both `prompt_version="v1"` and
    `prompt_version="v2"`.
  - Scores each output against the reference using `sacrebleu` (compute both
    BLEU and ChrF).
  - Writes results to `eval/results/scores.csv` with columns:
    `image, prompt_version, bleu, chrf, model_output, reference`.
  - Prints average BLEU and ChrF per prompt version to the console.

**Acceptance criteria:** Running `python eval/score.py` produces `scores.csv` and
prints a clear comparison (e.g., "v1 avg BLEU: 24.3 | v2 avg BLEU: 31.7") showing
which prompt performs better.

### Step 9 — Results summary

- Add a short `eval/RESULTS.md` summarizing: which prompt version performed
  better and by how much, 2-3 example panels where the two versions differed
  most, and a brief hypothesis for why.

---

## Notes for Claude Code

- Work through steps in order. After each step, run the relevant acceptance
  test before moving on.
- Keep API keys out of source code — read from `.env` only.
- Prefer small, working increments over large untested changes.
- If a manga site blocks Playwright scraping (anti-bot measures), note this in
  `KNOWN_ISSUES.md` and suggest 1-2 alternative sites to test with rather than
  spending excessive time defeating anti-scraping measures.
- Use andrej-karpathy skill when develipoing code 
