# Repository Guidelines

This file is the shared instruction set for every AI coding agent in this repository (Codex, Claude Code, and others). Add project guidance here, not in agent-specific files, so all agents stay in sync.

## Required Session Startup

Before task work, read [README.md](README.md) in full; it's the source for requirements, setup, launch, controls, and CI checks. Claude Code already imports it through `CLAUDE.md`. Prefer the current content of this file and README.md over prior-session memory.

## Project Structure & Module Organization

In `shooter/`, `app.py` handles startup/shutdown, `game.py` orchestrates frames, and `input.py`, `simulation.py`, and `combat.py` handle gameplay. `state.py` and `map.py` own state; `entities.py` defines enemies, pickups, and spawning.

Rendering uses `render_*.py`, `raycaster.py`, and `occlusion.py`. Shared definitions live in `constants.py` and `types.py`. Runtime assets come from `textures.py`, `sound.py`, and `weapon_models.py` (weapon artwork). `screenshots/` holds README illustrations; `tests/` holds tests and reusable fixtures in `tests/support.py`.

## Architecture

### Frame Loop

`game.run_game` runs each frame as `input.handle_events` → `simulation.update_game` → `render_game.draw_frame`. `dt` is in milliseconds. Pause and game-over skip simulation.

- Discrete actions (pause, weapon keys, fire, `E`, cheats) are handled in `handle_events`. Held movement keys are read in `update_player`. Held fire is tracked as `state.mouse_held`, which drives gatling auto-fire in `combat.update_combat`.
- WASD, the number row, `E`, and `R` use **scancodes** so they work on any keyboard layout. Held WASD is tracked in `pressed_scancodes`; the others match `event.scancode` in `handle_events`. Arrows, Shift, and Space use `pygame.key.get_pressed()`. Cheat letters, `Esc`, and `Q` use keycodes (`event.key`), so cheats match the letters typed. Keep this split for new bindings.
- `update_game` order is significant: player → combat → doors → enemies → rockets → pickups → `check_win_lose`. Rockets and pickups are skipped once `hp <= 0`, so lethal damage beats a pickup in the same frame.

### State and Lifecycle

`GameState` (`state.py`) is the single mutable object passed to every system. Its docstring documents each field. A new field must go in the correct reset scope:

- `reset()`: whole-game state that survives levels (ammo, owned weapons, `god_mode`).
- `enter_level()`: per-level state (HP, cooldowns, doors, entity lists).
- `start_level(state, n)`: generates the map and spawns entities. It and `reset_game(state)`, which runs `state.reset()` then `start_level(state, 1)`, are module functions, not `GameState` methods.

`GameState(seed=...)` seeds two independent RNGs. `level_rng` drives generation and spawning, and each spawned enemy and pickup gets its own `random.Random` derived from it. `rng` drives combat spread. Gameplay code shouldn't use the module-level `random`, because tests depend on seeded reproducibility.

### Map, Tiles, and Collision

`LevelState` (`map.py`) owns a 20×20 grid indexed as `maze[row][col]`. Positions are float `(x, y)` = `(col, row)`, and the integer part is the tile. Each kind of query has its own predicate, so pick the right one:

| Predicate | Used for | Notes |
|---|---|---|
| `is_blocked(x, y, jump_h, exit_open)` | player movement | barriers passable when jumping; exit passable once the boss is dead |
| `is_obstacle` (via `entities._blocks_enemy`) | enemy movement | the enemy variant also treats the exit as solid |
| `is_solid` | raycasting/rendering, door targeting (`find_door_in_front`) | every non-floor tile |
| `blocks_sight` (via `has_line_of_sight` / `wall_hit_fraction`) | hitscan, rockets, enemy LOS | barriers are below eye level, so they don't block |

Door animation lives in `state.door_anim`, keyed by `(col, row)`. A fully open door is **rewritten to `FLOOR_TILE`** in the maze. It is rewritten to `DOOR_TILE` when closing starts, which only happens when the tile is unoccupied. During animation the tile id alone doesn't tell you whether a door is there.

Vertical units are wall heights: floor 0, ceiling 1, eye `EYE_HEIGHT + jump_height`, barriers `BARRIER_HEIGHT` (1/3).

### Rendering Pipeline

`draw_frame` composes the frame in this order:

1. `raycaster.cast_rays` returns one `WallColumn` per screen column (`NUM_RAYS == WIDTH`). Partial obstacles (barriers, animating doors) add `bg_hits`, and the ray continues until it reaches a full wall.
2. `draw_floor_ceiling` renders with NumPy from `Textures.samples`.
3. `draw_3d` paints `bg_hits` from far to near, then the foreground slice. It records per-pixel depth in `occlusion.DepthBuffer`.
4. `draw_world_sprites` sorts every sprite by **camera-space depth** (not radial distance). Each sprite draws through the `z_buffer.sprite(...)` context manager, which clips it pixel by pixel against walls.
5. Minimap, crosshair, weapon view-model, HUD.

To add a sprite type, add it to the union and dispatch in `draw_world_sprites`, and draw it through `DepthBuffer.sprite` so partial occlusion works.

### Assets and Weapons

`app.main` generates textures and sounds at startup. Weapon art is drawn on first use and cached. `weapon_models.weapon_frame` returns shared surfaces, so copy one before tinting it or changing its alpha. `Sfx` is keyed by the `SoundName` Literal in `types.py`; add new sound names there. The mixer is fixed at 16-bit mono `SAMPLE_RATE` with `allowedchanges=0`, and the synthesized buffers assume that format.

`Weapon` (an IntEnum) indexes the `WEAPONS` tuple and `state.owned`. Ammo is per pool (`WEAPONS[w].ammo_pool`), and the pistol and gatling share pool 0.

## Development Commands

README.md covers setup, launch, and the CI checks. Beyond those:

- `python -m unittest tests.test_cheats -v`: run one module; append `.CheatTests.test_<name>` for one test.
- Without an activated venv, prefix tools with `.venv/bin/`, as `.github/workflows/typecheck.yml` does.

## Coding Style & Naming Conventions

Ruff (configured in `pyproject.toml`) enforces formatting and lint, but not naming. Use `snake_case` for modules, functions, and variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Annotate code for strict Pyright without diagnostic suppressions. Reuse named weapon/tile identifiers; keep changes in relevant modules.

This codebase is 100% AI-generated. Comments are optional: retain explanations of non-obvious constraints, units, or regression cases that help AI agents maintain the code. Omit comments that merely repeat clear code.

## Testing Guidelines

Use standard-library `unittest`, `test_*.py` files, and descriptive `test_*` methods. Add regression tests for gameplay/rendering fixes.

- Reuse the fixtures in `tests/support.py`:
  - `open_world()`: an empty map with border walls.
  - `SoundMocks`: pass `.sfx` into the code; index by name to assert `.play` calls.
  - `Keys(*down)`: a `KeyState` stand-in.
- Simulation tests usually follow this pattern: `GameState(seed=0)`, set `state.world = open_world()`, edit maze tiles or place entities, then call `update_game(state, 16, Keys(), set(), sfx)`.
- Rendering tests draw onto an off-screen `pygame.Surface((WIDTH, HEIGHT))` and check pixels. They need no display, but call `pygame.freetype.init()` when fonts are involved. Only `test_startup.py` launches the real app, in a subprocess with SDL dummy video/audio drivers.

## Commit & Pull Request Guidelines

Use focused commits with imperative subjects, such as `Fix depth ordering across world sprites`; no prefix scheme is required. PRs should explain the problem, resulting behavior, and checks; link relevant issues and include screenshots for visible changes. Run all CI checks before requesting review.
