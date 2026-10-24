"""Interactive terminal menu with arrow navigation for Windows and Unix."""

import os
import sys
import time

from rom.utils import write


def fmt_row(r, i):
    size = f"{r.size:>9}" if r.size else " " * 9
    kind = f"{r.kind:<6}" if r.kind else " " * 6
    star = "★ " if r.meta.get("pop") is not None else ""
    return f"{i:>2}  {r.platform[:11]:<11} {kind} {size}  {star}{r.title[:52]}"


def show(results, limit=15):
    write()
    write(f"  {'#':>2}  {'platform':<11} {'type':<6} {'size':>9}  title")
    write("  " + "-" * 80)
    for i, r in enumerate(results[:limit], 1):
        write("  " + fmt_row(r, i))
    write()


def _select_menu_win(results, limit=15):
    """Interactive menu using msvcrt (Windows)."""
    import msvcrt
    items = results[:limit]
    idx, chosen, n_lines = 0, set(), 0
    sys.stdout.write("\033[?25l")
    try:
        while True:
            if n_lines:
                sys.stdout.write(f"\033[{n_lines}A")
            lines = [f"  ↑↓ move · space mark · Enter download · q cancel — {len(items)} found"]
            for i, r in enumerate(items):
                mark = "❯" if i == idx else " "
                line = f"  {mark} {'✔' if i in chosen else ' '} {fmt_row(r, i + 1)}"
                if i == idx:
                    line = "\033[7m" + line + "\033[0m"
                lines.append(line)
            write("\033[J")
            write("\n".join(lines) + "\n")
            n_lines = len(lines)
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):  # special key prefix
                ch2 = msvcrt.getwch()
                if ch2 == "H":      # Arrow Up
                    idx = max(0, idx - 1)
                elif ch2 == "P":    # Arrow Down
                    idx = min(len(items) - 1, idx + 1)
            elif ch in ("\r", "\n"):
                return [items[i] for i in sorted(chosen)] or [items[idx]]
            elif ch == " ":
                chosen.symmetric_difference_update({idx})
            elif ch in ("q", "Q", "\x03"):
                return []
            elif ch.isdigit():
                num = int(ch)
                if 1 <= num <= len(items):
                    idx = num - 1
    finally:
        write("\033[?25h")
        write("\n")


def select_menu(results, limit=15):
    if sys.platform == "win32":
        return _select_menu_win(results, limit)
    import select as _select
    import termios
    import tty
    items = results[:limit]
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    idx, chosen, n_lines = 0, set(), 0
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?25l")
        while True:
            if n_lines:
                sys.stdout.write(f"\033[{n_lines}A")
            lines = [f"  ↑↓ move · space mark · Enter download · q cancel — {len(items)} found"]
            for i, r in enumerate(items):
                mark = "❯" if i == idx else " "
                line = f"  {mark} {'✔' if i in chosen else ' '} {fmt_row(r, i + 1)}"
                if i == idx:
                    line = "\033[7m" + line + "\033[0m"
                lines.append(line)
            write("\033[J")
            write("\n".join(lines) + "\n")
            n_lines = len(lines)
            ch = os.read(fd, 1).decode("utf-8", "replace")
            if ch == "\x1b":
                seq = b""
                stop = time.time() + 0.4
                while time.time() < stop:
                    if _select.select([fd], [], [], 0.05)[0]:
                        try:
                            seq += os.read(fd, 64)
                        except OSError:
                            break
                        if seq.endswith((b"A", b"B")):
                            break
                    elif seq:
                        break
                if seq.endswith(b"A"):
                    idx = max(0, idx - 1)
                elif seq.endswith(b"B"):
                    idx = min(len(items) - 1, idx + 1)
            elif ch in ("\r", "\n"):
                return [items[i] for i in sorted(chosen)] or [items[idx]]
            elif ch == " ":
                chosen.symmetric_difference_update({idx})
            elif ch in ("q", "Q", "\x03"):
                return []
            elif ch.isdigit():
                num = int(ch)
                if 1 <= num <= len(items):
                    idx = num - 1
    finally:
        write("\033[?25h")
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        write("\n")
