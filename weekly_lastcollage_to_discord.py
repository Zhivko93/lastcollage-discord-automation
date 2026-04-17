import os
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

LASTCOLLAGE_URL = "https://lastcollage.io"

def generate_collage(username, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1800})

        page.goto(LASTCOLLAGE_URL)

        # Fill username
        page.locator("input").first.fill(username)

        # Try clicking "Last 7 Days"
        try:
            page.get_by_text("Last 7 Days").click()
        except:
            pass

        # Try selecting 5x5
        try:
            page.get_by_text("5x5").click()
        except:
            pass

        # Click generate
        page.get_by_text("Generate").click()

        # Wait for result
        page.wait_for_timeout(5000)

        # Screenshot full page (simplest reliable fallback)
        page.screenshot(path=str(output_path), full_page=True)

        browser.close()


def send_to_discord(webhook_url, image_path, username):
    with open(image_path, "rb") as f:
        response = requests.post(
            webhook_url,
            data={"content": f"{username}'s weekly 5x5 collage"},
            files={"file": f},
        )

    if response.status_code >= 300:
        raise Exception(f"Discord error: {response.text}")


def main():
    username = os.environ["LASTFM_USERNAME"]
    webhook = os.environ["DISCORD_WEBHOOK_URL"]

    output = Path("collage.png")

    generate_collage(username, output)
    send_to_discord(webhook, output, username)


if __name__ == "__main__":
    main()
