# Manga / Manhwa OCR Translator

Translate a manga (Japanese) or manhwa (Korean) panel into English — and get the
translation **rendered back onto the image**: the original text is erased from the
art and the English is typeset into the speech bubbles.

You can upload a single panel, or paste a chapter URL and have every panel
scraped and translated.

```
  原文 / 원문 / texto original   ──▶   clean English, in the bubble
```

This project uses the same pipeline the established open-source manga translators
use (manga-image-translator, MangaQuick, Koharu): a dedicated text **detector**, a
**translation** model, an **inpainter** to remove the original text, and a
**typesetter** to draw the new text in. Claude is used for the *translation* step
only — not for finding the text.

---

## How it works

A panel flows through four stages:

| Stage | What happens | Tool |
|---|---|---|
| 1. **Detect** | Find tight boxes around every line of text; group lines into bubbles | DBNet (PaddleOCR) |
| 2. **Translate** | Read + translate each bubble crop to natural English | Claude (`claude-sonnet-4-6`) |
| 3. **Inpaint** | Erase the original text so the bubble/art shows through | LaMa (`big-lama`) |
| 4. **Typeset** | Draw the English into each bubble with a fitted comic font | Pillow |

Why a dedicated detector instead of just asking the LLM where the text is? An LLM
translates well but returns fuzzy/incomplete bounding boxes (it misses duplicated
and busy regions). A purpose-built detector gives pixel-accurate boxes, which is
what makes the erase-and-replace step look clean. See
[`ARCHITECTURE.md`](ARCHITECTURE.md) for the full design.

### What makes the translation better than other tools

Most open-source/commercial manga translators translate **one bubble at a time**
through a stateless API (Google/DeepL), so they lose context and drift on names.
Because our translation step is an LLM, we do what they structurally can't:

- **Whole-page context** — the full page + all bubbles go to Claude in one request,
  translated as a coherent scene, so pronouns, speaker turns, and tone stay consistent.
- **Chapter-consistent names/terms** — Claude returns a glossary that's threaded
  across panels, so a character or term is translated the same way every time.
- **Tone control** — `natural` (default), `literal`, or `localized`, plus a
  keep-honorifics toggle (`-san`/`-nim`/`oppa`).

---

## Tech stack

- **Backend:** Python 3.11, FastAPI + Uvicorn
- **Detection:** PaddleOCR (DBNet) · **Inpaint:** simple-lama-inpainting (LaMa, via PyTorch CPU)
- **Translation:** Anthropic Claude API (`claude-sonnet-4-6`)
- **Scraping:** Playwright (headless Chromium)
- **Frontend:** React + Vite + Tailwind CSS

> Runs **CPU-only** here — no GPU required. Expect **~30s per panel**. The first
> request also downloads/loads the detector and LaMa model weights (~200MB once).

---

## Repository layout

```
OCR Manga Translator/
├── backend/
│   ├── main.py            # FastAPI app + HTTP endpoints
│   ├── translate.py       # pipeline orchestrator + Claude translation step
│   ├── detect.py          # DBNet text detection + bubble grouping
│   ├── inpaint.py         # LaMa text removal
│   ├── render.py          # typesetting (draw English into bubbles)
│   ├── scraper.py         # Playwright: chapter URL -> panel image URLs
│   ├── test_translate.py  # CLI helper to translate one image
│   ├── requirements.txt
│   └── .env               # ANTHROPIC_API_KEY (gitignored)
├── frontend/
│   └── src/
│       ├── App.jsx
│       └── components/{UrlInput,ImageUpload,PanelResult}.jsx
├── README.md              # you are here
├── ARCHITECTURE.md        # deep dive on the design + request flows
├── AGENTS.md              # guide for contributors / AI coding agents
├── KNOWN_ISSUES.md        # limitations & failure modes
└── CLAUDE.md              # original build spec + project notes
```

---

## Quickstart

### 1. Backend

```bash
cd backend
py -3.11 -m venv venv
venv\Scripts\activate              # PowerShell/cmd  (bash: source venv/Scripts/activate)
pip install -r requirements.txt
playwright install chromium        # only needed for chapter-URL scraping
```

Add your Anthropic key to `backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Run the server:

```bash
python -m uvicorn main:app --port 8000
```

> Heads-up (Windows): the deps include PyTorch + PaddlePaddle, which is a large
> install (~1GB). The pinned versions (`paddlepaddle==2.6.2`, torch imported
> first) are deliberate — see [`AGENTS.md`](AGENTS.md) if you hit DLL/OneDNN errors.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually <http://127.0.0.1:5173>). The dev server proxies
API calls to the backend, so there are no CORS issues.

---

## Using it

**Single panel (works today):** in the UI, use *"Translate a single panel image"*,
pick an image, click Translate. First run ~30s (model load), then ~30s/panel.

**From the command line:**

```bash
cd backend
# PYTHONIOENCODING=utf-8 avoids a Windows console error when printing CJK text
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe test_translate.py input.jpg output.png
```

**Whole chapter (URL):** paste a chapter URL in the UI. This runs the same
pipeline on every scraped panel — **but** scraping is currently blocked by
Cloudflare on the sites tested, so this path may return no panels. See
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).

---

## Run on a free GPU (~4x faster)

Detection + inpainting are the slow part on CPU. Run them on a free Colab **T4
GPU** to go from ~30s to ~8s per panel — no code changes (the backend
auto-detects CUDA).

1. Open **[colab.research.google.com](https://colab.research.google.com)** → upload [`colab_gpu.ipynb`](colab_gpu.ipynb).
2. **Runtime → Change runtime type → T4 GPU**.
3. Run the cells: it clones this repo, installs GPU deps, takes your API key, and
   prints a public `trycloudflare.com` URL serving the backend.

Point the frontend's Vite proxy (or your requests) at that URL. Colab sessions
are ephemeral (~12h max), so this is a dev/demo accelerator, not 24/7 hosting.

## Status

- ✅ Single-image translation: detect → translate → inpaint → typeset, end to end
- ✅ Output quality on par with hand-scanlated references
- ✅ Context-aware translation: whole-page context, chapter-consistent glossary, tone control
- ⚠️ Chapter scraping blocked by Cloudflare (bypass is the next work item)
- ⚠️ Stylized sound-effects drawn into the art (not in bubbles) are left untranslated
- ⬜ Phase 2 (translation-quality eval pipeline) — planned, not built

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for internals and [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md)
for limitations.
