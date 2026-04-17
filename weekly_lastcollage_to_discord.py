import os
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

LASTCOLLAGE_URL = "https://lastcollage.io"

def generate_collage(username, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1800})

        page.goto(LASTCOLLAGE_URL, wait_until="domcontentloaded")

        page.wait_for_timeout(3000)

        # Fill visible username field
        username_filled = False
        selectors = [
            'input[placeholder*="Last.fm"]',
            'input[placeholder*="username"]',
            'input[name*="user"]',
            'input[name*="username"]',
            'input[type="text"]'
        ]

        for selector in selectors:
            try:
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=5000)
                locator.fill(username)
                username_filled = True
                break
            except:
                pass

        if not username_filled:
            raise Exception("Could not find a visible Last.fm username input field.")

        # Try clicking Last 7 Days
        for text in ["Last 7 Days", "7 days", "Weekly"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=3000)
                break
            except:
                pass

        # Try clicking 5x5
        for text in ["5x5", "5 x 5"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=3000)
                break
            except:
                pass

        # Try albums mode
        for text in ["Albums", "Album"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=2000)
                break
            except:
                pass

        # Click Generate
        generated = False
        for text in ["Generate", "Create", "Make collage"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=5000)
                generated = True
                break
            except:
                pass

        if not generated:
            raise Exception("Could not find Generate button.")

        page.wait_for_timeout(7000)

        page.screenshot(path=str(output_path), full_page=True)
        browser.close()


def send_to_discord(webhook_url, image_path, username):
    with open(image_path, "rb") as f:
        response = requests.post(
            webhook_url,
            data={"content": f"{username}'s weekly 5x5 collage"},
            files={"file": ("collage.png", f, "image/png")},
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
