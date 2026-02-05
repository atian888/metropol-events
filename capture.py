import asyncio
import io
import os
from typing import Optional, Tuple

from PIL import Image
from playwright.async_api import async_playwright

URL = "https://metropol.vartoslo.no/events"
OUTPUT_PATH = "events.jpg"
MAX_BYTES = 100_000
VIEWPORT = {"width": 1400, "height": 900}

# Default crop box (left, top, right, bottom). Used as fallback.
DEFAULT_CROP_BOX = (0, 150, 1400, 750)

# Provide a selector for the event cards via env if you can inspect it.
# Example: CARD_SELECTOR="a.card" or ".event-card"
# Default uses a stable data-testid prefix seen on event cards.
CARD_SELECTOR = os.getenv(
    "CARD_SELECTOR",
    'div.infinite-scroll-component a[role="link"][data-testid^="event-poster-"]',
)

async def capture_events():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport=VIEWPORT)

        try:
            await page.goto(URL, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            crop_box = await get_cards_crop_box(page, CARD_SELECTOR)
            if crop_box is None:
                crop_box = DEFAULT_CROP_BOX

            screenshot_bytes = await page.screenshot(type="png")
        finally:
            await browser.close()

    img = Image.open(io.BytesIO(screenshot_bytes))
    img_cropped = img.crop(crop_box).convert("RGB")

    save_jpeg_under_size(img_cropped, OUTPUT_PATH, MAX_BYTES)

    file_size = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"Saved {OUTPUT_PATH} ({file_size:.1f} KB)")


async def get_cards_crop_box(page, card_selector: Optional[str]) -> Optional[Tuple[int, int, int, int]]:
    if not card_selector:
        return None

    locator = page.locator(card_selector)
    try:
        await locator.first.wait_for(state="visible", timeout=5000)
    except Exception:
        return None

    boxes = []
    for idx in range(4):
        box = await locator.nth(idx).bounding_box()
        if box:
            boxes.append(box)

    if len(boxes) < 4:
        return None

    left = min(b["x"] for b in boxes)
    top = min(b["y"] for b in boxes)
    right = max(b["x"] + b["width"] for b in boxes)
    bottom = max(b["y"] + b["height"] for b in boxes)

    return (int(left), int(top), int(right), int(bottom))


def save_jpeg_under_size(image: Image.Image, output_path: str, max_bytes: int) -> None:
    quality = 70
    min_quality = 30
    scale = 1.0

    while True:
        resized = image
        if scale < 1.0:
            new_w = max(1, int(image.width * scale))
            new_h = max(1, int(image.height * scale))
            resized = image.resize((new_w, new_h), Image.LANCZOS)

        resized.save(output_path, "JPEG", quality=quality, optimize=True)
        if os.path.getsize(output_path) <= max_bytes:
            return

        if quality > min_quality:
            quality = max(min_quality, int(quality * 0.9))
            continue

        scale = scale * 0.9
        if scale < 0.2:
            return

if __name__ == "__main__":
    asyncio.run(capture_events())
