"""Modal screens: Help, Pause, Transfer, Won, GameOver."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from . import droids as D
from .transfer import TransferGame, N_ROWS

if TYPE_CHECKING:
    from .app import ParadroidApp


class HelpScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "close", "close"),
        Binding("question_mark", "close", "close"),
        Binding("q", "close", "close"),
    ]

    def compose(self) -> ComposeResult:
        t = Text()
        t.append("Paradroid TUI — Controls\n\n",
                 style="bold rgb(120,180,255)")
        rows = [
            ("Move / turn",    "←→↑↓  or  hjkl"),
            ("Fire weapon",    "space  or  f"),
            ("Initiate transfer", "t (on adjacent droid)"),
            ("Wait one tick",  "."),
            ("Pause",          "p  or  esc"),
            ("Reset",          "r"),
            ("Help",           "?"),
            ("Quit",           "q"),
        ]
        for desc, keys in rows:
            t.append(f"  {desc:<22}", style="rgb(200,200,220)")
            t.append(f"{keys}\n", style="bold rgb(255,255,255)")
        t.append("\nGoal\n", style="bold rgb(120,180,255)")
        t.append("  Reach the Bridge Ω, or neutralize all droids.\n",
                 style="rgb(220,220,235)")
        t.append("  You start as class 001 (weakest). TRANSFER into\n",
                 style="rgb(220,220,235)")
        t.append("  stronger droids to climb the ladder to 999.\n",
                 style="rgb(220,220,235)")
        t.append("\nTransfer game\n", style="bold rgb(120,180,255)")
        t.append("  1..6 select row · + or space place · esc forfeit\n",
                 style="rgb(220,220,235)")
        t.append("\nesc / ? to close", style="rgb(150,150,170)")
        yield Vertical(Static(t), id="help-panel")

    def action_close(self) -> None:
        self.app.pop_screen()


class PauseScreen(ModalScreen):
    BINDINGS = [
        Binding("p", "close", "resume"),
        Binding("escape", "close", "resume"),
        Binding("space", "close", "resume"),
        Binding("q", "quit", "quit"),
    ]

    def compose(self) -> ComposeResult:
        t = Text()
        t.append("⏸  PAUSED\n\n", style="bold rgb(220,180,80)")
        t.append("p / esc to resume · q to quit",
                 style="rgb(200,200,220)")
        yield Vertical(Static(t), id="pause-panel")

    def on_key(self, event) -> None:
        # Stop pause keys from bubbling — skill gotcha: modal dismiss
        # must stop the event or the same key re-pushes the modal.
        if event.key in ("p", "escape", "space"):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def action_close(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class WonScreen(ModalScreen):
    BINDINGS = [
        Binding("r", "restart", "restart"),
        Binding("escape", "close", "back"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, score: int, ticks: int, final_class: int) -> None:
        super().__init__()
        self.score = score
        self.ticks = ticks
        self.final_class = final_class

    def compose(self) -> ComposeResult:
        t = Text()
        t.append("★ SHIP CLEARED ★\n\n", style="bold rgb(120,230,120)")
        t.append(
            f"final class  {self.final_class:03d}   "
            f"score  {self.score}   "
            f"ticks  {self.ticks}\n\n",
            style="bold rgb(230,230,240)",
        )
        t.append("r restart · esc · q quit", style="rgb(180,200,240)")
        yield Vertical(Static(t), id="won-panel")

    def _p_app(self) -> "ParadroidApp":
        from .app import ParadroidApp
        return cast(ParadroidApp, self.app)

    def action_restart(self) -> None:
        a = self._p_app()
        a.pop_screen()
        a.action_reset()

    def action_close(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class GameOverScreen(ModalScreen):
    BINDINGS = [
        Binding("r", "restart", "restart"),
        Binding("escape", "close", "back"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, score: int, ticks: int, reason: str) -> None:
        super().__init__()
        self.score = score
        self.ticks = ticks
        self.reason = reason

    def compose(self) -> ComposeResult:
        t = Text()
        t.append("✗ INFLUENCE LOST ✗\n\n", style="bold rgb(255,120,120)")
        t.append(f"{self.reason}\n", style="rgb(230,230,240)")
        t.append(f"score {self.score} · {self.ticks} ticks\n\n",
                 style="rgb(200,200,220)")
        t.append("r restart · esc · q quit", style="rgb(180,200,240)")
        yield Vertical(Static(t), id="over-panel")

    def _p_app(self) -> "ParadroidApp":
        from .app import ParadroidApp
        return cast(ParadroidApp, self.app)

    def action_restart(self) -> None:
        a = self._p_app()
        a.pop_screen()
        a.action_reset()

    def action_close(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class TransferScreen(ModalScreen):
    """The iconic circuit-puzzle mini-game.

    `+` / `space` place an energizer in the selected row. `1..6` pick
    row. After the player plays, opponent AI auto-plays immediately.
    Esc forfeits (lose transfer). After both sides are out of pulses,
    the result is shown and the player presses enter to apply.
    """

    BINDINGS = [
        Binding("escape", "forfeit", "forfeit"),
        Binding("plus", "place", "place energizer", show=False),
        Binding("equals_sign", "place", show=False),  # `=` key
        Binding("space", "place", "place energizer", show=False),
        Binding("enter", "confirm", "confirm"),
        *[Binding(str(i), f"select_row({i - 1})", show=False)
          for i in range(1, 7)],
        Binding("up", "select_up", show=False, priority=True),
        Binding("down", "select_down", show=False, priority=True),
        Binding("k", "select_up", show=False),
        Binding("j", "select_down", show=False),
    ]

    def __init__(self, transfer: TransferGame) -> None:
        super().__init__()
        self.transfer = transfer

    def compose(self) -> ComposeResult:
        self._view = Static(self._render_view(), id="transfer-view")
        yield Vertical(self._view, id="transfer-panel")

    def on_mount(self) -> None:
        self._refresh()

    # ---- rendering -------------------------------------------------

    def _render_view(self) -> Text:
        g = self.transfer
        t = Text()
        t.append("◆ TRANSFER CIRCUIT ◆\n",
                 style="bold rgb(120,180,255)")
        t.append(
            f"  you class {g.player_class:03d}  "
            f"→  host class {g.host_class:03d}   "
            f"threshold {g.threshold()}/{N_ROWS}\n\n",
            style="rgb(200,200,230)",
        )
        for i in range(N_ROWS):
            sel = "▶ " if i == g.selected_row else "  "
            val = g.rows[i]
            bar = _row_bar(val)
            if val > 0:
                score_style = "bold rgb(120,230,120)"
            elif val < 0:
                score_style = "bold rgb(255,120,120)"
            else:
                score_style = "rgb(200,200,220)"
            t.append(f"{sel}row {i + 1}  ", style="rgb(200,200,230)")
            t.append(bar, style=score_style)
            t.append(f"  {val:+d}\n", style=score_style)
        t.append("\n")
        t.append(
            f"  + energizers left  {g.player_left}    "
            f"− siphons left  {g.opp_left}    "
            f"turn  {g.turn}\n",
            style="rgb(180,200,230)",
        )
        t.append("  1..6 row · +/space place · enter confirm · "
                 "esc forfeit\n",
                 style="rgb(150,150,170)")
        if g.finished:
            won = g.rows_won()
            status = "[bold rgb(120,230,120)]TRANSFER OK[/]" if g.won \
                else "[bold rgb(255,120,120)]TRANSFER FAIL[/]"
            # use markup explicitly
            t.append(f"\n  {won}/{N_ROWS} rows won — ",
                     style="bold rgb(230,230,240)")
            if g.won:
                t.append("TRANSFER OK", style="bold rgb(120,230,120)")
            else:
                t.append("TRANSFER FAIL", style="bold rgb(255,120,120)")
            t.append("   (enter to continue)\n",
                     style="rgb(200,200,230)")
        return t

    def _refresh(self) -> None:
        self._view.update(self._render_view())

    # ---- actions ---------------------------------------------------

    def action_select_row(self, row: int) -> None:
        self.transfer.selected_row = max(0, min(N_ROWS - 1, row))
        self._refresh()

    def action_select_up(self) -> None:
        self.transfer.selected_row = (
            self.transfer.selected_row - 1) % N_ROWS
        self._refresh()

    def action_select_down(self) -> None:
        self.transfer.selected_row = (
            self.transfer.selected_row + 1) % N_ROWS
        self._refresh()

    def action_place(self) -> None:
        g = self.transfer
        if g.finished:
            return
        ok = g.play_player(g.selected_row)
        self._refresh()
        if ok and not g.finished:
            # Let AI play immediately so the tempo is snappy.
            g.play_ai_turn()
            self._refresh()

    def action_forfeit(self) -> None:
        if not self.transfer.finished:
            self.transfer.forfeit()
        self._refresh()
        self._finish()

    def action_confirm(self) -> None:
        # Enter advances: if not finished, play like place; if finished,
        # close and apply.
        if not self.transfer.finished:
            self.action_place()
            return
        self._finish()

    def _finish(self) -> None:
        from .app import ParadroidApp
        a = cast(ParadroidApp, self.app)
        a.pop_screen()
        a.on_transfer_done()


def _row_bar(val: int) -> str:
    if val == 0:
        return "·········"
    n = min(abs(val), 9)
    ch = "+" if val > 0 else "−"
    filler = ch * n
    return filler + "·" * (9 - n)
