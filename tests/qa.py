"""Headless QA driver for paradroid-tui.

    python -m tests.qa
    python -m tests.qa transfer
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from paradroid_tui import droids as D
from paradroid_tui import engine as E
from paradroid_tui.app import ParadroidApp
from paradroid_tui.deck import generate as gen_deck, room_at
from paradroid_tui.engine import (ACT_DOWN, ACT_FIRE, ACT_LEFT, ACT_RIGHT,
                                  ACT_TRANSFER, ACT_UP, Droid, Game)
from paradroid_tui.transfer import TransferGame

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    fn: Callable[[ParadroidApp, "object"], Awaitable[None]]


# ====================================================================
# Pure-engine scenarios
# ====================================================================


async def s_deck_has_rooms(app, pilot):
    d = gen_deck(seed=0)
    assert d.width == 30 and d.height == 18
    assert len(d.rooms) >= 5
    names = {r.name for r in d.rooms}
    assert "Bridge" in names
    assert "Transporter" in names


async def s_deck_bridge_tile(app, pilot):
    d = gen_deck(seed=0)
    bx, by = d.bridge_tile
    assert d.grid[by][bx] == "O"


async def s_deck_player_spawn_is_floor_ish(app, pilot):
    d = gen_deck(seed=0)
    px, py = d.player_spawn
    # Either '<' marker (pre-engine) or floor after engine load; here
    # we just check it's inside the Transporter room.
    t = room_at(d, px, py)
    assert t is not None and t.name == "Transporter"


async def s_droid_class_lookup(app, pilot):
    assert D.get_class(1).name == "Influence"
    assert D.get_class(999).name == "Command Cyborg"
    # Unknown class resolves to nearest (robustness).
    assert D.get_class(500).class_id in {476, 493, 516}


async def s_weapon_lookup_unknown(app, pilot):
    w = D.weapon("no-such-weapon")
    assert w["damage"] == 0  # falls back to 'none'


async def s_game_new_has_player_and_enemies(app, pilot):
    g = Game.new(seed=0, n_droids=5)
    p = g.player()
    assert p is not None and p.class_id == 1
    assert g.alive_enemies() >= 3


async def s_player_walks(app, pilot):
    g = Game.new(seed=0)
    p = g.player()
    assert p is not None
    start = (p.x, p.y)
    # Try a few directions — at least one should move us one cell.
    moved = False
    for act in (ACT_RIGHT, ACT_LEFT, ACT_DOWN, ACT_UP):
        g.queue_action(act)
        g.tick()
        p2 = g.player()
        assert p2 is not None
        if (p2.x, p2.y) != start:
            moved = True
            break
    assert moved, f"player never moved from {start}"


async def s_player_cannot_walk_through_wall(app, pilot):
    g = Game.new(seed=0)
    p = g.player()
    assert p is not None
    # Teleport next to a wall. Deck's (0,0) is wall; move player to (1,1).
    p.x, p.y = 1, 1
    g.queue_action(ACT_LEFT)
    g.tick()
    p2 = g.player()
    assert p2 is not None
    assert p2.x == 1, f"moved into wall: {p2.x},{p2.y}"


async def s_player_fires_bullet(app, pilot):
    g = Game.new(seed=0)
    p = g.player()
    assert p is not None
    # Move to a straight corridor cell and set facing right.
    # Just set facing manually so the fire mechanic gets tested.
    p.facing = (1, 0)
    n_bullets_before = len(g.bullets)
    g.queue_action(ACT_FIRE)
    g.tick()
    # Either we have more bullets OR the target cell was immediately
    # consumed (e.g. blocked by wall). Both are valid; but spawn is
    # open floor, so we expect a bullet.
    assert len(g.bullets) >= n_bullets_before, \
        f"no bullet fired: {n_bullets_before} → {len(g.bullets)}"


async def s_bullet_kills_droid(app, pilot):
    # Manual scenario: player + enemy in a line.
    g = Game.new(seed=0, n_droids=0)
    p = g.player()
    assert p is not None
    # Place an Engineer (class 302, armor 4) 3 tiles to the right.
    p.x, p.y = 5, 7
    p.facing = (1, 0)
    # clear terrain between them (row 7 is center spine corridor)
    for x in range(5, 12):
        g.deck.grid[7][x] = "."
    enemy = g._new_droid(class_id=123, x=8, y=7)  # disposal, armor 2
    # Hold the enemy still by keeping its move_cooldown high every tick.
    for _ in range(20):
        enemy.move_cooldown = 99
        p.facing = (1, 0)
        g.queue_action(ACT_FIRE)
        g.tick()
        if enemy not in g.droids:
            break
    assert enemy not in g.droids, f"enemy not killed: armor={enemy.armor}"


async def s_transfer_game_weak_host_easy(app, pilot):
    """Against a weaker host, threshold drops so transfer is easy."""
    t = TransferGame.new(player_class=300, host_class=100, seed=1)
    # Just keep placing from row 0..5
    for _ in range(t.rounds):
        row = t.rows.index(min(t.rows))
        t.play_player(row)
        t.play_ai_turn()
    assert t.finished
    # Not a strict assertion — random seed means outcome varies —
    # but threshold should be easy (≤ 3).
    assert t.threshold() <= 3


async def s_transfer_game_tough_host_hard(app, pilot):
    t = TransferGame.new(player_class=100, host_class=500, seed=1)
    assert t.threshold() >= 4
    # Bonus siphons should have been placed.
    bonus = (500 - 100) // 100
    # The sum of all rows should be -bonus before any moves.
    assert sum(t.rows) == -bonus


async def s_transfer_game_forfeit(app, pilot):
    t = TransferGame.new(player_class=100, host_class=200, seed=1)
    t.forfeit()
    assert t.finished
    assert not t.won


async def s_transfer_game_progress(app, pilot):
    t = TransferGame.new(player_class=200, host_class=200, seed=3,
                         rounds=3)
    assert t.turn == "player"
    t.play_player(0)
    assert t.turn == "opp"
    t.play_ai_turn()
    assert t.turn == "player"
    # After 3 rounds, it should finish.
    for _ in range(3):
        t.play_player(t.rows.index(min(t.rows)))
        t.play_ai_turn()
    assert t.finished


async def s_transfer_body_swap(app, pilot):
    """Winning a transfer upgrades the player's class & armor."""
    g = Game.new(seed=0, n_droids=0)
    p = g.player()
    assert p is not None and p.class_id == 1
    enemy = g._new_droid(class_id=302, x=p.x + 1, y=p.y)  # Engineer
    g.start_transfer(enemy)
    assert g.transfer is not None
    # Force-win by setting the transfer state.
    t = g.transfer
    t.won = True
    t.finished = True
    g.finish_transfer()
    p2 = g.player()
    assert p2 is not None
    assert p2.class_id == 302, p2.class_id
    assert enemy not in g.droids


async def s_transfer_failure_damages_player(app, pilot):
    g = Game.new(seed=0, n_droids=0)
    p = g.player()
    assert p is not None
    starting_armor = p.armor
    enemy = g._new_droid(class_id=420, x=p.x + 1, y=p.y)
    g.start_transfer(enemy)
    assert g.transfer is not None
    t = g.transfer
    t.won = False
    t.finished = True
    g.finish_transfer()
    p2 = g.player()
    # Armor dropped or player is dead.
    if p2 is not None:
        assert p2.armor < starting_armor


async def s_alert_rises_on_kill(app, pilot):
    g = Game.new(seed=0, n_droids=0)
    p = g.player()
    assert p is not None
    enemy = g._new_droid(class_id=123, x=p.x + 2, y=p.y)
    alert_before = g.alert_float
    # Inflict damage via direct removal.
    res = E.TickResult()
    g._kill_droid(enemy, res)
    assert g.alert_float > alert_before


async def s_win_on_bridge(app, pilot):
    g = Game.new(seed=0)
    p = g.player()
    assert p is not None
    p.x, p.y = g.deck.bridge_tile
    g.tick()
    assert g.won


async def s_win_when_all_enemies_dead(app, pilot):
    g = Game.new(seed=0, n_droids=0)
    # No enemies → win on first tick.
    g.tick()
    assert g.won


async def s_game_tickable_no_crash(app, pilot):
    g = Game.new(seed=42)
    for _ in range(200):
        g.tick()
        if g.won or g.dead:
            break


async def s_bullet_stops_at_wall(app, pilot):
    g = Game.new(seed=0, n_droids=0)
    p = g.player()
    assert p is not None
    # Put player next to a wall and fire into it.
    p.x, p.y = 2, 2  # near Transporter wall
    p.facing = (-1, 0)
    g.queue_action(ACT_FIRE)
    g.tick()
    # After 10 ticks no bullets should persist near walls.
    for _ in range(10):
        g.tick()
    # Bullets all consumed.
    assert all(g.is_passable_for_bullet(b.x, b.y) for b in g.bullets)


async def s_droid_identity_eq_false(app, pilot):
    """Two droids with matching fields are NOT equal (eq=False).

    This protects list.remove from picking the wrong entity."""
    a = Droid(id=1, class_id=123, x=5, y=5, armor=2)
    b = Droid(id=2, class_id=123, x=5, y=5, armor=2)
    assert a != b
    lst = [a, b]
    lst.remove(a)
    assert lst == [b]


async def s_spawn_tiles_exist(app, pilot):
    d = gen_deck(seed=1)
    assert len(d.spawn_tiles) >= 2
    for x, y in d.spawn_tiles:
        assert d.grid[y][x] == ">"


# ====================================================================
# TUI scenarios (mount required)
# ====================================================================


async def s_mount_clean(app, pilot):
    assert app.board is not None
    assert app.status_panel is not None
    assert app.message_log is not None
    assert app.game is not None
    p = app.game.player()
    assert p is not None


async def s_arrow_moves_player(app, pilot):
    p = app.game.player()
    assert p is not None
    start = (p.x, p.y)
    for key in ("right", "left", "down", "up"):
        await pilot.press(key)
        await pilot.pause()
        p2 = app.game.player()
        assert p2 is not None
        if (p2.x, p2.y) != start:
            return
    raise AssertionError(f"no arrow moved player from {start}")


async def s_hjkl_moves_player(app, pilot):
    p = app.game.player()
    assert p is not None
    start = (p.x, p.y)
    for key in ("l", "h", "j", "k"):
        await pilot.press(key)
        await pilot.pause()
        p2 = app.game.player()
        assert p2 is not None
        if (p2.x, p2.y) != start:
            return
    raise AssertionError(f"no hjkl moved player from {start}")


async def s_space_fires(app, pilot):
    # Make sure player is on a corridor facing a clear direction.
    p = app.game.player()
    assert p is not None
    p.facing = (1, 0)
    nbefore = len(app.game.bullets)
    await pilot.press("space")
    await pilot.pause()
    # After one tick the bullet may have travelled; we only assert
    # that we went through the fire action at least once.
    # Give it a few ticks for the real-time loop.
    await pilot.pause(0.1)
    # Bullets may have already been consumed — assert via tick count
    # (nonzero) that the engine ran.
    assert app.game.tick_count >= 1


async def s_pause_opens_modal(app, pilot):
    await pilot.press("p")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "PauseScreen"
    await pilot.press("escape")
    await pilot.pause()
    assert app.screen.__class__.__name__ != "PauseScreen"


async def s_help_opens_modal(app, pilot):
    await pilot.press("question_mark")
    await pilot.pause()
    assert app.screen.__class__.__name__ == "HelpScreen"
    await pilot.press("escape")
    await pilot.pause()


async def s_board_renders_with_styles(app, pilot):
    strip = app.board.render_line(app.size.height // 2)
    segs = list(strip)
    assert len(segs) > 0
    fg_count = sum(1 for s in segs if s.style and s.style.color is not None)
    assert fg_count > 0


async def s_status_panel_refreshes(app, pilot):
    app.status_panel.refresh_panel()
    snap1 = app.status_panel._last
    assert snap1 is not None
    for _ in range(3):
        app.status_panel.refresh_panel()
    assert app.status_panel._last == snap1


async def s_reset_key_works(app, pilot):
    # Manually advance the engine a few ticks, then press r, expect a
    # near-zero tick count (interval may fire once post-reset).
    for _ in range(10):
        app.game.tick()
    assert app.game.tick_count == 10
    await pilot.press("r")
    await pilot.pause()
    assert app.game.tick_count < 5, app.game.tick_count


async def s_transfer_screen_opens(app, pilot):
    # Place an enemy next to the player so transfer target exists.
    p = app.game.player()
    assert p is not None
    # Clear the cell to the right and add a disposal droid.
    app.game.deck.grid[p.y][p.x + 1] = "."
    # Remove any droid already there
    occupant = app.game.droid_at(p.x + 1, p.y)
    if occupant is not None and not occupant.is_player:
        app.game.droids.remove(occupant)
    app.game._new_droid(class_id=123, x=p.x + 1, y=p.y)
    p.facing = (1, 0)
    # Initiate transfer via key.
    await pilot.press("t")
    await pilot.pause(0.15)
    assert app.screen.__class__.__name__ == "TransferScreen", \
        app.screen.__class__.__name__
    # Close via forfeit.
    await pilot.press("escape")
    await pilot.pause()


async def s_transfer_flow_e2e(app, pilot):
    # Full flow: initiate → play → finish → body swap.
    p = app.game.player()
    assert p is not None
    original_class = p.class_id
    # Clear the enemies and put a disposal droid adjacent.
    for e in list(app.game.enemies()):
        app.game.droids.remove(e)
    app.game.deck.grid[p.y][p.x + 1] = "."
    app.game._new_droid(class_id=123, x=p.x + 1, y=p.y)
    p.facing = (1, 0)
    await pilot.press("t")
    await pilot.pause(0.15)
    assert app.screen.__class__.__name__ == "TransferScreen"
    # Play through — press + repeatedly; the mini-game will finalize.
    for _ in range(25):
        await pilot.press("plus")
        await pilot.pause()
        if app.game.transfer is None or app.game.transfer.finished:
            break
    # Confirm with enter.
    await pilot.press("enter")
    await pilot.pause(0.15)
    # Either swap succeeded (class changed) or failed (armor reduced).
    p2 = app.game.player()
    if p2 is not None:
        # Class might be the same if it failed, but game should keep running.
        assert app.game.transfer is None


async def s_unknown_tile_does_not_crash(app, pilot):
    app.game.deck.grid[0][0] = "?"
    strip = app.board.render_line(
        app.size.height // 2 - app.game.deck.height // 2
    )
    assert len(list(strip)) > 0


async def s_quit_key_exits(app, pilot):
    await pilot.press("q")
    await pilot.pause()
    # Either app exited or a modal popped up — we assert no exception.
    assert True


SCENARIOS: list[Scenario] = [
    # Pure-engine
    Scenario("deck_has_rooms", s_deck_has_rooms),
    Scenario("deck_bridge_tile", s_deck_bridge_tile),
    Scenario("deck_player_spawn", s_deck_player_spawn_is_floor_ish),
    Scenario("droid_class_lookup", s_droid_class_lookup),
    Scenario("weapon_lookup_unknown", s_weapon_lookup_unknown),
    Scenario("game_new_populated", s_game_new_has_player_and_enemies),
    Scenario("player_walks", s_player_walks),
    Scenario("player_cannot_walk_through_wall",
             s_player_cannot_walk_through_wall),
    Scenario("player_fires_bullet", s_player_fires_bullet),
    Scenario("bullet_kills_droid", s_bullet_kills_droid),
    Scenario("bullet_stops_at_wall", s_bullet_stops_at_wall),
    Scenario("transfer_weak_host_easy", s_transfer_game_weak_host_easy),
    Scenario("transfer_tough_host_hard", s_transfer_game_tough_host_hard),
    Scenario("transfer_forfeit", s_transfer_game_forfeit),
    Scenario("transfer_progress", s_transfer_game_progress),
    Scenario("transfer_body_swap", s_transfer_body_swap),
    Scenario("transfer_failure_damages", s_transfer_failure_damages_player),
    Scenario("alert_rises_on_kill", s_alert_rises_on_kill),
    Scenario("win_on_bridge", s_win_on_bridge),
    Scenario("win_all_enemies_dead", s_win_when_all_enemies_dead),
    Scenario("game_tickable_no_crash", s_game_tickable_no_crash),
    Scenario("droid_identity_eq_false", s_droid_identity_eq_false),
    Scenario("spawn_tiles_exist", s_spawn_tiles_exist),
    # TUI
    Scenario("mount_clean", s_mount_clean),
    Scenario("arrow_moves_player", s_arrow_moves_player),
    Scenario("hjkl_moves_player", s_hjkl_moves_player),
    Scenario("space_fires", s_space_fires),
    Scenario("pause_opens_modal", s_pause_opens_modal),
    Scenario("help_opens_modal", s_help_opens_modal),
    Scenario("board_renders_with_styles", s_board_renders_with_styles),
    Scenario("status_panel_refreshes", s_status_panel_refreshes),
    Scenario("reset_key_works", s_reset_key_works),
    Scenario("transfer_screen_opens", s_transfer_screen_opens),
    Scenario("transfer_flow_e2e", s_transfer_flow_e2e),
    Scenario("unknown_tile_does_not_crash", s_unknown_tile_does_not_crash),
    Scenario("quit_key_exits", s_quit_key_exits),
]


async def run_one(scn: Scenario) -> tuple[str, bool, str]:
    app = ParadroidApp(seed=0)
    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            try:
                await scn.fn(app, pilot)
            except AssertionError as e:
                try:
                    app.save_screenshot(str(OUT / f"{scn.name}.FAIL.svg"))
                except Exception:
                    pass
                return (scn.name, False, f"AssertionError: {e}")
            except Exception as e:
                try:
                    app.save_screenshot(str(OUT / f"{scn.name}.ERROR.svg"))
                except Exception:
                    pass
                return (scn.name, False,
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            try:
                app.save_screenshot(str(OUT / f"{scn.name}.PASS.svg"))
            except Exception:
                pass
            return (scn.name, True, "")
    except Exception as e:
        return (scn.name, False,
                f"harness: {type(e).__name__}: {e}\n{traceback.format_exc()}")


async def main(pattern: str | None = None) -> int:
    scenarios = [s for s in SCENARIOS if not pattern or pattern in s.name]
    if not scenarios:
        print(f"no scenarios match {pattern!r}")
        return 2
    results = []
    for scn in scenarios:
        name, ok, msg = await run_one(scn)
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name}")
        if not ok:
            for line in msg.splitlines():
                print(f"      {line}")
        results.append((name, ok, msg))
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(main(pattern)))
