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
        except Exception:
            pass
    return None


def generate_collage(username, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1800})

        page.goto(LASTCOLLAGE_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        # Close changelog popup
        try:
            page.get_by_role("button", name="Done").click(timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass

        # Click landing page button
        try:
            page.get_by_role("button", name="Get started").click(timeout=5000)
            page.wait_for_timeout(2000)
        except Exception:
            pass

        # Dismiss common consent popups if present
        for text in ["Accept", "Accept all", "I agree", "Got it", "OK"]:
            try:
                page.get_by_role("button", name=text).click(timeout=2000)
                page.wait_for_timeout(1000)
                break
            except Exception:
                pass

        username_locator = first_visible(
            page,
            [
                'input[placeholder*="Last.fm"]',
                'input[placeholder*="last.fm"]',
                'input[placeholder*="username"]',
                'input[placeholder*="Username"]',
                'input[name*="user"]',
                'input[name*="username"]',
                'input[type="search"]',
                'input[type="text"]',
            ],
            timeout=5000,
        )

        if not username_locator:
            page.screenshot(path="debug-lastcollage-page.png", full_page=True)
            raise Exception(
                "Could not find a visible Last.fm username input field. Saved debug-lastcollage-page.png"
            )

        username_locator.click()
        username_locator.fill(username)
        page.wait_for_timeout(1000)

        # Step 1 -> next
        next_clicked = False
        for text in ["Next", "Continue"]:
            try:
                page.get_by_role("button", name=text).click(timeout=5000)
                next_clicked = True
                page.wait_for_timeout(2500)
                break
            except Exception:
                pass

        if not next_clicked:
            page.screenshot(path="debug-lastcollage-page.png", full_page=True)
            raise Exception(
                "Could not find Next button after username entry. Saved debug-lastcollage-page.png"
            )

        # Try common option selections on following screens
        for text in ["Last 7 Days", "7 days", "Weekly", "Last week"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=3000)
                page.wait_for_timeout(800)
                break
            except Exception:
                pass

        for text in ["5x5", "5 x 5"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=3000)
                page.wait_for_timeout(800)
                break
            except Exception:
                pass

        for text in ["Albums", "Album"]:
            try:
                page.get_by_text(text, exact=False).click(timeout=3000)
                page.wait_for_timeout(800)
                break
            except Exception:
                pass

        # Try action buttons on later steps
        for text in ["Generate", "Create", "Make collage", "Next", "Continue", "Done"]:
            try:
                page.get_by_role("button", name=text).click(timeout=4000)
                page.wait_for_timeout(4000)
                break
            except Exception:
                try:
                    page.get_by_text(text, exact=False).click(timeout=4000)
                    page.wait_for_timeout(4000)
                    break
                except Exception:
                    pass

        page.wait_for_timeout(4000)
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
