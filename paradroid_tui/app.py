"""Textual app for Paradroid.

Real-time ticks at 120ms (like Bomberman). 4 panels:
  BoardView / StatusPanel / ControlsPanel / RichLog.
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.geometry import Size
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Footer, Header, RichLog, Static

from . import droids as D
from . import tiles
from .engine import Game, TickResult, ACT_NONE, ACT_LEFT, ACT_RIGHT, \
    ACT_UP, ACT_DOWN, ACT_FIRE, ACT_TRANSFER, ACT_WAIT, DIRS
from .deck import room_at
from .screens import (GameOverScreen, HelpScreen, PauseScreen,
                      TransferScreen, WonScreen)


TICK_MS = 120  # real-time tick rate


# Movement keys — the game treats a direction key as "walk that way".
_MOVE_KEYS: dict[str, int] = {
    "left":  ACT_LEFT,  "h": ACT_LEFT,
    "right": ACT_RIGHT, "l": ACT_RIGHT,
    "up":    ACT_UP,    "k": ACT_UP,
    "down":  ACT_DOWN,  "j": ACT_DOWN,
}


# --------------------------------------------------------------------
# BoardView — strip-based renderer
# --------------------------------------------------------------------


class BoardView(Widget):
    """30×18 grid, centered inside the widget."""

    DEFAULT_CSS = ""

    def __init__(self, app_ref: "ParadroidApp", **kw) -> None:
        super().__init__(**kw)
        self._app = app_ref
        self._frame = 0

    def get_content_width(self, container: Size, viewport: Size) -> int:
        g = self._app.game
        return max((g.deck.width if g else 30) + 4, 34)

    def get_content_height(
        self, container: Size, viewport: Size, width: int
    ) -> int:
        g = self._app.game
        return max((g.deck.height if g else 18) + 2, 20)

    def render_line(self, y: int) -> Strip:
        g = self._app.game
        if g is None:
            return Strip.blank(self.size.width)

        widget_w = self.size.width
        widget_h = self.size.height
        deck_w = g.deck.width
        deck_h = g.deck.height
        pad_x = max(0, (widget_w - deck_w) // 2)
        pad_y = max(0, (widget_h - deck_h) // 2)

        board_y = y - pad_y
        if board_y < 0 or board_y >= deck_h:
            return Strip.blank(widget_w, tiles.S_EMPTY)

        segments: list[Segment] = []
        if pad_x > 0:
            segments.append(Segment(" " * pad_x, tiles.S_EMPTY))

        row_segs: list[Segment] = []
        for x in range(deck_w):
            glyph, style = _compose_cell(g, x, board_y)
            row_segs.append(Segment(glyph, style))
        segments.extend(_rle(row_segs))

        used = pad_x + deck_w
        if used < widget_w:
            segments.append(Segment(" " * (widget_w - used), tiles.S_EMPTY))
        return Strip(segments)


def _compose_cell(g: Game, x: int, y: int) -> tuple[str, Style]:
    # Bullets render on top of everything except droids.
    for b in g.bullets:
        if b.x == x and b.y == y:
            return b.glyph, tiles.bullet_style(b.damage)
    # Droids render on top of terrain.
    d = g.droid_at(x, y)
    if d is not None:
        return tiles.droid_glyph(d.class_id), tiles.droid_style(
            d.class_id, d.is_player)
    # Terrain.
    t = g.deck.grid[y][x]
    return tiles.terrain_glyph(t, x, y), tiles.terrain_style(t, x, y)


def _rle(segs: list[Segment]) -> list[Segment]:
    if not segs:
        return segs
    out = [segs[0]]
    for s in segs[1:]:
        last = out[-1]
        if s.style == last.style:
            out[-1] = Segment(last.text + s.text, last.style)
        else:
            out.append(s)
    return out


# --------------------------------------------------------------------
# Side panels
# --------------------------------------------------------------------


class StatusPanel(Static):
    def __init__(self, app_ref: "ParadroidApp") -> None:
        super().__init__("", id="status")
        self._app = app_ref
        self._last: tuple | None = None

    def refresh_panel(self) -> None:
        a = self._app
        g = a.game
        if g is None:
            return
        p = g.player()
        ptuple = (p.class_id, p.armor, p.x, p.y) if p else None
        room = None
        if p is not None:
            r = room_at(g.deck, p.x, p.y)
            if r is not None:
                room = r.name
        snap = (g.tick_count, g.alert_level, g.alive_enemies(),
                g.score, g.won, g.dead, ptuple, room)
        if snap == self._last:
            return
        self._last = snap

        t = Text()
        t.append("Paradroid\n", style="bold rgb(120,180,255)")
        t.append(f"room    {room or '—'}\n", style="rgb(220,220,235)")
        t.append("\n")
        if p is not None:
            spec = D.get_class(p.class_id)
            t.append("Class   ", style="rgb(150,150,170)")
            t.append(f"{p.class_id:03d} {spec.name}\n",
                     style="bold rgb(120,220,255)")
            t.append("Armor   ", style="rgb(150,150,170)")
            bar = "█" * max(0, p.armor) + "·" * max(
                0, max(5, spec.armor) - p.armor)
            color = ("bold rgb(120,230,120)" if p.armor > spec.armor * 0.6
                     else "bold rgb(255,220,80)" if p.armor > spec.armor * 0.3
                     else "bold rgb(255,120,120)")
            t.append(f"{bar[:20]}\n", style=color)
            t.append("Weapon  ", style="rgb(150,150,170)")
            t.append(f"{spec.weapon}\n", style="bold rgb(255,200,80)")
        else:
            t.append("NO HOST\n", style="bold rgb(255,120,120)")
        t.append("\n")
        t.append("Alert   ", style="rgb(150,150,170)")
        level_bar = "▮" * g.alert_level + "·" * (9 - g.alert_level)
        alert_color = ("bold rgb(120,230,120)" if g.alert_level < 3
                       else "bold rgb(255,220,80)" if g.alert_level < 6
                       else "bold rgb(255,120,90)")
        t.append(f"{level_bar}  {g.alert_level}\n", style=alert_color)
        t.append("Droids  ", style="rgb(150,150,170)")
        t.append(f"{g.alive_enemies()}\n", style="bold rgb(230,90,90)")
        t.append("Bullets ", style="rgb(150,150,170)")
        t.append(f"{len(g.bullets)}\n", style="rgb(220,220,235)")
        t.append("Score   ", style="rgb(150,150,170)")
        t.append(f"{g.score}\n", style="bold rgb(230,230,240)")
        t.append("Tick    ", style="rgb(150,150,170)")
        t.append(f"{g.tick_count}\n", style="rgb(220,220,235)")

        if g.won:
            t.append("\n★ SHIP CLEARED", style="bold rgb(120,230,120)")
        elif g.dead:
            t.append("\n✗ INFLUENCE LOST",
                     style="bold rgb(255,120,120)")
        elif a.paused:
            t.append("\n⏸  PAUSED", style="bold rgb(255,220,80)")
        elif g.transfer is not None:
            t.append("\n◆ TRANSFER", style="bold rgb(120,180,255)")
        self.update(t)


class ControlsPanel(Static):
    def __init__(self) -> None:
        t = Text()
        t.append("Controls\n", style="bold rgb(120,180,255)")
        rows = [
            ("←→↑↓ / hjkl",   "move / turn"),
            ("space / f",     "fire"),
            ("t",             "transfer (adj)"),
            (".",             "wait"),
            ("p / esc",       "pause"),
            ("r",             "reset"),
            ("?",             "help"),
            ("q",             "quit"),
        ]
        for k, desc in rows:
            t.append(f"  {k:<14}", style="bold rgb(255,220,80)")
            t.append(f"{desc}\n", style="rgb(200,200,215)")
        super().__init__(t, id="controls")


# --------------------------------------------------------------------
# The App
# --------------------------------------------------------------------


class ParadroidApp(App):
    CSS_PATH = "tui.tcss"
    TITLE = "Paradroid TUI"
    SUB_TITLE = ""

    BINDINGS = [
        *[Binding(k, f"move('{k}')", show=False, priority=True)
          for k in _MOVE_KEYS.keys()],
        Binding("space", "fire", show=False, priority=True),
        Binding("f", "fire", show=False, priority=True),
        Binding("t", "transfer", show=False, priority=True),
        Binding("full_stop", "wait", show=False, priority=True),
        Binding("p", "pause", "pause"),
        Binding("escape", "pause", show=False),
        Binding("r", "reset", "reset"),
        Binding("question_mark", "help", "help"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, seed: int = 0) -> None:
        super().__init__()
        self.seed = seed
        self.game: Game | None = None
        self.paused = False
        # widgets
        self.board: BoardView | None = None
        self.status_panel: StatusPanel | None = None
        self.flash_bar: Static | None = None
        self.message_log: RichLog | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        self.board = BoardView(self, id="board")
        self.status_panel = StatusPanel(self)
        self.flash_bar = Static("", id="flash")
        self.message_log = RichLog(id="log", max_lines=500, wrap=True,
                                   markup=True)
        with Vertical(id="left"):
            yield self.board
            yield self.flash_bar
        with Vertical(id="right"):
            yield self.status_panel
            yield ControlsPanel()
            yield self.message_log
        yield Footer()

    def on_mount(self) -> None:
        self._new_game()
        self.set_interval(TICK_MS / 1000, self._on_tick)

    # ---- game management --------------------------------------------

    def _new_game(self) -> None:
        self.game = Game.new(seed=self.seed)
        self.paused = False
        if self.board:
            self.board.refresh()
        if self.status_panel:
            self.status_panel.refresh_panel()
        if self.message_log:
            self.message_log.write(
                f"[bold rgb(120,180,255)]▶ ship deck 01[/] — "
                f"{self.game.alive_enemies()} droids"
            )
        self._flash("Transfer into stronger droids. Reach Ω.")

    def _flash(self, msg: str) -> None:
        if self.flash_bar:
            self.flash_bar.update(msg)

    # ---- main tick --------------------------------------------------

    def _on_tick(self) -> None:
        if self.game is None or self.paused:
            return
        if self.game.won or self.game.dead:
            return
        if self.game.transfer is not None:
            # Pause real-time during transfer.
            return
        res: TickResult = self.game.tick()
        self._on_tick_result(res)
        if self.board:
            self.board.refresh()
        if self.status_panel:
            self.status_panel.refresh_panel()

    def _on_tick_result(self, res: TickResult) -> None:
        if res.transfer_started is not None:
            self._open_transfer()
            return
        if res.droids_killed and self.message_log:
            self.message_log.write(
                f"[rgb(230,90,90)]✗ {res.droids_killed} droid(s) "
                f"neutralized[/]"
            )
        if res.player_hit and self.message_log:
            self.message_log.write(
                f"[rgb(255,120,120)]hit! -{res.player_hit} armor[/]"
            )
        if res.won:
            self._on_win()
        elif self.game is not None and self.game.dead:
            self._on_over(res.reason or "destroyed")

    # ---- key actions ------------------------------------------------

    def action_move(self, key: str) -> None:
        if self.game is None or self.paused:
            return
        if self.game.transfer is not None:
            return
        act = _MOVE_KEYS.get(key, ACT_NONE)
        self.game.queue_action(act)

    def action_fire(self) -> None:
        if self.game is None or self.paused:
            return
        if self.game.transfer is not None:
            return
        self.game.queue_action(ACT_FIRE)

    def action_transfer(self) -> None:
        if self.game is None or self.paused:
            return
        if self.game.transfer is not None:
            return
        self.game.queue_action(ACT_TRANSFER)

    def action_wait(self) -> None:
        if self.game is None or self.paused:
            return
        self.game.queue_action(ACT_WAIT)

    def action_pause(self) -> None:
        if self.game is None:
            return
        if self.game.transfer is not None:
            return
        if self.paused:
            return
        self.paused = True
        self.push_screen(PauseScreen())

    def on_screen_resume(self) -> None:
        # Clear pause when any modal closes.
        self.paused = False
        if self.status_panel:
            self.status_panel.refresh_panel()

    def action_reset(self) -> None:
        self._new_game()
        if self.message_log:
            self.message_log.write("[rgb(220,180,90)]↺ reset[/]")

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # ---- transfer flow ---------------------------------------------

    def _open_transfer(self) -> None:
        if self.game is None or self.game.transfer is None:
            return
        if self.message_log:
            p = self.game.player()
            target_id = self.game.transfer_target_id
            target = next((d for d in self.game.droids
                           if d.id == target_id), None)
            if p and target:
                self.message_log.write(
                    f"[bold rgb(120,180,255)]◆ transfer[/] "
                    f"{p.class_id:03d} → {target.class_id:03d}"
                )
        self.push_screen(TransferScreen(self.game.transfer))

    def on_transfer_done(self) -> None:
        if self.game is None:
            return
        t = self.game.transfer
        won = bool(t and t.won)
        self.game.finish_transfer()
        if self.message_log:
            if won:
                p = self.game.player()
                cls = p.class_id if p else 0
                self.message_log.write(
                    f"[bold rgb(120,230,120)]✓ transfer OK → "
                    f"class {cls:03d}[/]"
                )
            else:
                self.message_log.write(
                    "[bold rgb(255,120,120)]✗ transfer failed[/]"
                )
        if self.board:
            self.board.refresh()
        if self.status_panel:
            self.status_panel.refresh_panel()
        if self.game.dead:
            self._on_over(self.game.reason or "transfer failed")

    # ---- win / lose ------------------------------------------------

    def _on_win(self) -> None:
        g = self.game
        if g is None:
            return
        p = g.player()
        self.push_screen(WonScreen(
            score=g.score,
            ticks=g.tick_count,
            final_class=p.class_id if p else 1,
        ))

    def _on_over(self, reason: str) -> None:
        g = self.game
        if g is None:
            return
        self.push_screen(GameOverScreen(
            score=g.score,
            ticks=g.tick_count,
            reason=reason,
        ))


def run(seed: int = 0) -> None:
    ParadroidApp(seed=seed).run()
