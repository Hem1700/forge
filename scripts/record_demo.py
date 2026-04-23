"""Record a 45-second demo video via Playwright.

Tours the already-completed engagement (37ea430e) and a finding with all
features populated (exploit intelligence, PoC, live execution). No new
engagement is launched — that would take minutes.

Run from backend venv:
    source backend/.venv/bin/activate
    python scripts/record_demo.py

Output: docs/video/forge-demo.webm  (convert with ffmpeg if you need mp4)
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from playwright.async_api import Page, async_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "video"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENGAGEMENT_ID = "37ea430e-725d-449f-81ce-9707327c414c"
FINDING_ID = "68b28a23-3e08-4833-853c-f71d777de2f4"
BASE = "http://localhost:5173"

# Scene timings (ms). Roughly sum to ~45s.
DASHBOARD_DWELL = 3_500
ENGAGEMENT_HEADER_DWELL = 2_500
CONSOLE_SCROLL_DWELL = 3_500
FINDINGS_SCROLL_DWELL = 3_000
REPORT_DWELL = 2_500
FINDING_HEADER_DWELL = 2_500
EXPLOIT_DWELL = 4_000
POC_DWELL = 4_000
LIVE_EXPLOIT_DWELL = 5_000
FINAL_DWELL = 2_000


async def smooth_scroll_to(page: Page, y: int, duration_ms: int = 1200) -> None:
    """JS-driven smooth scroll so the video looks intentional, not jumpy."""
    await page.evaluate(
        """async ({target, duration}) => {
            const start = window.scrollY;
            const delta = target - start;
            const steps = 30;
            const stepMs = duration / steps;
            for (let i = 1; i <= steps; i++) {
                const t = i / steps;
                const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
                window.scrollTo(0, start + delta * eased);
                await new Promise(r => setTimeout(r, stepMs));
            }
        }""",
        {"target": y, "duration": duration_ms},
    )


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": 1600, "height": 1000},
            record_video_dir=str(OUT_DIR),
            record_video_size={"width": 1600, "height": 1000},
        )
        page = await ctx.new_page()

        # ─── Scene 1: Dashboard ────────────────────────────────
        await page.goto(f"{BASE}/", wait_until="networkidle")
        await page.wait_for_timeout(DASHBOARD_DWELL)

        # ─── Scene 2: Engagement page — header + console ──────
        await page.goto(f"{BASE}/engagement/{ENGAGEMENT_ID}", wait_until="networkidle")
        await page.wait_for_timeout(ENGAGEMENT_HEADER_DWELL)

        # Scroll through the live console / findings / report
        await smooth_scroll_to(page, 400, 1500)
        await page.wait_for_timeout(CONSOLE_SCROLL_DWELL)

        await smooth_scroll_to(page, 900, 1500)
        await page.wait_for_timeout(FINDINGS_SCROLL_DWELL)

        await smooth_scroll_to(page, 1600, 1500)
        await page.wait_for_timeout(REPORT_DWELL)

        # ─── Scene 3: Finding detail ──────────────────────────
        await page.goto(
            f"{BASE}/engagement/{ENGAGEMENT_ID}/findings/{FINDING_ID}",
            wait_until="networkidle",
        )
        await page.wait_for_timeout(FINDING_HEADER_DWELL)

        # Exploit intelligence + attack path
        await smooth_scroll_to(page, 600, 1500)
        await page.wait_for_timeout(EXPLOIT_DWELL)

        # PoC script + sequence diagram
        await smooth_scroll_to(page, 1700, 1800)
        await page.wait_for_timeout(POC_DWELL)

        # Live exploitation + verdict
        await smooth_scroll_to(page, 2800, 1800)
        await page.wait_for_timeout(LIVE_EXPLOIT_DWELL)

        await page.wait_for_timeout(FINAL_DWELL)

        # Close to flush the video file
        await page.close()
        video_path = await page.video.path() if page.video else None
        await ctx.close()
        await browser.close()

    # Rename to a predictable filename
    if video_path:
        final = OUT_DIR / "forge-demo.webm"
        shutil.move(video_path, final)
        print(f"saved: {final}  ({final.stat().st_size // 1024} KB)")
    else:
        print("no video recorded")


if __name__ == "__main__":
    asyncio.run(main())
