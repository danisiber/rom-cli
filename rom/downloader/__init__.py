"""Downloader module interface."""

import os
import re

from rom.config import LOG_FILE
from rom.downloader.engine import stream
from rom.providers import DLP, SOURCES
from rom.utils import (
    check_integrity,
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


def check_already_downloaded(result, outdir, name=None, ext=None):
    """Check if a Result has already been successfully downloaded to outdir."""
    if not outdir:
        return None
    folder = os.path.join(outdir, re.sub(r'[\\/:*?"<>|]', "", result.platform or "outros"))
    if not os.path.isdir(folder):
        return None

    # 1. Exact candidate paths if name or ext known
    candidates = []
    if name and ext:
        candidates.append(os.path.join(folder, safe_name(name, "rom", ext)))
    if ext:
        candidates.append(os.path.join(folder, safe_name(result.title, "rom", ext)))
    if result.meta.get("ext"):
        candidates.append(os.path.join(folder, safe_name(result.title, "rom", "." + result.meta["ext"].lstrip("."))))

    for cand in candidates:
        if os.path.isfile(cand) and os.path.getsize(cand) > 1024 and validate(cand):
            return cand

    # 2. Check existing files in folder matching the title prefix
    clean_target = safe_name(result.title, "rom", "").strip().lower()
    clean_name = safe_name(name, "rom", "").strip().lower() if name else ""

    try:
        entries = os.listdir(folder)
    except OSError:
        return None

    for fname in entries:
        if fname.endswith(".part"):
            continue
        full_path = os.path.join(folder, fname)
        if not os.path.isfile(full_path):
            continue
        stem, _ = os.path.splitext(fname)
        stem_norm = stem.strip().lower()
        # Remove trailing (2), (3) duplicate tags if present
        stem_norm = re.sub(r"\s*\(\d+\)$", "", stem_norm)

        if (clean_target and stem_norm == clean_target) or (clean_name and stem_norm == clean_name):
            if os.path.getsize(full_path) > 1024 and validate(full_path):
                return full_path

    return None


def download(result, outdir, on_progress=None):
    """Resolve and download a ROM Result to outdir with progress updates, skipping if already downloaded."""
    # Pre-check 1: Check if already downloaded before resolving link
    cached_path = check_already_downloaded(result, outdir)
    if cached_path:
        size = os.path.getsize(cached_path)
        if on_progress:
            on_progress(size, size, f"already downloaded: {os.path.basename(cached_path)}", {
                "speed": 0.0,
                "speed_str": "0 B/s",
                "eta": 0,
                "eta_str": "00:00",
                "percent": 100.0,
                "mode": "cached",
                "downloaded": size,
                "total": size,
                "already_exists": True,
                "path": cached_path,
            })
        return cached_path

    if on_progress:
        on_progress(0, 0, f"searching source link: {result.title[:45]}…")
    if result.meta.get("search_title"):
        pk = result.meta.get("pk")
        stitle = result.meta["search_title"]
        if result.source == "dlpsgame":
            found = DLP.search(stitle, pk)
        else:
            from rom.catalog import search as cat_search
            found = cat_search(stitle, pk)
        if not found:
            raise RuntimeError(f"could not find '{result.title}' on {result.source}")
        result = found[0]
    src = SOURCES[result.source]
    if on_progress:
        on_progress(0, 0, f"getting direct mirror link: {result.title[:45]}…")
    url, name = src.resolve(result)
    ext = ext_for(result, name, url)
    folder = os.path.join(outdir, re.sub(r'[\\/:*?"<>|]', "", result.platform or "outros"))
    os.makedirs(folder, exist_ok=True)

    # Pre-check 2: Check if exact resolved file name already exists and is valid
    canonical_name = safe_name(name or result.title, "rom", ext)
    canonical_path = os.path.join(folder, canonical_name)
    if os.path.isfile(canonical_path) and os.path.getsize(canonical_path) > 1024 and validate(canonical_path):
        size = os.path.getsize(canonical_path)
        if on_progress:
            on_progress(size, size, f"already downloaded: {canonical_name}", {
                "speed": 0.0,
                "speed_str": "0 B/s",
                "eta": 0,
                "eta_str": "00:00",
                "percent": 100.0,
                "mode": "cached",
                "downloaded": size,
                "total": size,
                "already_exists": True,
                "path": canonical_path,
            })
        return canonical_path

    path = unique_path(canonical_path)

    stream(url, result.page if result.source not in ("dlarchive", "nps") else None, on_progress, path)

    if on_progress:
        on_progress(0, 0, "verifying file integrity…")
    path = fix_magic_ext(path)
    valid, reason = check_integrity(path)
    if not valid:
        try:
            os.remove(path)
        except OSError:
            pass

        # If romsgames file is corrupted upstream, try automatic fallback to Archive.org!
        if result.source == "romsgames" and result.platform:
            from rom.providers import ARCHIVE_ORG
            if on_progress:
                on_progress(0, 0, f"upstream corrupt ({reason}) — searching Archive.org mirror…")
            try:
                ao_results = ARCHIVE_ORG.search(result.title, result.platform.lower().replace("playstation 2", "ps2").replace("playstation", "ps1"))
                if not ao_results:
                    clean_t = re.sub(r"\s*\(.*?\)", "", result.title).strip()
                    ao_results = ARCHIVE_ORG.search(clean_t, "ps2" if "2" in result.platform else None)
                if ao_results:
                    best_alt = ao_results[0]
                    for alt in ao_results:
                        if "europe" in alt.title.lower() or "usa" in alt.title.lower() or alt.title == result.title:
                            best_alt = alt
                            break
                    if on_progress:
                        on_progress(0, 0, f"found alternative mirror on Archive.org: {best_alt.title[:35]}…")
                    return download(best_alt, outdir, on_progress)
            except Exception as fb_err:
                log_error(f"Fallback to Archive.org failed: {fb_err}", exc=fb_err)

        raise RuntimeError(reason)
    return path


def run_cli_download(picked, outdir):
    """Download a list of picked Results in CLI mode with rich progress display."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.progress import (
            BarColumn,
            DownloadColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeRemainingColumn,
            TransferSpeedColumn,
        )
        use_rich = True
        console = Console()
    except Exception:
        use_rich = False

    ok = 0
    total_count = len(picked)

    for i, r in enumerate(picked, 1):
        existing = check_already_downloaded(r, outdir)
        if existing:
            size_str = human(os.path.getsize(existing))
            if use_rich:
                console.print()
                header = f"[bold yellow]✔ [{i}/{total_count} ALREADY DOWNLOADED][/bold yellow] [bold white]{r.title}[/bold white]\n[dim]Location: {existing} ({size_str}) — Skipped duplicate[/dim]"
                console.print(Panel(header, border_style="yellow", padding=(0, 1)))
            else:
                write()
                write(f"  [{i}/{total_count}] {r.title} ({r.platform})")
                write(f"  ✔ already downloaded (skipped): {existing}  ({size_str})")
            ok += 1
            continue
        if use_rich:
            console.print()
            info_line = f"[dim]Platform:[/dim] [cyan]{r.platform}[/cyan]"
            if r.kind:
                info_line += f"  •  [dim]Type:[/dim] [magenta]{r.kind}[/magenta]"
            if r.size:
                info_line += f"  •  [dim]Size:[/dim] [yellow]{r.size}[/yellow]"
            info_line += f"  •  [dim]Source:[/dim] [blue]{r.source}[/blue]"

            header = f"[bold cyan]▼ [{i}/{total_count}][/bold cyan] [bold white]{r.title}[/bold white]\n{info_line}"
            console.print(Panel(header, border_style="cyan", padding=(0, 1)))

            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(bar_width=28, complete_style="cyan", finished_style="bright_green"),
                "[progress.percentage]{task.percentage:>3.0f}%",
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=False,
            )

            task_id = progress.add_task("Preparing download…", total=None)

            def rich_on_progress(downloaded, total, msg, info=None, p=progress, tid=task_id):
                if total and total > 0:
                    p.update(tid, total=total, completed=downloaded, description=info.get("mode", "Downloading") if info else "Downloading")
                else:
                    clean_msg = re.sub(r"^[\[\d\w\s]+\]\s*", "", msg)
                    p.update(tid, description=clean_msg[:40] if clean_msg else msg[:40])

            try:
                with progress:
                    path = download(r, outdir, on_progress=rich_on_progress)
                console.print(f"  [bold green]✔ Completed:[/bold green] [white]{path}[/white]  [dim]({human(os.path.getsize(path))})[/dim]")
                ok += 1
            except Exception as e:
                log_error(f"Download failed for '{r.title}' ({r.platform}): {e}", exc=e)
                console.print(f"  [bold red]✖ Failed:[/bold red] {e}")
                console.print(f"    [dim](log: {LOG_FILE})[/dim]")
        else:
            write()
            write(f"  [{i}/{total_count}] {r.title} ({r.platform})")
            try:
                path = download(r, outdir, on_progress=lambda a, b, m, *args: status(f"   {m}"))
                clear_status()
                write(f"  ✔ done: {path}  ({human(os.path.getsize(path))})")
                ok += 1
            except Exception as e:
                clear_status()
                log_error(f"Download failed for '{r.title}' ({r.platform}): {e}", exc=e)
                write(f"  ✖ failed: {e}")
                write(f"    (log: {LOG_FILE})")

    if use_rich:
        console.print()
        if ok == total_count:
            console.print(f"  [bold green]✔ All {ok}/{total_count} downloaded to {outdir}[/bold green]")
        elif ok > 0:
            console.print(f"  [bold yellow]✔ {ok}/{total_count} downloaded to {outdir}[/bold yellow]")
        else:
            console.print(f"  [bold red]✖ 0/{total_count} downloaded to {outdir}[/bold red]")
    else:
        write()
        write(f"  {ok}/{total_count} downloaded to {outdir}")

    return 0 if ok else 1


__all__ = ["download", "run_cli_download", "stream", "check_already_downloaded"]
