"""Procedural ship-deck generator.

Generates a 30×18 grid of walls, floor, doors, and a set of rooms.
Rooms are named so the status bar + overlays can show which one the
player is in. Each room has a spawn count for starter droids.

Emitted as a simple ASCII grid:
    '#' wall
    '.' floor
    '+' door (passable; closed for flavor)
    ' ' exterior (unreachable — only around edges)
    '>' spawn tile
    '<' player spawn
    'O' bridge tile (win condition)

Plus a list of `Room(name, x0, y0, w, h)` for labeling.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


WIDTH = 30
HEIGHT = 18


@dataclass
class Room:
    name: str
    x: int
    y: int
    w: int
    h: int
    is_bridge: bool = False

    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def contains(self, x: int, y: int) -> bool:
        return (self.x <= x < self.x + self.w
                and self.y <= y < self.y + self.h)


@dataclass
class Deck:
    grid: list[list[str]]
    rooms: list[Room]
    player_spawn: tuple[int, int]
    spawn_tiles: list[tuple[int, int]]
    bridge_tile: tuple[int, int]
    width: int = WIDTH
    height: int = HEIGHT


# Fixed hand-designed layout. Rooms are labeled so they're
# recognizable. Deterministic regardless of seed (seed only affects
# droid placement + order).
_ROOM_DEFS: list[tuple[str, int, int, int, int, bool]] = [
    # name,          x,  y,   w, h, is_bridge
    ("Transporter",   2,  2,  6, 5, False),
    ("Armory",       10,  2,  6, 5, False),
    ("Hold",         18,  2,  5, 5, False),
    ("Bridge",       24,  2,  5, 5, True),
    ("Engineering",   2,  9,  8, 7, False),
    ("Brig",         12,  9,  5, 4, False),
    ("Science",      12, 14,  5, 3, False),
    ("Reactor",      19,  9,  9, 7, False),
]


def generate(seed: int = 0) -> Deck:
    rng = random.Random(seed)
    grid: list[list[str]] = [[" "] * WIDTH for _ in range(HEIGHT)]

    # Outer hull — a big rectangle of walls (unused exterior beyond).
    for y in range(HEIGHT):
        for x in range(WIDTH):
            grid[y][x] = "#"

    rooms: list[Room] = []
    for (name, x, y, w, h, is_bridge) in _ROOM_DEFS:
        # Fill room interior with floor.
        for ry in range(y + 1, y + h - 1):
            for rx in range(x + 1, x + w - 1):
                grid[ry][rx] = "."
        # Walls around the room remain '#'.
        rooms.append(Room(name, x, y, w, h, is_bridge))

    # Connect corridors. We carve straight corridors between
    # room-edge midpoints, which makes a clean starship feel.
    corridors: list[tuple[tuple[int, int], tuple[int, int]]] = [
        # Top row connections
        ((5, 2), (5, 9)),      # Transporter ↓ Engineering
        ((13, 2), (13, 9)),    # Armory ↓ Brig
        ((13, 13), (13, 14)),  # Brig ↓ Science
        ((20, 2), (20, 9)),    # Hold ↓ Reactor
        ((26, 2), (26, 9)),    # Bridge ↓ Reactor
        # Horizontal spine row 4 (between top rooms)
        ((8, 4), (10, 4)),
        ((16, 4), (18, 4)),
        ((23, 4), (24, 4)),
        # Horizontal mid spine row 11
        ((10, 11), (12, 11)),
        ((17, 11), (19, 11)),
        # Long center corridor row 7
        *[((x, 7), (x + 1, 7)) for x in range(2, 28)],
        # Vertical corridor down col 8 from row 4..9
        ((8, 4), (8, 9)),
    ]

    for (ax, ay), (bx, by) in corridors:
        # carve a floor line between (ax,ay) and (bx,by) — inclusive.
        x, y = ax, ay
        while (x, y) != (bx, by):
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                if grid[y][x] == "#":
                    grid[y][x] = "."
            if x < bx:
                x += 1
            elif x > bx:
                x -= 1
            elif y < by:
                y += 1
            elif y > by:
                y -= 1
        # final cell
        if 0 <= x < WIDTH and 0 <= y < HEIGHT and grid[y][x] == "#":
            grid[y][x] = "."

    # Doors — put '+' at the intersection of a corridor + room wall.
    # We detect: a wall tile with floor on both sides (N/S or E/W).
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            if grid[y][x] != "#":
                continue
            n = grid[y - 1][x]
            s = grid[y + 1][x]
            e = grid[y][x + 1]
            w_t = grid[y][x - 1]
            if (n == "." and s == ".") or (e == "." and w_t == "."):
                grid[y][x] = "+"

    # Player spawn — Transporter center.
    tran = rooms[0]
    psx, psy = tran.center()
    grid[psy][psx] = "<"
    player_spawn = (psx, psy)

    # Bridge tile
    bridge = next(r for r in rooms if r.is_bridge)
    bx, by = bridge.center()
    grid[by][bx] = "O"
    bridge_tile = (bx, by)

    # Spawn tiles — one in each non-Transporter, non-Bridge room.
    spawn_tiles: list[tuple[int, int]] = []
    for r in rooms:
        if r is tran or r.is_bridge:
            continue
        # place a spawn tile on a random floor cell in the room
        candidates = [
            (x, y) for y in range(r.y + 1, r.y + r.h - 1)
            for x in range(r.x + 1, r.x + r.w - 1)
            if grid[y][x] == "."
        ]
        if not candidates:
            continue
        x, y = rng.choice(candidates)
        grid[y][x] = ">"
        spawn_tiles.append((x, y))

    return Deck(grid=grid, rooms=rooms,
                player_spawn=player_spawn,
                spawn_tiles=spawn_tiles,
                bridge_tile=bridge_tile)


def room_at(deck: Deck, x: int, y: int) -> Room | None:
    for r in deck.rooms:
        if r.contains(x, y):
            return r
    return None
