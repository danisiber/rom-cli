"""Utility functions: console output, formatting, text cleaning, Windows compatibility."""

import html as htmllib
import os
import re
import struct
import sys
import unicodedata
import urllib.parse
import zipfile

import time

from rom.config import BAD, CACHE_DIR, EXT_RE, LOG_FILE, PLATFORM_LABELS, STOP, TTY


def log_error(msg, exc=None):
    """Log an error message and optional exception traceback to LOG_FILE."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] ERROR: {msg}\n")
            if exc:
                if isinstance(exc, Exception):
                    import traceback
                    tb = traceback.format_exc()
                    if tb and "NoneType: None" not in tb:
                        f.write(f"{tb}\n")
                    else:
                        f.write(f"  {type(exc).__name__}: {exc}\n")
                else:
                    f.write(f"  {exc}\n")
    except Exception:
        pass


def log_info(msg):
    """Log an info message to LOG_FILE."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] INFO: {msg}\n")
    except Exception:
        pass


def init_windows_console():
    """Enable VT100 / ANSI escape sequences and UTF-8 encoding on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes as _ctypes
            _kernel32 = _ctypes.windll.kernel32
            _h = _kernel32.GetStdHandle(-11)
            _m = _ctypes.c_ulong()
            _kernel32.GetConsoleMode(_h, _ctypes.byref(_m))
            _kernel32.SetConsoleMode(_h, _m.value | 4)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def write(text="", newline=True):
    sys.stdout.write(text)
    if newline and not text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()


def status(msg):
    if TTY:
        write(f"\r\033[K  {msg}")
    else:
        write(f"  {msg}\n")


def clear_status():
    if TTY:
        write("\r\033[K")


def human(n):
    if not n:
        return "?"
    n = float(n)
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = htmllib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def significant(words):
    sig = [w for w in words if w not in STOP and len(w) > 1]
    return sig or words


def pretty_title(fn):
    base = EXT_RE.sub("", fn or "")
    base = re.sub(r"\[[^\]]*\]", " ", base)
    base = re.sub(r"\bv\d+(?:\.\d+)*\b", " ", base, flags=re.I)
    base = base.replace("_", " ")
    base = re.sub(r"^\s*download\s+", "", base, flags=re.I)
    base = re.sub(r"\s+", " ", base).strip(" .-")
    return base or (fn or "")


def kind_of(fn):
    low = (fn or "").lower()
    if re.search(r"\bports?\b", low) or "homebrew" in low:
        return "Port"
    if "[dlc" in low or " dlc" in low or "dlc " in low:
        return "DLC"
    if "[up " in low or "upd" in low or "update" in low or re.search(r"\bv\d+", low):
        return "Update"
    if "[base]" in low:
        return "Base"
    return ""


def platform_of(fn, folder):
    ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
    low = (fn or "").lower()
    flat = re.sub(r"[_\-]+", " ", low)
    if (ext in ("nsp", "xci", "nsz") or re.search(r"\b(?:nintendo )?switch\b", flat)
            or re.search(r"\b01[0-9a-f]{12}\b", low) or kind_of(fn) == "Port"):
        return "switch", "Switch"
    fl = (folder or "").lower()
    for token, key in (("nintendo_ds", "nds"), ("gameboy_advance", "gba"),
                       ("super_nintendo", "snes"), ("playstation_2", "ps2"),
                       ("playstation_portable", "psp"), ("game_pc", "pc"),
                       ("gameboy_color", "gbc"), ("gameboy", "gb"), ("sega", "genesis")):
        if token in fl:
            return key, PLATFORM_LABELS.get(key, key.upper())
    return "", "Other"


def safe_name(name, fallback, ext):
    base = clean(name) or fallback
    base = EXT_RE.sub("", base)
    base = re.sub(r'[\\/:*?"<>|]', " ", base)
    base = re.sub(r"\s+", " ", base).strip(" .")[:140] or fallback
    return f"{base}{ext}"


def unique_path(path):
    root, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(path):
        path = f"{root} ({i}){ext}"
        i += 1
    return path


def safe_replace(src, dst, max_retries=10, delay=0.15):
    """Safely replace src with dst, retrying on transient Windows file locking/sharing violations."""
    for attempt in range(max_retries):
        try:
            os.replace(src, dst)
            return
        except (PermissionError, OSError):
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)


def check_integrity(path):
    """Validate file and archive integrity, returning (is_valid, reason_if_invalid)."""
    if not path or not os.path.isfile(path):
        return False, "File does not exist on disk"
    try:
        size = os.path.getsize(path)
    except OSError as e:
        return False, f"File access error: {e}"

    if size < 1024:
        return False, f"File too small ({human(size)})"

    name = path.lower()

    # 1. 7-Zip Archive (.7z) integrity validation
    if name.endswith(".7z"):
        if size < 32:
            return False, "Corrupted archive (size under 32 bytes)"
        try:
            with open(path, "rb") as f:
                head = f.read(32)
            if len(head) < 32 or not head.startswith(b"7z\xbc\xaf'\x1c"):
                return False, "Invalid 7z signature (corrupted archive)"
            # 7z 32-byte header structure:
            # 6s Signature, B Major, B Minor, I StartHdrCRC, Q NextHdrOffset, Q NextHdrSize, I NextHdrCRC
            _, _, _, _, next_hdr_offset, next_hdr_size, _ = struct.unpack("<6sBBIQQI", head)
            expected_min = 32 + next_hdr_offset + next_hdr_size
            # If actual file size is smaller than offset + header size, the archive is truncated!
            if size < expected_min:
                return False, f"Corrupted upstream: server gave {human(size)}, but archive requires {human(expected_min)}"
            if next_hdr_offset > 0 and next_hdr_size > 0:
                with open(path, "rb") as f:
                    f.seek(32 + next_hdr_offset)
                    trailer = f.read(min(next_hdr_size, 1024))
                    if not trailer:
                        return False, "Corrupted 7z archive (truncated end header)"
            return True, ""
        except Exception as e:
            return False, f"7z parsing error: {e}"

    # 2. ZIP Archive (.zip) integrity validation
    if name.endswith(".zip"):
        if not zipfile.is_zipfile(path):
            return False, f"Corrupted upstream: ZIP archive is incomplete/truncated ({human(size)})"
        try:
            with zipfile.ZipFile(path, "r") as zf:
                _ = zf.infolist()
            return True, ""
        except Exception as e:
            return False, f"Corrupted ZIP archive: {e}"

    # 3. RAR Archive (.rar) magic validation
    if name.endswith(".rar"):
        if size < 7:
            return False, "RAR file too small"
        try:
            with open(path, "rb") as f:
                head = f.read(8)
            # RAR 1.5 - 4.x: Rar!\x1a\x07\x00 | RAR 5.0+: Rar!\x1a\x07\x01\x00
            if not head.startswith(b"Rar!\x1a\x07"):
                return False, "Invalid RAR archive signature"
            return True, ""
        except Exception as e:
            return False, f"RAR read error: {e}"

    # 4. Nintendo Switch PFS0 (.nsp)
    if name.endswith(".nsp"):
        try:
            with open(path, "rb") as f:
                if f.read(4) != b"PFS0":
                    return False, "Invalid NSP PFS0 header"
            return True, ""
        except Exception as e:
            return False, f"NSP read error: {e}"

    # 5. Nintendo Switch XCI (.xci)
    if name.endswith(".xci"):
        try:
            with open(path, "rb") as f:
                f.seek(0x100)
                if f.read(4) != b"HEAD":
                    return False, "Invalid XCI HEAD header"
            return True, ""
        except Exception as e:
            return False, f"XCI read error: {e}"

    # 6. PlayStation Package (.pkg)
    if name.endswith(".pkg"):
        try:
            with open(path, "rb") as f:
                if f.read(4) not in (b"\x7fPKG", b"\x7fCNT"):
                    return False, "Invalid PKG header"
            return True, ""
        except Exception as e:
            return False, f"PKG read error: {e}"

    # 7. Disc image (.iso)
    if name.endswith(".iso"):
        if size < 100 * 1024:
            return False, "ISO file too small"
        return True, ""

    return True, ""


def validate(path):
    """Validate file and archive integrity to detect truncated or corrupted downloads."""
    valid, _ = check_integrity(path)
    return valid


def ext_for(result, name, url):
    for cand in (name, urllib.parse.urlparse(url).path):
        m = EXT_RE.search(cand or "")
        if m:
            return "." + m.group(1).lower()
    if result.meta.get("ext"):
        return "." + result.meta["ext"]
    return ".nsp" if result.platform == "Switch" else ".zip"


def fix_magic_ext(path):
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return path
    for magic, ext in ((b"PK\x03\x04", ".zip"), (b"Rar!", ".rar"), (b"7z\xbc", ".7z"),
                       (b"PFS0", ".nsp"), (b"HEAD", ".xci"), (b"\x7fPKG", ".pkg"),
                       (b"\x7fCNT", ".pkg")):
        if head.startswith(magic):
            root, cur = os.path.splitext(path)
            if cur.lower() != ext:
                new = root + ext
                new = unique_path(new)
                safe_replace(path, new)
                return new
    return path
