"""Archive.org provider: search and download from Internet Archive."""

import json
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from rom.config import CACHE_DIR, PLATFORM_LABELS, PORTS_FILE, PORTS_TTL, PORTS_VER
from rom.providers.base import BaseProvider, Result, request
from rom.utils import clean, human, norm, pretty_title

PORTS_CACHE = None


class ArchiveOrg(BaseProvider):
    name = "archive.org"
    base = "https://archive.org"
    tags = {
        "nes": ("NES", ["nes", "zip", "7z"]),
        "snes": ("SNES", ["sfc", "smc", "zip", "7z"]),
        "n64": ("Nintendo 64", ["z64", "n64", "v64", "zip", "7z"]),
        "gb": ("Game Boy", ["gb", "zip", "7z"]),
        "gbc": ("Game Boy Color", ["gbc", "zip", "7z"]),
        "gba": ("Game Boy Advance", ["gba", "zip", "7z"]),
        "nds": ("Nintendo DS", ["nds", "zip", "7z", "rar"]),
        "3ds": ("Nintendo 3DS", ["cia", "3ds", "zip", "7z", "rar"]),
        "gc": ("GameCube", ["iso", "gcm", "rvz", "zip", "7z", "rar"]),
        "wii": ("Wii", ["iso", "wbfs", "rvz", "zip", "7z", "rar"]),
        "ps1": ("PlayStation", ["bin", "cue", "iso", "chd", "zip", "7z", "rar"]),
        "ps2": ("PlayStation 2", ["iso", "zip", "7z", "rar", "chd", "cso", "bin", "gz"]),
        "ps3": ("PlayStation 3", ["iso", "pkg", "zip", "7z", "rar"]),
        "psp": ("PlayStation Portable", ["iso", "cso", "pbp", "zip", "7z", "rar"]),
        "genesis": ("Genesis", ["md", "bin", "gen", "zip", "7z"]),
        "mastersystem": ("Master System", ["sms", "zip", "7z"]),
        "dreamcast": ("Dreamcast", ["cdi", "gdi", "chd", "zip", "7z"]),
        "saturn": ("Saturn", ["cue", "bin", "chd", "zip", "7z"]),
        "arcade": ("Arcade", ["zip", "7z", "chd"]),
        "xbox": ("Xbox", ["iso", "xbe", "zip", "7z", "rar"]),
    }
    skip = ("_files.xml", "_meta.xml", "_meta.sqlite", "_archive.torrent", ".torrent")
    port_queries = (
        'title:("switch port") AND mediatype:software',
        'title:("homebrew port") AND mediatype:software',
        'title:(nsp) AND (port OR homebrew) AND mediatype:software',
        'title:("nintendo switch") AND (port OR homebrew) AND mediatype:software',
    )
    port_exts = ["nsp", "xci", "nsz", "zip", "7z", "rar"]

    def switch_ports(self, force=False, on_progress=None):
        global PORTS_CACHE
        if PORTS_CACHE is not None and not force:
            return PORTS_CACHE
        if not force and os.path.exists(PORTS_FILE):
            try:
                with open(PORTS_FILE, encoding="utf-8") as _f:
                    d = json.load(_f)
                if (time.time() - d.get("fetched_at", 0) < PORTS_TTL
                        and d.get("ver") == PORTS_VER and d.get("items")):
                    PORTS_CACHE = d["items"]
                    return PORTS_CACHE
            except Exception:
                pass
        pair, seen = [], set()
        for q in self.port_queries:
            url = (f"{self.base}/advancedsearch.php?q={urllib.parse.quote(q)}"
                   "&fl%5B%5D=identifier&fl%5B%5D=title&rows=60&output=json")
            st, _, body = request(url, retries=2)
            if st != 200:
                continue
            try:
                docs = json.loads(body.decode("utf-8", "replace"))["response"]["docs"]
            except Exception:
                continue
            for doc in docs:
                ident = doc.get("identifier")
                if ident and ident not in seen:
                    seen.add(ident)
                    pair.append((ident, clean(doc.get("title") or "")))
        out, state = [], {"done": 0}

        def work(item):
            ident, title = item
            try:
                st, _, body = request(f"{self.base}/metadata/{ident}", retries=2,
                                      headers={"Accept": "application/json"}, timeout=40)
                data = json.loads(body.decode("utf-8", "replace")) if st == 200 else {}
            except Exception:
                data = {}
            state["done"] += 1
            if on_progress:
                on_progress(state["done"], len(pair))
            files = [f for f in data.get("files", []) if not f["name"].endswith(self.skip)]
            for ext in self.port_exts:
                cands = [f for f in files if f["name"].lower().endswith("." + ext)]
                if cands:
                    best = max(cands, key=lambda f: int(f.get("size") or 0))
                    return {"title": title or pretty_title(best["name"]), "ident": ident,
                            "size": int(best.get("size") or 0), "file": best["name"],
                            "nsp": ext in ("nsp", "xci", "nsz")}
            return None

        with ThreadPoolExecutor(max_workers=6) as pool:
            for r in pool.map(work, pair):
                if r:
                    out.append(r)
        block = ("theme", "dbi", "installer", "autoloader", "payload", "firmware",
                 "devkitpro", "source code", "godot", "psvita", "ps vita", " vita",
                 "3ds", "psp", "wiiu", "wii u")
        out = [r for r in out if not any(b in r["title"].lower() for b in block)]
        out.sort(key=lambda x: (not x.get("nsp"), norm(x["title"])))
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = PORTS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"fetched_at": time.time(), "ver": PORTS_VER, "items": out}, f)
            os.replace(tmp, PORTS_FILE)
        except Exception:
            pass
        PORTS_CACHE = out
        return out

    def port_results(self, force=False, on_progress=None):
        out = []
        for it in self.switch_ports(force=force, on_progress=on_progress):
            out.append(Result(self.name, it["title"], PLATFORM_LABELS["switch"],
                              f"{self.base}/details/{it['ident']}",
                              human(it["size"]) if it["size"] else "",
                              meta={"exts": self.port_exts, "ext": "nsp",
                                    "pk": "switch", "kind": "Port"}))
        return out

    def search(self, query, platform_key=None):
        if platform_key not in self.tags:
            return []
        tag, exts = self.tags[platform_key]
        q = f'({query}) AND mediatype:software AND ("{tag}" OR "{platform_key}")'
        url = (f"{self.base}/advancedsearch.php?q={urllib.parse.quote(q)}"
               "&fl%5B%5D=identifier&fl%5B%5D=title&fl%5B%5D=item_size&rows=20&page=1&output=json")
        st, _, body = request(url, retries=2)
        if st != 200:
            return []
        try:
            docs = json.loads(body.decode("utf-8", "replace"))["response"]["docs"]
        except Exception:
            return []
        out = []
        for doc in docs:
            title = clean(doc.get("title") or "")
            if title:
                item_sz = doc.get("item_size")
                sz_str = human(int(item_sz)) if item_sz else ""
                out.append(Result(self.name, title, PLATFORM_LABELS.get(platform_key, platform_key),
                                  f"{self.base}/details/{doc['identifier']}", size=sz_str, meta={"exts": exts}))
        return out

    def resolve(self, result):
        ident = result.page.rsplit("/", 1)[-1]
        st, _, body = request(f"{self.base}/metadata/{ident}", retries=2,
                              headers={"Accept": "application/json"})
        if st != 200:
            raise RuntimeError(f"item unavailable ({st})")
        data = json.loads(body.decode("utf-8", "replace"))
        files = [f for f in data.get("files", []) if not f["name"].endswith(self.skip)]
        if not files:
            raise RuntimeError("item has no downloadable file")
        for ext in result.meta.get("exts", []):
            matches = [f for f in files if f["name"].lower().endswith("." + ext)]
            if matches:
                best = max(matches, key=lambda f: int(f.get("size") or 0))
                return (f"{self.base}/download/{ident}/{urllib.parse.quote(best['name'])}",
                        best["name"])
        loose = [f for f in files if re.search(r"\.(zip|7z|rar|ips|bps|xdelta|iso|bin|cue|chd|cia|3ds|nsp|xci)$",
                                               f["name"], re.I)]
        if loose:
            best = max(loose, key=lambda f: int(f.get("size") or 0))
            return f"{self.base}/download/{ident}/{urllib.parse.quote(best['name'])}", best["name"]
        raise RuntimeError("no compatible format in the item")
