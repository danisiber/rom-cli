"""RomsGames provider: search and download from romsgames.net."""

import json
import re
import urllib.parse

from rom.config import LABELS
from rom.providers.base import BaseProvider, Result, request
from rom.utils import clean

PLATFORM_RE = re.compile(r"^/([a-z0-9\-]+?)-rom-")


class RomsGames(BaseProvider):
    name = "romsgames"
    base = "https://www.romsgames.net"

    def search(self, query, prefixes=None):
        url = f"{self.base}/search/hint/?q={urllib.parse.quote_plus(query)}"
        st, _, body = request(url, headers={"X-Requested-With": "XMLHttpRequest",
                                            "Accept": "application/json"}, retries=2)
        if st != 200:
            return []
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except Exception:
            return []
        out, seen = [], set()
        for item in data:
            href = item.get("url") or ""
            pm = PLATFORM_RE.match(href)
            if not pm:
                continue
            prefix = pm.group(1)
            if prefixes and prefix not in prefixes:
                continue
            if href in seen:
                continue
            seen.add(href)
            title = clean(item.get("name") or "")
            if not title:
                continue
            thumb = item.get("thumbnailImageURL") or ""
            out.append(Result(self.name, title, LABELS.get(prefix, prefix.replace("-", " ").title()),
                              self.base + href, meta={"ext": "zip", "thumb": thumb}))
        return out

    def resolve(self, result):
        st, _, body = request(result.page, retries=2)
        if st != 200:
            raise RuntimeError(f"page unavailable ({st})")
        page = body.decode("utf-8", "replace")
        action = re.search(r'<form[^>]*id="download-form"[^>]*action="([^"]+)"', page)
        media = re.search(r'data-media-id="(\d+)"', page)
        if not action or not media:
            raise RuntimeError("download button not found")
        form = urllib.parse.urljoin(self.base, action.group(1))
        st, _, body = request(form + "?download",
                              data=f"mediaId={media.group(1)}&g-recaptcha-response=".encode(),
                              headers={"accept": "application/json",
                                       "Content-Type": "application/x-www-form-urlencoded",
                                       "Referer": result.page}, retries=3)
        if st != 200:
            raise RuntimeError(f"download server responded {st}")
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except Exception:
            raise RuntimeError("invalid download response")
        url = data.get("downloadUrl")
        if not url:
            raise RuntimeError("download link missing")
        return url, urllib.parse.unquote(data.get("downloadName") or "")
