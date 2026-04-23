"""Glyph + style tables for Paradroid rendering."""

from __future__ import annotations

from rich.style import Style

from . import droids as D


# --- terrain --------------------------------------------------------
TERRAIN_GLYPH = {
    "#": "█",    # wall
    ".": "·",    # floor (alt in tile_glyph_at)
    "+": "╬",    # door
    "O": "Ω",    # bridge / win tile
    ">": "◇",    # spawn tile
    " ": " ",    # exterior
}

# Two-glyph pattern for floor — palette rule #1 (never repeat).
FLOOR_A = "·"
FLOOR_B = " "

# Background colors (palette rule #7 — mostly black).
BG_DEFAULT = "rgb(8,8,12)"
BG_FLOOR = "rgb(10,12,18)"
BG_WALL = "rgb(18,18,28)"
BG_DOOR = "rgb(18,20,30)"
BG_BRIDGE = "rgb(10,20,30)"
BG_SPAWN = "rgb(18,10,10)"

S_WALL = Style.parse(f"rgb(90,100,130) on {BG_WALL}")
S_WALL_ALT = Style.parse(f"rgb(70,80,110) on {BG_WALL}")
S_FLOOR = Style.parse(f"rgb(48,54,72) on {BG_FLOOR}")
S_FLOOR_ALT = Style.parse(f"rgb(38,44,58) on {BG_FLOOR}")
S_DOOR = Style.parse(f"bold rgb(220,180,80) on {BG_DOOR}")
S_BRIDGE = Style.parse(f"bold rgb(120,230,255) on {BG_BRIDGE}")
S_SPAWN = Style.parse(f"rgb(200,90,90) on {BG_SPAWN}")
S_EMPTY = Style.parse(f"on {BG_DEFAULT}")


def terrain_glyph(t: str, x: int, y: int) -> str:
    if t == ".":
        return FLOOR_A if (x + y) & 1 else FLOOR_B
    return TERRAIN_GLYPH.get(t, " ")


def terrain_style(t: str, x: int, y: int) -> Style:
    if t == "#":
        return S_WALL if (x + y) & 1 else S_WALL_ALT
    if t == ".":
        return S_FLOOR if (x + y) & 1 else S_FLOOR_ALT
    if t == "+":
        return S_DOOR
    if t == "O":
        return S_BRIDGE
    if t == ">":
        return S_SPAWN
    return S_EMPTY


# --- droids ----------------------------------------------------------
# One glyph per broad class tier. Higher class = scarier-looking glyph.
def droid_glyph(class_id: int) -> str:
    if class_id <= 1:
        return "☺"           # player influence droid
    if class_id < 140:
        return "◇"           # small / service
    if class_id < 300:
        return "○"           # mid service
    if class_id < 450:
        return "●"           # guard
    if class_id < 550:
        return "◎"           # security
    if class_id < 650:
        return "◉"           # command / heavy guard
    if class_id < 800:
        return "♦"           # warrior / battle
    return "☠"               # cyborg / heavy warrior


def droid_style(class_id: int, is_player: bool = False) -> Style:
    if is_player:
        return Style.parse(f"bold rgb(90,220,255) on {BG_FLOOR}")
    if class_id < 200:
        return Style.parse(f"rgb(160,200,160) on {BG_FLOOR}")
    if class_id < 350:
        return Style.parse(f"rgb(200,200,120) on {BG_FLOOR}")
    if class_id < 500:
        return Style.parse(f"bold rgb(230,170,90) on {BG_FLOOR}")
    if class_id < 700:
        return Style.parse(f"bold rgb(255,120,120) on {BG_FLOOR}")
    return Style.parse(f"bold rgb(255,90,255) on {BG_FLOOR}")


# --- bullets ---------------------------------------------------------
def bullet_style(damage: int) -> Style:
    if damage <= 2:
        return Style.parse(f"rgb(220,220,140) on {BG_FLOOR}")
    if damage <= 5:
        return Style.parse(f"bold rgb(255,200,80) on {BG_FLOOR}")
    return Style.parse(f"bold rgb(255,120,90) on {BG_FLOOR}")
