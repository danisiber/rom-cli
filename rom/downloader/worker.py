"""Worker thread for downloading a specific byte-range slice."""

import time
import urllib.error
import urllib.request

from rom.config import UA
from rom.utils import log_error


def download_chunk_worker(target_file, url, referer, start_byte, end_byte, progress, stop_event, max_retries=5):
    """Download bytes [start_byte, end_byte] inclusive and write to target_file at offset."""
    expected_bytes = end_byte - start_byte + 1
    bytes_downloaded = 0

    with open(target_file, "r+b") as out_fp:
        for attempt in range(max_retries):
            if stop_event.is_set():
                return False

            current_start = start_byte + bytes_downloaded
            if current_start > end_byte:
                return True

            req = urllib.request.Request(url)
            req.add_header("User-Agent", UA)
            if referer:
                req.add_header("Referer", referer)
            req.add_header("Range", f"bytes={current_start}-{end_byte}")

            try:
                with urllib.request.build_opener().open(req, timeout=30) as resp:
                    # Validate server accepted partial content
                    if resp.status != 206:
                        raise RuntimeError(f"Expected HTTP 206 Partial Content, got {resp.status}")

                    out_fp.seek(current_start)
                    chunk_buffer_size = 524288  # 512 KB buffer

                    while not stop_event.is_set():
                        data = resp.read(chunk_buffer_size)
                        if not data:
                            break
                        out_fp.write(data)
                        bytes_downloaded += len(data)
                        progress.update(len(data))

                    if bytes_downloaded == expected_bytes:
                        return True

                    # Connection dropped early without error
                    if stop_event.is_set():
                        return False

                    time.sleep(1 + attempt * 0.5)

            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as err:
                log_error(f"Chunk [{start_byte}-{end_byte}] attempt {attempt + 1}/{max_retries} failed for {url}: {err}", exc=err)
                if stop_event.is_set():
                    return False
                if attempt + 1 >= max_retries:
                    raise RuntimeError(f"Chunk [{start_byte}-{end_byte}] failed after {max_retries} attempts: {err}")
                time.sleep(1 + attempt * 1.0)

    return bytes_downloaded == expected_bytes
