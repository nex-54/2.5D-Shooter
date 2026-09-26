# 2.5D Maze Shooter

A retro first-person shooter built in Python with Pygame CE, using a from-scratch raycasting engine. **Every asset is procedurally generated at runtime** — no images, no audio files, no external dependencies beyond Pygame and NumPy.

## Screenshots

| | |
|---|---|
| ![Pistol vs. enemy](screenshots/enemy.jpg) | ![Gatling gun in a corridor](screenshots/gatling.jpg) |
| Pistol facing a regular enemy | Gatling gun cruising the maze |

![Boss fight with the shotgun](screenshots/boss.jpg)
*Shotgun showdown with the level boss — note the boss HP bar overhead.*

## Features

- **Raycasting 3D engine** — textured walls, floors, and ceilings rendered one column at a time
- **Procedural everything** — all wall textures, sprites, and sound effects synthesized in code at startup
- **5 weapons** — pistol, shotgun, gatling gun, rocket launcher, and a screen-clearing nuke
- **4 enemy types** — regular grunts, fast scouts, ceiling spiders, and a level-end boss
- **Procedural level generation** — each level rewrites the maze, doors, and spawn points
- **Doors, jumping, sprinting, strafing**, and a live minimap
- **Fully typed** — passes `pyright` in strict mode

## Requirements

- Python 3.14+
- [Pygame CE](https://pyga.me/) and NumPy

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
./run.sh
```

Or, with the venv activated:

```bash
python shooter.py
# or, equivalently
python -m shooter
```

## Controls

| Action | Keys |
|---|---|
| Move forward / back | `W` / `S` (or `↑` / `↓`) |
| Strafe left / right | `A` / `D` |
| Turn | Mouse, or `←` / `→` |
| Sprint | `Shift` |
| Jump | `Space` |
| Open door | `E` |
| Fire | Left mouse button |
| Pistol / Shotgun / Gatling / Rockets | `1` / `2` / `3` / `4` |
| Nuke | `0` |
| Restart (on death) | `R` |
| Pause / resume | `Esc` (a click also resumes) |
| Quit | `Q` while paused, `Esc` on the game-over screen |

## Development Checks

With the virtual environment activated, install the development tools:

```bash
python -m pip install -r requirements-dev.txt
```

Run the same checks as CI:

```bash
ruff check .
ruff format --check .
pyright
python -m unittest discover -s tests -v
```

Use `ruff format .` to apply formatting. Ruff configuration lives in `pyproject.toml`. Pyright checks the package, entry point, and tests in strict mode without diagnostic suppressions; its configuration uses the project's `.venv`.

## License

Released into the public domain under [The Unlicense](LICENSE). Do whatever you want with it.
