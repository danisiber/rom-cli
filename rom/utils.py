"""Utility functions: console output, formatting, text cleaning, Windows compatibility."""

import html as htmllib
import os
import re
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


def validate(path):
    size = os.path.getsize(path) if os.path.exists(path) else 0
    if size < 1024:
        return False
    if size > 50 * 1024 * 1024:
        return True
    name = path.lower()
    if name.endswith(".zip"):
        with open(path, "rb") as f:
            head = f.read(4)
        return head.startswith(b"PK") or zipfile.is_zipfile(path)
    if name.endswith(".7z"):
        with open(path, "rb") as f:
            return f.read(3) == b"7z\xbc"
    if name.endswith(".nsp"):
        with open(path, "rb") as f:
            return f.read(4) == b"PFS0"
    if name.endswith(".pkg"):
        with open(path, "rb") as f:
            return f.read(4) in (b"\x7fPKG", b"\x7fCNT")
    return True


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
                os.replace(path, new)
                return new
    return path
