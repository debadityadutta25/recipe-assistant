import asyncio
import os
import shutil
from playwright.async_api import async_playwright

FRONTEND_URL = "https://recipe-assistant-frontend-671099702193.us-east1.run.app"
ARTIFACT_DIR = "/config/.gemini/antigravity/brain/e207a180-80b9-4291-ae85-c9e9700c55ec"
TMP_VIDEO_DIR = "/config/.gemini/antigravity/scratch/recipe-assistant/scratch/videos"

os.makedirs(TMP_VIDEO_DIR, exist_ok=True)
os.makedirs(ARTIFACT_DIR, exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=TMP_VIDEO_DIR,
            record_video_size={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        print("1. Navigating to frontend...")
        await page.goto(FRONTEND_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        print("2. Clicking example prompt '🍝 Italian <30m'...")
        prompt_btn = page.locator("button:has-text('Italian')")
        if await prompt_btn.count() > 0:
            await prompt_btn.click()
        else:
            await page.fill("#input", "Find Italian recipes under 30 mins")
            await page.press("#input", "Enter")

        # Wait for agent response
        await page.wait_for_timeout(10000)

        print("3. Sending second rich prompt...")
        await page.fill("#input", "Generate a photo of Gluten-Free Penne Arrabbiata and find nearby supermarkets in San Francisco")
        await page.press("#input", "Enter")

        # Wait for rich tool execution response (image generation & places lookup)
        await page.wait_for_timeout(15000)

        print("4. Final pause to show output cards...")
        await page.wait_for_timeout(4000)

        video_path = await page.video.path()
        print(f"Recorded video path: {video_path}")
        await context.close()
        await browser.close()

        dest_file = os.path.join(ARTIFACT_DIR, "demo_recording.webm")
        shutil.copy(video_path, dest_file)
        print(f"Successfully copied demo video to artifact directory: {dest_file}")

if __name__ == "__main__":
    asyncio.run(main())
