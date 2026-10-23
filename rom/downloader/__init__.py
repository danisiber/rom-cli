"""Downloader module interface."""

import os
import re

from rom.config import LOG_FILE
from rom.downloader.engine import stream
from rom.providers import DLP, SOURCES
from rom.utils import (
    clear_status,
    ext_for,
    fix_magic_ext,
    human,
    log_error,
    safe_name,
    status,
    unique_path,
    validate,
    write,
)


def download(result, outdir, on_progress=None):
    """Resolve and download a ROM Result to outdir with progress updates."""
    if on_progress:
        on_progress(0, 0, f"looking for: {result.title[:45]}…")
    if result.meta.get("search_title"):
        found = DLP.search(result.meta["search_title"], result.meta.get("pk"))
        if not found:
            raise RuntimeError(f"could not find '{result.title}' on dlpsgame")
        result = found[0]
    src = SOURCES[result.source]
    if on_progress:
        on_progress(0, 0, f"getting link: {result.title[:45]}…")
    url, name = src.resolve(result)
    ext = ext_for(result, name, url)
    folder = os.path.join(outdir, re.sub(r'[\\/:*?"<>|]', "", result.platform or "outros"))
    os.makedirs(folder, exist_ok=True)
    path = unique_path(os.path.join(folder, safe_name(name or result.title, "rom", ext)))

    stream(url, result.page if result.source not in ("dlarchive", "nps") else None, on_progress, path)
    path = fix_magic_ext(path)
    if not validate(path):
        try:
            os.remove(path)
        except OSError:
            pass
        raise RuntimeError("invalid file (expired link?)")
    return path


def run_cli_download(picked, outdir):
    """Download a list of picked Results in CLI mode."""
    ok = 0
    for i, r in enumerate(picked, 1):
        write()
        write(f"  [{i}/{len(picked)}] {r.title} ({r.platform})")
        try:
            path = download(r, outdir, on_progress=lambda a, b, m: status(f"   {m}"))
            clear_status()
            write(f"  ✔ done: {path}  ({human(os.path.getsize(path))})")
            ok += 1
        except Exception as e:
            clear_status()
            log_error(f"Download failed for '{r.title}' ({r.platform}): {e}", exc=e)
            write(f"  ✖ failed: {e}")
            write(f"    (log: {LOG_FILE})")
    write()
    write(f"  {ok}/{len(picked)} downloaded to {outdir}")
    return 0 if ok else 1


__all__ = ["download", "run_cli_download", "stream"]
