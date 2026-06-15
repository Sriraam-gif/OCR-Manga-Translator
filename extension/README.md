# Manga OCR Translator — Chrome extension

A "Translate this page" button that finds the manga/manhwa panels on whatever
page you're reading and replaces them with translated versions — using **your
own local backend**. Because it reads images from the tab you're already viewing,
it works on sites the scraper can't reach (e.g. behind Cloudflare).

## Setup

1. **Run the backend** (see the repo [README](../README.md)):
   ```bash
   cd backend
   PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m uvicorn main:app --port 8000
   ```
2. **Load the extension** in Chrome:
   - Go to `chrome://extensions`
   - Turn on **Developer mode** (top right)
   - Click **Load unpacked** and select this `extension/` folder

## Use

1. Open a manga/manhwa chapter page.
2. Click the extension icon → **Translate this page**.
3. Each panel (~400px+) is sent to your backend and swapped for the translation.
   On CPU expect ~30s per panel; the popup shows progress.

The backend URL defaults to `http://localhost:8000` — change it in the popup if
you're running the backend elsewhere (e.g. a Colab GPU tunnel URL).

## How it works

The popup tags the large `<img>`s on the page, fetches each image's bytes
(the extension's host permissions bypass the page's CORS), POSTs them to
`/translate-image`, and replaces the panel `src` with the returned image. No
scraping, no hosting — just your local pipeline applied to the page you're on.
