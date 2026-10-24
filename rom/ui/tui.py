"""Textual-based interactive Terminal User Interface (TUI) for rom."""

import os
import re
import threading
import time
import urllib.parse

from rom.catalog import browse_items, rank, search
from rom.config import OUT_DIR, PLATFORM_LABELS, get_out_dir, set_out_dir
from rom.downloader import check_already_downloaded, download
from rom.thumb import get_thumb_urls, load_thumb_bytes, open_in_browser, render_thumb
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

        def on_mount(self):
            try:
                self.query_one("#opts-list", OptionList).focus()
            except Exception:
                pass

        def on_key(self, event):
            if event.key in ("escape", "q", "ctrl+b"):
                event.stop()
                event.prevent_default()
                self.dismiss(None)

        def on_click(self, event):
            if getattr(event, "widget", None) == self:
                self.dismiss(None)

        def on_option_list_option_selected(self, event):
            event.stop()
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
            event.stop()
            if self.filtered:
                opt_list = self.query_one("#plat-list", OptionList)
                chosen_idx = opt_list.highlighted if opt_list.highlighted is not None else 0
                if 0 <= chosen_idx < len(self.filtered):
                    self.dismiss(self.filtered[chosen_idx][1])
                    return
                self.dismiss(self.filtered[0][1])

        def on_key(self, event):
            if event.key in ("escape", "q", "ctrl+b"):
                event.stop()
                event.prevent_default()
                self.dismiss(None)
                return
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
            event.stop()
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
            event.stop()
            val = event.value.strip()
            if val:
                self.dismiss(val)
            else:
                self.dismiss(None)

        def on_key(self, event):
            if event.key in ("escape", "ctrl+b"):
                event.stop()
                event.prevent_default()
                self.dismiss(None)

        def action_cancel(self):
            self.dismiss(None)

    class DownloadsScreen(ModalScreen):
        CSS = """
        DownloadsScreen { align: center middle; background: $background 70%; }
        #dl-all-box {
            width: 95%;
            height: 85%;
            background: $surface;
            border: heavy $primary;
            padding: 1 2;
        }
        #dl-all-title {
            text-style: bold;
            color: $accent;
            margin-bottom: 1;
        }
        #dl-all-table {
            height: 1fr;
        }
        #dl-all-hint {
            text-style: dim italic;
            margin-top: 1;
        }
        """
        BINDINGS = [
            Binding("escape", "cancel", "Close"),
            Binding("l", "cancel", "Close"),
            Binding("ctrl+l", "cancel", "Close", show=False),
            Binding("ctrl+j", "cancel", "Close", show=False),
            Binding("q", "cancel", "Close"),
        ]

        def __init__(self, get_tasks_callback):
            super().__init__()
            self.get_tasks = get_tasks_callback
            self.col_keys = []
            self.known_ids = set()

        def compose(self) -> ComposeResult:
            with Vertical(id="dl-all-box"):
                yield Static("📥 Downloads Manager", id="dl-all-title")
                yield DataTable(id="dl-all-table", cursor_type="row")
                yield Static("esc / l / q close · enter view details · live progress updates", id="dl-all-hint")

        def on_mount(self):
            table = self.query_one("#dl-all-table", DataTable)
            table.add_columns("#", "Status", "Title", "Platform", "Progress", "Speed", "Size / Transferred", "ETA", "Destination / Details")
            self.col_keys = list(table.columns.keys())
            self._render_rows()
            self.set_interval(0.25, self._refresh_view)

        def _cell_data(self, t):
            from rich.text import Text as RT
            st = t.get("status", "queued")
            if st == "downloading":
                status_txt = RT(" ⏳ DOWNLOADING ", style="bold black on yellow")
            elif st == "completed":
                status_txt = RT(" ✔ COMPLETED ", style="bold white on dark_green")
            elif st == "exists":
                status_txt = RT(" ⏭ ALREADY SAVED ", style="bold black on cyan")
            elif st == "failed":
                status_txt = RT(" ✖ FAILED ", style="bold white on dark_red")
            else:
                status_txt = RT(" 🕒 QUEUED ", style="bold black on bright_black")

            pct = t.get("percent", 0.0)
            bar_len = 10
            filled = int((pct / 100.0) * bar_len)
            filled = max(0, min(bar_len, filled))
            bar_str = "█" * filled + "░" * (bar_len - filled)
            pct_str = f"{pct:5.1f}% [{bar_str}]"

            dest = t.get("dest") or t.get("error") or "Queued in background…"

            # Calculate clear Size / Transferred representation
            curr_read = t.get("read", 0)
            curr_tot = t.get("total", 0)
            if curr_tot > 0 and curr_read > 0:
                size_str = f"{human(curr_read)} / {human(curr_tot)}"
            elif curr_tot > 0:
                size_str = f"0 B / {human(curr_tot)}"
            elif curr_read > 0:
                size_str = human(curr_read)
            else:
                size_str = str(t.get("transferred_str", "--"))

            return [
                str(t.get("id", 1)),
                status_txt,
                str(t.get("title", "")[:45]),
                str(t.get("platform", "")),
                pct_str,
                str(t.get("speed_str", "-- MB/s")),
                size_str,
                str(t.get("eta_str", "--:--")),
                str(dest),
            ]

        def _refresh_view(self):
            tasks = self.get_tasks()
            title_widget = self.query_one("#dl-all-title", Static)
            active_cnt = sum(1 for t in tasks if t.get("status") == "downloading")
            queued_cnt = sum(1 for t in tasks if t.get("status") == "queued")
            completed_cnt = sum(1 for t in tasks if t.get("status") in ("completed", "exists"))
            failed_cnt = sum(1 for t in tasks if t.get("status") == "failed")
            title_widget.update(
                f"📥 Downloads Manager ({len(tasks)} total · {active_cnt} active · {queued_cnt} queued · {completed_cnt} done · {failed_cnt} failed)"
            )
            self._render_rows()

        def _render_rows(self):
            tasks = self.get_tasks()
            table = self.query_one("#dl-all-table", DataTable)
            if not tasks:
                if not self.known_ids:
                    table.clear()
                    table.add_row("-", "No downloads yet", "Use 'd' or 'ctrl+b' to start downloads", "", "", "", "", "", "", key="__empty__")
                    self.known_ids.add("__empty__")
                return

            if "__empty__" in self.known_ids:
                table.clear()
                self.known_ids.clear()

            for t in tasks:
                tid = str(t["id"])
                cells = self._cell_data(t)
                if tid not in self.known_ids:
                    table.add_row(*cells, key=tid)
                    self.known_ids.add(tid)
                else:
                    for ck, val in zip(self.col_keys, cells):
                        try:
                            table.update_cell(tid, ck, val)
                        except Exception:
                            pass

        def on_data_table_row_selected(self, event):
            table = self.query_one("#dl-all-table", DataTable)
            if table.cursor_row is not None:
                tasks = self.get_tasks()
                if 0 <= table.cursor_row < len(tasks):
                    t = tasks[table.cursor_row]
                    dest = t.get("dest") or t.get("error") or "In queue"
                    self.notify(f"{t['title']}\nStatus: {t['status'].upper()}\nInfo: {dest}", title=f"Task #{t['id']}")

        def on_key(self, event):
            if event.key in ("escape", "q", "l", "ctrl+l", "ctrl+j"):
                event.stop()
                event.prevent_default()
                self.dismiss(None)

        def action_cancel(self):
            self.dismiss(None)

    class RomApp(App):
        TITLE = "rom"
        CSS = """
        Input { dock: top; }
        #main-view {
            height: 1fr;
            layout: horizontal;
        }
        #games-table {
            width: 1fr;
            height: 100%;
        }
        #preview-pane {
            width: 32;
            height: 100%;
            background: $surface;
            border-left: round $primary;
            padding: 0 1;
            overflow-y: auto;
        }
        #preview-header {
            text-style: bold;
            color: $accent;
            text-align: center;
            height: 1;
            margin-bottom: 1;
        }
        #preview-art {
            height: auto;
            text-align: center;
            margin-bottom: 1;
        }
        #preview-info {
            height: auto;
            text-overflow: ellipsis;
        }
        #preview-hint {
            text-style: dim italic;
            text-align: center;
            margin-top: 1;
        }
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
            Binding("l", "downloads_view", "Downloads"),
            Binding("ctrl+l", "downloads_view", "Downloads", show=False),
            Binding("ctrl+j", "downloads_view", "Downloads", show=False),
            ("space", "toggle", "Select"),
            Binding("escape", "back_to_main", "Main (★)"),
            Binding("r", "back_to_main", "Reset (★)", show=False),
            Binding("t", "toggle_preview", "Preview (t)"),
            Binding("v", "view_image", "Open Image (v)", show=False),
            Binding("slash", "focus_search", "Search (/)", show=False),
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
            self._browse_cache = {}
            self._thumb_cache = {}
            self._current_thumb_url = None
            self._current_preview_token = 0
            self.page = 0
            self._req_token = 0
            self.download_tasks = []
            self.download_queue = []
            self._dl_worker_running = False
            self._dl_lock = threading.Lock()

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Input(placeholder="Type game name & press Enter… (Esc / empty Enter returns to ★ main list, p platform)", id="main-search")
            with Horizontal(id="main-view"):
                yield DataTable(cursor_type="row", id="games-table")
                with Vertical(id="preview-pane"):
                    yield Static("Cover Art", id="preview-header")
                    yield Static("", id="preview-art")
                    yield Static("", id="preview-info")
                    yield Static("[dim]v[/dim] open image · [dim]t[/dim] toggle", id="preview-hint")
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
            self.query_one("#main-search", Input).focus()
            if self.initial_query:
                self.query_one("#main-search", Input).value = self.initial_query
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
            dl_cnt = len(self.download_tasks)
            dl_hint = f" · l downloads ({dl_cnt})" if dl_cnt else " · l downloads"
            return (f"platform: {plat} · esc main (★) · space mark · d download{dl_hint} · "
                    f"p platform · o folder · n/b page · ctrl+b options · q quit")

        def _set_status(self, msg):
            self._busy = None
            self.query_one(Static).update(msg)

        def _busy_msg(self, msg):
            self._busy = msg

        def on_key(self, event):
            if isinstance(self.screen, ModalScreen):
                # Let active modal dialog (Options, Platforms, etc.) handle its own keys
                return

            if event.key == "escape":
                self.action_back_to_main()
                event.prevent_default()
            elif event.key == "down":
                try:
                    inp = self.query_one("#main-search", Input)
                    if inp.has_focus:
                        table = self.query_one(DataTable)
                        table.focus()
                        event.prevent_default()
                except Exception:
                    pass
            elif event.key == "up":
                try:
                    table = self.query_one(DataTable)
                    if table.has_focus and (table.cursor_row == 0 or table.cursor_row is None):
                        inp = self.query_one("#main-search", Input)
                        inp.focus()
                        event.prevent_default()
                except Exception:
                    pass

        def on_input_submitted(self, event):
            if getattr(event.input, "id", None) != "main-search":
                return
            q = event.value.strip()
            if not q or q.lower() in ("*", "top", "popular", "home", "main", "star", "bintang", "all", "clear"):
                self.action_back_to_main()
            else:
                self._start_search(q)

        def _start_search(self, q):
            self._req_token += 1
            token = self._req_token
            self.last_query = q
            self.selected.clear()
            self._busy = f"searching for '{q}'…"
            self.query_one(Static).update(f"⠋ searching for '{q}'…")
            threading.Thread(target=self._search_bg, args=(q, token), daemon=True).start()

        def _search_bg(self, q, token):
            try:
                results = search(
                    q, self.pk or None,
                    on_progress=lambda d, t: self._busy_msg(f"building the catalog index… {d}/{t}"),
                    force=self.force)
                self.force = False
                if token == self._req_token:
                    self.call_from_thread(self._show, rank(results, q), token)
            except Exception as e:
                if token == self._req_token:
                    self.call_from_thread(self._set_status, f"✖ search error: {e}")

        def _show(self, results, token=None):
            if token is not None and token != self._req_token:
                return
            self.browse_items = None
            table = self.query_one(DataTable)
            table.clear()
            self.results = results
            for i, r in enumerate(results[:200]):
                table.add_row(*self._cells(i, r), key=str(i))
            table.focus()
            if results:
                self._update_preview(results[0])
            else:
                self._clear_preview()
            msg = f"{len(results)} results" if results else "nothing found"
            self._set_status(f"{msg} — {self._hint()}")

        def _start_browse(self, pk):
            self._req_token += 1
            token = self._req_token
            self.last_query = ""
            self.selected.clear()
            self._busy = f"opening {PLATFORM_LABELS.get(pk, pk)}…"
            self.query_one(Static).update(f"⠋ {self._busy}")
            threading.Thread(target=self._browse_bg, args=(pk, token), daemon=True).start()

        def _browse_bg(self, pk, token):
            try:
                items = browse_items(pk)
                if token == self._req_token:
                    self.call_from_thread(self._set_browse, items, token)
            except Exception as e:
                if token == self._req_token:
                    self.call_from_thread(self._set_status, f"✖ {e}")

        def _set_browse(self, items, token=None):
            if token is not None and token != self._req_token:
                return
            self.browse_items = items
            if self.pk:
                self._browse_cache[self.pk] = items
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
            if chunk:
                self._update_preview(chunk[0])
            else:
                self._clear_preview()
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
            for i, r in enumerate(self.results):
                for ck, val in zip(self.col_keys, self._cells(i, r)):
                    table.update_cell(str(i), ck, val)

        def _status_sel(self):
            n = len(self.selected)
            if self.browse_items is not None:
                items = self.browse_items or []
                size = 300
                pages = max(1, (len(items) + size - 1) // size)
                plat = PLATFORM_LABELS.get(self.pk, self.pk or "todas")
                msg = f"{plat} · {len(items)} items · page {self.page + 1}/{pages}"
                if n:
                    msg += f" · ✔ {n} selected"
                self._set_status(msg + " — n/b page · space mark · d download · q quit")
            else:
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
            self.selected = set(range(len(self.results)))
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
                self.last_query = ""
                try:
                    self.query_one("#main-search", Input).value = ""
                except Exception:
                    pass
                if self.pk:
                    self._start_browse(self.pk)
                else:
                    self._set_status("platform: all — type a name and press Enter")
            self.push_screen(PlataformasScreen([]), callback=chosen)

        def action_downloads_view(self):
            self.push_screen(DownloadsScreen(lambda: self.download_tasks))

        def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
            idx = event.cursor_row
            if 0 <= idx < len(self.results):
                self._update_preview(self.results[idx])

        def _update_preview(self, r):
            self._current_preview_token += 1
            token = self._current_preview_token

            # Update info text
            star = "★ " if r.meta.get("pop") is not None else ""
            info = (
                f"[bold accent]{star}{r.title[:45]}[/]\n"
                f"[dim]Platform:[/] [green]{r.platform}[/]\n"
                f"[dim]Size:[/] [yellow]{r.size or '?'}[/] · [dim]Type:[/] {r.kind or '-'}\n"
                f"[dim]Source:[/] [cyan]{r.source}[/]"
            )
            try:
                self.query_one("#preview-info", Static).update(info)
            except Exception:
                pass

            # Update cover art from cache if available
            if r.title in self._thumb_cache:
                art, url = self._thumb_cache[r.title]
                self._current_thumb_url = url
                try:
                    self.query_one("#preview-art", Static).update(art)
                except Exception:
                    pass
                return

            # Placeholder while loading
            try:
                self.query_one("#preview-art", Static).update("⠋ loading cover…")
            except Exception:
                pass

            threading.Thread(target=self._thumb_bg, args=(r, token), daemon=True).start()

        def _thumb_bg(self, r, token):
            urls = get_thumb_urls(r)
            data, url = load_thumb_bytes(urls)
            art = render_thumb(data, max_w=28, max_h=22)
            if not art:
                plat = r.platform or "ROM"
                art = (
                    f"┌──────────────────────────┐\n"
                    f"│       ★ {plat:^8} ★       │\n"
                    f"│                          │\n"
                    f"│     [ No Cover Art ]     │\n"
                    f"│                          │\n"
                    f"│   press 'v' to search    │\n"
                    f"└──────────────────────────┘"
                )
            if token == self._current_preview_token:
                self._thumb_cache[r.title] = (art, url)
                self._current_thumb_url = url
                self.call_from_thread(self._set_art_ui, art, token)

        def _set_art_ui(self, art, token):
            if token == self._current_preview_token:
                try:
                    self.query_one("#preview-art", Static).update(art)
                except Exception:
                    pass

        def _clear_preview(self):
            try:
                self.query_one("#preview-info", Static).update("")
                self.query_one("#preview-art", Static).update("")
            except Exception:
                pass

        def action_view_image(self):
            if self._current_thumb_url:
                open_in_browser(self._current_thumb_url)
                self.notify(f"Opened cover image in browser:\n{self._current_thumb_url}", title="Cover Image")
            else:
                table = self.query_one(DataTable)
                if table.cursor_row is not None and 0 <= table.cursor_row < len(self.results):
                    r = self.results[table.cursor_row]
                    q = urllib.parse.quote(f"{r.title} {r.platform} cover box art")
                    search_url = f"https://www.google.com/search?tbm=isch&q={q}"
                    open_in_browser(search_url)
                    self.notify(f"Searching images for:\n{r.title}", title="Google Images")

        def action_toggle_preview(self):
            try:
                pane = self.query_one("#preview-pane")
                pane.display = not pane.display
            except Exception:
                pass

        def action_back_to_main(self):
            try:
                inp = self.query_one("#main-search", Input)
                inp.value = ""
            except Exception:
                pass
            if self.pk:
                if self.pk in self._browse_cache and self._browse_cache[self.pk]:
                    self.browse_items = self._browse_cache[self.pk]
                    self.page = 0
                    self._render_page()
                else:
                    self._start_browse(self.pk)
            else:
                self.action_platform()

        def action_focus_search(self):
            try:
                self.query_one("#main-search", Input).focus()
            except Exception:
                pass

        def action_palette(self):
            self.push_screen(
                OptionsScreen([
                    ("Download selected", "sel"),
                    ("Download current", "cur"),
                    ("View all downloads (Downloads Manager)", "dl_view"),
                    ("Return to main list (★)", "main"),
                    ("Toggle cover preview panel", "toggle_prev"),
                    ("Open cover image in browser", "open_img"),
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
            elif choice == "dl_view":
                self.action_downloads_view()
            elif choice == "main":
                self.action_back_to_main()
            elif choice == "toggle_prev":
                self.action_toggle_preview()
            elif choice == "open_img":
                self.action_view_image()
            elif choice == "outdir":
                self.action_set_outdir()
            elif choice == "browse":
                self.action_back_to_main()
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
            added = 0
            with self._dl_lock:
                for r in rows:
                    already = any(
                        t["title"] == r.title and t["status"] in ("queued", "downloading")
                        for t in self.download_tasks
                    )
                    if already:
                        continue
                    tid = len(self.download_tasks) + 1
                    task = {
                        "id": tid,
                        "result": r,
                        "title": r.title,
                        "platform": r.platform,
                        "status": "queued",
                        "read": 0,
                        "total": 0,
                        "percent": 0.0,
                        "speed_str": "-- MB/s",
                        "transferred_str": "0 B",
                        "eta_str": "--:--",
                        "mode_str": "",
                        "dest": "",
                        "error": "",
                    }
                    self.download_tasks.append(task)
                    self.download_queue.append(tid)
                    self.downloading_titles.add(r.title)
                    added += 1

            if added == 0:
                self.notify("Selected game(s) already in download queue", title="Already Queued", severity="warning")
                return

            self._redraw()
            self._ensure_dl_worker()
            self._set_status(f"{len(self.download_queue)} download(s) in queue — press 'l' to view")
            self.notify(f"Added {added} game(s) to download queue (press 'l' to view all)", title="Queue Updated", severity="information")

        def _ensure_dl_worker(self):
            with self._dl_lock:
                if not self._dl_worker_running:
                    self._dl_worker_running = True
                    threading.Thread(target=self._dl_worker_loop, daemon=True).start()

        def _dl_worker_loop(self):
            import os
            import time

            dl_box = self.query_one("#download-box")
            dl_header = self.query_one("#dl-header", Static)
            dl_progress = self.query_one("#dl-progress", ProgressBar)
            dl_speed = self.query_one("#dl-speed", Static)
            dl_transferred = self.query_one("#dl-transferred", Static)
            dl_eta = self.query_one("#dl-eta", Static)
            dl_mode = self.query_one("#dl-mode", Static)
            dl_dest = self.query_one("#dl-dest", Static)

            self.call_from_thread(dl_box.add_class, "active")

            while True:
                with self._dl_lock:
                    if not self.download_queue:
                        self._dl_worker_running = False
                        break
                    task_id = self.download_queue.pop(0)
                    task = next((t for t in self.download_tasks if t["id"] == task_id), None)

                if not task:
                    continue

                r = task["result"]
                task["status"] = "downloading"
                self.call_from_thread(self._redraw)

                total_cnt = len(self.download_tasks)
                queued_cnt = len(self.download_queue)

                existing = check_already_downloaded(r, self.outdir)
                if existing:
                    size_str = human(os.path.getsize(existing)) if os.path.exists(existing) else ""
                    task["status"] = "exists"
                    task["percent"] = 100.0
                    task["transferred_str"] = size_str
                    task["dest"] = existing
                    self.downloading_titles.discard(r.title)
                    self.completed_titles.add(r.title)
                    self.call_from_thread(self._redraw)
                    self.call_from_thread(
                        self.notify,
                        f"Already downloaded: {r.title} ({size_str})",
                        title=f"File Exists [{task['id']}/{total_cnt}]",
                        severity="warning",
                    )
                    def update_cached(t=task, q_cnt=queued_cnt, ex=existing, sz=size_str):
                        q_hint = f" · ({q_cnt} queued)" if q_cnt else ""
                        dl_header.update(f"✔ [{t['id']}/{len(self.download_tasks)}] {t['title'][:40]} ({t['platform']}) — ALREADY DOWNLOADED{q_hint}")
                        dl_progress.update(total=100, progress=100)
                        dl_speed.update("⚡ Status: Skipped")
                        dl_transferred.update(f"📦 Size: {sz}")
                        dl_eta.update("⏳ ETA: 00:00")
                        dl_mode.update("📁 Local disk")
                        dl_dest.update(f"📂 File: {ex} (press 'l' for all downloads)")
                    self.call_from_thread(update_cached)
                    time.sleep(0.4)
                    continue

                self.call_from_thread(
                    self.notify,
                    f"Downloading: {r.title}",
                    title=f"Download [{task['id']}/{total_cnt}]",
                    severity="information",
                )

                def update_ui_init(t=task, q_cnt=queued_cnt):
                    q_hint = f" · ({q_cnt} queued)" if q_cnt else ""
                    dl_header.update(f"⬇ [{t['id']}/{len(self.download_tasks)}] {t['title'][:40]} ({t['platform']}) · Preparing…{q_hint}")
                    dl_progress.update(total=None, progress=0)
                    dl_speed.update("⚡ Speed: Connecting…")
                    dl_transferred.update("📦 Transferred: 0 B")
                    dl_eta.update("⏳ ETA: Estimating…")
                    dl_mode.update("🧵 Mode: Initing")
                    dl_dest.update(f"📂 Destination: {self.outdir} (press 'l' for all downloads)")

                self.call_from_thread(update_ui_init)

                def prog(read, tot, msg, info=None, t=task):
                    if tot and tot > 0:
                        t["total"] = tot
                    if read and read > 0:
                        t["read"] = read

                    curr_tot = t.get("total", 0)
                    curr_read = t.get("read", 0)

                    if curr_tot > 0:
                        pct = min(100.0, (curr_read * 100.0 / curr_tot))
                        speed_str = info.get("speed_str", t.get("speed_str", "-- MB/s")) if info else t.get("speed_str", "-- MB/s")
                        eta_str = info.get("eta_str", t.get("eta_str", "--:--")) if info else t.get("eta_str", "--:--")
                        mode_str = info.get("mode", t.get("mode_str", "single")) if info else t.get("mode_str", "single")
                        trans_str = f"{human(curr_read)} / {human(curr_tot)}"
                    else:
                        pct = 0.0
                        speed_str = "-- MB/s"
                        eta_str = "--:--"
                        mode_str = "single"
                        trans_str = human(curr_read) if curr_read else "0 B"

                    t["percent"] = pct
                    t["speed_str"] = speed_str
                    t["transferred_str"] = trans_str
                    t["eta_str"] = eta_str
                    t["mode_str"] = mode_str

                    def update_prog():
                        try:
                            q_cnt = len(self.download_queue)
                            q_hint = f" · ({q_cnt} queued)" if q_cnt else ""
                            if curr_tot > 0:
                                dl_progress.update(total=curr_tot, progress=curr_read)
                                dl_header.update(f"⬇ [{t['id']}/{len(self.download_tasks)}] {t['title'][:40]} ({t['platform']}) · {pct:.1f}%{q_hint}")
                                dl_speed.update(f"⚡ Speed: {speed_str}")
                                dl_transferred.update(f"📦 Size: {trans_str} ({pct:.1f}%)")
                                dl_eta.update(f"⏳ ETA: {eta_str}")
                                dl_mode.update(f"🧵 {mode_str}")
                            else:
                                clean_m = re.sub(r"^[\[\d\w\s]+\]\s*", "", str(msg or ""))
                                dl_header.update(f"⬇ [{t['id']}/{len(self.download_tasks)}] {t['title'][:40]} ({t['platform']}){q_hint}")
                                dl_speed.update(f"⚡ Status: {clean_m[:25]}")
                                if curr_read > 0:
                                    dl_transferred.update(f"📦 Transferred: {human(curr_read)}")
                        except Exception:
                            pass
                    self.call_from_thread(update_prog)

                try:
                    path = download(r, self.outdir, on_progress=prog)
                    task["status"] = "completed"
                    task["dest"] = path
                    task["percent"] = 100.0
                    size_str = human(os.path.getsize(path)) if os.path.exists(path) else ""
                    task["transferred_str"] = size_str
                    self.downloading_titles.discard(r.title)
                    self.completed_titles.add(r.title)
                    self.call_from_thread(self._redraw)

                    self.call_from_thread(
                        self.notify,
                        f"✔ {r.title} ({size_str})",
                        title=f"Saved [{task['id']}/{len(self.download_tasks)}]",
                        severity="information",
                    )

                    def update_done(t=task, sz=size_str, p=path):
                        q_cnt = len(self.download_queue)
                        q_hint = f" · ({q_cnt} queued)" if q_cnt else ""
                        dl_header.update(f"✔ [{t['id']}/{len(self.download_tasks)}] {t['title'][:40]} — COMPLETED{q_hint}")
                        dl_progress.update(total=100, progress=100)
                        dl_speed.update("⚡ Speed: Complete")
                        dl_transferred.update(f"📦 Total: {sz}")
                        dl_eta.update("⏳ Finished")
                        dl_mode.update("✔ Verified")
                        dl_dest.update(f"📂 Saved: {p} (press 'l' for all downloads)")
                    self.call_from_thread(update_done)

                except Exception as e:
                    task["status"] = "failed"
                    task["error"] = str(e)
                    curr_read = task.get("read", 0)
                    curr_tot = task.get("total", 0)
                    if curr_read and curr_tot:
                        task["transferred_str"] = f"{human(curr_read)} / {human(curr_tot)}"
                    elif curr_read:
                        task["transferred_str"] = human(curr_read)
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

                    def update_err(t=task, err_m=str(e)):
                        q_cnt = len(self.download_queue)
                        q_hint = f" · ({q_cnt} queued)" if q_cnt else ""
                        dl_header.update(f"✖ [{t['id']}/{len(self.download_tasks)}] {t['title'][:40]} — FAILED{q_hint}")
                        dl_speed.update("✖ Error")
                        curr_r = t.get("read", 0)
                        curr_t = t.get("total", 0)
                        if curr_r and curr_t:
                            dl_transferred.update(f"📦 Size: {human(curr_r)} / {human(curr_t)}")
                        elif curr_r:
                            dl_transferred.update(f"📦 Transferred: {human(curr_r)}")
                        dl_dest.update(f"Error: {err_m} (press 'l' for all downloads)")
                    self.call_from_thread(update_err)

            total_done = sum(1 for t in self.download_tasks if t["status"] in ("completed", "exists"))
            total_failed = sum(1 for t in self.download_tasks if t["status"] == "failed")
            total_all = len(self.download_tasks)
            summary = f"✔ {total_done}/{total_all} downloaded to {self.outdir}" + (f" · {total_failed} failed" if total_failed else "")
            self.call_from_thread(self._set_status, summary + " — " + self._hint())

    RomApp(platform_key, query, outdir, force).run()
