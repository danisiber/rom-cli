"""NoPayStation provider: search and download PlayStation games via NPS TSV databases."""

import json
import os
import re
import threading
import time

from rom.config import CACHE_DIR, PLATFORM_LABELS
from rom.providers.base import BaseProvider, Result, request
from rom.utils import human, norm, pretty_title, significant


class NoPayStation(BaseProvider):
    name = "nps"
    base = "https://nopaystation.com/tsv/"
    tsv = {"ps3": "PS3_GAMES.tsv", "psv": "PSV_GAMES.tsv",
           "psp": "PSP_GAMES.tsv", "ps1": "PSX_GAMES.tsv"}
    cache_file = os.path.join(CACHE_DIR, "nps.json")
    _cache = None
    _lock = threading.Lock()

    def _fetch(self, key):
        st, _, body = request(self.base + self.tsv[key], timeout=120, retries=3)
        if st != 200:
            return []
        lines = body.decode("utf-8", "replace").splitlines()
        if not lines:
            return []
        hdr = [h.strip().lower() for h in lines[0].split("\t")]
        i_size = next((i for i, n in enumerate(hdr) if "size" in n), None)
        i_orig = next((i for i, n in enumerate(hdr) if "original name" in n), None)
        rows = []
        for line in lines[1:]:
            c = line.split("\t")
            url = next((x for x in c if x.startswith("http")), None)
            if not url or len(c) < 3:
                continue
            size = 0
            if i_size is not None and i_size < len(c):
                digits = re.sub(r"[^0-9]", "", c[i_size])
                size = int(digits) if digits else 0
            orig = c[i_orig] if i_orig is not None and i_orig < len(c) else ""
            rows.append({"tid": c[0], "region": c[1] if len(c) > 1 else "",
                         "name": c[2], "url": url, "size": size, "orig": orig})
        return rows

    def load(self, force=False, on_progress=None):
        with self._lock:
            if NoPayStation._cache and not force:
                return NoPayStation._cache
            if not force and os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, encoding="utf-8") as _f:
                        d = json.load(_f)
                    if time.time() - d.get("fetched_at", 0) < 7 * 86400 and d.get("data"):
                        NoPayStation._cache = d["data"]
                        return NoPayStation._cache
                except Exception:
                    pass
            data = {}
            for i, k in enumerate(self.tsv, 1):
                if on_progress:
                    on_progress(i, len(self.tsv))
                data[k] = self._fetch(k)
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
                tmp = self.cache_file + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"fetched_at": time.time(), "data": data}, f)
                os.replace(tmp, self.cache_file)
            except Exception:
                pass
            NoPayStation._cache = data
            return data

    def _result(self, e, pk):
        title = pretty_title(e["name"])
        return Result(
            self.name, title, PLATFORM_LABELS.get(pk, "PS3"), e["url"],
            human(e["size"]) if e["size"] else "",
            meta={"ext": "pkg", "bytes": e["size"], "tid": e["tid"], "pk": pk,
                  "filename": f"{title} [{e['tid']}].pkg"})

    def search(self, query, pk=None, on_progress=None, force=False):
        rows = self.load(force=force, on_progress=on_progress).get(pk or "ps3", [])
        toks = significant(norm(query).split())
        scored = []
        for e in rows:
            nt = norm(f"{e['name']} {e['orig']}")
            hits = sum(1 for t in toks if t in nt)
            if hits:
                scored.append((hits, e))
        scored.sort(key=lambda x: (-x[0], len(x[1]["name"])))
        return [self._result(e, pk) for _hits, e in scored[:80]]

    def all_items(self, pk=None):
        rows = self.load().get(pk or "ps3", [])
        out = [self._result(e, pk) for e in rows]
        out.sort(key=lambda r: norm(r.title))
        return out

    def resolve(self, result):
        return result.page, result.meta.get("filename") or result.title
