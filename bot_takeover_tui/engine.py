"""Paradroid engine — pure-Python, clean-room reimplementation.

Design decisions in DECISIONS.md. Summary:
- 30×18 single-deck grid, procedurally generated with named rooms.
- Player controls a droid of class 001..999 (starts 001 "Influence").
- Other droids patrol / pursue / hunt per their class AI mode.
- Fire bullets that travel N cells/tick; damage -> armor 0 -> kill.
- Transfer is a separate state machine (see `transfer.py`); engine
  exposes `start_transfer(target)` / `finish_transfer(won, new_class)`.
- Real-time tick driven by the app's set_interval; engine tick is
  `Game.tick()` with a directional input queue.

Grid tiles: see `deck.py`. Engine sees:
    '#' wall (blocks movement and bullets)
    '.' floor
    '+' door (passable)
    'O' bridge (win tile — player stepping on WINS)
    '>' spawn tile
    '<' player-spawn marker (we convert to '.' at load)

Actions:
    ACT_NONE, ACT_LEFT, ACT_RIGHT, ACT_UP, ACT_DOWN — queue a
    direction. Also set `facing`.
    ACT_FIRE — fire in current `facing`.
    ACT_TRANSFER — initiate transfer on adjacent non-player droid.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from . import droids as D
from .deck import Deck, Room, generate as gen_deck, room_at
from .transfer import TransferGame


# --- actions ---------------------------------------------------------
ACT_NONE = 0
ACT_LEFT = 1
ACT_RIGHT = 2
ACT_UP = 3
ACT_DOWN = 4
ACT_FIRE = 5
ACT_TRANSFER = 6
ACT_WAIT = 7

DIRS = {
    ACT_LEFT:  (-1, 0),
    ACT_RIGHT: (1, 0),
    ACT_UP:    (0, -1),
    ACT_DOWN:  (0, 1),
}


# --- entities --------------------------------------------------------


@dataclass(eq=False)
class Droid:
    """Identity-based entity. See the skill's `eq=False` guidance —
    two droids at the same coord with the same class should NOT
    compare equal (otherwise list.remove picks the wrong one)."""
    id: int
    class_id: int
    x: int
    y: int
    armor: int
    facing: tuple[int, int] = (1, 0)   # (dx, dy)
    cooldown: int = 0                  # ticks until can fire again
    move_cooldown: int = 0             # ticks until can move again
    is_player: bool = False
    patrol: list[tuple[int, int]] = field(default_factory=list)
    patrol_i: int = 0
    # AI scratchpad
    last_seen_player: tuple[int, int] | None = None


@dataclass(eq=False)
class Bullet:
    x: int
    y: int
    dx: int
    dy: int
    damage: int
    range_left: int
    owner_id: int
    glyph: str = "·"


@dataclass
class TickResult:
    player_moved: bool = False
    player_fired: bool = False
    shots_fired: int = 0
    droids_killed: int = 0
    player_hit: int = 0                # damage taken this tick
    player_dead: bool = False
    won: bool = False
    transfer_started: int | None = None  # target droid_id
    reason: str = ""


# --- the game --------------------------------------------------------


@dataclass
class Game:
    deck: Deck
    droids: list[Droid] = field(default_factory=list)
    bullets: list[Bullet] = field(default_factory=list)
    tick_count: int = 0
    alert_level: int = 0       # 0..9
    alert_float: float = 0.0   # continuous version for decay
    score: int = 0
    won: bool = False
    dead: bool = False
    reason: str = ""
    _next_id: int = 1
    _rng: random.Random = field(default_factory=lambda: random.Random(0))
    # One-shot action queue filled by the app's input handlers.
    _queued_action: int = ACT_NONE
    # Active transfer mini-game, if any.
    transfer: TransferGame | None = None
    # The droid targeted by current transfer (so we can apply body-swap).
    transfer_target_id: int | None = None

    # -------- construction --------------------------------------------

    @classmethod
    def new(cls, seed: int = 0,
            n_droids: int = 8) -> "Game":
        rng = random.Random(seed)
        deck = gen_deck(seed=seed)
        g = cls(deck=deck, _rng=rng)

        # Player droid starts on the player_spawn tile.
        px, py = deck.player_spawn
        player = g._new_droid(class_id=1, x=px, y=py, is_player=True)
        # overwrite the '<' marker so render looks clean
        g.deck.grid[py][px] = "."

        # Place initial droids. Light mix: disposal/service/guard.
        starter_classes = [123, 139, 247, 249, 296, 302, 329, 420]
        # Shuffle deterministically.
        rng.shuffle(starter_classes)
        placed = 0
        for room in deck.rooms:
            if placed >= n_droids:
                break
            if room.is_bridge or room.name == "Transporter":
                continue
            cls_id = starter_classes[placed % len(starter_classes)]
            # find a floor cell not already occupied
            spot = g._find_spawn_in_room(room)
            if spot is None:
                continue
            x, y = spot
            d = g._new_droid(class_id=cls_id, x=x, y=y)
            # patrol = all 4 corners inside the room walls
            r = room
            d.patrol = [
                (r.x + 1, r.y + 1),
                (r.x + r.w - 2, r.y + 1),
                (r.x + r.w - 2, r.y + r.h - 2),
                (r.x + 1, r.y + r.h - 2),
            ]
            placed += 1

        return g

    def _new_droid(self, class_id: int, x: int, y: int,
                   is_player: bool = False) -> Droid:
        spec = D.get_class(class_id)
        d = Droid(
            id=self._next_id,
            class_id=class_id,
            x=x, y=y,
            armor=spec.armor,
            is_player=is_player,
        )
        self._next_id += 1
        self.droids.append(d)
        return d

    def _find_spawn_in_room(self, room: Room) -> tuple[int, int] | None:
        for y in range(room.y + 1, room.y + room.h - 1):
            for x in range(room.x + 1, room.x + room.w - 1):
                if self.deck.grid[y][x] not in (".", ">"):
                    continue
                if self.droid_at(x, y) is not None:
                    continue
                return (x, y)
        return None

    # -------- queries -------------------------------------------------

    def player(self) -> Droid | None:
        for d in self.droids:
            if d.is_player:
                return d
        return None

    def droid_at(self, x: int, y: int) -> Droid | None:
        for d in self.droids:
            if d.x == x and d.y == y:
                return d
        return None

    def enemies(self) -> list[Droid]:
        return [d for d in self.droids if not d.is_player]

    def alive_enemies(self) -> int:
        return len(self.enemies())

    def is_passable(self, x: int, y: int) -> bool:
        if x < 0 or x >= self.deck.width or y < 0 or y >= self.deck.height:
            return False
        t = self.deck.grid[y][x]
        return t in (".", "+", "O", ">")

    def is_passable_for_bullet(self, x: int, y: int) -> bool:
        if x < 0 or x >= self.deck.width or y < 0 or y >= self.deck.height:
            return False
        t = self.deck.grid[y][x]
        return t != "#"  # doors + open tiles let bullets pass

    # -------- input queue --------------------------------------------

    def queue_action(self, action: int) -> None:
        """Set the player's pending action. Replaces any earlier one."""
        self._queued_action = action

    # -------- tick ---------------------------------------------------

    def tick(self) -> TickResult:
        res = TickResult()
        if self.won or self.dead or self.transfer is not None:
            # Pause real time during transfer or after the game ends.
            return res

        # --- Player action ------------------------------------------
        self._tick_player(res)

        # --- Bullets move -------------------------------------------
        self._tick_bullets(res)

        # --- Enemy AI -----------------------------------------------
        self._tick_enemies(res)

        # --- Decay cooldowns ----------------------------------------
        for d in self.droids:
            if d.cooldown > 0:
                d.cooldown -= 1
            if d.move_cooldown > 0:
                d.move_cooldown -= 1

        # --- Security alert -----------------------------------------
        self.alert_float = max(0.0, self.alert_float - 0.01)
        # Spawn hostiles at high alert.
        if (self.alert_level >= 3
                and self.tick_count % 60 == 0
                and len(self.enemies()) < 12):
            self._maybe_spawn_hostile()
        self.alert_level = max(0, min(9, int(self.alert_float)))

        # --- Win / lose checks --------------------------------------
        p = self.player()
        if p is None:
            self.dead = True
            res.player_dead = True
            res.reason = "no host"
        else:
            # step on Bridge tile → win
            if (p.x, p.y) == self.deck.bridge_tile:
                self.won = True
                res.won = True
            # if no enemies remain → win
            if self.alive_enemies() == 0:
                self.won = True
                res.won = True

        self.tick_count += 1
        return res

    # -------- player action ------------------------------------------

    def _tick_player(self, res: TickResult) -> None:
        p = self.player()
        if p is None:
            return
        act = self._queued_action
        self._queued_action = ACT_NONE

        if act in DIRS:
            dx, dy = DIRS[act]
            p.facing = (dx, dy)
            if p.move_cooldown == 0:
                nx, ny = p.x + dx, p.y + dy
                if self.is_passable(nx, ny) and self.droid_at(nx, ny) is None:
                    p.x, p.y = nx, ny
                    res.player_moved = True
                    spec = D.get_class(p.class_id)
                    p.move_cooldown = spec.speed_ticks
        elif act == ACT_FIRE:
            if self._fire(p):
                res.player_fired = True
                res.shots_fired += 1
        elif act == ACT_TRANSFER:
            # Initiate transfer on adjacent droid in facing direction.
            tx, ty = p.x + p.facing[0], p.y + p.facing[1]
            target = self.droid_at(tx, ty)
            if target is not None and not target.is_player:
                self.start_transfer(target)
                res.transfer_started = target.id
        # ACT_NONE / ACT_WAIT — no-op

    def _fire(self, d: Droid) -> bool:
        spec = D.get_class(d.class_id)
        wpn = D.weapon(spec.weapon)
        if wpn["damage"] == 0:
            return False
        if d.cooldown > 0:
            return False
        dx, dy = d.facing
        if (dx, dy) == (0, 0):
            dx = 1
        bx, by = d.x + dx, d.y + dy
        if not self.is_passable_for_bullet(bx, by):
            return False
        b = Bullet(
            x=bx, y=by, dx=dx, dy=dy,
            damage=wpn["damage"],
            range_left=wpn["range"],
            owner_id=d.id,
            glyph=wpn["glyph"],
        )
        self.bullets.append(b)
        d.cooldown = wpn["cooldown"]
        return True

    # -------- bullets -------------------------------------------------

    def _tick_bullets(self, res: TickResult) -> None:
        # Bullets move 2 cells per tick (speed). We advance in 2 sub-steps
        # so collisions happen cell-by-cell.
        remaining: list[Bullet] = []
        for b in self.bullets:
            alive = True
            for _step in range(2):
                # Check current cell for hit
                d = self.droid_at(b.x, b.y)
                if d is not None and d.id != b.owner_id:
                    # hit!
                    d.armor -= b.damage
                    alive = False
                    if d.is_player:
                        res.player_hit += b.damage
                    if d.armor <= 0:
                        self._kill_droid(d, res)
                    break
                if not self.is_passable_for_bullet(b.x, b.y):
                    alive = False
                    break
                b.range_left -= 1
                if b.range_left <= 0:
                    alive = False
                    break
                b.x += b.dx
                b.y += b.dy
            if alive:
                remaining.append(b)
        self.bullets = remaining

    def _kill_droid(self, d: Droid, res: TickResult) -> None:
        if d.is_player:
            self.dead = True
            res.player_dead = True
            res.reason = "destroyed"
            # remove player too
        # Remove by identity — rely on @dataclass(eq=False).
        try:
            self.droids.remove(d)
        except ValueError:
            pass
        res.droids_killed += 1
        if not d.is_player:
            self.score += d.class_id
            self.alert_float = min(9.99, self.alert_float + 0.3)

    # -------- enemy AI -----------------------------------------------

    def _tick_enemies(self, res: TickResult) -> None:
        p = self.player()
        if p is None:
            return
        for d in self.enemies():
            spec = D.get_class(d.class_id)
            if d.move_cooldown > 0:
                # Still move AI decision forward? No — movement-gated.
                continue

            mode = spec.ai
            next_pos: tuple[int, int] | None = None

            if mode == D.AI_IDLE:
                # Only move if player in LOS AND adjacent.
                if self._has_los(d, p):
                    next_pos = self._step_toward(d.x, d.y, (p.x, p.y))
            elif mode == D.AI_WANDER:
                next_pos = self._wander_step(d)
            elif mode == D.AI_PATROL:
                # If player LOS, pursue; else continue patrol.
                if self._has_los(d, p):
                    next_pos = self._step_toward(d.x, d.y, (p.x, p.y))
                else:
                    next_pos = self._patrol_step(d)
            elif mode == D.AI_PURSUE:
                # BFS toward player if within 10 cells.
                if self._manhattan(d, p) <= 10:
                    next_pos = self._step_toward(d.x, d.y, (p.x, p.y))
                else:
                    next_pos = self._wander_step(d)
            elif mode == D.AI_HUNT:
                next_pos = self._step_toward(d.x, d.y, (p.x, p.y))

            if next_pos is not None:
                nx, ny = next_pos
                # Update facing regardless of whether the move succeeds.
                d.facing = (
                    (1 if nx > d.x else -1 if nx < d.x else d.facing[0]),
                    (1 if ny > d.y else -1 if ny < d.y else d.facing[1]),
                )
                if (self.is_passable(nx, ny)
                        and self.droid_at(nx, ny) is None):
                    d.x, d.y = nx, ny
                    d.move_cooldown = spec.speed_ticks

            # Shoot if has LOS to player and weapon ready.
            if self._has_los(d, p) and self._aligned(d, p):
                wpn = D.weapon(spec.weapon)
                if wpn["damage"] > 0 and d.cooldown == 0:
                    self._fire(d)

    def _wander_step(self, d: Droid) -> tuple[int, int] | None:
        """Random step; if blocked, turn. Deterministic via self._rng."""
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        self._rng.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = d.x + dx, d.y + dy
            if (self.is_passable(nx, ny)
                    and self.droid_at(nx, ny) is None):
                return (nx, ny)
        return None

    def _patrol_step(self, d: Droid) -> tuple[int, int] | None:
        if not d.patrol:
            return None
        target = d.patrol[d.patrol_i]
        if (d.x, d.y) == target:
            d.patrol_i = (d.patrol_i + 1) % len(d.patrol)
            target = d.patrol[d.patrol_i]
        return self._step_toward(d.x, d.y, target)

    def _manhattan(self, a: Droid, b: Droid) -> int:
        return abs(a.x - b.x) + abs(a.y - b.y)

    def _aligned(self, a: Droid, b: Droid) -> bool:
        return a.x == b.x or a.y == b.y

    def _has_los(self, a: Droid, b: Droid, max_dist: int = 14) -> bool:
        """Bresenham-ish line-of-sight — walls block."""
        if not self._aligned(a, b):
            return False
        if abs(a.x - b.x) + abs(a.y - b.y) > max_dist:
            return False
        if a.x == b.x:
            y0, y1 = sorted([a.y, b.y])
            for y in range(y0 + 1, y1):
                if self.deck.grid[y][a.x] == "#":
                    return False
            return True
        y = a.y
        x0, x1 = sorted([a.x, b.x])
        for x in range(x0 + 1, x1):
            if self.deck.grid[y][x] == "#":
                return False
        return True

    def _step_toward(self, sx: int, sy: int,
                     target: tuple[int, int],
                     max_nodes: int = 500) -> tuple[int, int] | None:
        """BFS one-step path planner. Returns the first step from (sx,sy)
        toward `target`, or None if no path found within node budget."""
        if (sx, sy) == target:
            return None
        seen: dict[tuple[int, int], tuple[int, int] | None] = {(sx, sy): None}
        q: deque[tuple[int, int]] = deque([(sx, sy)])
        nodes = 0
        found = None
        while q and nodes < max_nodes:
            nodes += 1
            x, y = q.popleft()
            if (x, y) == target:
                found = (x, y)
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in seen:
                    continue
                if not self.is_passable(nx, ny):
                    continue
                # allow target cell even if occupied (so we find a path
                # that ends at the player); but otherwise block occupied
                occ = self.droid_at(nx, ny)
                if occ is not None and (nx, ny) != target:
                    continue
                seen[(nx, ny)] = (x, y)
                q.append((nx, ny))
        if found is None:
            # Greedy fallback — closest reached cell
            best = None
            best_d = 1 << 30
            for (x, y) in seen:
                if (x, y) == (sx, sy):
                    continue
                d = abs(x - target[0]) + abs(y - target[1])
                if d < best_d:
                    best_d = d
                    best = (x, y)
            if best is None:
                return None
            found = best
        # Walk back to first step.
        prev = found
        while True:
            parent = seen[prev]
            if parent is None or parent == (sx, sy):
                return prev
            prev = parent

    # -------- transfer -----------------------------------------------

    def start_transfer(self, target: Droid) -> None:
        p = self.player()
        if p is None:
            return
        self.transfer = TransferGame.new(
            player_class=p.class_id,
            host_class=target.class_id,
            seed=self.tick_count,
        )
        self.transfer_target_id = target.id

    def finish_transfer(self) -> None:
        """Called when the transfer mini-game is over. Applies result."""
        if self.transfer is None:
            return
        won = self.transfer.won
        target_id = self.transfer_target_id
        self.transfer = None
        self.transfer_target_id = None
        p = self.player()
        if p is None:
            return
        target = next((d for d in self.droids if d.id == target_id), None)
        if target is None:
            return
        if won:
            # Body-swap: player becomes the target's class.
            p.class_id = target.class_id
            spec = D.get_class(p.class_id)
            p.armor = spec.armor
            # The target droid is destroyed.
            try:
                self.droids.remove(target)
            except ValueError:
                pass
            self.score += target.class_id * 2
            self.alert_float = min(9.99, self.alert_float + 0.5)
        else:
            # Player loses some armor on failed transfer.
            p.armor = max(0, p.armor - 2)
            if p.armor <= 0:
                self.dead = True
                self.reason = "transfer failed"

    # -------- hostile spawning ---------------------------------------

    def _maybe_spawn_hostile(self) -> None:
        if not self.deck.spawn_tiles:
            return
        tile = self._rng.choice(self.deck.spawn_tiles)
        if self.droid_at(*tile) is not None:
            return
        # Pick a class roughly matching alert.
        target_class = 100 + self.alert_level * 80
        candidates = D.classes_in_range(max(100, target_class - 80),
                                        target_class + 80)
        if not candidates:
            candidates = [D.CLASSES[1]]  # disposal fallback
        spec = self._rng.choice(candidates)
        self._new_droid(class_id=spec.class_id, x=tile[0], y=tile[1])
