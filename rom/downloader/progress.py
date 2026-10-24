"""Thread-safe progress calculation and status formatting for multi-part downloads."""

import threading
import time
from rom.utils import human


class DownloadProgress:
    """Thread-safe multi-threaded download progress tracker with speed and ETA estimation."""

    def __init__(self, total_bytes, on_progress=None, mode="single"):
        self.total_bytes = total_bytes
        self.downloaded_bytes = 0
        self.start_time = time.time()
        self.on_progress = on_progress
        self.mode = mode
        self._lock = threading.Lock()
        self._last_report = 0
        self.speed = 0.0
        self.eta = 0

    def update(self, chunk_size):
        with self._lock:
            self.downloaded_bytes += chunk_size
            now = time.time()
            if self.on_progress and (now - self._last_report >= 0.08 or self.downloaded_bytes >= self.total_bytes):
                self._last_report = now
                self._emit()

    def _emit(self):
        elapsed = max(time.time() - self.start_time, 0.05)
        bps = self.downloaded_bytes / elapsed
        self.speed = bps
        tag = f"[{self.mode}] " if self.mode else ""

        if self.total_bytes > 0:
            pct = min(self.downloaded_bytes * 100.0 / self.total_bytes, 100.0)
            remaining_bytes = max(0, self.total_bytes - self.downloaded_bytes)
            eta_sec = int(remaining_bytes / bps) if bps > 0 else 0
            self.eta = eta_sec
            m, s = divmod(eta_sec, 60)
            h, m = divmod(m, 60)
            eta_str = f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

            # Visual progress bar (16 chars)
            bar_len = 16
            filled = int(bar_len * pct / 100.0)
            bar = "█" * filled + "░" * (bar_len - filled)

            msg = (f"{tag}{bar} {pct:5.1f}%  {human(self.downloaded_bytes)}/{human(self.total_bytes)}  "
                   f"{bps / 1048576:.1f} MB/s  ETA {eta_str}")
        else:
            pct = 0.0
            eta_sec = 0
            eta_str = "--:--"
            msg = f"{tag}{human(self.downloaded_bytes)}  {bps / 1048576:.1f} MB/s"

        info = {
            "speed": bps,
            "speed_str": f"{bps / 1048576:.1f} MB/s",
            "eta": eta_sec,
            "eta_str": eta_str,
            "percent": pct,
            "mode": self.mode,
            "downloaded": self.downloaded_bytes,
            "total": self.total_bytes,
        }

        if not self.on_progress:
            return

        try:
            # Attempt calling with extra info dictionary
            self.on_progress(self.downloaded_bytes, self.total_bytes, msg, info)
        except TypeError:
            try:
                # Fallback to standard 3-arg callback
                self.on_progress(self.downloaded_bytes, self.total_bytes, msg)
            except Exception:
                pass
        except Exception:
            pass

    def finish(self):
        with self._lock:
            if self.on_progress:
                self._emit()
