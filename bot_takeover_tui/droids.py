"""Droid taxonomy — class IDs, armor, weapons, AI behaviors.

Class IDs match the well-documented C64 Paradroid subset. See
DECISIONS.md for the full table.
"""

from __future__ import annotations

from dataclasses import dataclass


# AI modes
AI_PLAYER = "player"
AI_IDLE = "idle"
AI_WANDER = "wander"
AI_PATROL = "patrol"
AI_PURSUE = "pursue"
AI_HUNT = "hunt"

# Weapon kinds. `cooldown` is ticks between shots.
# `damage` is applied per hit; `range` is cells bullet travels before fade.
WEAPONS: dict[str, dict] = {
    "none":     {"damage": 0, "cooldown": 9999, "range": 0,  "glyph": " "},
    "taser":    {"damage": 1, "cooldown":    4, "range": 3,  "glyph": "·"},
    "stun":     {"damage": 1, "cooldown":    5, "range": 5,  "glyph": "."},
    "laser-s":  {"damage": 2, "cooldown":    5, "range": 8,  "glyph": "-"},
    "laser-m":  {"damage": 3, "cooldown":    4, "range": 10, "glyph": "="},
    "laser-l":  {"damage": 4, "cooldown":    4, "range": 12, "glyph": "═"},
    "plasma":   {"damage": 5, "cooldown":    5, "range": 10, "glyph": "◆"},
    "double":   {"damage": 6, "cooldown":    4, "range": 10, "glyph": "◈"},
    "missile":  {"damage": 7, "cooldown":    8, "range": 14, "glyph": "▶"},
    "rocket":   {"damage": 8, "cooldown":    6, "range": 14, "glyph": "▷"},
    "disruptr": {"damage":10, "cooldown":    5, "range": 12, "glyph": "♦"},
}


@dataclass
class DroidClass:
    class_id: int
    name: str
    armor: int
    weapon: str
    speed_ticks: int   # number of engine ticks per move (higher = slower)
    ai: str            # AI mode name


# The canonical Paradroid droid ladder. Class 001 is the player's
# influence droid. 999 is the command cyborg.
CLASSES: list[DroidClass] = [
    DroidClass(  1, "Influence",      1,  "taser",    2, AI_PLAYER),
    DroidClass(123, "Disposal",       2,  "none",     4, AI_WANDER),
    DroidClass(139, "Messenger",      2,  "stun",     3, AI_PATROL),
    DroidClass(247, "Service",        3,  "laser-s",  3, AI_WANDER),
    DroidClass(249, "Maintenance",    3,  "laser-s",  3, AI_PATROL),
    DroidClass(296, "Science",        3,  "stun",     4, AI_IDLE),
    DroidClass(302, "Engineer",       4,  "laser-m",  3, AI_PATROL),
    DroidClass(329, "Interior Guard", 5,  "laser-m",  3, AI_PURSUE),
    DroidClass(420, "Exterior Guard", 6,  "laser-l",  3, AI_PURSUE),
    DroidClass(476, "Interior Sec",   7,  "plasma",   3, AI_PURSUE),
    DroidClass(493, "Exterior Sec",   8,  "plasma",   3, AI_PURSUE),
    DroidClass(516, "Command",        9,  "plasma",   2, AI_PURSUE),
    DroidClass(571, "Heavy Guard",   10,  "double",   3, AI_HUNT),
    DroidClass(598, "Heavy Command", 11,  "double",   3, AI_HUNT),
    DroidClass(629, "Special Guard", 12,  "missile",  3, AI_HUNT),
    DroidClass(711, "Warrior",       14,  "rocket",   2, AI_HUNT),
    DroidClass(742, "Battle",        16,  "rocket",   2, AI_HUNT),
    DroidClass(751, "Heavy Battle",  18,  "rocket",   3, AI_HUNT),
    DroidClass(821, "Heavy Warrior", 20,  "rocket",   3, AI_HUNT),
    DroidClass(999, "Command Cyborg",25,  "disruptr", 2, AI_HUNT),
]


_BY_ID: dict[int, DroidClass] = {c.class_id: c for c in CLASSES}


def get_class(class_id: int) -> DroidClass:
    """Look up a droid class. Returns nearest known class if unknown."""
    if class_id in _BY_ID:
        return _BY_ID[class_id]
    # Fallback: nearest class by numeric distance. Robustness — never
    # crash on unexpected IDs.
    nearest = min(CLASSES, key=lambda c: abs(c.class_id - class_id))
    return nearest


def class_above(class_id: int) -> DroidClass | None:
    """Next-stronger class, or None if 999."""
    ids = [c.class_id for c in CLASSES]
    for cid in ids:
        if cid > class_id:
            return _BY_ID[cid]
    return None


def classes_in_range(lo: int, hi: int) -> list[DroidClass]:
    """All known classes with lo <= class_id <= hi."""
    return [c for c in CLASSES if lo <= c.class_id <= hi]


def weapon(kind: str) -> dict:
    """Look up a weapon spec. Returns 'none' if unknown (robustness)."""
    return WEAPONS.get(kind, WEAPONS["none"])
