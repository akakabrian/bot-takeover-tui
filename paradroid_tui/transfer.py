"""Transfer mini-game — the iconic circuit-puzzle.

Simplified TUI-native variant of Braybrook's 1985 "flow" duel. See
DECISIONS.md for why we use this shape rather than the pixel-accurate
12-column board.

Game shape
----------
- 6 rows. Each row is a tally of +/- pulses.
- Both sides take turns placing into rows:
    Player plays `+` (energizer) in a chosen row.
    Opponent plays `−` (siphon). AI chooses the row with the
    smallest negative lead (most at-risk).
- Total turns = `rounds` × 2 (default 10 player + 10 opponent).
- Per-row score: (player pluses) - (opponent minuses).
  Row is WON if score > 0, LOST if score < 0, TIED if 0.
- Transfer result after all rounds:
    Player must win at least `threshold` of 6 rows.
    threshold = 4 baseline, adjusted by relative class:
      weaker host  (class_host <= class_player) -> 2
      even                                      -> 3 or 4
      stronger host (class_host > class_player) -> 5

Opponent also gets bonus starter `-` pulses equal to
`max(0, (host_class - player_class) // 100)`, placed automatically
on random rows at init. (Higher-class hosts resist harder.)

Player / opponent "energy":
- Player starts with `rounds` energizers.
- Opponent starts with `rounds` siphons + bonus.

The game exposes a pure-Python state machine so the TUI screen just
reads fields and calls `play_player(row)` / `play_ai_turn()` /
`is_over()` / `result()`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


N_ROWS = 6


@dataclass(eq=False)
class TransferGame:
    """Circuit-puzzle state.

    The `eq=False` keeps identity semantics for list ops (not strictly
    needed here but matches the skill's guidance on entity-ish
    dataclasses).
    """
    player_class: int
    host_class: int
    rounds: int = 10        # moves per side
    rows: list[int] = field(default_factory=list)  # per-row tally
    player_left: int = 0    # pluses remaining
    opp_left: int = 0       # minuses remaining
    turn: str = "player"    # "player" | "opp"
    finished: bool = False
    won: bool = False       # player won the transfer
    log: list[str] = field(default_factory=list)
    _rng: random.Random = field(default_factory=lambda: random.Random(0))
    # For the TUI cursor.
    selected_row: int = 0

    @classmethod
    def new(cls, player_class: int, host_class: int,
            seed: int = 0, rounds: int = 10) -> "TransferGame":
        rng = random.Random(seed)
        g = cls(
            player_class=player_class,
            host_class=host_class,
            rounds=rounds,
            rows=[0] * N_ROWS,
            player_left=rounds,
            opp_left=rounds,
            _rng=rng,
        )
        # Bonus siphons for tougher hosts.
        bonus = max(0, (host_class - player_class) // 100)
        for _ in range(bonus):
            r = rng.randrange(N_ROWS)
            g.rows[r] -= 1
            g.log.append(f"bonus siphon row {r + 1}")
        return g

    # ---- rules -------------------------------------------------------

    def threshold(self) -> int:
        """Rows the player needs to WIN to transfer."""
        if self.host_class <= self.player_class:
            return 2
        diff = self.host_class - self.player_class
        if diff < 100:
            return 3
        if diff < 300:
            return 4
        return 5

    def play_player(self, row: int) -> bool:
        """Place a player `+` in row (0..5). Returns True if played."""
        if self.finished:
            return False
        if self.turn != "player":
            return False
        if row < 0 or row >= N_ROWS:
            return False
        if self.player_left <= 0:
            return False
        self.rows[row] += 1
        self.player_left -= 1
        self.log.append(f"+ row {row + 1}")
        self.selected_row = row
        self.turn = "opp"
        self._maybe_finish()
        return True

    def play_ai_turn(self) -> int | None:
        """AI places a `-` in the row currently least negative (most
        at-risk from player's perspective = most worth sabotaging).
        Returns the row chosen, or None if skipped."""
        if self.finished:
            return None
        if self.turn != "opp":
            return None
        if self.opp_left <= 0:
            # Opp has no siphons left; pass turn.
            self.turn = "player"
            self._maybe_finish()
            return None
        # Pick row whose CURRENT score is highest (most player-led) —
        # the siphon hurts it most.
        best = 0
        best_score = self.rows[0]
        for i in range(1, N_ROWS):
            if self.rows[i] > best_score:
                best = i
                best_score = self.rows[i]
        # Tiebreak: random row to keep things lively.
        ties = [i for i in range(N_ROWS) if self.rows[i] == best_score]
        chosen = self._rng.choice(ties)
        self.rows[chosen] -= 1
        self.opp_left -= 1
        self.log.append(f"− row {chosen + 1}")
        self.turn = "player"
        self._maybe_finish()
        return chosen

    def forfeit(self) -> None:
        """Player aborts the transfer — lose."""
        if self.finished:
            return
        self.finished = True
        self.won = False
        self.log.append("forfeit")

    def _maybe_finish(self) -> None:
        if self.player_left <= 0 and self.opp_left <= 0:
            self._finalize()

    def _finalize(self) -> None:
        won_rows = sum(1 for v in self.rows if v > 0)
        self.finished = True
        self.won = won_rows >= self.threshold()
        self.log.append(
            f"FINAL: {won_rows}/{N_ROWS} rows, "
            f"threshold {self.threshold()}"
        )

    def is_over(self) -> bool:
        return self.finished

    def rows_won(self) -> int:
        return sum(1 for v in self.rows if v > 0)

    def rows_lost(self) -> int:
        return sum(1 for v in self.rows if v < 0)

    def result_str(self) -> str:
        if not self.finished:
            return "(in progress)"
        return "TRANSFER OK" if self.won else "TRANSFER FAIL"
