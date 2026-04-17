import io
import os
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
GRID_SIZE = 5
CELL_SIZE = 300
PADDING = 0
OUTPUT_WIDTH = GRID_SIZE * CELL_SIZE + (GRID_SIZE - 1) * PADDING
OUTPUT_HEIGHT = GRID_SIZE * CELL_SIZE + (GRID_SIZE - 1) * PADDING


def get_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def lastfm_get_top_albums(username: str, api_key: str, limit: int = 25) -> list[dict]:
    params = {
        "method": "user.gettopalbums",
        "user": username,
        "period": "7day",
        "limit": limit,
        "api_key": api_key,
        "format": "json",
    }
    response = requests.get(LASTFM_API_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"Last.fm API error: {data.get('message', 'Unknown error')}")

    albums = data.get("topalbums", {}).get("album", [])
    if not albums:
        raise RuntimeError("No albums returned from Last.fm for the last 7 days.")

    return albums


def extract_image_url(album: dict) -> str | None:
    images = album.get("image", [])
    if not isinstance(images, list):
        return None

    preferred_sizes = ["extralarge", "large", "medium"]
    for size in preferred_sizes:
        for img in images:
            if img.get("size") == size and img.get("#text"):
                return img["#text"]

    for img in reversed(images):
        if img.get("#text"):
            return img["#text"]

    return None


def download_cover(url: str) -> Image.Image | None:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception:
        return None


def crop_to_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def get_fonts():
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        artist_font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except Exception:
        title_font = ImageFont.load_default()
        artist_font = ImageFont.load_default()
    return title_font, artist_font


def wrap_text(text: str, width: int) -> list[str]:
    return textwrap.wrap(text or "", width=width)[:2]


def add_lastcollage_style_overlay(img: Image.Image, album_name: str, artist_name: str) -> Image.Image:
    img = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    title_font, artist_font = get_fonts()

    gradient_height = int(img.height * 0.38)
    start_y = img.height - gradient_height

    for i in range(gradient_height):
        alpha = int(180 * (i / gradient_height))
        y = start_y + i
        draw.rectangle([(0, y), (img.width, y + 1)], fill=(0, 0, 0, alpha))

    title_lines = wrap_text(album_name, 18)
    artist_lines = wrap_text(artist_name, 22)

    padding_x = 12
    current_y = img.height - 70

    if len(title_lines) == 2:
        current_y -= 16
    if len(artist_lines) == 2:
        current_y -= 10

    for line in title_lines:
        draw.text((padding_x, current_y), line, font=title_font, fill=(255, 255, 255, 235))
        current_y += 22

    current_y += 4

    for line in artist_lines:
        draw.text((padding_x, current_y), line, font=artist_font, fill=(220, 220, 220, 225))
        current_y += 18

    return Image.alpha_composite(img, overlay).convert("RGB")


def make_placeholder(album_name: str, artist_name: str) -> Image.Image:
    img = Image.new("RGB", (CELL_SIZE, CELL_SIZE), color=(45, 45, 45))
    draw = ImageDraw.Draw(img)
    title_font, artist_font = get_fonts()

    title_lines = wrap_text(album_name or "Unknown Album", 16)
    artist_lines = wrap_text(artist_name or "Unknown Artist", 20)

    y = 40
    for line in title_lines:
        draw.text((16, y), line, fill=(255, 255, 255), font=title_font)
        y += 26

    y += 10
    for line in artist_lines:
        draw.text((16, y), line, fill=(210, 210, 210), font=artist_font)
        y += 20

    return img


def prepare_cover(album: dict) -> Image.Image:
    album_name = album.get("name", "Unknown Album")
    artist_name = album.get("artist", {}).get("name", "Unknown Artist")
    image_url = extract_image_url(album)

    cover = download_cover(image_url) if image_url else None
    if cover is None:
        cover = make_placeholder(album_name, artist_name)
    else:
        cover = crop_to_square(cover)
        cover = cover.resize((CELL_SIZE, CELL_SIZE), Image.Resampling.LANCZOS)

    cover = add_lastcollage_style_overlay(cover, album_name, artist_name)
    return cover


def build_collage(albums: list[dict], output_path: Path) -> None:
    collage = Image.new("RGB", (OUTPUT_WIDTH, OUTPUT_HEIGHT), color=(20, 20, 20))

    for idx, album in enumerate(albums[: GRID_SIZE * GRID_SIZE]):
        row = idx // GRID_SIZE
        col = idx % GRID_SIZE
        x = col * (CELL_SIZE + PADDING)
        y = row * (CELL_SIZE + PADDING)

        cover = prepare_cover(album)
        collage.paste(cover, (x, y))

    collage.save(output_path, format="PNG")


def send_to_discord(webhook_url: str, image_path: Path) -> None:
    with open(image_path, "rb") as f:
        response = requests.post(
            webhook_url,
            data={"content": "Zhivko's weekly top 25 albums"},
            files={"file": ("weekly-collage.png", f, "image/png")},
            timeout=60,
        )

    if response.status_code >= 300:
        raise RuntimeError(f"Discord webhook error: {response.status_code} {response.text}")


def main() -> None:
    username = get_env("LASTFM_USERNAME").lower()
    api_key = get_env("LASTFM_API_KEY")
    webhook_url = get_env("DISCORD_WEBHOOK_URL")

    output_path = Path("collage.png")

    albums = lastfm_get_top_albums(username=username, api_key=api_key, limit=25)
    build_collage(albums, output_path)
    send_to_discord(webhook_url=webhook_url, image_path=output_path)


if __name__ == "__main__":
    main()
