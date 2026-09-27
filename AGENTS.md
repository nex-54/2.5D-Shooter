# Repository Guidelines

## Required Session Startup

Before task work in every Codex session, read the complete root [README.md](README.md) from disk. Use its current overview, requirements, launch instructions, controls, and development checks rather than prior-session memory.

## Project Structure & Module Organization

This Python 3.14+ game uses Pygame CE and NumPy. In `shooter/`, `app.py` handles startup/shutdown, `game.py` orchestrates frames, and `input.py`, `simulation.py`, and `combat.py` handle gameplay. `state.py` and `map.py` own state; `entities.py` defines enemies, pickups, and spawning.

Rendering uses `render_*.py`, `raycaster.py`, and `occlusion.py`. Shared definitions live in `constants.py` and `types.py`. Runtime assets come from `textures.py`, `sound.py`, and `weapon_models.py` (weapon artwork). `screenshots/` holds README illustrations; `tests/` holds tests and reusable fixtures in `tests/support.py`.

## Build, Test, and Development Commands

From the repository root, using Python 3.14+:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

- `./run.sh`: launch; creates `.venv` and installs runtime dependencies if absent.
- `python -m shooter` or `python shooter.py`: launch with the activated environment.
- `ruff check .`: check lint and import ordering.
- `ruff format --check .`: verify formatting; use `ruff format .` to apply it.
- `pyright`: strictly type-check source and tests.
- `python -m unittest discover -s tests -v`: run all tests.

No build step is required. Checks match `.github/workflows/typecheck.yml`.

## Coding Style & Naming Conventions

Use four-space indentation, Ruff formatting, and 100-character lines. Use `snake_case` for modules/functions/variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Annotate functions and shared structures for strict Pyright without diagnostic suppressions. Reuse named weapon/tile identifiers; keep changes in relevant modules.

This codebase is 100% AI-generated. Comments are optional: retain explanations of non-obvious constraints, units, or regression cases that help AI agents maintain the code. Omit comments that merely repeat clear code.

## Testing Guidelines

Use standard-library `unittest`, `test_*.py` files, and descriptive `test_*` methods. Reuse world and sound fixtures from `tests/support.py`. Add regression tests for gameplay/rendering fixes. Startup tests use SDL dummy video/audio drivers. No coverage threshold is configured.

## Commit & Pull Request Guidelines

Use focused commits with imperative subjects, such as `Fix depth ordering across world sprites`; no prefix scheme is required. PRs should explain the problem, resulting behavior, and checks; link relevant issues and include screenshots for visible changes. Run all CI checks before requesting review.
