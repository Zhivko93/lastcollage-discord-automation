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
    Try clicking a button or visible text from a list of names.
    Returns True if successful.
    """
    for name in names:
        try:
            page.get_by_role("button", name=name).click(timeout=timeout)
            page.wait_for_timeout(800)
            return True
        except Exception:
            pass

        try:
            page.get_by_text(name, exact=False).click(timeout=timeout)
            page.wait_for_timeout(800)
            return True
        except Exception:
            pass

    return False


def wait_for_text(page, text, timeout=8000):
    page.get_by_text(text, exact=False).wait_for(state="visible", timeout=timeout)


def type_username_like_user(page, username):
    """
    The username field seems to behave like a custom/styled control.
    So instead of relying on DOM input APIs, type like a user.
    """
    # First attempt: the cursor often lands in the field automatically.
    try:
        page.keyboard.type(username, delay=120)
        page.wait_for_timeout(1200)
    except Exception:
        pass

    # Try Next immediately. If it works, great.
    if click_button(page, ["Next"]):
        return True

    # Second attempt: click where the username line sits, then type.
    # These coordinates are based on the debug screenshots and viewport 1600x1800.
    # The username field is roughly centered horizontally and around y=285-330.
    fallback_points = [
        (800, 300),
        (800, 320),
        (780, 305),
        (820, 305),
    ]

    for x, y in fallback_points:
        try:
            page.mouse.click(x, y)
            page.wait_for_timeout(400)

            # Clear any prior text using keyboard
            try:
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
            except Exception:
                pass

            page.keyboard.type(username, delay=120)
            page.wait_for_timeout(1200)

            if click_button(page, ["Next"]):
                return True
        except Exception:
            pass

    # Third attempt: press Tab once or twice, then type.
    for tab_count in [1, 2, 3]:
        try:
            for _ in range(tab_count):
                page.keyboard.press("Tab")
                page.wait_for_timeout(250)

            page.keyboard.type(username, delay=120)
            page.wait_for_timeout(1000)

            if click_button(page, ["Next"]):
                return True
        except Exception:
            pass

    return False


def click_grid_5x5(page):
    """
    Click the 5th square in the 5th row on the collage size grid.
    Uses the actual grid element bounds and clicks inside the 5x5 cell.
    """
    grid = page.evaluate(
        """
        () => {
            const divs = Array.from(document.querySelectorAll('div'));
            let best = null;
            let bestArea = 0;

            for (const el of divs) {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);

                if (style.display === 'none' || style.visibility === 'hidden') continue;
                if (r.width < 300 || r.height < 300) continue;
                if (r.width > window.innerWidth * 0.95) continue;
                if (r.height > window.innerHeight * 0.8) continue;

                const text = (el.innerText || '').toLowerCase();
                if (text.includes('click a square in the grid below')) continue;

                const area = r.width * r.height;
                if (area > bestArea) {
                    bestArea = area;
                    best = {
                        x: r.x,
                        y: r.y,
                        width: r.width,
                        height: r.height
                    };
                }
            }

            return best;
        }
        """
    )

    if not grid:
        raise Exception("Could not detect the collage size grid.")

    x = grid["x"]
    y = grid["y"]
    width = grid["width"]
    height = grid["height"]

    # Lastcollage grid appears 20x20. Click center of row 5, col 5.
    cell_w = width / 20.0
    cell_h = height / 20.0
    click_x = x + (4 * cell_w) + (cell_w / 2)
    click_y = y + (4 * cell_h) + (cell_h / 2)

    page.mouse.click(click_x, click_y)
    page.wait_for_timeout(1200)


def generate_collage(username, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1800})

        # 1. Open
        page.goto(LASTCOLLAGE_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)
        save_debug(page, "debug-01-landing.png")

        # 2. Close popup
        click_button(page, ["Done"])
        page.wait_for_timeout(1000)
        save_debug(page, "debug-02-after-done.png")

        # 3. Get started
        if not click_button(page, ["Get started"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Get started. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1500)
        save_debug(page, "debug-03-after-get-started.png")

        # 4. Username step
        wait_for_text(page, "Enter your Last.fm username")
        if not type_username_like_user(page, username):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not fill username / proceed with Next. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1500)
        save_debug(page, "debug-04-after-username-next.png")

        # 5. What kind of collage? -> Albums
        wait_for_text(page, "What kind of collage")
        if not click_button(page, ["Albums"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Albums. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1200)
        save_debug(page, "debug-05-after-albums.png")

        # 6. Time span -> 1 Week
        wait_for_text(page, "How long do you want this collage to span")
        if not click_button(page, ["1 Week", "1 week"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click 1 Week. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1500)
        save_debug(page, "debug-06-after-1week.png")

        # 7. Grid -> 5x5
        wait_for_text(page, "Click a square in the grid below")
        click_grid_5x5(page)
        save_debug(page, "debug-07-after-grid-click.png")

        # 8. Next
        if not click_button(page, ["Next"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Next after grid selection. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1500)
        save_debug(page, "debug-08-after-grid-next.png")

        # 9. Overlay names? -> Yes
        wait_for_text(page, "overlay the album and artist name")
        if not click_button(page, ["Yes"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Yes for overlay. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1200)
        save_debug(page, "debug-09-after-overlay-yes.png")

        # 10. Hide missing artwork? -> No
        wait_for_text(page, "hide albums with missing artwork")
        if not click_button(page, ["No"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click No for missing artwork. Saved debug-lastcollage-page.png")

        page.wait_for_timeout(1200)
        save_debug(page, "debug-10-after-missing-artwork-no.png")

        # 11. Generate
        wait_for_text(page, "generate your collage")
        if not click_button(page, ["Generate"]):
            save_debug(page, "debug-lastcollage-page.png")
            raise Exception("Could not click Generate. Saved debug-lastcollage-page.png")

        # 12. Wait for collage
        page.wait_for_timeout(10000)
        save_debug(page, "debug-11-final-result.png")

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
