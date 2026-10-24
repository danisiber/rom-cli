"""CoolROM provider: search and download from coolrom.com."""

import html as html_lib
import re
import urllib.parse

from rom.config import PLATFORM_LABELS
from rom.providers.base import BaseProvider, Result, request
from rom.utils import clean, human

# Map CoolROM system identifiers to our standard platform keys
SYSTEM_MAP = {
    "ps2": "ps2",
    "psx": "ps1",
    "psp": "psp",
    "ps3": "ps3",
    "gba": "gba",
    "gbc": "gbc",
    "nds": "nds",
    "n64": "n64",
    "snes": "snes",
    "nes": "nes",
    "gcn": "gc",
    "wii": "wii",
    "dc": "dreamcast",
    "genesis": "genesis",
    "saturn": "saturn",
    "mame": "arcade",
    "cps1": "arcade",
    "cps2": "arcade",
    "neogeo": "arcade",
    "xbox": "xbox",
    "xbox360": "xbox360",
}

# Reverse mapping: platform_key -> coolrom system list
PLATFORM_TO_SYS = {
    "ps2": ["ps2"],
    "ps1": ["psx"],
    "psp": ["psp"],
    "ps3": ["ps3"],
    "gba": ["gba"],
    "gbc": ["gbc"],
    "gb": ["gbc"],
    "nds": ["nds"],
    "n64": ["n64"],
    "snes": ["snes"],
    "nes": ["nes"],
    "gc": ["gcn"],
    "wii": ["wii"],
    "dreamcast": ["dc"],
    "genesis": ["genesis"],
    "saturn": ["saturn"],
    "arcade": ["mame", "cps1", "cps2", "neogeo"],
    "xbox": ["xbox"],
}

RESULT_RE = re.compile(
    r'<a href="/roms/(?P<sys>[a-z0-9]+)/"[^>]*>(?P<plat>[^<]+)</a>\s*&raquo\s*<a href="(?P<path>/roms/[a-z0-9]+/(?P<id>\d+)/(?P<slug>[^"]+)\.php)"[^>]*>(?P<title>[^<]+)</a>',
    re.I
)


def _parse_bytes(sz_str):
    if not sz_str:
        return 0
    m = re.match(r'([\d.]+)\s*([KMGTP]?B)', sz_str, re.I)
    if not m:
        return 0
    val, unit = float(m.group(1)), m.group(2).upper()
    mult = {"KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}.get(unit, 1)
    return int(val * mult)


class CoolRom(BaseProvider):
    name = "coolrom"
    base = "https://coolrom.com"

    def search(self, query, platform_key=None):
        url = f"{self.base}/search?q={urllib.parse.quote_plus(query)}"
        st, _, body = request(url, headers={"Referer": self.base}, retries=2)
        if st != 200:
            return []

        html = body.decode("utf-8", "replace")
        target_systems = PLATFORM_TO_SYS.get(platform_key) if platform_key else None

        out, seen = [], set()
        for m in RESULT_RE.finditer(html):
            sys_id = m.group("sys").lower()
            if target_systems and sys_id not in target_systems:
                continue

            path = m.group("path")
            if path in seen:
                continue
            seen.add(path)

            raw_title = clean(html_lib.unescape(m.group("title")))
            if not raw_title:
                continue

            pk = SYSTEM_MAP.get(sys_id, sys_id)
            plat_label = PLATFORM_LABELS.get(pk, m.group("plat").strip())
            clean_title_fn = re.sub(r'[\/\\:*?"<>|]', "", raw_title)
            thumb = f"{self.base}/screenshots/{sys_id}/{urllib.parse.quote(clean_title_fn)}.jpg"

            out.append(Result(
                self.name,
                raw_title,
                plat_label,
                self.base + path,
                meta={"pk": pk, "sys": sys_id, "id": m.group("id"), "ext": "7z", "thumb": thumb}
            ))
        return out

    def resolve(self, result):
        st, _, body = request(result.page, headers={"Referer": f"{self.base}/search"}, retries=2)
        if st != 200:
            raise RuntimeError(f"CoolROM page unavailable ({st})")

        html = body.decode("utf-8", "replace")

        # Parse file size from JSON-LD schema
        sz_m = re.search(r'"fileSize"\s*:\s*"([^"]+)"', html)
        if sz_m:
            result.size = sz_m.group(1).strip()
            result.meta["bytes"] = _parse_bytes(result.size)

        m = re.search(r'href="(https://dl\.coolrom\.com/roms/[^"]+)"', html)
        if not m:
            raise RuntimeError("CoolROM direct download link not found on game page")

        dl_url = m.group(1)

        # Extract filename from URL path
        # Format: https://dl.coolrom.com/roms/{sys}/{quoted_filename}/{token}/{timestamp}/
        parts = dl_url.split("/")
        filename = ""
        for p in parts[4:]:
            if p and "." in p:
                filename = urllib.parse.unquote(p)
                break
        if not filename:
            filename = f"{result.title}.7z"

        if "." in filename:
            result.meta["ext"] = filename.rsplit(".", 1)[-1].lower()

        return dl_url, filename
