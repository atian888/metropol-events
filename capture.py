import asyncio
from playwright.async_api import async_playwright
from PIL import Image
import io
import os

async def capture_events():
      async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(viewport={'width': 1400, 'height': 900})

        await page.goto('https://metropol.vartoslo.no/events', wait_until='networkidle')
        await page.wait_for_timeout(3000)

        screenshot_bytes = await page.screenshot(type='png')
        await browser.close()

        img = Image.open(io.BytesIO(screenshot_bytes))

        # Crop to top cards area (adjust if needed later)
        crop_box = (0, 150, 1400, 750)
        img_cropped = img.crop(crop_box)

        # Save as compressed JPG
        output_path = 'events.jpg'
        quality = 70
        img_cropped.save(output_path, 'JPEG', quality=quality, optimize=True)

        # Reduce quality if over 100kb
        while os.path.getsize(output_path) > 100_000 and quality > 30:
                      quality = int(quality * 0.9)
                      img_cropped.save(output_path, 'JPEG', quality=quality, optimize=True)

        file_size = os.path.getsize(output_path) / 1024
        print(f"Saved {output_path} ({file_size:.1f} KB)")

if __name__ == '__main__':
      asyncio.run(capture_events())
