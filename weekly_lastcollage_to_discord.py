import os
import time
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

LASTCOLLAGE_URL = "https://lastcollage.io"


def save_debug(page, name="debug-lastcollage-page.png"):
    try:
        page.screenshot(path=name, full_page=True)
    except Exception:
        pass


def fill_username_field(page, username):
    """
    Tries multiple ways to fill the Last.fm username field and verifies that a value was entered.
    Returns True if successful, False otherwise.
    """
    candidate_selectors = [
        'input[placeholder*="Username"]',
        'input[placeholder*="username"]',
        'input[name*="user"]',
        'input[name*="username"]',
        'input[type="text"]',
        'input',
    ]

    for selector in candidate_selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=5000)

            # Method 1: standard fill
            try:
                locator.click(timeout=2000)
                locator.fill("")
                locator.fill(username)
                page.wait_for_timeout(500)
            except Exception:
                pass

            # Check if it worked
            try:
                value = locator.input_value(timeout=1000)
                if value and value.strip() == username:
                    return True
            except Exception:
                pass

            # Method 2: type like a user
            try:
                locator.click(timeout=2000)
                locator.press("Control+A")
                locator.press("Backspace")
                locator.type(username, delay=100)
                page.wait_for_timeout(500)
            except Exception:
                pass

            try:
                value = locator.input_value(timeout=1000)
                if value and value.strip() == username:
                    return True
            except Exception:
                pass

            # Method 3: JS force-set + trigger events
            try:
                page.evaluate(
                    """
                    ([selector, username]) => {
                        const el = document.querySelector(selector);
                        if (!el) return false;
                        el.focus();
                        el.value = username;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                        return true;
                    }
                    """,
                    [selector, username],
                )
                page.wait_for_timeout(700)
            except Exception:
                pass

            try:
                value = locator.input_value(timeout=1000)
                if value and value.strip() == username:
                    return True
            except Exception:
                pass

        except Exception:
            continue

    return False


def click_button_by_name(page, names, timeout=5000):
    """
    Tries to click a visible button by accessible name or text.
    Returns True if a click succeeded.
    """
    for name in names:
        try:
            page.get_by_role("button", name=name).click(timeout=timeout)
            return True
        except Exception:
            pass

        try:
            page.get_by_text(name, exact=False).click(timeout=timeout)
            return True
        except Exception:
            pass

    return False


def wait_for_username_screen(page):
    """
    Wait until the username step is visible.
    """
    candidates = [
        lambda: page.get_by_text("Enter your Last.fm username", exact=False),
        lambda: page.get_by_placeholder("Username"),
        lambda: page.locator('input[placeholder*="Username"]').first,
        lambda: page.locator('input[type="text"]').first,
    ]

    for candidate in candidates:
        try:
            loc = candidate()
            loc.wait_for(state="visible", timeout=8000)
            return True
        except Exception:
            pass

    return False


def generate_collage(username, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1800})

        page.goto(LASTCOLLAGE_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        save_debug(page, "debug-01-landing.png")

        # Close changelog / modal if present
        click_button_by_name(page, ["Done"], timeout=4000)
        page.wait_for_timeout(1000)
        save_debug(page, "debug-02-after-done.png")

        # Click landing CTA if present
        click_button_by_name(page, ["Get started"], timeout=5000)
        page.wait_for_timeout(2000)
        save_debug(page, "debug-03-after-get-started.png")

        # Wait for username screen
        if not wait_for_username_screen(page):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not reach username screen. Saved debug-lastcollage-page.png")

        # Fill username robustly
        success = fill_username_field(page, username)
        page.wait_for_timeout(1000)
        save_debug(page, "debug-04-after-username-fill.png")

        if not success:
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not fill the username field. Saved debug-lastcollage-page.png")

        # Some sites enable button only after blur / tab
        try:
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)
        except Exception:
            pass

        try:
            page.locator("body").click(position={"x": 10, "y": 10}, timeout=2000)
            page.wait_for_timeout(800)
        except Exception:
            pass

        save_debug(page, "debug-05-before-next.png")

        # Click Next
        next_clicked = click_button_by_name(page, ["Next", "Continue"], timeout=6000)

        if not next_clicked:
            # Try JS click as fallback
            try:
                page.evaluate(
                    """
                    () => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const btn = buttons.find(b => /next|continue/i.test((b.innerText || '').trim()));
                        if (btn) {
                            btn.click();
                            return true;
                        }
                        return false;
                    }
                    """
                )
                page.wait_for_timeout(1500)
                next_clicked = True
            except Exception:
                pass

        if not next_clicked:
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Next after username entry. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(2500)
        save_debug(page, "debug-06-after-next.png")

        # Try common wizard choices
        for label in ["Last 7 Days", "7 days", "Last week", "Weekly"]:
            if click_button_by_name(page, [label], timeout=2500):
                page.wait_for_timeout(1000)
                break

        save_debug(page, "debug-07-after-period.png")

        for label in ["5x5", "5 x 5"]:
            if click_button_by_name(page, [label], timeout=2500):
                page.wait_for_timeout(1000)
                break

        save_debug(page, "debug-08-after-grid.png")

        for label in ["Albums", "Album"]:
            if click_button_by_name(page, [label], timeout=2500):
                page.wait_for_timeout(1000)
                break

        save_debug(page, "debug-09-after-mode.png")

        # Try final action(s)
        clicked_final = False
        for _ in range(3):
            if click_button_by_name(page, ["Generate", "Create", "Make collage", "Next", "Continue", "Done"], timeout=4000):
                clicked_final = True
                page.wait_for_timeout(2500)
                save_debug(page, f"debug-final-step-{_ + 1}.png")
            else:
                break

        # Wait for result screen / collage to render
        page.wait_for_timeout(8000)
        save_debug(page, "debug-10-final-screen.png")

        # Save final screenshot to send to Discord
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
