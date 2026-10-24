"""Main entrypoint for rom CLI."""

import argparse
import os
import sys

from rom.catalog import browse_items, load_popular, rank, search
from rom.config import INDEX_FILE, LOG_FILE, OUT_DIR, PLATFORM_LABELS, PLATFORMS, get_out_dir, set_out_dir
from rom.downloader import run_cli_download
from rom.providers import DLA, DLP, SOURCES
from rom.ui import _has_textual, run_tui, select_menu, show
from rom.utils import clear_status, init_windows_console, log_error, log_info, status, write


def main():
    init_windows_console()

    ap = argparse.ArgumentParser(description="Search and download ROMs/ISOs/Switch games.")
    ap.add_argument("query", nargs="*")
    ap.add_argument("-p", "--platform", help="switch, snes, gba, ps2, nds, wii… (see -l)")
    ap.add_argument("-l", "--platforms", action="store_true", help="list platforms")
    ap.add_argument("-y", "--yes", action="store_true", help="download the best match without asking")
    ap.add_argument("--list", action="store_true", help="list results only")
    ap.add_argument("--print-url", action="store_true", help="print the direct link and exit")
    ap.add_argument("--refresh", action="store_true", help="rebuild the catalog index")
    ap.add_argument("--index", action="store_true", help="download/print the index and exit")
    ap.add_argument("-n", "--number", type=int, default=15, help="how many results to show")
    ap.add_argument("-o", "--out", default=get_out_dir(), help="destination folder")
    ap.add_argument("--set-dir", metavar="PATH", help="set default download directory and exit")
    ap.add_argument("--show-dir", action="store_true", help="show current default download directory and exit")
    ap.add_argument("--debug", action="store_true", help="show verbose error tracebacks and log to file")
    args = ap.parse_args()

    if args.set_dir:
        new_dir = set_out_dir(args.set_dir)
        try:
            os.makedirs(new_dir, exist_ok=True)
        except OSError:
            pass
        write(f"  ✔ default download directory set to: {new_dir}")
        return 0

    if args.show_dir:
        write(f"  default download directory: {get_out_dir()}")
        return 0

    if args.platforms:
        write("  platforms: " + ", ".join(sorted(PLATFORMS)))
        return 0

    key = (args.platform or "").lower().strip()
    if key and key not in PLATFORMS:
        ap.error(f"unknown platform: {key}\n  use: {', '.join(sorted(PLATFORMS))}")

    if args.index:
        write("  building index…")
        idx = DLA.load_index(force=args.refresh,
                             on_progress=lambda d, t: status(f"   {d}/{t} pages"))
        clear_status()
        with_rom = sum(1 for e in idx if e["ext"] in ("nsp", "xci", "nsz"))
        write(f"  {len(idx)} files in the index ({with_rom} for Switch)")
        write(f"  cache: {INDEX_FILE}")
        pop = load_popular(force=args.refresh)
        top = ", ".join(f"{k}({len(v)})" for k, v in sorted(pop.items()) if v)
        write(f"  best sellers (Wikipedia): {top}")
        return 0

    if not args.query:
        if args.list:
            if not key:
                write("  use -p <platform> (e.g. rom -p switch --list)  ·  or rom -l")
                return 1
            try:
                items = browse_items(key)
            except Exception as e:
                log_error(f"Browse failed for '{key}': {e}", exc=e)
                write(f"  ✖ {e}")
                write(f"    (log: {LOG_FILE})")
                if args.debug:
                    import traceback
                    traceback.print_exc()
                return 1
            show(items, args.number)
            write(f"  {len(items)} items in the {PLATFORM_LABELS.get(key, key)} catalog"
                  " — the TUI (rom) browses everything")
            return 0
        if not sys.stdin.isatty() or not _has_textual():
            write('  type: rom -p switch "game name"   (or rom -l)')
            return 0

    query = " ".join(args.query)

    if not query:
        run_tui(key, "", args.out, args.refresh)
        return 0

    status(f"searching for '{query}'…")
    try:
        results = search(query, key or None,
                         on_progress=lambda d, t: status(f"   index {d}/{t} pages"),
                         force=args.refresh)
    except Exception as e:
        clear_status()
        log_error(f"Search failed for '{query}': {e}", exc=e)
        write(f"  ✖ search failed: {e}")
        write(f"    (log: {LOG_FILE})")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1
    clear_status()

    if not results:
        write("  ✖ nothing found. Try a different name or platform.")
        return 1

    results = rank(results, query)
    outdir = os.path.expanduser(args.out)

    if args.list:
        show(results, args.number)
        return 0

    if args.print_url:
        for r in results[:args.number]:
            write(f"  {r.title} [{r.platform} {r.kind or '-'} {r.size or '?'}]")
            if r.source == "dlpsgame":
                for u in DLP.links(r.page):
                    write(f"  {u}")
            else:
                try:
                    url, name = SOURCES[r.source].resolve(r)
                    write(f"  {url}")
                except Exception as e:
                    write(f"  (error: {e})")
            write()
        return 0

    if args.yes or not sys.stdin.isatty():
        show(results, args.number)
        return run_cli_download(results[:1], outdir)

    picked = select_menu(results, args.number)
    if not picked:
        write("  cancelled.")
        return 0
    return run_cli_download(picked, outdir)


def cli_entrypoint():
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        clear_status()
        write("\n  cancelled.")
        sys.exit(130)


if __name__ == "__main__":
    cli_entrypoint()
