import io
import os
import math
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
CELL_SIZE = 300
GRID_SIZE = 5
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

    # Prefer larger images first
    preferred_sizes = ["extralarge", "large", "medium"]
    for size in preferred_sizes:
        for img in images:
            if img.get("size") == size and img.get("#text"):
                return img["#text"]

    # Fallback to any image with a URL
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


def make_placeholder(album_name: str, artist_name: str) -> Image.Image:
    img = Image.new("RGB", (CELL_SIZE, CELL_SIZE), color=(50, 50, 50))
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_artist = ImageFont.truetype("DejaVuSans.ttf", 18)
    except Exception:
        font_title = ImageFont.load_default()
        font_artist = ImageFont.load_default()

    title_lines = textwrap.wrap(album_name or "Unknown Album", width=18)[:4]
    artist_lines = textwrap.wrap(artist_name or "Unknown Artist", width=20)[:2]

    y = 30
    for line in title_lines:
        draw.text((15, y), line, fill=(255, 255, 255), font=font_title)
        y += 30

    y += 20
    for line in artist_lines:
        draw.text((15, y), line, fill=(200, 200, 200), font=font_artist)
        y += 24

    return img


def crop_to_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def prepare_cover(album: dict) -> Image.Image:
    album_name = album.get("name", "Unknown Album")
    artist_name = album.get("artist", {}).get("name", "Unknown Artist")
    image_url = extract_image_url(album)

    cover = download_cover(image_url) if image_url else None
    if cover is None:
        return make_placeholder(album_name, artist_name)

    cover = crop_to_square(cover)
    cover = cover.resize((CELL_SIZE, CELL_SIZE), Image.Resampling.LANCZOS)
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


def send_to_discord(webhook_url: str, image_path: Path, username: str) -> None:
    with open(image_path, "rb") as f:
        response = requests.post(
            webhook_url,
            data={"content": f"{username}'s weekly 5x5 album collage"},
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
    send_to_discord(webhook_url=webhook_url, image_path=output_path, username=username)


if __name__ == "__main__":
    main()
