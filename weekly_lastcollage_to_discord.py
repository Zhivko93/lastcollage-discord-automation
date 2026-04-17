import os
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

LASTCOLLAGE_URL = "https://lastcollage.io"


def save_debug(page, filename):
    try:
        page.screenshot(path=filename, full_page=True)
    except Exception:
        pass


def click_button(page, names, timeout=6000):
    """
    Try clicking a button/text from a list of possible names.
    Returns True if successful.
    """
    for name in names:
        try:
            page.get_by_role("button", name=name).click(timeout=timeout)
            page.wait_for_timeout(1000)
            return True
        except Exception:
            pass

        try:
            page.get_by_text(name, exact=False).click(timeout=timeout)
            page.wait_for_timeout(1000)
            return True
        except Exception:
            pass

    return False


def fill_username(page, username):
    """
    Fill the username field robustly and confirm the value was entered.
    """
    selectors = [
        'input[placeholder*="Username"]',
        'input[placeholder*="username"]',
        'input[name*="user"]',
        'input[name*="username"]',
        'input[type="text"]',
        'input',
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=6000)

            # Try standard fill
            try:
                locator.click(timeout=2000)
                locator.fill("")
                locator.fill(username)
                page.wait_for_timeout(500)
            except Exception:
                pass

            try:
                value = locator.input_value(timeout=1000)
                if value and value.strip().lower() == username.lower():
                    return True
            except Exception:
                pass

            # Try typing like a user
            try:
                locator.click(timeout=2000)
                locator.press("Control+A")
                locator.press("Backspace")
                locator.type(username, delay=80)
                page.wait_for_timeout(700)
            except Exception:
                pass

            try:
                value = locator.input_value(timeout=1000)
                if value and value.strip().lower() == username.lower():
                    return True
            except Exception:
                pass

            # Try JS force-set
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
                if value and value.strip().lower() == username.lower():
                    return True
            except Exception:
                pass

        except Exception:
            continue

    return False


def click_grid_5x5(page):
    """
    On the grid selection screen, click the 5th column / 5th row square.
    Uses a DOM heuristic to find the large square grid.
    """
    handle = page.evaluate(
        """
        () => {
            const els = Array.from(document.querySelectorAll('div'));
            let best = null;
            let bestScore = -1;

            for (const el of els) {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);

                if (r.width < 250 || r.height < 250) continue;
                if (r.width > window.innerWidth * 0.95) continue;
                if (r.height > window.innerHeight * 0.95) continue;
                if (style.display === 'none' || style.visibility === 'hidden') continue;

                const ratio = r.width / r.height;
                if (ratio < 0.7 || ratio > 1.4) continue;

                const childCount = el.querySelectorAll('div').length;
                const score = childCount + (r.width * r.height / 10000);

                if (score > bestScore) {
                    best = {
                        x: r.x,
                        y: r.y,
                        width: r.width,
                        height: r.height,
                        childCount
                    };
                    bestScore = score;
                }
            }

            return best;
        }
        """
    )

    if not handle:
        raise Exception("Could not detect the collage size grid.")

    x = handle["x"]
    y = handle["y"]
    width = handle["width"]
    height = handle["height"]

    # The grid appears to be 20x20. Click the center of the 5th cell, 5th row.
    click_x = x + width * 0.225
    click_y = y + height * 0.225

    page.mouse.click(click_x, click_y)
    page.wait_for_timeout(1200)


def wait_for_text(page, text, timeout=8000):
    page.get_by_text(text, exact=False).wait_for(state="visible", timeout=timeout)


def generate_collage(username, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1800})

        # Step 1: Open site
        page.goto(LASTCOLLAGE_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)
        save_debug(page, "debug-01-landing.png")

        # Step 2: Close popup
        click_button(page, ["Done"])
        page.wait_for_timeout(1000)
        save_debug(page, "debug-02-after-done.png")

        # Step 3: Get started
        if not click_button(page, ["Get started"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Get started. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1500)
        save_debug(page, "debug-03-after-get-started.png")

        # Step 4: Username screen
        wait_for_text(page, "Enter your Last.fm username")
        if not fill_username(page, username):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not fill the username field. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1000)
        save_debug(page, "debug-04-after-username-fill.png")

        # Step 5: Next
        if not click_button(page, ["Next", "Continue"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Next after username entry. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(2000)
        save_debug(page, "debug-05-after-next.png")

        # Step 6: What kind of collage? -> Albums
        wait_for_text(page, "What kind of collage")
        if not click_button(page, ["Albums"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Albums. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1500)
        save_debug(page, "debug-06-after-albums.png")

        # Step 7: 1 Week
        wait_for_text(page, "How long do you want this collage to span")
        if not click_button(page, ["1 Week", "1 week"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click 1 Week. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(2000)
        save_debug(page, "debug-07-after-1week.png")

        # Step 8: Grid screen -> click 5x5
        wait_for_text(page, "Click a square in the grid below")
        click_grid_5x5(page)
        save_debug(page, "debug-08-after-grid-click.png")

        # Step 9: Next
        if not click_button(page, ["Next", "Continue"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Next after grid selection. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(2000)
        save_debug(page, "debug-09-after-grid-next.png")

        # Step 10: Overlay names? -> Yes
        wait_for_text(page, "overlay the album and artist name")
        if not click_button(page, ["Yes"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Yes for overlay. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1500)
        save_debug(page, "debug-10-after-overlay-yes.png")

        # Step 11: Hide missing artwork? -> No
        wait_for_text(page, "hide albums with missing artwork")
        if not click_button(page, ["No"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click No for missing artwork. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1500)
        save_debug(page, "debug-11-after-missing-artwork-no.png")

        # Step 12: Generate
        wait_for_text(page, "generate your collage")
        if not click_button(page, ["Generate"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Generate. Saved debug-lastcollage-page.png")

        # Step 13: Wait for collage result
        page.wait_for_timeout(10000)
        save_debug(page, "debug-12-final-result.png")

        # Final screenshot to send to Discord
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
    username = os.environ["LASTFM_USERNAME"].strip().lower()
    webhook = os.environ["DISCORD_WEBHOOK_URL"].strip()
    output = Path("collage.png")

    generate_collage(username, output)
    send_to_discord(webhook, output, username)


if __name__ == "__main__":
    main()
