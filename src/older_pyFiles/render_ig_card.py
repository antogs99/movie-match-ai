"""
testing ig post generator
"""

import asyncio
from playwright.async_api import async_playwright
import os

OUTPUT_PATH = "data/output/generated_card.png"
TEMPLATE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/templates/ig_card_template.html"))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 768, "height": 1152})
        await page.goto(f"file://{TEMPLATE_PATH}")
        await page.wait_for_timeout(1000)  # wait for images to load
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        print(f"Saving to: {os.path.abspath(OUTPUT_PATH)}")
        print(await page.content())
        await page.screenshot(path=OUTPUT_PATH)
        await browser.close()
        print(f"[✓] IG card saved: {OUTPUT_PATH}")

if __name__ == "__main__":
    asyncio.run(main())