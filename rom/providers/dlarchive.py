"""DlArchive provider: search and download from dlarchive."""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from rom.config import CACHE_DIR, INDEX_FILE, INDEX_PAGE, INDEX_TTL
from rom.providers.base import BaseProvider, Result, request
from rom.utils import human, kind_of, norm, platform_of, pretty_title, significant


class DlArchive(BaseProvider):
    name = "dlarchive"
    api = "https://uptobox.dlarchive.my.id/files_api.php"
    _cache = None
    _lock = threading.Lock()

    def _entry(self, item):
        fn = item.get("filename") or ""
        size = int(item.get("size") or 0)
        return {
            "id": item.get("id"), "filename": fn, "size": size,
            "folder": item.get("folder") or "",
        }

    def _rehydrate(self, e):
        fn = e.get("filename") or ""
        pk, label = platform_of(fn, e.get("folder") or "")
        e["pk"], e["plat"] = pk, label
        e["kind"] = kind_of(fn)
        e["ext"] = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
        e["title"] = pretty_title(fn)
        e["ntitle"] = norm(e["title"])
        return e

    def _fetch(self, on_progress=None):
        st, _, body = request(f"{self.api}?action=list&limit=1",
                              headers={"Accept": "application/json"}, timeout=60)
        total = int(json.loads(body.decode("utf-8", "replace")).get("total") or 0)
        offsets = list(range(0, total, INDEX_PAGE))
        entries, done = [], [0]
        lock = threading.Lock()

        def work(off):
            st, _, body = request(f"{self.api}?action=list&offset={off}&limit={INDEX_PAGE}",
                                  headers={"Accept": "application/json"}, timeout=60, retries=4)
            items = json.loads(body.decode("utf-8", "replace")).get("items", [])
            with lock:
                for it in items:
                    entries.append(self._entry(it))
                done[0] += 1
                if on_progress:
                    on_progress(done[0], len(offsets))

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(work, offsets))
        return [self._rehydrate(e) for e in entries]

    def load_index(self, force=False, on_progress=None):
        with self._lock:
            if DlArchive._cache and not force:
                return DlArchive._cache
            if not force and os.path.exists(INDEX_FILE):
                try:
                    with open(INDEX_FILE, encoding="utf-8") as _f:
                        data = json.load(_f)
                    if (time.time() - data.get("fetched_at", 0) < INDEX_TTL
                            and data.get("entries")):
                        DlArchive._cache = [self._rehydrate(e) for e in data["entries"]]
                        return DlArchive._cache
                except Exception:
                    pass
            entries = self._fetch(on_progress)
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
                tmp = INDEX_FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"fetched_at": time.time(), "entries": entries}, f)
                os.replace(tmp, INDEX_FILE)
            except Exception:
                pass
            DlArchive._cache = entries
            return entries

    def _result(self, e):
        return Result(
            self.name, e["title"], e["plat"],
            f"{self.api}?action=file-url&id={e['id']}",
            human(e["size"]) if e["size"] else "",
            meta={"id": e["id"], "filename": e["filename"], "ext": e["ext"],
                  "kind": kind_of(e["filename"]), "pk": e["pk"], "bytes": e["size"]})

    def search(self, query, pk=None, on_progress=None, force=False):
        idx = self.load_index(force=force, on_progress=on_progress)
        toks = significant(norm(query).split())
        out = []
        for e in idx:
            if pk and e["pk"] != pk:
                continue
            nt = e["ntitle"]
            hits = sum(1 for t in toks if t in nt)
            if hits == 0:
                continue
            if pk is None and hits < len(toks):
                continue
            out.append((hits, e))
        if not out and toks:
            for e in idx:
                if pk and e["pk"] != pk:
                    continue
                if toks[0] in e["ntitle"]:
                    out.append((1, e))
        out.sort(key=lambda x: (-x[0], len(x[1]["title"])))
        return [self._result(e) for _hits, e in out[:120]]

    def all_items(self, pk=None, ports_only=False):
        out = []
        for e in self.load_index():
            if not e["pk"] or (pk and e["pk"] != pk):
                continue
            if ports_only and kind_of(e["filename"]) != "Port":
                continue
            out.append(self._result(e))
        out.sort(key=lambda r: norm(r.title))
        return out

    def resolve(self, result):
        fid = result.meta.get("id")
        st, _, body = request(f"{self.api}?action=file-url&id={fid}",
                              headers={"Accept": "application/json"}, timeout=60, retries=3)
        if st != 200:
            raise RuntimeError(f"server responded {st}")
        data = json.loads(body.decode("utf-8", "replace"))
        if not data.get("ok") or not data.get("url"):
            raise RuntimeError(data.get("error") or "link unavailable")
        return data["url"], result.meta.get("filename") or result.title
