"""Provider registry and catalog instances."""

from rom.providers.archive_org import ArchiveOrg
from rom.providers.base import BaseProvider, Result, request
from rom.providers.dlarchive import DlArchive
from rom.providers.dlpsgame import DlpsGame
from rom.providers.nopaystation import NoPayStation
from rom.providers.romsgames import RomsGames

DLA = DlArchive()
NPS = NoPayStation()
DLP = DlpsGame()
ROMSGAMES = RomsGames()
ARCHIVE_ORG = ArchiveOrg()

SOURCES = {
    "dlarchive": DLA,
    "romsgames": ROMSGAMES,
    "archive.org": ARCHIVE_ORG,
    "nps": NPS,
    "dlpsgame": DLP,
}

__all__ = [
    "BaseProvider",
    "Result",
    "request",
    "DLA",
    "NPS",
    "DLP",
    "ROMSGAMES",
    "ARCHIVE_ORG",
    "SOURCES",
]
