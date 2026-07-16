import io
import os
import textwrap
import time
from datetime import datetime, timedelta, timezone
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
COLLAGE_TRIGGER_WEEKDAY = 6
COLLAGE_TRIGGER_HOUR_UTC = 18
COLLAGE_WINDOW_DAYS = 7
LASTFM_PAGE_LIMIT = 200
COMPLETED_ALBUM_OUTLINE_COLOR = (255, 196, 45)
COMPLETED_ALBUM_OUTLINE_WIDTH = 10


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def get_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def normalize_name(value: str) -> str:
    return " ".join((value or "").casefold().split())


def get_lastfm_text(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("#text") or value.get("name") or "").strip()
    return str(value or "").strip()


def lastfm_request(params: dict) -> dict:
    response = requests.get(LASTFM_API_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"Last.fm API error: {data.get('message', 'Unknown error')}")

    return data


def get_collage_window(now: datetime | None = None) -> tuple[datetime, datetime, int, int]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    days_since_trigger_day = (now.weekday() - COLLAGE_TRIGGER_WEEKDAY) % 7
    window_end = now.replace(
        hour=COLLAGE_TRIGGER_HOUR_UTC,
        minute=0,
        second=0,
        microsecond=0,
    ) - timedelta(days=days_since_trigger_day)

    if window_end > now:
        window_end -= timedelta(days=COLLAGE_WINDOW_DAYS)

    window_start = window_end - timedelta(days=COLLAGE_WINDOW_DAYS)

    # Last.fm's range is strictly "after from" and "before to".
    # Querying from one second before the boundary includes the exact trigger second
    # in the following week's collage without overlapping the previous one.
    from_ts = int(window_start.timestamp()) - 1
    to_ts = int(window_end.timestamp())
    return window_start, window_end, from_ts, to_ts


def lastfm_get_recent_tracks(
    username: str,
    api_key: str,
    from_ts: int,
    to_ts: int,
) -> list[dict]:
    tracks = []
    page = 1

    while True:
        data = lastfm_request(
            {
                "method": "user.getrecenttracks",
                "user": username,
                "from": from_ts,
                "to": to_ts,
                "limit": LASTFM_PAGE_LIMIT,
                "page": page,
                "api_key": api_key,
                "format": "json",
            }
        )

        recent_tracks = data.get("recenttracks", {})
        batch = recent_tracks.get("track", [])
        if isinstance(batch, dict):
            batch = [batch]

        dated_tracks = [
            track
            for track in batch
            if isinstance(track, dict) and "date" in track and "@attr" not in track
        ]
        tracks.extend(dated_tracks)

        attrs = recent_tracks.get("@attr", {})
        total_pages = int(attrs.get("totalPages") or page)
        if page >= total_pages or not batch:
            break

        page += 1

    if not tracks:
        raise RuntimeError("No scrobbles returned from Last.fm for this collage window.")

    return tracks


def album_key(artist_name: str, album_name: str) -> tuple[str, str]:
    return normalize_name(artist_name), normalize_name(album_name)


def build_album_records(tracks: list[dict], limit: int = 25) -> list[dict]:
    albums: dict[tuple[str, str], dict] = {}

    for track in tracks:
        album_name = get_lastfm_text(track.get("album"))
        artist_name = get_lastfm_text(track.get("artist"))
        track_name = get_lastfm_text(track.get("name"))

        if not album_name or not artist_name or not track_name:
            continue

        key = album_key(artist_name, album_name)
        uts = int(track.get("date", {}).get("uts") or 0)

        if key not in albums:
            albums[key] = {
                "name": album_name,
                "artist": {"name": artist_name},
                "image": track.get("image", []),
                "mbid": get_lastfm_text(track.get("album", {}).get("mbid")),
                "playcount": 0,
                "latest_uts": uts,
                "listened_tracks": set(),
                "complete": False,
            }

        album = albums[key]
        album["playcount"] += 1
        album["latest_uts"] = max(album["latest_uts"], uts)
        album["listened_tracks"].add(normalize_name(track_name))

        if not album.get("image") and track.get("image"):
            album["image"] = track.get("image", [])

    ranked_albums = sorted(
        albums.values(),
        key=lambda album: (
            -album["playcount"],
            -album["latest_uts"],
            normalize_name(album["artist"]["name"]),
            normalize_name(album["name"]),
        ),
    )

    if not ranked_albums:
        raise RuntimeError("No album scrobbles returned from Last.fm for this collage window.")

    return ranked_albums[:limit]


def lastfm_get_album_track_names(
    album_name: str,
    artist_name: str,
    api_key: str,
    mbid: str = "",
) -> set[str]:
    params = {
        "method": "album.getinfo",
        "api_key": api_key,
        "format": "json",
        "autocorrect": 1,
    }

    if mbid:
        params["mbid"] = mbid
    else:
        params["artist"] = artist_name
        params["album"] = album_name

    try:
        data = lastfm_request(params)
    except Exception as exc:
        print(f"Could not fetch tracklist for {artist_name} - {album_name}: {exc}")
        return set()

    track_data = data.get("album", {}).get("tracks", {}).get("track", [])
    if isinstance(track_data, dict):
        track_data = [track_data]

    return {
        normalize_name(get_lastfm_text(track.get("name")))
        for track in track_data
        if isinstance(track, dict) and get_lastfm_text(track.get("name"))
    }


def mark_completed_albums(albums: list[dict], api_key: str) -> None:
    for album in albums:
        album_name = album.get("name", "")
        artist_name = album.get("artist", {}).get("name", "")
        tracklist = lastfm_get_album_track_names(
            album_name=album_name,
            artist_name=artist_name,
            api_key=api_key,
            mbid=album.get("mbid", ""),
        )

        listened_tracks = album.get("listened_tracks", set())
        album["complete"] = bool(tracklist) and tracklist.issubset(listened_tracks)

        # Keep these calls gentle for Last.fm when all 25 albums need tracklists.
        time.sleep(0.2)


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


def add_completed_album_outline(img: Image.Image) -> Image.Image:
    img = img.copy()
    draw = ImageDraw.Draw(img)
    half_width = COMPLETED_ALBUM_OUTLINE_WIDTH // 2
    draw.rectangle(
        [
            (half_width, half_width),
            (img.width - half_width - 1, img.height - half_width - 1),
        ],
        outline=COMPLETED_ALBUM_OUTLINE_COLOR,
        width=COMPLETED_ALBUM_OUTLINE_WIDTH,
    )
    return img


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
    if album.get("complete"):
        cover = add_completed_album_outline(cover)
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


def send_to_discord(webhook_url: str, image_path: Path, window_start: datetime, window_end: datetime) -> None:
    content = (
        "Zhivko's weekly top 25 albums\n"
        f"Window: {window_start:%Y-%m-%d %H:%M} UTC to {window_end:%Y-%m-%d %H:%M} UTC"
    )
    with open(image_path, "rb") as f:
        response = requests.post(
            webhook_url,
            data={"content": content},
            files={"file": ("weekly-collage.png", f, "image/png")},
            timeout=60,
        )

    if response.status_code >= 300:
        raise RuntimeError(f"Discord webhook error: {response.status_code} {response.text}")


def main() -> None:
    username = get_env("LASTFM_USERNAME").lower()
    api_key = get_env("LASTFM_API_KEY")
    preview_only = env_flag("PREVIEW_ONLY")
    webhook_url = "" if preview_only else get_env("DISCORD_WEBHOOK_URL")

    output_path = Path("collage.png")
    window_start, window_end, from_ts, to_ts = get_collage_window()

    tracks = lastfm_get_recent_tracks(
        username=username,
        api_key=api_key,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    albums = build_album_records(tracks, limit=GRID_SIZE * GRID_SIZE)
    mark_completed_albums(albums, api_key=api_key)
    build_collage(albums, output_path)

    if preview_only:
        print(f"Preview generated at {output_path}")
        print(f"Window: {window_start:%Y-%m-%d %H:%M} UTC to {window_end:%Y-%m-%d %H:%M} UTC")
    else:
        send_to_discord(
            webhook_url=webhook_url,
            image_path=output_path,
            window_start=window_start,
            window_end=window_end,
        )


if __name__ == "__main__":
    main()
