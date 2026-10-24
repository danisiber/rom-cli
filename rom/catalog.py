"""Catalog searching, ranking, popularity scoring, and platform browsing."""

import json
import os
import re
import time
import urllib.parse

from rom.config import (
    BAD,
    CACHE_DIR,
    LABEL_KEY,
    PLATFORM_LABELS,
    PLATFORMS,
    POPULAR_FILE,
    POPULAR_TTL,
    WIKI_LISTS,
)
from rom.providers import (
    ARCHIVE_ORG,
    COOLROM,
    DLA,
    DLP,
    NPS,
    ROMSGAMES,
    SOURCES,
    Result,
    request,
)
from rom.providers.archive_org import ArchiveOrg
from rom.utils import norm, significant

POPULAR = None
POPULAR_NORM = None
KIND_ORDER = {"Base": 0, "": 1, "Port": 1, "Update": 2, "DLC": 3}


def _wiki_raw(title, depth=0):
    st, _, body = request(f"https://en.wikipedia.org/w/index.php?title={title}&action=raw",
                          retries=2, timeout=40)
    if st != 200 or depth > 2:
        return ""
    text = body.decode("utf-8", "replace")
    m = re.match(r"\s*#REDIRECT\s*\[\[([^\]]+)\]\]", text, re.I)
    if m:
        return _wiki_raw(urllib.parse.quote(m.group(1).replace(" ", "_")), depth + 1)
    return text


_WIKI_ATTR = re.compile(r'^[|!]\s*(?:[A-Za-z_:][\w:.-]*\s*=\s*'
                        r'(?:"[^"]*"|\'[^\']*\'|[^\s|]+)\s*)*\|?\s*')
_WIKI_LINK = re.compile(r"\[\[([^\]\|#]+)(?:\|([^\]]+))?\]\]")
_WIKI_SALES = (re.compile(r"\{\{nts\|([\d.,]+)\}\}"),
               re.compile(r"\{\{val\|([\d.,]+)"),
               re.compile(r"\b(\d{1,3}(?:,\d{3}){1,}|\d{6,})\b"))


def _wiki_tables(text):
    out, cur, depth = [], None, 0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("{|"):
            if depth == 0:
                cur = []
            depth += 1
        if cur is not None:
            cur.append(line)
        if s.startswith("|}"):
            depth = max(0, depth - 1)
            if depth == 0 and cur is not None:
                out.append(cur)
                cur = None
    return out


def _wiki_rows(lines):
    rows, cur = [], None

    def flush(cells):
        if not cells:
            return
        title, sales = None, 0.0
        for cell in cells:
            body = _WIKI_ATTR.sub("", cell.strip(), count=1)
            if title is None:
                m = _WIKI_LINK.search(body)
                if m:
                    title = re.sub(r"''", "", m.group(2) or m.group(1))
                    title = re.sub(r"&nbsp;|&#160;|\u00a0", " ", title)
                    title = re.sub(r"\s+", " ", title).strip()
            if sales == 0.0:
                for pat in _WIKI_SALES:
                    mm = pat.search(body)
                    if mm:
                        try:
                            sales = float(mm.group(1).replace(",", ""))
                        except ValueError:
                            sales = 0.0
                        if sales:
                            break
        if title and sales > 0:
            rows.append(title)

    for line in lines:
        s = line.strip()
        if s == "|-":
            flush(cur)
            cur = []
        elif cur is not None and s.startswith(("|", "!")):
            cur.append(line)
    flush(cur)
    return rows


def _parse_wiki(text):
    best = []
    for tbl in _wiki_tables(text):
        rows = _wiki_rows(tbl)
        if len(rows) > len(best):
            best = rows
    return best


def load_popular(force=False):
    global POPULAR, POPULAR_NORM
    if POPULAR is not None and not force:
        return POPULAR
    data = {}
    if not force and os.path.exists(POPULAR_FILE):
        try:
            with open(POPULAR_FILE, encoding="utf-8") as _f:
                d = json.load(_f)
            if time.time() - d.get("fetched_at", 0) < POPULAR_TTL and d.get("data"):
                data = d["data"]
        except Exception:
            pass
    dirty = False
    for pk, page in WIKI_LISTS.items():
        if pk in data and data[pk]:
            continue
        try:
            titles = _parse_wiki(_wiki_raw(page))
        except Exception:
            titles = []
        seen, ranked = set(), []
        for t in titles:
            nt = norm(t)
            if nt and nt not in seen:
                seen.add(nt)
                ranked.append(t)
        if ranked:
            data[pk] = ranked
            dirty = True
    if dirty or (not os.path.exists(POPULAR_FILE) and data):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = POPULAR_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"fetched_at": time.time(), "data": data}, f)
            os.replace(tmp, POPULAR_FILE)
        except Exception:
            pass
    POPULAR = data
    POPULAR_NORM = None
    return data


def _pop_norm(pk):
    global POPULAR_NORM
    if POPULAR_NORM is None:
        POPULAR_NORM = {}
    if pk not in POPULAR_NORM:
        POPULAR_NORM[pk] = {norm(t): i for i, t in enumerate((POPULAR or {}).get(pk, []))}
    return POPULAR_NORM[pk]


def pop_rank(pk, title):
    nt = norm(title)
    if not nt:
        return None
    m = _pop_norm(pk)
    if not m:
        return None
    if nt in m:
        return m[nt]
    best = None
    for wt, i in m.items():
        if nt.startswith(wt + " "):
            if best is None or i < best:
                best = i
    return best


def annotate_popular(results):
    load_popular()
    for r in results:
        pk = r.meta.get("pk") or LABEL_KEY.get(r.platform)
        if not pk:
            continue
        rk = pop_rank(pk, r.title)
        if rk is not None:
            r.meta["pop"] = rk
    return results


def rank(results, query):
    words = significant(norm(query).split())

    def score(r):
        t = norm(f"{r.title} {r.platform}")
        s = sum(7 for w in words if w in t)
        if words and all(w in t for w in words):
            s += 30
        low = r.title.lower()
        for pat in BAD:
            if pat in low:
                s -= 12
        if r.meta.get("ext") in ("nsp", "xci"):
            s += 4
        pop = r.meta.get("pop")
        if pop is not None:
            s += min(12, max(2, 14 - pop))
        if r.kind == "Base":
            s += 3
        elif r.kind in ("Update", "DLC"):
            s -= 3
        if r.source == "archive.org":
            s -= 8
        if r.source == "dlpsgame":
            s -= 5
        if len(r.title) > 70:
            s -= 6
        return s

    return sorted(results, key=score, reverse=True)


def search(query, platform_key=None, on_progress=None, force=False):
    results, seen = [], set()

    def add(batch):
        for r in batch:
            key = (r.source, r.title, r.size)
            if key not in seen:
                seen.add(key)
                results.append(r)

    words = significant(norm(query).split())
    tries = [query]
    if len(words) >= 2:
        tries.append(" ".join(words))
        tries.append(" ".join(words[:2]))
    tries += sorted(words, key=len, reverse=True)[:2]

    first = True
    for attempt in tries:
        if platform_key:
            src_name, arg = PLATFORMS[platform_key]
            src = SOURCES[src_name]
            if src_name in ("dlarchive", "nps"):
                add(src.search(attempt, arg, on_progress=on_progress, force=force))
            else:
                add(src.search(attempt, arg))
            if "coolrom" in SOURCES and len(results) < 12:
                try:
                    add(COOLROM.search(attempt, platform_key))
                except Exception:
                    pass
        else:
            try:
                add(SOURCES["romsgames"].search(attempt))
            except Exception:
                pass
            try:
                add(COOLROM.search(attempt))
            except Exception:
                pass
            try:
                add(DLA.search(attempt, None, on_progress=on_progress, force=force))
            except Exception:
                pass
            if first:
                try:
                    add(NPS.search(attempt, "ps3", on_progress=on_progress, force=force))
                except Exception:
                    pass
                try:
                    add(DLP.search(attempt, None))
                except Exception:
                    pass
        force = False
        first = False
        if len(results) >= 12:
            break

    if platform_key == "switchports":
        try:
            words = significant(norm(query).split())
            for r in SOURCES["archive.org"].port_results(force=force):
                if all(w in norm(r.title) for w in words):
                    add([r])
        except Exception:
            pass
        results = [r for r in results if r.kind == "Port"]
        seen = {(r.source, r.title, r.size) for r in results}
    if platform_key and len(results) < 6 and platform_key in ArchiveOrg.tags:
        try:
            add(ArchiveOrg().search(query, platform_key=platform_key))
        except Exception:
            pass
    annotate_popular(results)
    return results


def browse_items(platform_key):
    if platform_key == "switchports":
        items = DLA.all_items("switch", ports_only=True)
        try:
            items += SOURCES["archive.org"].port_results()
        except Exception:
            pass
        seen, uniq = set(), []
        for r in items:
            k = norm(r.title)
            if k and k not in seen:
                seen.add(k)
                uniq.append(r)
        uniq.sort(key=lambda r: norm(r.title))
        return uniq
    src_name, arg = PLATFORMS[platform_key]
    src = SOURCES[src_name]
    pk = platform_key
    if hasattr(src, "all_items"):
        items = src.all_items(arg)
    else:
        load_popular()
        titles = (POPULAR or {}).get(pk) or []
        if not titles:
            raise RuntimeError(f"{PLATFORM_LABELS.get(pk, pk)}: no listing — use the search")
        ext = "pkg" if src_name == "dlpsgame" else "zip"
        items = [Result(src_name, t, PLATFORM_LABELS.get(pk, pk), "",
                        meta={"ext": ext, "pk": pk, "pop": i, "search_title": t})
                 for i, t in enumerate(titles)]
        return items
    load_popular()
    if (POPULAR or {}).get(pk):
        def key(r):
            kind = KIND_ORDER.get(r.kind, 1)
            size = -int(r.meta.get("bytes") or 0)
            rk = pop_rank(pk, r.title)
            if rk is not None:
                r.meta["pop"] = rk
                return (0, rk, kind, size, norm(r.title))
            return (1, 0, kind, size, norm(r.title))
        items.sort(key=key)
    return items
