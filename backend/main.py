import logging
import threading
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import detect
import inpaint
from scraper import get_panel_image_urls
from translate import translate_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("manga-translator")


def _warm_models():
    # Load the detector + LaMa now so the first translate request isn't cold.
    try:
        detect._get_ocr()
        inpaint._get_lama()
        logger.info("Models warmed and ready")
    except Exception as exc:
        logger.warning("Model warm-up failed (will load on first request): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm in a background thread so /health responds immediately.
    threading.Thread(target=_warm_models, daemon=True).start()
    yield


app = FastAPI(title="Manga/Manhwa OCR Translator", lifespan=lifespan)

# Image CDNs frequently require a browser-like UA and a referer to serve panels.
_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


class ChapterRequest(BaseModel):
    url: str
    tone: str = "natural"
    keep_honorifics: bool = True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/translate-image")
async def translate_image_endpoint(
    file: UploadFile = File(...),
    tone: str = Form("natural"),
    keep_honorifics: bool = Form(True),
):
    image_bytes = await file.read()
    options = {"tone": tone, "keep_honorifics": keep_honorifics}
    # The pipeline (detection + LaMa + Claude) is heavy blocking work; run it off
    # the event loop so the server stays responsive.
    return await run_in_threadpool(translate_image, image_bytes, options)


@app.post("/translate-chapter")
def translate_chapter(req: ChapterRequest):
    image_urls = get_panel_image_urls(req.url)
    logger.info("Found %d candidate panels at %s", len(image_urls), req.url)

    headers = {**_DOWNLOAD_HEADERS, "Referer": req.url}
    options = {"tone": req.tone, "keep_honorifics": req.keep_honorifics}
    glossary: dict[str, str] = {}  # carried across panels for name/term consistency
    panels = []
    for url in image_urls:
        try:
            resp = httpx.get(
                url, headers=headers, timeout=30.0, follow_redirects=True
            )
            resp.raise_for_status()
            result = translate_image(resp.content, options, glossary)
            glossary = result.get("glossary", glossary)
            panels.append({"image_url": url, **result})
        except Exception as exc:
            # One bad panel shouldn't fail the whole chapter — log and move on.
            logger.warning("Skipping panel %s: %s", url, exc)
            continue

    return {"panels": panels}
