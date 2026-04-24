"""Performance baseline for bot-takeover-tui.

    python -m tests.perf
"""

from __future__ import annotations

import time

from bot_takeover_tui import engine as E
from bot_takeover_tui.engine import Game


def bench(name: str, fn, n: int = 100):
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    dt = (time.perf_counter() - t0) / n * 1000
    print(f"  {name:<40} {dt:7.3f} ms/iter  (n={n})")


def main() -> int:
    print("Paradroid-tui perf benchmark")
    g = Game.new(seed=0)
    bench("engine.tick() empty input", lambda: g.tick(), n=500)

    g2 = Game.new(seed=1)
    # Pre-fire a shot to exercise bullet logic.
    p = g2.player()
    if p is not None:
        p.facing = (1, 0)
        g2.queue_action(E.ACT_FIRE)
    bench("engine.tick() with bullet active", lambda: g2.tick(), n=500)

    g3 = Game.new(seed=2)

    def tick_batch():
        for _ in range(100):
            g3.tick()
            if g3.won or g3.dead:
                break
    bench("engine.tick() ×100 batch", tick_batch, n=20)

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
