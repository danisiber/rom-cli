"""Core downloader engine supporting segmented multi-threaded chunking (IDM-style) with auto-fallback."""

import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from rom.config import UA
from rom.downloader.progress import DownloadProgress
from rom.downloader.worker import download_chunk_worker
from rom.utils import human, log_error, log_info, safe_replace


def probe_url(url, referer=None, timeout=15):
    """Probe URL to determine total size and HTTP Range (partial content) support."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    if referer:
        req.add_header("Referer", referer)
    req.add_header("Range", "bytes=0-0")

    try:
        with urllib.request.build_opener().open(req, timeout=timeout) as resp:
            status = resp.status
            headers = resp.headers

            # Check if Range is supported
            if status == 206:
                cr = headers.get("Content-Range") or ""
                # Format: bytes 0-0/1234567
                m = re.search(r"/(\d+)$", cr)
                if m:
                    return True, int(m.group(1))

            # If server returned 200 instead of 206, it ignored Range
            cl = headers.get("Content-Length")
            total = int(cl) if cl and cl.isdigit() else 0
            supports_range = (headers.get("Accept-Ranges") == "bytes")
            return supports_range, total

    except Exception:
        return False, 0


def single_stream(url, referer, on_progress, dest, stop_event=None):
    """Single-connection fallback stream download with range resume."""
    part = dest + ".part"
    pos = os.path.getsize(part) if os.path.exists(part) else 0

    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    if referer:
        req.add_header("Referer", referer)
    if pos:
        req.add_header("Range", f"bytes={pos}-")

    with urllib.request.build_opener().open(req, timeout=60) as r:
        resumed = pos and r.status == 206
        if not resumed:
            pos = 0

        total = int(r.headers.get("Content-Length") or 0) + pos
        read = pos
        progress = DownloadProgress(total, on_progress, mode="single")
        if pos:
            progress.update(pos)

        with open(part, "ab" if resumed else "wb") as f:
            while True:
                if stop_event and stop_event.is_set():
                    return read
                chunk = r.read(524288)
                if not chunk:
                    break
                f.write(chunk)
                read += len(chunk)
                progress.update(len(chunk))

    if total > 0 and read < total:
        raise RuntimeError(f"Download incomplete: received {read} bytes out of {total} bytes")

    safe_replace(part, dest)
    return read


def stream(url, referer, on_progress, dest):
    """Stream download: uses multi-threaded chunking (IDM-style) when supported, or single-stream fallback."""
    part = dest + ".part"
    stop_event = threading.Event()

    # Step 1: Probe server capabilities
    if on_progress:
        on_progress(0, 0, "connecting to download server…")
    can_chunk, total_size = probe_url(url, referer)

    # Threshold: files < 15 MB don't benefit much from multi-threading overhead
    min_chunk_size = 15 * 1024 * 1024
    if not can_chunk or total_size < min_chunk_size:
        return single_stream(url, referer, on_progress, dest, stop_event)

    # Step 2: Determine dynamic worker count based on size
    if total_size < 50 * 1024 * 1024:
        num_workers = 2
    elif total_size < 300 * 1024 * 1024:
        num_workers = 4
    elif total_size < 1024 * 1024 * 1024:
        num_workers = 6
    else:
        num_workers = 8  # Large ISOs (Xbox, PS2, PS3)

    # Step 3: Pre-allocate file space (avoids double disk space and merge lag)
    # If partial download already exists with exact size, we can reuse it
    cur_size = os.path.getsize(part) if os.path.exists(part) else 0
    if cur_size != total_size:
        if on_progress:
            on_progress(0, total_size, f"allocating disk space ({human(total_size)})…")
        with open(part, "wb") as f:
            f.truncate(total_size)

    # Step 4: Partition byte ranges
    chunk_size = total_size // num_workers
    ranges = []
    for i in range(num_workers):
        start = i * chunk_size
        end = (i + 1) * chunk_size - 1 if i < num_workers - 1 else total_size - 1
        ranges.append((start, end))

    if on_progress:
        on_progress(0, total_size, f"starting {num_workers} parallel download chunks…")

    progress = DownloadProgress(total_size, on_progress, mode=f"{num_workers} chunks")

    # Step 5: Execute parallel chunk workers
    download_ok = False
    try:
        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            futures = []
            for s, e in ranges:
                time.sleep(0.05)  # 50ms stagger jitter to prevent burst rate-limiting
                futures.append(pool.submit(
                    download_chunk_worker,
                    part, url, referer, s, e, progress, stop_event
                ))

            # Wait for all chunks to finish
            for fut in as_completed(futures):
                fut.result()

        progress.finish()
        download_ok = True
    except KeyboardInterrupt:
        stop_event.set()
        raise
    except Exception as err:
        stop_event.set()
        log_error(f"Multi-thread chunk download failed for {url}: {err}", exc=err)
        # Fallback to single stream if chunking encountered unexpected server error
        if not os.path.exists(dest):
            try:
                log_info(f"Falling back to single-stream download for {url}")
                return single_stream(url, referer, on_progress, dest)
            except Exception as single_err:
                log_error(f"Single-stream fallback also failed for {url}: {single_err}", exc=single_err)
                raise single_err
        raise err

    if download_ok:
        safe_replace(part, dest)
        return total_size
