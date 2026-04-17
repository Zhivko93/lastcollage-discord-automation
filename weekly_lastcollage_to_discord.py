import os
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

LASTCOLLAGE_URL = "https://lastcollage.io"


def first_visible(page, selectors, timeout=4000):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout)
            return locator
        except:
            pass
    return None


def generate_collage(username, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1800})


        page.goto(LASTCOLLAGE_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        # Close popup (IMPORTANT)
try:
    page.get_by_role("button", name="Done").click(timeout=5000)
    page.wait_for_timeout(1000)
except:
    pass

# Click "Get started"
try:
    page.get_by_role("button", name="Get started").click(timeout=5000)
    page.wait_for_timeout(2000)
except:
    pass

        # Dismiss common cookie / consent popups
        for text in ["Accept", "Accept all", "I agree", "Got it", "OK"]:
            try:
                page.get_by_role("button", name=text).click(timeout=2000)
                page.wait_for_timeout(1000)
                break
            except:
                pass

        # Look for a visible username field
        username_locator = first_visible(page, [
            'input[placeholder*="Last.fm"]',
            'input[placeholder*="last.fm"]',
            'input[placeholder*="username"]',
            'input[placeholder*="Username"]',
            'input[name*="user"]',
            'input[name*="username"]',
            'input[type="search"]',
            'input[type="text"]'
        ], timeout=5000)

        if not username_locator:
            page.screenshot(path="debug-lastcollage-page.png", full_page=True)
            raise Exception("Could not find a visible Last.fm username input field. Saved debug-lastcollage-page.png")

        username_locator.click()
        username_locator.fill(username)
        page.wait_for_timeout(1000)

        # Try to pick time period
        for text in ["Last 7 Days", "7 days", "Last week", "Weekly"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=3000)
                page.wait_for_timeout(500)
                break
            except:
                pass

        # Try to pick 5x5
        for text in ["5x5", "5 x 5"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=3000)
                page.wait_for_timeout(500)
                break
            except:
                pass

        # Try to pick albums mode
        for text in ["Albums", "Album"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=3000)
                page.wait_for_timeout(500)
                break
            except:
                pass

        # Generate
        generated = False
        for text in ["Generate", "Create", "Make collage"]:
            try:
                page.get_by_role("button", name=text).click(timeout=3000)
                generated = True
                break
            except:
                try:
                    page.get_by_text(text, exact=False).click(timeout=3000)
                    generated = True
                    break
                except:
                    pass

        if not generated:
            page.screenshot(path="debug-lastcollage-page.png", full_page=True)
            raise Exception("Could not find Generate button. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(8000)

        page.screenshot(path=str(output_path), full_page=True)
        browser.close()


def send_to_discord(webhook_url, image_path, username):
    with open(image_path, "rb") as f:
        response = requests.post(
            webhook_url,
            data={"content": f"{username}'s weekly 5x5 collage"},
            files={"file": ("collage.png", f, "image/png")},
            timeout=60,
        )

    if response.status_code >= 300:
        raise Exception(f"Discord error: {response.status_code} - {response.text}")


def main():
    username = os.environ["LASTFM_USERNAME"]
    webhook = os.environ["DISCORD_WEBHOOK_URL"]

    output = Path("collage.png")

    generate_collage(username, output)
    send_to_discord(webhook, output, username)


if __name__ == "__main__":
    main()
