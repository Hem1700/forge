"""Capture README screenshots via Playwright.

Run from backend venv:
    source backend/.venv/bin/activate
    python scripts/capture_screenshots.py
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

ENGAGEMENT_ID = "37ea430e-725d-449f-81ce-9707327c414c"
FINDING_ID = "68b28a23-3e08-4833-853c-f71d777de2f4"
BASE = "http://localhost:5173"


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = await ctx.new_page()

        shots = [
            ("dashboard.png",   f"{BASE}/",                                                     False),
            ("engagement.png",  f"{BASE}/engagement/{ENGAGEMENT_ID}",                           True),
            ("finding.png",     f"{BASE}/engagement/{ENGAGEMENT_ID}/findings/{FINDING_ID}",     True),
        ]

        for name, url, full in shots:
            print(f"→ {name} ← {url}")
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUT / name), full_page=full)

        await browser.close()
    print(f"\nsaved to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
