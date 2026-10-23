"""Thread-safe progress calculation and status formatting for multi-part downloads."""

import threading
import time
from rom.utils import human


class DownloadProgress:
    """Thread-safe multi-threaded download progress tracker."""

    def __init__(self, total_bytes, on_progress=None, mode="single"):
        self.total_bytes = total_bytes
        self.downloaded_bytes = 0
        self.start_time = time.time()
        self.on_progress = on_progress
        self.mode = mode
        self._lock = threading.Lock()
        self._last_report = 0

    def update(self, chunk_size):
        with self._lock:
            self.downloaded_bytes += chunk_size
            now = time.time()
            if self.on_progress and (now - self._last_report >= 0.1 or self.downloaded_bytes >= self.total_bytes):
                self._last_report = now
                self._emit()

    def _emit(self):
        elapsed = max(time.time() - self.start_time, 0.05)
        bps = self.downloaded_bytes / elapsed
        tag = f"[{self.mode}] " if self.mode else ""
        if self.total_bytes > 0:
            pct = min(self.downloaded_bytes * 100.0 / self.total_bytes, 100.0)
            msg = (f"{tag}{pct:5.1f}%  {human(self.downloaded_bytes)}/{human(self.total_bytes)}  "
                   f"{bps / 1048576:.1f} MB/s")
        else:
            msg = f"{tag}{human(self.downloaded_bytes)}  {bps / 1048576:.1f} MB/s"
        try:
            self.on_progress(self.downloaded_bytes, self.total_bytes, msg)
        except Exception:
            pass

    def finish(self):
        with self._lock:
            if self.on_progress:
                self._emit()
