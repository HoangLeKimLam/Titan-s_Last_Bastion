# characters/commanders/__init__.py
from characters.commanders.commander import Commander
from characters.commanders.eren import ErenCommander
from characters.commanders.mikasa import MikasaCommander
from characters.commanders.armin import ArminCommander

COMMANDER_TYPES: dict = {
    "Eren": ErenCommander,
    "Mikasa": MikasaCommander,
    "Armin": ArminCommander,
}

__all__ = [
    "Commander",
    "ErenCommander",
    "MikasaCommander",
    "ArminCommander",
    "COMMANDER_TYPES",
]
