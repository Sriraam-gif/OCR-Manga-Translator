# How to use it — first-time guide

A friendly, step-by-step walkthrough to go from "I just cloned this" to "I'm
reading a translated chapter." No prior knowledge of the code needed.

> If you just want the short version: **clone → add your own API key → run the
> backend → upload a panel (or use the Chrome extension).**

---

## What you'll need

- **Python 3.11** — <https://www.python.org/downloads/> (tick "Add to PATH").
- **Node.js 18+** — <https://nodejs.org/> (only for the web UI, not the extension).
- **Your own Anthropic API key** — free signup at
  <https://console.anthropic.com/> → *API Keys* → create one. Translations are
  done by Claude, so this is required; it costs a few cents per page.
- **~1.5 GB free disk** — the AI libraries (PyTorch + PaddlePaddle) and model
  weights are large. The first translation downloads ~200 MB of weights once.
- **Windows** is the tested platform. Mac/Linux should work but is unverified.

You do **not** need a GPU. It runs on CPU at about ~30 seconds per panel.

---

## Step 1 — Get the code

```bash
git clone https://github.com/Sriraam-gif/OCR-Manga-Translator.git
cd OCR-Manga-Translator
```

## Step 2 — Set up the backend (one time)

```bash
cd backend
py -3.11 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

This installs the AI libraries and takes a few minutes the first time.

## Step 3 — Add your API key

```bash
copy .env.example .env
```

Then open `backend\.env` in a text editor and replace the placeholder with your
real key:

```
ANTHROPIC_API_KEY=sk-ant-...your key here...
```

This file stays on your computer and is never uploaded.

## Step 4 — Start it

From the **repo root** (the `OCR-Manga-Translator` folder), the easy way:

```powershell
./start.ps1
```

That opens the backend and the web UI in two windows. (Manual alternative: run
`python -m uvicorn main:app --port 8000` in `backend/`, and `npm install` then
`npm run dev` in `frontend/`.)

Wait until the backend window says it's running. The very first translation is
slower because it downloads the AI model weights once.

---

## Step 5 — Translate something

You have two ways to use it. Pick whichever fits.

### Option A — Upload a single panel (web UI)

Best for trying it out or translating one image you've saved.

1. Open **<http://127.0.0.1:5173>** in your browser.
2. Choose **"Translate a single panel image"**, pick an image file, click
   **Translate**.
3. After ~30 seconds you'll see the panel with the original text erased and the
   English typeset into the bubbles.

### Option B — Translate a whole page on a manga site (Chrome extension)

Best for actually reading chapters. This works even on sites that block the
built-in scraper, because it reads the page **you** have open.

1. Make sure the backend is running (Step 4).
2. In Chrome, go to `chrome://extensions`, turn on **Developer mode** (top-right),
   click **Load unpacked**, and select the **`extension/`** folder from the repo.
3. Open a manga/manhwa chapter page and scroll through it once so all the images
   load.
4. Click the extension icon → **Translate this page**.
5. Each panel gets replaced with its translation. The popup shows progress
   (`Translating 3/14…`). On CPU a full page takes a few minutes — that's normal.

---

## Options you can tweak

When translating, the backend accepts (defaults in **bold**):

- **Tone** — `natural` *(default)*, `literal`, or `localized`.
- **Honorifics** — keep `-san`/`-nim`/`oppa` *(default)* or drop them.

These are wired into the API; the UI/extension use the defaults for now.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **401 / "invalid x-api-key"** | Your key in `backend\.env` is wrong or still the placeholder. Paste a real key and restart the backend. |
| **"No panel images found" (extension)** | Scroll the page first so images load. If panels are small, they may be under the 400px size cutoff. |
| **Extension does nothing / network error** | The backend isn't running, or the backend URL in the popup is wrong (should be `http://localhost:8000`). |
| **It's slow (~30s/panel)** | Normal on CPU. The progress counter means it's working, not frozen. |
| **Install errors about torch / paddle / OpenCV (Windows)** | See [`AGENTS.md`](AGENTS.md) → "Critical environment gotchas." |
| **Site watermarks get "translated"** | Known limitation — watermark text baked into scans is read like dialogue. |

---

## Want it faster?

If you have an NVIDIA GPU it's used automatically. If you don't, you can run the
backend on a **free Colab GPU** (~4x faster) — see the "Run on a free GPU" section
of the [README](README.md). It's optional; the local CPU setup is the supported
default.

---

Stuck? See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for current limitations, or
[`README.md`](README.md) for the overview.
