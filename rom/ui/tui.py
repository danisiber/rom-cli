"""Textual-based interactive Terminal User Interface (TUI) for rom."""

import threading

from rom.catalog import browse_items, rank, search
from rom.config import OUT_DIR, PLATFORM_LABELS
from rom.downloader import download
from rom.utils import log_error


def run_tui(platform_key="", query="", outdir=None, force=False):
    """Launch the interactive Textual TUI."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import ModalScreen
    from textual.widgets import DataTable, Footer, Header, Input, OptionList, Static
    from textual.widgets.option_list import Option

    outdir = outdir or OUT_DIR

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

    class PlataformasScreen(OptionsScreen):
        def compose(self) -> ComposeResult:
            with Vertical(id="opts"):
                yield Static("Platform", id="opts-title")
                opts = [("todas", "all")] + [(PLATFORM_LABELS[k], k) for k in sorted(PLATFORM_LABELS)]
                yield OptionList(*[Option(t, id=i) for t, i in opts], id="opts-list")
                yield Static("↑↓ move · Enter choose · esc close", id="opts-hint")

    class RomApp(App):
        TITLE = "rom"
        CSS = """
        Input { dock: top; }
        #status { height: 3; background: $surface; padding: 0 1; dock: bottom; }
        Footer { dock: bottom; }
        DataTable { height: 1fr; }
        """
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("d", "download", "Download"),
            ("space", "toggle", "Select"),
            ("p", "platform", "Platform"),
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
            yield Footer()
            yield Static("", id="status")

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
            return (f"platform: {plat} · space mark · d download · p browse/switch · "
                    f"n/b page · ctrl+b options · q quit")

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
            mark = RT("  ✔  ", style="black on green") if sel else ""
            style = "black on dark_green" if sel else None
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
            ok, fail, total = 0, 0, len(rows)
            for n, r in enumerate(rows, 1):
                label = f"{n}/{total} {r.title[:38]}"

                def prog(read, tot, msg, label=label):
                    self.call_from_thread(self._set_status, f"downloading {label} · {msg}")
                try:
                    path = download(r, self.outdir, on_progress=prog)
                    ok += 1
                    self.call_from_thread(self._set_status, f"✔ {path}")
                except Exception as e:
                    fail += 1
                    log_error(f"TUI download failed for '{r.title}' ({r.platform}): {e}", exc=e)
                    self.call_from_thread(self._set_status, f"✖ {r.title[:40]}: {e}")
            self.call_from_thread(self._set_status,
                                  f"✔ {ok}/{total} downloaded to {self.outdir}"
                                  + (f" · {fail} failed" if fail else ""))

    RomApp(platform_key, query, outdir, force).run()
