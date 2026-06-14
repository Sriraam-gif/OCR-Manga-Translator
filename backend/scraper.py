from playwright.sync_api import sync_playwright


def get_panel_image_urls(
    chapter_url: str, min_width: int = 400, min_height: int = 400
) -> list[str]:
    """Load a manga/manhwa chapter page and return panel image URLs in page order.

    Heuristic: any <img> whose rendered natural size is at least min_width x
    min_height is treated as a panel. Lazy-loaded images are triggered by
    scrolling to the bottom before reading.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1600})
        page.goto(chapter_url, wait_until="domcontentloaded", timeout=60000)
        _scroll_to_bottom(page)

        # currentSrc resolves srcset/lazy attributes; src is already absolute.
        images = page.eval_on_selector_all(
            "img",
            """els => els.map(e => ({
                src: e.currentSrc || e.src,
                w: e.naturalWidth,
                h: e.naturalHeight
            }))""",
        )
        browser.close()

    urls = []
    seen = set()
    for img in images:
        src = img["src"]
        if not src or src in seen:
            continue
        if img["w"] >= min_width and img["h"] >= min_height:
            urls.append(src)
            seen.add(src)
    return urls


def _scroll_to_bottom(page, step: int = 1200, max_steps: int = 40) -> None:
    """Scroll down in increments so lazy-loaded panel images start fetching."""
    last = -1
    for _ in range(max_steps):
        page.mouse.wheel(0, step)
        page.wait_for_timeout(300)
        height = page.evaluate("document.body.scrollHeight")
        if height == last:
            break
        last = height
    # Give the last batch of images a moment to finish loading.
    page.wait_for_timeout(1000)
