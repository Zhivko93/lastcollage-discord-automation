import io
import os
import textwrap
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
MUSICBRAINZ_RELEASE_GROUP_URL = "https://musicbrainz.org/ws/2/release-group/"
COVER_ART_ARCHIVE_RELEASE_GROUP_URL = "https://coverartarchive.org/release-group/{mbid}/front-500"
REQUEST_HEADERS = {
    "User-Agent": "lastcollage-discord-automation/1.0 (https://github.com/Zhivko93/lastcollage-discord-automation)"
}
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


def extract_image_urls(album: dict) -> list[str]:
    images = album.get("image", [])
    if not isinstance(images, list):
        return []

    preferred_sizes = ["mega", "extralarge", "large", "medium", "small"]
    urls = []
    for size in preferred_sizes:
        for img in images:
            url = img.get("#text", "").strip()
            if img.get("size") == size and url and url not in urls:
                urls.append(url)

    for img in reversed(images):
        url = img.get("#text", "").strip()
        if url and url not in urls:
            urls.append(url)

    return urls


def download_cover(url: str) -> Image.Image | None:
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if content_type and not content_type.startswith("image/"):
            return None
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        image.load()
        return image
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

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    text = f"{artist_name} - {album_name}"
    lines = textwrap.wrap(text, width=28)[:2]

    padding_x = 8
    padding_y = 6

    text_width = 0
    text_height = 0

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        text_width = max(text_width, w)
        text_height += h

    text_height += (len(lines) - 1) * 2

    box_x = 0
    box_y = img.height - text_height - (padding_y * 2)

    draw.rectangle(
        [
            (box_x, box_y),
            (box_x + text_width + padding_x * 2, img.height)
        ],
        fill=(0, 0, 0, 140)
    )

    current_y = box_y + padding_y

    for line in lines:
        draw.text(
            (padding_x, current_y),
            line,
            font=font,
            fill=(255, 255, 255, 230)
        )
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


def fetch_itunes_cover_url(album_name: str, artist_name: str) -> str | None:
    params = {
        "term": f"{artist_name} {album_name}",
        "entity": "album",
        "media": "music",
        "limit": 10,
    }
    try:
        response = requests.get(ITUNES_SEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    album_lower = album_name.casefold()
    artist_lower = artist_name.casefold()
    results = data.get("results", [])
    ranked_results = sorted(
        results,
        key=lambda item: (
            album_lower in item.get("collectionName", "").casefold(),
            artist_lower in item.get("artistName", "").casefold(),
        ),
        reverse=True,
    )

    for item in ranked_results:
        url = item.get("artworkUrl100", "").strip()
        if url:
            return url.replace("100x100bb", "600x600bb")

    return None


def fetch_musicbrainz_cover_url(album_name: str, artist_name: str) -> str | None:
    query = f'releasegroup:"{album_name}" AND artist:"{artist_name}"'
    params = {
        "query": query,
        "fmt": "json",
        "limit": 5,
    }
    try:
        response = requests.get(
            MUSICBRAINZ_RELEASE_GROUP_URL,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    for item in data.get("release-groups", []):
        mbid = item.get("id")
        if mbid:
            return COVER_ART_ARCHIVE_RELEASE_GROUP_URL.format(mbid=mbid)

    return None


def fallback_cover_urls(album_name: str, artist_name: str) -> list[str]:
    urls = []

    itunes_url = fetch_itunes_cover_url(album_name, artist_name)
    if itunes_url:
        urls.append(itunes_url)

    # MusicBrainz asks clients to avoid bursts; this fallback only runs when Last.fm/iTunes miss.
    time.sleep(1)
    musicbrainz_url = fetch_musicbrainz_cover_url(album_name, artist_name)
    if musicbrainz_url:
        urls.append(musicbrainz_url)

    return urls


def find_cover(album: dict, album_name: str, artist_name: str) -> Image.Image | None:
    for url in extract_image_urls(album):
        cover = download_cover(url)
        if cover is not None:
            return cover

    for url in fallback_cover_urls(album_name, artist_name):
        cover = download_cover(url)
        if cover is not None:
            return cover

    return None


def prepare_cover(album: dict) -> Image.Image:
    album_name = album.get("name", "Unknown Album")
    artist_name = album.get("artist", {}).get("name", "Unknown Artist")

    cover = find_cover(album, album_name, artist_name)
    if cover is None:
        print(f"No cover found for {artist_name} - {album_name}; using placeholder")
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
