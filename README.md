# rom

Python CLI to find and download ROMs, ISOs and Switch games from the terminal.
It has an interactive UI (Textual) like `epub-search`, name search, downloads with
a progress bar, and a folder organised by platform.

> English-language version of the original Portuguese project by
> [sostenesapollo](https://github.com/sostenesapollo/rom-cli). Thanks to the
> original author for the base work — this fork translates the interface and
> docs to English and tracks the upstream fixes.

## Requirements

- Python 3.8+
- Windows (CMD, PowerShell, or Git Bash), macOS, or Linux
- `textual` (`install.sh` or `install.bat` installs it into its own venv)

## Installation

```bash
git clone https://github.com/danisiber/rom-cli.git
cd rom-cli

# Linux / macOS / Git Bash:
make install
# or: ./install.sh

# Windows (CMD / PowerShell):
install.bat
```

This creates a venv in `~/.venvs/rom`, installs `textual`, and publishes `rom`
(and `rom-remote`) into `~/bin` (or `%USERPROFILE%\bin`). Use `PREFIX=/usr/local make install` for a
different destination.

### Makefile Commands

| Target | Description |
|---|---|
| `make install` | Install venv and binary wrappers (Linux / macOS / Git Bash) |
| `make install-bat` | Install on Windows using native batch script (CMD / PowerShell) |
| `make exe` | Compile standalone Windows executable (`dist/rom.exe`) using PyInstaller |
| `make check` | Validate Python syntax across all modules |
| `make test` | Test installed CLI binary (`rom -l`) |
| `make clean` | Clean Python bytecode (`__pycache__`, `.pyc`) and build artifacts (`build`, `dist`) |
| `make clean-cache` | Clean downloaded metadata & catalog caches (`~/.cache/rom-cli`) |
| `make uninstall` | Remove binary wrappers from `~/bin` |
| `make uninstall-all` | Remove wrappers, virtual environment, and cache |

## Standalone Windows Executable (.exe)

You can compile `rom-cli` into a single standalone `rom.exe` file that runs without requiring Python installed:

```bat
:: Via native Windows batch script (CMD / PowerShell):
build-exe.bat

:: Or via Makefile:
make exe
```

The standalone executable will be generated at `dist\rom.exe` (and automatically copied to `%USERPROFILE%\bin\rom.exe` if present in your PATH).

## Usage

```bash
rom                          # opens the platform picker and browses
rom -p switch                # opens straight into the Switch catalog
rom -p switchports           # only the Switch ports/homebrew
rom "metroid"                # searches every source
rom -y -p gba "pokemon"      # downloads the best match without asking
rom --list "metroid"         # lists only, does not download
rom --print-url -p switch …  # prints the direct link (aria2/curl)
rom -l                       # lists the platforms
rom --index                  # builds/prints the catalog index
rom --refresh                # rebuilds the index (ignores the cache)
```

With no query, `rom` opens the **platform picker**; once you pick one, it lists
that platform's whole catalog (pages of 300, `n`/`b` to move) — so you can
browse without typing anything. Typing in the field and pressing `Enter` goes
back to searching.

In the UI: `↑↓` navigate, `space` mark, `d` download (the marked ones or the
current one), `p` switch platform, `n`/`b` page, `ctrl+b` options palette,
`ctrl+a` select all, `ctrl+n` clear, `q` quit.

| Flag | Description |
|------|-------------|
| `-p, --platform` | platform (switch, snes, gba, ps2, nds, wii…) |
| `-y, --yes` | download the best match without the menu |
| `--list` | list only |
| `--print-url` | resolve and print the direct link only |
| `--refresh` | rebuild the catalog index |
| `--index` | download/print the index and exit |
| `-n, --number` | how many results to show (default 15) |
| `-o, --out` | destination folder (default `~/Downloads/roms` or `$ROM_DIR`) |
| `-l, --platforms` | list platforms |
| `--debug` | show verbose error tracebacks and log to file |

Platforms (26): `switch`, `switchports`, `ps5`, `ps4`, `ps3`, `psv`, `ps2`, `ps1`,
`psp`, `nds`, `gba`, `snes`, `pc`, `nes`, `gb`, `gbc`, `n64`, `3ds`, `gc`, `wii`,
`genesis`, `mastersystem`, `dreamcast`, `saturn`, `arcade`, `xbox`.

Files go to `~/Downloads/roms/<platform>/`.

## How it works

- **Switch**: the dlarchive index (`files_api.php`). The nsp-roms page embeds
  links with a token that expires; here `rom` resolves through the index and
  grabs a direct, token-free URL. It also works for NDS, GBA, SNES and PC.
- **Switch ports**: the `switchports` platform merges two sources — the dlarchive
  catalog and an Archive.org scan (`switch port` / `homebrew port` / `nsp`+`port`),
  with a 7-day cache. Around 35 ports (GTA, Halo, Simpsons Hit & Run, SM64 NX,
  Twilight Princess, Cave Story, Pizza Tower, Max Payne, Hello Neighbor, Diablo...).
- **PS3 and PS Vita**: NoPayStation — downloads `.pkg` straight from Sony's CDN
  (`zeus.dl.playstation.net`), no token needed.
- **PS2, PS1 and PSP**: RomsGames (search + a POST that returns the file).
- **Xbox**: RomsGames (`microsoft-xbox`) and Archive.org scans for Xbox Classic games and ISOs.
- **PS4 and PS5**: dlpsgame (search via WP REST). The direct download works when
  the post links a supported host (mediafire, Google Drive, 1fichier); when it
  doesn't, `rom` shows the page so you can grab the link yourself.
- **IDM-Style Segmented Downloads**: Parallel multi-threaded chunking (2–8 workers) with HTTP Range probing and sparse file pre-allocation for high-speed downloads, with auto-fallback to single connection.
- **Windows Console & Arrow Navigation**: Native ANSI VT100 processing, UTF-8 reconfigured streams, and `msvcrt`-powered interactive arrow selection in CMD/PowerShell.
- **Best sellers first**: while browsing a platform, the best-selling titles
  (Wikipedia lists, 30-day cache) come first with ★; the rest follow alphabetically.
  Platforms without a full listing (PS4/PS5) are browsed through that best-seller
  list itself.
- **Fallback**: Archive.org on platforms with a thin catalogue.
- The catalog index is cached (`~/.cache/rom-cli/dlarchive.json`, 12h TTL) —
  which makes searches instant. `--refresh` rebuilds it.
- Ranking is by title match, with a penalty for hacks/translations/betas and a
  preference for `Base` over `Update`/`DLC`.
- Files are validated before being written (zip, 7z, `PFS0` for `.nsp`, and
  `PKG`/`CNT` for `.pkg`).
- Downloads are resumable (`.part` + `Range`).

## Remote mode (`rom-remote`)

Runs on the Mac worker (`ssh mac`) and brings the files back. Useful when this
Mac's network blocks the download hosts.

```bash
rom-remote -p switch "mario kart"    # opens the UI on the worker
rom-remote -y -p snes "metroid"      # downloads there and syncs back here
```

Tune it with `ROM_REMOTE_HOST`, `ROM_REMOTE_DIR` and `ROM_DIR`.

## Architecture & Internals

For a deep dive into the modular design, IDM-style multi-threaded chunked downloader, range probing, edge-case engineering, and provider subsystems, see:

📖 **[ARCHITECTURE.md](ARCHITECTURE.md)**

## Notice

Only use what you have the right to.
