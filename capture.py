import asyncio
import io
import os
from typing import Optional, Tuple

from PIL import Image
from playwright.async_api import async_playwright

URL = "https://metropol.vartoslo.no/events"
OUTPUT_PATH = "events.jpg"
MAX_BYTES = 100_000
VIEWPORT = {
    "width": int(os.getenv("VIEWPORT_WIDTH", "1300")),
    "height": int(os.getenv("VIEWPORT_HEIGHT", "900")),
}
CARDS_TO_CAPTURE = int(os.getenv("CARDS_TO_CAPTURE", "2"))
SCROLL_OFFSET = 800
LEFT_TRIM = int(os.getenv("LEFT_TRIM", "0"))

# Default crop box (left, top, right, bottom). Used as fallback.
DEFAULT_CROP_BOX = (
    0,
    0,
    700,
    900
)

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
            await dismiss_cookie_banner(page)
            await scroll_to_today_section(page, SCROLL_OFFSET)

            crop_box = await get_cards_crop_box(page, CARD_SELECTOR, CARDS_TO_CAPTURE)
            if crop_box is None or not is_reasonable_crop(crop_box):
                crop_box = DEFAULT_CROP_BOX

            screenshot_bytes = await page.screenshot(type="png")
        finally:
            await browser.close()

    img = Image.open(io.BytesIO(screenshot_bytes))
    crop_box = normalize_crop_box(crop_box, img.width, img.height)
    if not is_reasonable_crop(crop_box):
        crop_box = normalize_crop_box(DEFAULT_CROP_BOX, img.width, img.height)
    img_cropped = img.crop(crop_box).convert("RGB")

    save_jpeg_under_size(img_cropped, OUTPUT_PATH, MAX_BYTES)

    file_size = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"Saved {OUTPUT_PATH} ({file_size:.1f} KB)")


async def get_cards_crop_box(
    page, card_selector: Optional[str], count: int
) -> Optional[Tuple[int, int, int, int]]:
    if not card_selector:
        return None

    locator = page.locator(card_selector)
    try:
        await locator.first.wait_for(state="visible", timeout=5000)
    except Exception:
        return None

    boxes = []
    for idx in range(max(1, count)):
        box = await locator.nth(idx).bounding_box()
        if box:
            boxes.append(box)

    if len(boxes) < max(1, count):
        return None

    left = min(b["x"] for b in boxes)
    top = min(b["y"] for b in boxes)
    right = max(b["x"] + b["width"] for b in boxes)
    bottom = max(b["y"] + b["height"] for b in boxes)

    return (int(left), int(top), int(right), int(bottom))


def normalize_crop_box(
    crop_box: Tuple[int, int, int, int], image_width: int, image_height: int
) -> Tuple[int, int, int, int]:
    left, top, right, bottom = crop_box
    left = max(0, min(left, image_width - 1))
    top = max(0, min(top, image_height - 1))
    right = max(left + 1, min(right, image_width))
    bottom = max(top + 1, min(bottom, image_height))

    if bottom <= top or right <= left:
        return DEFAULT_CROP_BOX

    return (left, top, right, bottom)


def is_reasonable_crop(crop_box: Tuple[int, int, int, int]) -> bool:
    left, top, right, bottom = crop_box
    return (right - left) >= 200 and (bottom - top) >= 200


async def scroll_to_today_section(page, offset: int) -> None:
    try:
        heading = page.get_by_text("I Dag", exact=True).first
        await heading.wait_for(state="visible", timeout=5000)
        box = await heading.bounding_box()
        if box:
            target_y = max(0, int(box["y"]) + offset)
            await page.evaluate("window.scrollTo(0, arguments[0])", target_y)
            await page.wait_for_timeout(800)
            return

        if offset:
            await page.evaluate("window.scrollBy(0, arguments[0])", offset)
            await page.wait_for_timeout(800)
    except Exception:
        return


async def dismiss_cookie_banner(page) -> None:
    # Best-effort dismissal of common cookie popups.
    selectors = [
        'button:has-text("Godta")',
        'button:has-text("Aksepter")',
        'button:has-text("Tillat")',
        'button:has-text("Accept")',
        'button:has-text("Allow")',
        'button:has-text("OK")',
        '[aria-label*="cookie" i] button',
        '[class*="cookie" i] button',
        '[id*="cookie" i] button',
    ]

    for selector in selectors:
        try:
            button = page.locator(selector).first
            if await button.is_visible():
                await button.click()
                await page.wait_for_timeout(500)
                return
        except Exception:
            continue


def save_jpeg_under_size(image: Image.Image, output_path: str, max_bytes: int) -> None:
    quality = 70
    min_quality = 30

    while True:
        image.save(output_path, "JPEG", quality=quality, optimize=True)
        if os.path.getsize(output_path) <= max_bytes:
            return

        if quality > min_quality:
            quality = max(min_quality, int(quality * 0.9))
            continue
        return

if __name__ == "__main__":
    asyncio.run(capture_events())
