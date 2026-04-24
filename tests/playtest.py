"""End-to-end playtest harness for bot-takeover-tui.

    python -m tests.playtest

Drives the full Textual app through a scripted play session:
boot, move, fire, initiate transfer, quit. Saves screenshots
to `tests/out/playtest-*.svg` at each checkpoint.

This is the "does it still feel like a game" smoke test that
complements the unit-ish scenarios in tests/qa.py.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from bot_takeover_tui.app import ParadroidApp

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def _shot(app: ParadroidApp, label: str) -> None:
    path = OUT / f"playtest-{label}.svg"
    try:
        app.save_screenshot(str(path))
        print(f"  shot: {path.name}")
    except Exception as exc:
        print(f"  shot failed ({label}): {exc}")


async def play() -> bool:
    app = ParadroidApp(seed=0)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.game is not None, "game did not initialize on mount"

        # --- boot -----------------------------------------------------
        print("boot: game mounted")
        assert app.game.player() is not None
        assert app.game.alive_enemies() > 0
        _shot(app, "01-boot")

        # --- move -----------------------------------------------------
        print("move: walk a few steps")
        p0 = app.game.player()
        assert p0 is not None
        start_xy = (p0.x, p0.y)
        for key in ("l", "l", "j", "h", "k"):
            await pilot.press(key)
            await pilot.pause(0.05)
        p1 = app.game.player()
        assert p1 is not None
        end_xy = (p1.x, p1.y)
        print(f"  player {start_xy} -> {end_xy}")
        _shot(app, "02-move")

        # --- fire -----------------------------------------------------
        print("fire: space-bar shot")
        before = app.game.tick_count
        await pilot.press("space")
        await pilot.pause(0.15)
        after = app.game.tick_count
        print(f"  tick advanced {before} -> {after}")
        _shot(app, "03-fire")

        # --- initiate transfer ---------------------------------------
        print("transfer: inject adjacent droid and press t")
        p = app.game.player()
        assert p is not None
        tx, ty = p.x + 1, p.y
        # Clear the cell and place a disposal droid to transfer into.
        app.game.deck.grid[ty][tx] = "."
        occupant = app.game.droid_at(tx, ty)
        if occupant is not None and not occupant.is_player:
            app.game.droids.remove(occupant)
        app.game._new_droid(class_id=123, x=tx, y=ty)
        p.facing = (1, 0)
        await pilot.press("t")
        await pilot.pause(0.2)
        screen_name = app.screen.__class__.__name__
        print(f"  active screen: {screen_name}")
        assert screen_name == "TransferScreen", screen_name
        _shot(app, "04-transfer-open")

        # Back out via escape (forfeit).
        await pilot.press("escape")
        await pilot.pause(0.15)
        assert app.game.transfer is None, "transfer state did not clear"
        print("  transfer closed cleanly (forfeit)")
        _shot(app, "05-transfer-closed")

        # --- quit -----------------------------------------------------
        print("quit: press q")
        await pilot.press("q")
        await pilot.pause(0.15)
        _shot(app, "06-quit")

    print("playtest: OK")
    return True


def main() -> int:
    try:
        ok = asyncio.run(play())
    except AssertionError as e:
        print(f"playtest FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"playtest ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
