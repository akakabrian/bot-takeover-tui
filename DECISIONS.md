# Paradroid TUI — Design Decisions

## Engine: pure-Python clean-room reimplementation

Classic **Paradroid** (Andrew Braybrook / Graftgold, 1985, C64) — top-down
action where the player is a weak "influence droid" (class 001) aboard a
hostile starship, and transfers to stronger droids by winning a circuit-
puzzle mini-game. Graftgold retains IP rights; we do NOT vendor their
code. Pattern 4 from the tui-game-build skill: **clean-room
reimplementation** from public design docs + high-level references:

- `freedroid.org` — GPL open-source remake by Johannes Prix; confirms
  the gameplay structure.
- C64 Wiki / Lemon64 / Mobygames writeups on the droid taxonomy and
  the "transfer game".
- Interviews with Braybrook (zzap64 retrospective) for the rules.

Mechanics are ~700 lines of Python. The iconic **transfer mini-game**
(dual-circuit row-based flow puzzle) is simplified to a 6-row variant
that preserves the feel.

## Droid taxonomy (matches the Paradroid mythology, abridged)

| class | name            | armor | weapon  | speed | AI            |
|------:|-----------------|:-----:|:--------|:-----:|:--------------|
|  001  | Influence       |   1   | taser   |   2   | player-owned  |
|  123  | Disposal        |   2   | none    |   1   | wander        |
|  139  | Messenger       |   2   | stun    |   2   | patrol        |
|  247  | Service         |   3   | laser-s |   2   | wander        |
|  249  | Maintenance     |   3   | laser-s |   2   | patrol        |
|  296  | Science         |   3   | stun    |   2   | idle          |
|  302  | Engineer        |   4   | laser-m |   2   | patrol        |
|  329  | Interior Guard  |   5   | laser-m |   2   | patrol+pursue |
|  420  | Exterior Guard  |   6   | laser-l |   2   | patrol+pursue |
|  476  | Interior Sec    |   7   | plasma  |   2   | pursue        |
|  493  | Exterior Sec    |   8   | plasma  |   2   | pursue        |
|  516  | Command         |   9   | plasma  |   3   | pursue+hunt   |
|  571  | Heavy Guard     |  10   | double  |   2   | pursue+hunt   |
|  598  | Heavy Command   |  11   | double  |   2   | pursue+hunt   |
|  629  | Special Guard   |  12   | missile |   2   | pursue+hunt   |
|  711  | Warrior Droid   |  14   | rocket  |   3   | hunt          |
|  742  | Battle Droid    |  16   | rocket  |   3   | hunt          |
|  751  | Heavy Battle    |  18   | rocket  |   2   | hunt          |
|  821  | Heavy Warrior   |  20   | rocket  |   2   | hunt          |
|  999  | Command Cyborg  |  25   | disruptr|   3   | hunt          |

The **class number** is canonical Paradroid lore (the C64 release has
exactly these IDs; we use the well-documented subset). Higher class ≈
stronger. AI modes:

- **idle** — stand still unless player in LOS.
- **wander** — random walk, turn on wall.
- **patrol** — pre-planned loop, pursue if LOS.
- **pursue** — BFS toward player within range.
- **hunt** — BFS without range cap; faster.

## Transfer mini-game (the signature mechanic)

Real game is a 12-column × 2-row "circuit board" where both players
simultaneously place numbered rotators. We simplify to **6 rows × 1 tile
each** and turn it into a sequential place-and-count puzzle that
reproduces the FEEL in a TUI:

- 6 rows of "flow wire", 10 cells each.
- Each row starts blank. Both the player and the opponent droid have
  an "energy pool" (pulse counter).
- Turns alternate: player places an **energizer** (`+`) in a row,
  opponent places a **siphon** (`−`). Each row tallies `Σ + − Σ`.
- After 10 rounds of placing the row scores are totalled. If player
  has ≥4 of 6 rows won, transfer succeeds.
- Weaker droids (class < player) auto-win.
- Stronger droids (class > player) give the opponent bonus energizers
  at start.

This is not pixel-perfect to the C64 original, but preserves:
- dual-player simultaneous tactical game over rows (the iconic shape),
- risk/reward (weaker=easy / stronger=hard),
- a terminal "win / lose / neutralize both" outcome, where a stalemate
  destroys both droids (classic Braybrook).

## Ship layout

Single deck for v0 (room for more in polish).

- **30×18 grid**, walls + doors + corridors + rooms.
- Rooms: Bridge (where win-tile lives), Hold, Engineering, Brig,
  Transporter, Armory, Reactor. Labels drawn in-world.
- Doors auto-open for droids.
- Player starts in Transporter. Must reach Bridge tile (marked `Ω`)
  to WIN, OR kill/transfer-out all non-001 droids.

Generated deterministically from a seed so tests reproduce.

## Controls

| Key             | Action                        |
|-----------------|-------------------------------|
| ←→↑↓ / hjkl     | move (also fires weapon)      |
| space / f       | fire weapon                   |
| t               | initiate transfer (adjacent)  |
| `.`             | wait one tick                 |
| p / esc         | pause                         |
| r               | reset level                   |
| ?               | help                          |
| q               | quit                          |

During **transfer screen**:
- 1..6 select row
- `+` / `space` place energizer in selected row
- esc abort transfer (forfeit)

## Ticks

Real-time-ish. 120ms tick. Each tick:
1. player move (if queued key)
2. bullets advance (2 cells/tick)
3. droid AI advance (speed-gated)
4. collisions / damage
5. security alert recompute

## Security

`alert_level` (0..9) rises with each kill or successful transfer,
decays slowly. Every 15 ticks at level ≥ N spawns a new droid of class
~100 × alert_level from a spawn tile.

## Win / Lose

- **WIN**: step on the Bridge tile `Ω` as player-droid, OR reduce
  alive hostile droids to zero.
- **LOSE**: player's current droid loses all armor to fire, OR loses
  the transfer mini-game with no host available.

## Gate order (tui-game-build skill, 7 stages)

1. Research — Wikipedia + freedroid.org + C64-wiki + Lemon64 (DONE).
2. Engine — pure-Python `engine.py`, `transfer.py`. Gate: REPL
   tick + move + fire + transfer succeeds.
3. TUI scaffold — 4-panel Textual app. Gate: launch, move, fire.
4. QA harness — ~25 scenarios before polish.
5. Perf — baseline; only optimize if needed.
6. Robustness — out-of-bounds, unknown class, transfer with no host.
7. Polish (phased):
   - A: UI beauty (pattern-cycling floors, droid sprites per class)
   - B: Submenus (help, pause, transfer screen polish, game-over)
   - C: (optional) agent REST API
   - D: (optional) sound

## Intentionally-not-in-MVP

- Multi-deck elevators / lifts. Single deck for v0.
- Graftgold's pixel-accurate "flow animation" inside the transfer
  game. We do an ASCII flow: `○ > > > +` per row.
- Accurate C64 droid health formulas.
- Two-player hotseat.

## Performance budget

120ms tick × ~30 droids worst-case × BFS is comfortably sub-millisecond.
No `ctypes` zero-copy needed — we're pure-Python, single struct per droid.

## Layout

```
bot-takeover-tui/
├── paradroid.py                  # entry: argparse → run(...)
├── pyproject.toml
├── Makefile
├── DECISIONS.md                  # this file
├── bot_takeover_tui/
│   ├── __init__.py
│   ├── engine.py                 # Ship, Droid, Bullet, Game, tick
│   ├── droids.py                 # class 001..999 table + AI selectors
│   ├── transfer.py               # circuit mini-game
│   ├── deck.py                   # deck generator (procedural)
│   ├── tiles.py                  # glyphs + styles
│   ├── app.py                    # ParadroidApp, BoardView, panels
│   ├── screens.py                # Help, Pause, TransferScreen, GameOver, Won
│   └── tui.tcss
└── tests/
    ├── qa.py
    └── perf.py
```
