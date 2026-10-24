"""Textual-based interactive Terminal User Interface (TUI) for rom."""

import os
import re
import threading
import time

from rom.catalog import browse_items, rank, search
from rom.config import OUT_DIR, PLATFORM_LABELS, get_out_dir, set_out_dir
from rom.downloader import check_already_downloaded, download
from rom.utils import human, log_error


def run_tui(platform_key="", query="", outdir=None, force=False):
    """Launch the interactive Textual TUI."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import DataTable, Footer, Header, Input, OptionList, ProgressBar, Static
    from textual.widgets.option_list import Option

    outdir = outdir or get_out_dir()

    class OptionsScreen(ModalScreen):
        CSS = """
        OptionsScreen { align: center middle; background: $background 60%; }
        #opts { width: 64; height: auto; max-height: 80%; background: $surface;
                border: round $primary; padding: 1 2; }
        #opts-title { text-style: bold; margin-bottom: 1; }
        #opts-list { height: auto; }
        #opts-hint { text-style: dim italic; margin-top: 1; }
        """
        BINDINGS = [Binding("escape", "cancel", "Close"),
                    Binding("ctrl+b", "cancel", "Close", show=False),
                    Binding("q", "cancel", "Close", show=False)]

        def __init__(self, options):
            super().__init__()
            self.options = options

        def compose(self) -> ComposeResult:
            with Vertical(id="opts"):
                yield Static("Options", id="opts-title")
                yield OptionList(*[Option(o[0], id=o[1]) for o in self.options], id="opts-list")
                yield Static("↑↓ move · Enter select · esc close", id="opts-hint")

        def on_option_list_option_selected(self, event):
            self.dismiss(event.option_id)

        def action_cancel(self):
            self.dismiss(None)

    class PlataformasScreen(ModalScreen):
        CSS = """
        PlataformasScreen { align: center middle; background: $background 60%; }
        #plat-box { width: 68; height: auto; max-height: 85%; background: $surface;
                    border: heavy $primary; padding: 1 2; }
        #plat-title { text-style: bold; margin-bottom: 1; color: $accent; }
        #plat-search { margin-bottom: 1; }
        #plat-list { height: auto; max-height: 16; }
        #plat-hint { text-style: dim italic; margin-top: 1; }
        """
        BINDINGS = [
            Binding("escape", "cancel", "Close"),
            Binding("ctrl+b", "cancel", "Close", show=False),
            Binding("q", "cancel", "Close", show=False),
        ]

        def __init__(self, *args, **kwargs):
            super().__init__()
            self.all_opts = [("All Platforms (todas)", "all")] + [
                (f"{PLATFORM_LABELS[k]} ({k})", k) for k in sorted(PLATFORM_LABELS)
            ]
            self.filtered = list(self.all_opts)

        def compose(self) -> ComposeResult:
            with Vertical(id="plat-box"):
                yield Static("Select Platform", id="plat-title")
                yield Input(placeholder="Search platform (e.g. ps2, switch, nintendo, gba)…", id="plat-search")
                yield OptionList(*[Option(t, id=i) for t, i in self.all_opts], id="plat-list")
                yield Static("↑↓ move · Enter choose · esc close", id="plat-hint")

        def on_mount(self):
            self.query_one("#plat-search", Input).focus()

        def on_input_changed(self, event: Input.Changed):
            q = event.value.strip().lower()
            opt_list = self.query_one("#plat-list", OptionList)
            opt_list.clear_options()
            if q:
                self.filtered = [o for o in self.all_opts if q in o[0].lower() or q in o[1].lower()]
            else:
                self.filtered = list(self.all_opts)

            if self.filtered:
                opt_list.add_options([Option(t, id=i) for t, i in self.filtered])
                opt_list.highlighted = 0
            else:
                opt_list.add_options([Option("✖ No platforms match", id="__none__", disabled=True)])

        def on_input_submitted(self, event: Input.Submitted):
            if self.filtered:
                opt_list = self.query_one("#plat-list", OptionList)
                chosen_idx = opt_list.highlighted if opt_list.highlighted is not None else 0
                if 0 <= chosen_idx < len(self.filtered):
                    self.dismiss(self.filtered[chosen_idx][1])
                    return
                self.dismiss(self.filtered[0][1])

        def on_key(self, event):
            if event.key == "down":
                inp = self.query_one("#plat-search", Input)
                opt_list = self.query_one("#plat-list", OptionList)
                if inp.has_focus:
                    opt_list.focus()
                    if opt_list.highlighted is None and self.filtered:
                        opt_list.highlighted = 0
                    event.prevent_default()
            elif event.key == "up":
                inp = self.query_one("#plat-search", Input)
                opt_list = self.query_one("#plat-list", OptionList)
                if opt_list.has_focus and (opt_list.highlighted == 0 or opt_list.highlighted is None):
                    inp.focus()
                    event.prevent_default()

        def on_option_list_option_selected(self, event: OptionList.OptionSelected):
            if event.option_id and event.option_id != "__none__":
                self.dismiss(event.option_id)

        def action_cancel(self):
            self.dismiss(None)

    class SetDirScreen(ModalScreen):
        CSS = """
        SetDirScreen { align: center middle; background: $background 60%; }
        #dir-box { width: 72; height: auto; max-height: 80%; background: $surface;
                   border: heavy $primary; padding: 1 2; }
        #dir-title { text-style: bold; margin-bottom: 1; color: $accent; }
        #dir-current { margin-bottom: 1; color: $text-muted; }
        #dir-input { margin-bottom: 1; }
        #dir-hint { text-style: dim italic; }
        """
        BINDINGS = [
            Binding("escape", "cancel", "Close"),
            Binding("ctrl+b", "cancel", "Close", show=False),
        ]

        def __init__(self, current_dir):
            super().__init__()
            self.current_dir = current_dir

        def compose(self) -> ComposeResult:
            with Vertical(id="dir-box"):
                yield Static("Configure Download Directory", id="dir-title")
                yield Static(f"Current: {self.current_dir}", id="dir-current")
                yield Input(value=self.current_dir, placeholder="Enter download folder path (e.g. D:\\Games\\ROMs)…", id="dir-input")
                yield Static("Enter save · esc cancel", id="dir-hint")

        def on_mount(self):
            inp = self.query_one("#dir-input", Input)
            inp.focus()
            inp.cursor_position = len(inp.value)

        def on_input_submitted(self, event: Input.Submitted):
            val = event.value.strip()
            if val:
                self.dismiss(val)
            else:
                self.dismiss(None)

        def action_cancel(self):
            self.dismiss(None)

    class RomApp(App):
        TITLE = "rom"
        CSS = """
        Input { dock: top; }
        DataTable { height: 1fr; }
        #download-box {
            display: none;
            dock: bottom;
            height: auto;
            max-height: 10;
            background: $surface;
            border: heavy $primary;
            padding: 0 1;
            margin: 0 1;
        }
        #download-box.active {
            display: block;
        }
        #dl-header {
            text-style: bold;
            color: $accent;
            height: 1;
        }
        #dl-progress {
            margin: 0;
            padding: 0;
            height: 1;
        }
        #dl-stats {
            height: 1;
            layout: horizontal;
        }
        #dl-speed {
            width: 1fr;
            color: $success;
            text-style: bold;
        }
        #dl-transferred {
            width: 1fr;
            color: $warning;
        }
        #dl-eta {
            width: 1fr;
            color: $accent;
        }
        #dl-mode {
            width: 1fr;
            color: $text-muted;
        }
        #dl-dest {
            color: $text-muted;
            height: 1;
            text-overflow: ellipsis;
        }
        #status { height: 2; background: $surface; padding: 0 1; dock: bottom; }
        Footer { dock: bottom; }
        """
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("d", "download", "Download"),
            ("space", "toggle", "Select"),
            ("p", "platform", "Platform"),
            ("o", "set_outdir", "Folder"),
            ("n", "next_page", "Page+"),
            ("b", "prev_page", "Page-"),
            ("ctrl+b", "palette", "Options"),
            ("ctrl+a", "select_all", "Select all"),
            ("ctrl+n", "select_none", "Clear"),
        ]

        def __init__(self, platform_key, query, outdir, force):
            super().__init__()
            self.results = []
            self.selected = set()
            self.downloading_titles = set()
            self.completed_titles = set()
            self.failed_titles = set()
            self.last_query = ""
            self.pk = platform_key or ""
            self.initial_query = query or ""
            self.outdir = outdir
            self.force = force
            self.browse_items = None
            self.page = 0

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Input(placeholder="Type the game name and press Enter…  (p switches platform)")
            yield DataTable(cursor_type="row")
            with Vertical(id="download-box"):
                yield Static("", id="dl-header")
                yield ProgressBar(id="dl-progress", show_percentage=True, show_eta=True)
                with Horizontal(id="dl-stats"):
                    yield Static("⚡ Speed: --", id="dl-speed")
                    yield Static("📦 Transferred: --", id="dl-transferred")
                    yield Static("⏳ ETA: --", id="dl-eta")
                    yield Static("🧵 Mode: --", id="dl-mode")
                yield Static("", id="dl-dest")
            yield Static("", id="status")
            yield Footer()

        def on_mount(self):
            table = self.query_one(DataTable)
            table.add_columns(" ", "Title", "Platform", "Type", "Size", "Source")
            self.col_keys = list(table.columns.keys())
            self._busy = None
            self._frame = 0
            self.set_interval(0.1, self._tick)
            self._set_status(self._hint())
            self.query_one(Input).focus()
            if self.initial_query:
                self.query_one(Input).value = self.initial_query
                self._start_search(self.initial_query)
            elif self.pk:
                self._start_browse(self.pk)
            else:
                self.call_after_refresh(self._open_platforms)

        def _tick(self):
            if not self._busy:
                return
            frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
            self._frame += 1
            self.query_one(Static).update(f"{frames[self._frame % len(frames)]} {self._busy}")

        def _hint(self):
            plat = PLATFORM_LABELS.get(self.pk, "todas") if self.pk else "todas"
            return (f"platform: {plat} · space mark · d download · p platform · "
                    f"o folder · n/b page · ctrl+b options · q quit")

        def _set_status(self, msg):
            self._busy = None
            self.query_one(Static).update(msg)

        def _busy_msg(self, msg):
            self._busy = msg

        def on_input_submitted(self, event):
            q = event.value.strip()
            if q:
                self._start_search(q)

        def _start_search(self, q):
            self.last_query = q
            self.selected.clear()
            self._busy = f"searching for '{q}'…"
            self.query_one(Static).update(f"⠋ searching for '{q}'…")
            threading.Thread(target=self._search_bg, args=(q,), daemon=True).start()

        def _search_bg(self, q):
            try:
                results = search(
                    q, self.pk or None,
                    on_progress=lambda d, t: self._busy_msg(f"building the catalog index… {d}/{t}"),
                    force=self.force)
                self.force = False
                self.call_from_thread(self._show, rank(results, q))
            except Exception as e:
                self.call_from_thread(self._set_status, f"✖ search error: {e}")

        def _show(self, results):
            self.browse_items = None
            table = self.query_one(DataTable)
            table.clear()
            self.results = results
            for i, r in enumerate(results[:200]):
                table.add_row(*self._cells(i, r), key=str(i))
            table.focus()
            msg = f"{len(results)} results" if results else "nothing found"
            self._set_status(f"{msg} — {self._hint()}")

        def _start_browse(self, pk):
            self.last_query = ""
            self.selected.clear()
            self._busy = f"opening {PLATFORM_LABELS.get(pk, pk)}…"
            self.query_one(Static).update(f"⠋ {self._busy}")
            threading.Thread(target=self._browse_bg, args=(pk,), daemon=True).start()

        def _browse_bg(self, pk):
            try:
                self.call_from_thread(self._set_browse, browse_items(pk))
            except Exception as e:
                self.call_from_thread(self._set_status, f"✖ {e}")

        def _set_browse(self, items):
            self.browse_items = items
            self.page = 0
            self._render_page()

        def _render_page(self):
            items = self.browse_items or []
            size = 300
            pages = max(1, (len(items) + size - 1) // size)
            self.page = max(0, min(self.page, pages - 1))
            chunk = items[self.page * size:(self.page + 1) * size]
            self.results = chunk
            self.selected.clear()
            table = self.query_one(DataTable)
            table.clear()
            for i, r in enumerate(chunk):
                table.add_row(*self._cells(i, r), key=str(i))
            table.focus()
            plat = PLATFORM_LABELS.get(self.pk, self.pk or "todas")
            self._set_status(f"{plat} · {len(items)} items · page {self.page + 1}/{pages}"
                             " — n/b page · space mark · d download · q quit")

        def action_next_page(self):
            if self.browse_items is None:
                return
            self.page += 1
            self._render_page()

        def action_prev_page(self):
            if self.browse_items is None:
                return
            self.page = max(0, self.page - 1)
            self._render_page()

        def _cells(self, i, r):
            from rich.text import Text as RT
            sel = i in self.selected

            if r.title in self.downloading_titles:
                mark = RT(" ⏳ DL ", style="bold black on yellow")
                style = "bold yellow"
            elif r.title in self.completed_titles or check_already_downloaded(r, self.outdir):
                mark = RT(" ✔ SAVED", style="bold white on dark_green")
                style = "bold green"
            elif r.title in self.failed_titles:
                mark = RT(" ✖ ERR", style="bold white on dark_red")
                style = "bold red"
            elif sel:
                mark = RT("  ✔  ", style="black on green")
                style = "black on dark_green"
            else:
                mark = ""
                style = None

            star = "★ " if r.meta.get("pop") is not None else ""
            vals = [mark, star + r.title[:60], r.platform, r.kind or "-",
                    r.size or "?", r.source]
            out = [mark]
            for v in vals[1:]:
                out.append(RT(str(v), style=style) if style else str(v))
            return out

        def _redraw(self):
            table = self.query_one(DataTable)
            for i, r in enumerate(self.results[:200]):
                for ck, val in zip(self.col_keys, self._cells(i, r)):
                    table.update_cell(str(i), ck, val)

        def _status_sel(self):
            n = len(self.selected)
            msg = f"{len(self.results)} results"
            if n:
                msg += f" · ✔ {n} selected"
            self._set_status(msg + " — " + self._hint())

        def action_toggle(self):
            table = self.query_one(DataTable)
            if table.cursor_row is None or not self.results:
                return
            i = table.cursor_row
            self.selected.symmetric_difference_update({i})
            self._redraw()
            self._status_sel()

        def action_select_all(self):
            self.selected = set(range(len(self.results[:200])))
            self._redraw()
            self._status_sel()

        def action_select_none(self):
            self.selected.clear()
            self._redraw()
            self._status_sel()

        def action_platform(self):
            self._open_platforms()

        def _open_platforms(self):
            def chosen(val):
                if val is None:
                    return
                self.pk = "" if val == "all" else val
                if self.last_query:
                    self._start_search(self.last_query)
                elif self.pk:
                    self._start_browse(self.pk)
                else:
                    self._set_status("platform: all — type a name and press Enter")
            self.push_screen(PlataformasScreen([]), callback=chosen)

        def action_palette(self):
            self.push_screen(
                OptionsScreen([
                    ("Download selected", "sel"),
                    ("Download current", "cur"),
                    ("Configure download folder", "outdir"),
                    ("Browse this platform", "browse"),
                    ("Switch platform", "plat"),
                    ("Select all", "all"),
                    ("Clear selection", "none"),
                ]),
                callback=self._palette,
            )

        def _palette(self, choice):
            if choice is None:
                return
            if choice == "sel":
                self._batch([self.results[i] for i in sorted(self.selected)])
            elif choice == "cur":
                self.action_download()
            elif choice == "outdir":
                self.action_set_outdir()
            elif choice == "browse":
                if self.pk:
                    self._start_browse(self.pk)
                else:
                    self.action_platform()
            elif choice == "all":
                self.action_select_all()
            elif choice == "none":
                self.action_select_none()
            elif choice == "plat":
                self.action_platform()

        def action_set_outdir(self):
            def chosen(val):
                if val:
                    try:
                        clean = set_out_dir(val)
                        os.makedirs(clean, exist_ok=True)
                        self.outdir = clean
                        self.notify(f"Download folder set to:\n{clean}", title="Folder Updated", severity="information")
                        self._set_status(f"download folder: {clean} — {self._hint()}")
                        self._redraw()
                    except Exception as e:
                        self.notify(f"Failed to set folder: {e}", title="Error", severity="error")
            self.push_screen(SetDirScreen(self.outdir), callback=chosen)

        def on_data_table_row_selected(self, event):
            table = self.query_one(DataTable)
            if table.cursor_row is not None and self.results:
                self.selected.add(table.cursor_row)
                self._redraw()
                self.action_palette()

        def action_download(self):
            table = self.query_one(DataTable)
            if table.cursor_row is None or not self.results:
                return
            self._batch([self.results[table.cursor_row]])

        def _batch(self, rows):
            if not rows:
                self._set_status("nothing selected")
                return
            self._set_status(f"downloading 0/{len(rows)}…")
            threading.Thread(target=self._batch_bg, args=(rows,), daemon=True).start()

        def _batch_bg(self, rows):
            import os
            import time
            ok, fail, total = 0, 0, len(rows)

            dl_box = self.query_one("#download-box")
            dl_header = self.query_one("#dl-header", Static)
            dl_progress = self.query_one("#dl-progress", ProgressBar)
            dl_speed = self.query_one("#dl-speed", Static)
            dl_transferred = self.query_one("#dl-transferred", Static)
            dl_eta = self.query_one("#dl-eta", Static)
            dl_mode = self.query_one("#dl-mode", Static)
            dl_dest = self.query_one("#dl-dest", Static)

            self.call_from_thread(dl_box.add_class, "active")

            for n, r in enumerate(rows, 1):
                # Check if already downloaded before attempting download
                existing = check_already_downloaded(r, self.outdir)
                if existing:
                    size_str = human(os.path.getsize(existing)) if os.path.exists(existing) else ""
                    ok += 1
                    self.downloading_titles.discard(r.title)
                    self.completed_titles.add(r.title)
                    self.call_from_thread(self._redraw)
                    self.call_from_thread(
                        self.notify,
                        f"Already downloaded: {r.title} ({size_str})",
                        title=f"File Exists [{n}/{total}]",
                        severity="warning",
                    )
                    def update_cached(n=n, r=r, existing=existing, size_str=size_str):
                        dl_header.update(f"✔ [{n}/{total}] {r.title[:45]} ({r.platform}) — ALREADY DOWNLOADED")
                        dl_progress.update(total=100, progress=100)
                        dl_speed.update("⚡ Status: Skipped")
                        dl_transferred.update(f"📦 Size: {size_str}")
                        dl_eta.update("⏳ ETA: 00:00")
                        dl_mode.update("📁 Local disk")
                        dl_dest.update(f"📂 File: {existing} (Already downloaded)")
                    self.call_from_thread(update_cached)
                    time.sleep(0.4)
                    continue

                self.downloading_titles.add(r.title)
                self.call_from_thread(self._redraw)
                self.call_from_thread(
                    self.notify,
                    f"Downloading: {r.title}",
                    title=f"Download [{n}/{total}]",
                    severity="information",
                )

                def update_ui_init(n=n, r=r):
                    dl_header.update(f"⬇ [{n}/{total}] {r.title[:45]} ({r.platform}) · Preparing…")
                    dl_progress.update(total=None, progress=0)
                    dl_speed.update("⚡ Speed: Connecting…")
                    dl_transferred.update("📦 Transferred: 0 B")
                    dl_eta.update("⏳ ETA: Estimating…")
                    dl_mode.update("🧵 Mode: Initing")
                    dl_dest.update(f"📂 Destination folder: {self.outdir}")

                self.call_from_thread(update_ui_init)

                def prog(read, tot, msg, info=None, n=n, r=r):
                    def update_prog():
                        try:
                            if tot and tot > 0:
                                dl_progress.update(total=tot, progress=read)
                                speed_str = info.get("speed_str", "-- MB/s") if info else ""
                                eta_str = info.get("eta_str", "--:--") if info else ""
                                mode_str = info.get("mode", "single") if info else ""
                                pct = (read * 100.0 / tot) if tot else 0.0
                                dl_header.update(f"⬇ [{n}/{total}] {r.title[:45]} ({r.platform}) · {pct:.1f}%")
                                dl_speed.update(f"⚡ Speed: {speed_str}")
                                dl_transferred.update(f"📦 {human(read)} / {human(tot)} ({pct:.1f}%)")
                                dl_eta.update(f"⏳ ETA: {eta_str}")
                                dl_mode.update(f"🧵 {mode_str}")
                            else:
                                clean_m = re.sub(r"^[\[\d\w\s]+\]\s*", "", str(msg or ""))
                                dl_header.update(f"⬇ [{n}/{total}] {r.title[:45]} ({r.platform})")
                                dl_speed.update(f"⚡ Status: {clean_m[:25]}")
                        except Exception:
                            pass
                    self.call_from_thread(update_prog)

                try:
                    path = download(r, self.outdir, on_progress=prog)
                    ok += 1
                    self.downloading_titles.discard(r.title)
                    self.completed_titles.add(r.title)
                    self.call_from_thread(self._redraw)

                    size_str = human(os.path.getsize(path)) if os.path.exists(path) else ""
                    self.call_from_thread(
                        self.notify,
                        f"✔ {r.title} ({size_str})",
                        title=f"Saved [{n}/{total}]",
                        severity="information",
                    )

                    def update_done(n=n, r=r, path=path, size_str=size_str):
                        dl_header.update(f"✔ [{n}/{total}] {r.title[:45]} — COMPLETED")
                        dl_progress.update(total=100, progress=100)
                        dl_speed.update("⚡ Speed: Complete")
                        dl_transferred.update(f"📦 Total: {size_str}")
                        dl_eta.update("⏳ Finished")
                        dl_mode.update("✔ Verified")
                        dl_dest.update(f"📂 Saved: {path}")
                    self.call_from_thread(update_done)

                except Exception as e:
                    fail += 1
                    self.downloading_titles.discard(r.title)
                    self.failed_titles.add(r.title)
                    self.call_from_thread(self._redraw)
                    log_error(f"TUI download failed for '{r.title}' ({r.platform}): {e}", exc=e)

                    self.call_from_thread(
                        self.notify,
                        f"✖ {r.title}: {e}",
                        title="Download Error",
                        severity="error",
                    )

                    def update_err(n=n, r=r, err_msg=str(e)):
                        dl_header.update(f"✖ [{n}/{total}] {r.title[:45]} — FAILED")
                        dl_speed.update("✖ Error")
                        dl_dest.update(f"Error: {err_msg}")
                    self.call_from_thread(update_err)

            summary = f"✔ {ok}/{total} downloaded to {self.outdir}" + (f" · {fail} failed" if fail else "")
            self.call_from_thread(self._set_status, summary)

    RomApp(platform_key, query, outdir, force).run()
