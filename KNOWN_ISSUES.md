# Known Issues

Failure patterns and limitations of the manga/manhwa OCR translator. Some are
inherent to the current design; the per-site ones should be filled in as you
test against real chapter URLs (Step 5).

## Setup / configuration

- **A real Anthropic API key is required.** `backend/.env` ships with a
  placeholder (`ANTHROPIC_API_KEY=your_key_here`). Translation calls fail with a
  401 until you replace it with a real key. The `.env` file is gitignored.

## Scraping (`scraper.py`)

- **Anti-bot protection blocks Playwright on some sites.** Sites behind
  Cloudflare or with bot detection may serve a challenge page instead of panels,
  returning zero images. We don't try to defeat anti-scraping — **use the Chrome
  extension instead**, which reads panels from the tab you've already opened (so
  you've already passed Cloudflare/login). See [`extension/`](extension/).
- **Panel detection is a size heuristic.** Any `<img>` rendered at least
  400×400px is treated as a panel. This can miss small panels and can include
  large ads, banners, or cover art. Tune `min_width` / `min_height` in
  `get_panel_image_urls` per site if needed.
- **Lazy-loading timing.** The scraper scrolls to the bottom to trigger
  lazy-loaded images, but very long chapters or slow image hosts may not finish
  loading within the scroll window, dropping late panels.

## Image download (`main.py`)

- **Some CDNs require referer/cookies we don't send.** Downloads use a
  browser-like User-Agent and the chapter URL as Referer, but hosts that gate on
  cookies or hotlink tokens may return 403. Those panels are skipped (logged),
  not fatal.

## Pipeline (`detect.py` / `translate.py` / `inpaint.py` / `render.py`)

- **CPU-bound, ~30s per panel.** There's no GPU; detection, LaMa inpainting, and
  the Claude call all run per panel. A long chapter is processed sequentially, so
  it's slow (minutes). The **first** request after startup is slower still — it
  loads PaddleOCR + LaMa and downloads `big-lama.pt` (~196MB) once.
- **Heavy dependencies / fragile install.** The stack needs PyTorch (CPU) +
  PaddlePaddle + LaMa. On Windows this requires specific handling: import torch
  before paddle, pin `paddlepaddle==2.6.2` with mkldnn disabled, and keep a single
  OpenCV install. See [`AGENTS.md`](AGENTS.md) → "Critical environment gotchas".
- **Sound effects drawn into the art are not translated.** Stylized onomatopoeia
  baked into the artwork (outside speech bubbles) is intentionally left alone —
  the detector may not box it, and inpainting it would damage the art.
- **Site watermarks get treated as dialogue.** Scanlation/site watermark text
  baked into the image (e.g. `MANGA18.CLUB`, "Read Manga Online…") is detected and
  translated like a real bubble. No filter for this yet.
- **Untranslated boxes are left as-is (not blanked).** Earlier, any detected box
  was erased even when the translation came back empty, leaving blank white
  rectangles. Now only boxes with a real translation are erased + typeset; empties
  keep the original art. The trade-off: a genuinely-missed line stays in its
  original language rather than being wiped.
- **Detection quality drives everything.** If DBNet misses a bubble, it won't be
  translated or cleaned; if a box is loose, the inpaint mask is larger than
  needed. Tall strips are tiled so detection runs near native resolution
  (`detect.py`), which is what makes recall on long manhwa strips reliable.
- **Inpaint is OpenCV-grade LaMa on flat bubbles.** Clean on typical white/solid
  bubbles; busy or textured backgrounds under text are reconstructed less
  perfectly than a GPU-scale model would manage.

## Per-site findings (fill in during testing)

- **manga18.club** — Cloudflare bot challenge. Headless Playwright gets the
  "Attention Required! | Cloudflare" page instead of the chapter; 0 panels
  detected. Anti-bot — skip (per spec, not worth defeating).

<!-- Add more as you test:
- example-site.com: works; ~30 panels detected, translation good.
-->
