"""Thumbnail fetching, caching, and ANSI half-block rendering for game covers."""

import hashlib
import io
import os
import re
import urllib.parse
import urllib.request
import webbrowser

from rom.config import CACHE_DIR, UA

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

THUMBS_DIR = os.path.join(CACHE_DIR, "thumbs")

LIBRETRO_MAP = {
    "ps2": "Sony - PlayStation 2",
    "ps1": "Sony - PlayStation",
    "psp": "Sony - PlayStation Portable",
    "ps3": "Sony - PlayStation 3",
    "gba": "Nintendo - Game Boy Advance",
    "gbc": "Nintendo - Game Boy Color",
    "gb": "Nintendo - Game Boy",
    "nds": "Nintendo - Nintendo DS",
    "n64": "Nintendo - Nintendo 64",
    "snes": "Nintendo - Super Nintendo Entertainment System",
    "nes": "Nintendo - Nintendo Entertainment System",
    "gc": "Nintendo - GameCube",
    "wii": "Nintendo - Wii",
    "genesis": "Sega - Mega Drive - Genesis",
    "dreamcast": "Sega - Dreamcast",
    "saturn": "Sega - Saturn",
    "arcade": "FBNeo - Arcade Games",
}


def get_thumb_urls(result):
    """Return a list of candidate thumbnail URLs for the result, ordered by priority."""
    urls = []

    # 1. Direct thumb from provider metadata (e.g. romsgames)
    direct = result.meta.get("thumb")
    if direct:
        urls.append(direct)

    # 2. CoolROM screenshot candidate
    sys_id = result.meta.get("sys")
    if result.source == "coolrom" and sys_id:
        clean_title = re.sub(r'[\/\\:*?"<>|]', "", result.title)
        urls.append(f"https://coolrom.com/screenshots/{sys_id}/{urllib.parse.quote(clean_title)}.jpg")

    # 3. Archive.org item image
    if result.source == "archive.org":
        ident = result.meta.get("id") or result.page.rstrip("/").split("/")[-1]
        if ident:
            urls.append(f"https://archive.org/services/img/{ident}")

    # 4. Libretro Boxart CDN
    pk = result.meta.get("pk") or (result.platform.lower() if result.platform else "")
    lib_sys = LIBRETRO_MAP.get(pk)
    if lib_sys:
        base_title = result.title.strip()
        quoted_title = urllib.parse.quote(base_title)
        urls.append(f"https://thumbnails.libretro.com/{urllib.parse.quote(lib_sys)}/Named_Boxarts/{quoted_title}.png")
        # Try simplified title without region (e.g. "Game (USA)" -> "Game")
        simple_title = re.sub(r"\s*\([^)]*\)", "", base_title).strip()
        if simple_title != base_title:
            urls.append(f"https://thumbnails.libretro.com/{urllib.parse.quote(lib_sys)}/Named_Boxarts/{urllib.parse.quote(simple_title)}.png")

    return urls


def load_thumb_bytes(urls):
    """Download or load cached thumbnail image bytes."""
    os.makedirs(THUMBS_DIR, exist_ok=True)
    for u in urls:
        if not u or not u.startswith("http"):
            continue
        h = hashlib.sha1(u.encode("utf-8")).hexdigest()
        cache_path = os.path.join(THUMBS_DIR, f"{h}.dat")
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    data = f.read()
                if len(data) > 200:
                    return data, u
            except Exception:
                pass

        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 200:
                        try:
                            with open(cache_path, "wb") as f:
                                f.write(data)
                        except Exception:
                            pass
                        return data, u
        except Exception:
            continue
    return None, None


def render_thumb(data, max_w=28, max_h=24):
    """Convert raw image bytes to a Rich Text renderable using ANSI ▀ half-blocks."""
    if not HAS_PIL or not data:
        return None

    import rich.text
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None

    # Maintain aspect ratio within (max_w, max_h)
    resample_filter = getattr(Image, "Resampling", Image).LANCZOS
    img.thumbnail((max_w, max_h), resample_filter)
    w, h = img.size

    # Ensure even height for paired ▀ blocks
    if h % 2 != 0:
        pad = Image.new("RGB", (w, h + 1), (0, 0, 0))
        pad.paste(img, (0, 0))
        img = pad
        h += 1

    out = rich.text.Text()
    for y in range(0, h, 2):
        for x in range(w):
            c1 = img.getpixel((x, y))
            c2 = img.getpixel((x, y + 1))
            out.append("▀", style=f"rgb({c1[0]},{c1[1]},{c1[2]}) on rgb({c2[0]},{c2[1]},{c2[2]})")
        out.append("\n")
    return out


def open_in_browser(url):
    """Open image or page URL in user's default browser."""
    if url:
        try:
            webbrowser.open(url)
        except Exception:
            pass
