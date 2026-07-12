# characters/commanders/__init__.py
from characters.commanders.commander import Commander
from characters.commanders.mikasa import MikasaCommander
from characters.commanders.eren import ErenCommander

COMMANDER_TYPES: dict = {
    "Mikasa": MikasaCommander,
    "Eren": ErenCommander,
}

__all__ = [
    "Commander",
    "MikasaCommander",
    "ErenCommander",
    "COMMANDER_TYPES",
]
