"""Configuration constants, platform mappings, and paths for rom."""

import json
import os
import re
import sys

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

CACHE_DIR = os.path.expanduser(os.environ.get("XDG_CACHE_HOME") or "~/.cache") + "/rom-cli"
CONFIG_FILE = os.path.join(CACHE_DIR, "config.json")


def load_config():
    """Load persistent configuration dictionary."""
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg):
    """Save persistent configuration dictionary."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def get_out_dir():
    """Retrieve the configured download directory."""
    if os.environ.get("ROM_DIR"):
        return os.path.expanduser(os.environ["ROM_DIR"])
    cfg = load_config()
    if cfg.get("download_dir"):
        return os.path.expanduser(cfg["download_dir"])
    return os.path.expanduser("~/Downloads/roms")


def set_out_dir(path):
    """Save and persist a new default download directory."""
    clean = os.path.abspath(os.path.expanduser(path.strip()))
    cfg = load_config()
    cfg["download_dir"] = clean
    save_config(cfg)
    return clean


OUT_DIR = get_out_dir()
LOG_FILE = os.path.join(CACHE_DIR, "rom.log")
INDEX_FILE = os.path.join(CACHE_DIR, "dlarchive.json")
INDEX_TTL = 12 * 3600
INDEX_PAGE = 200

POPULAR_FILE = os.path.join(CACHE_DIR, "popular.json")
POPULAR_TTL = 30 * 86400
PORTS_FILE = os.path.join(CACHE_DIR, "switchports.json")
PORTS_TTL = 7 * 86400
PORTS_VER = 2

PLATFORMS = {
    "switch": ("dlarchive", "switch"),
    "switchports": ("dlarchive", "switch"),
    "nds": ("dlarchive", "nds"),
    "gba": ("dlarchive", "gba"),
    "snes": ("dlarchive", "snes"),
    "pc": ("dlarchive", "pc"),
    "nes": ("romsgames", ["nintendo"]),
    "gb": ("romsgames", ["gameboy"]),
    "gbc": ("romsgames", ["gameboy-color"]),
    "n64": ("romsgames", ["nintendo-64"]),
    "3ds": ("romsgames", ["nintendo-3ds"]),
    "gc": ("romsgames", ["gamecube"]),
    "wii": ("romsgames", ["nintendo-wii"]),
    "ps1": ("romsgames", ["playstation"]),
    "ps2": ("romsgames", ["playstation-2"]),
    "psp": ("romsgames", ["playstation-portable"]),
    "ps3": ("nps", "ps3"),
    "psv": ("nps", "psv"),
    "ps4": ("dlpsgame", "ps4"),
    "ps5": ("dlpsgame", "ps5"),
    "genesis": ("romsgames", ["sega-genesis"]),
    "mastersystem": ("romsgames", ["sega-master-system"]),
    "dreamcast": ("romsgames", ["sega-dreamcast"]),
    "saturn": ("romsgames", ["sega-saturn"]),
    "arcade": ("romsgames", ["mame", "snk-neo-geo"]),
    "xbox": ("romsgames", ["microsoft-xbox"]),
}

PLATFORM_LABELS = {
    "switch": "Switch", "switchports": "Switch Ports", "nds": "NDS", "gba": "GBA", "snes": "SNES", "ps2": "PS2",
    "psp": "PSP", "pc": "PC", "nes": "NES", "gb": "GB", "gbc": "GBC", "n64": "N64",
    "3ds": "3DS", "gc": "GameCube", "wii": "Wii", "ps1": "PS1", "ps3": "PS3",
    "psv": "PS Vita", "ps4": "PS4", "ps5": "PS5",
    "genesis": "Genesis", "mastersystem": "Master System", "dreamcast": "Dreamcast",
    "saturn": "Saturn", "arcade": "Arcade", "xbox": "Xbox",
}

LABELS = {
    "nintendo": "NES", "super-nintendo": "SNES", "nintendo-64": "N64", "gameboy": "GB",
    "gameboy-color": "GBC", "gameboy-advance": "GBA", "nintendo-ds": "NDS",
    "nintendo-3ds": "3DS", "gamecube": "GameCube", "nintendo-wii": "Wii",
    "playstation": "PS1", "playstation-2": "PS2", "playstation-3": "PS3",
    "playstation-portable": "PSP", "sega-genesis": "Genesis",
    "sega-master-system": "Master System", "sega-dreamcast": "Dreamcast",
    "sega-saturn": "Saturn", "mame": "Arcade", "snk-neo-geo": "Neo Geo",
    "microsoft-xbox": "Xbox",
}

LABEL_KEY = {v: k for k, v in PLATFORM_LABELS.items()}

ROM_EXTS = ("zip", "7z", "rar", "nsp", "xci", "nsz", "iso", "cia", "pkg", "rom",
            "bin", "sfc", "smc", "nes", "gba", "gbc", "gb", "nds", "n64", "z64",
            "md", "smd", "gcm", "wbfs", "rvz", "cso", "pbp", "xbe")
EXT_RE = re.compile(r"\.(" + "|".join(ROM_EXTS) + r")$", re.I)

STOP = {"the", "of", "a", "an", "and", "de", "do", "da", "o", "os", "as", "in",
        "to", "for", "e", "y", "the"}
BAD = ("romhack", "translation", "beta", "prototype", "demo", "sample", "unlicensed",
       "(hack)", "homebrew", "soundtrack", "manual", "emulator")

WIKI_LISTS = {
    "switch": "List_of_best-selling_Nintendo_Switch_video_games",
    "ps5": "List_of_best-selling_PlayStation_5_video_games",
    "ps4": "List_of_best-selling_PlayStation_4_video_games",
    "ps3": "List_of_best-selling_PlayStation_3_video_games",
    "ps2": "List_of_best-selling_PlayStation_2_video_games",
    "ps1": "List_of_best-selling_PlayStation_video_games",
    "psp": "List_of_best-selling_PlayStation_Portable_video_games",
    "nds": "List_of_best-selling_Nintendo_DS_video_games",
    "3ds": "List_of_best-selling_Nintendo_3DS_video_games",
    "gba": "List_of_best-selling_Game_Boy_Advance_video_games",
    "gb": "List_of_best-selling_Game_Boy_video_games",
    "snes": "List_of_best-selling_Super_Nintendo_Entertainment_System_video_games",
    "nes": "List_of_best-selling_Nintendo_Entertainment_System_video_games",
    "n64": "List_of_best-selling_Nintendo_64_video_games",
    "gc": "List_of_best-selling_GameCube_video_games",
    "wii": "List_of_best-selling_Wii_video_games",
    "genesis": "List_of_best-selling_Sega_Genesis_games",
    "xbox": "List_of_best-selling_Xbox_video_games",
    "gbc": "List_of_best-selling_Game_Boy_video_games",
    "dreamcast": "List_of_best-selling_Dreamcast_games",
    "saturn": "List_of_best-selling_Sega_Saturn_games",
}

TTY = sys.stdout.isatty()
