"""Capture README screenshots via Playwright.

Run from backend venv:
    source backend/.venv/bin/activate
    python scripts/capture_screenshots.py
"""
import asyncio
from pathlib import Path

from playwright.async_api import Page, async_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

ENGAGEMENT_ID = "37ea430e-725d-449f-81ce-9707327c414c"
FINDING_ID = "68b28a23-3e08-4833-853c-f71d777de2f4"
BASE = "http://localhost:5173"


async def shot(page: Page, name: str, url: str, *, full: bool = False, wait_ms: int = 1500, selector: str | None = None) -> None:
    print(f"→ {name}")
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(wait_ms)
    if selector:
        el = page.locator(selector)
        await el.screenshot(path=str(OUT / name))
    else:
        await page.screenshot(path=str(OUT / name), full_page=full)


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
        page = await ctx.new_page()

        # Dashboard (viewport)
        await shot(page, "dashboard.png", f"{BASE}/")

        # Engagement — three framings
        eng_url = f"{BASE}/engagement/{ENGAGEMENT_ID}"
        # 1. Above-the-fold: header + live console
        await shot(page, "engagement-console.png", eng_url)
        # 2. Full page: console + status + findings + report
        await shot(page, "engagement-full.png", eng_url, full=True)
        # 3. Findings table + report summary (scroll and clip viewport)
        await page.goto(eng_url, wait_until="networkidle")
        await page.wait_for_timeout(1500)
        await page.evaluate("window.scrollTo(0, 700)")
        await page.wait_for_timeout(400)
        await page.screenshot(path=str(OUT / "engagement-findings.png"))

        # Finding detail — full page
        await shot(page, "finding.png", f"{BASE}/engagement/{ENGAGEMENT_ID}/findings/{FINDING_ID}", full=True)

        await browser.close()
    print(f"\nsaved to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
