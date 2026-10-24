"""Base models and networking helper for providers."""

import time
import urllib.error
import urllib.request

from rom.config import UA


def request(url, data=None, headers=None, timeout=40, retries=3, method=None):
    """Perform an HTTP request with retry logic and standard browser headers."""
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("User-Agent", UA)
        req.add_header("Accept-Language", "en-US,en;q=0.9,pt-BR;q=0.8")
        req.add_header("Accept", "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.build_opener().open(req, timeout=timeout) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                time.sleep(1 + attempt)
                continue
            return e.code, e.headers, e.read()
        except Exception as e:
            last = e
            if attempt + 1 < retries:
                time.sleep(1 + attempt)
    raise last


class Result:
    """Represents a found game/ROM entry."""
    __slots__ = ("source", "title", "platform", "size", "page", "meta")

    def __init__(self, source, title, platform, page, size="", meta=None):
        self.source = source
        self.title = title
        self.platform = platform
        self.page = page
        self.size = size
        self.meta = meta or {}

    @property
    def kind(self):
        return self.meta.get("kind", "")

    @property
    def ext(self):
        return self.meta.get("ext", "")

    def __repr__(self):
        return f"<Result {self.platform} '{self.title}' [{self.source}]>"


class BaseProvider:
    """Interface for ROM catalog and download providers."""
    name = ""

    def search(self, query, platform_key=None, on_progress=None, force=False):
        raise NotImplementedError

    def resolve(self, result):
        raise NotImplementedError
