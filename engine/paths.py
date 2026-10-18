"""Where the code lives, and where the data lives. They are not the same place.

    CODE   the engine, templates and web assets. Read-only when installed (a Nix store path,
           a container image layer). Never written to.
    HOME   projects, the equipment catalog, `config/current` and `.env`. Always writable.

In a git checkout the two coincide, which is how the tool has always worked: `./bin/design`
writes into `projects/` beside the code. Installed with Nix or run from the container image,
the code is immutable and HOME moves out to a data directory.

HOME is chosen, highest first:
  1. $ROOMSMITH_HOME
  2. the checkout itself, if it is writable and not inside /nix/store
  3. $XDG_DATA_HOME/roomsmith, else ~/.local/share/roomsmith
"""
from __future__ import annotations

import os
import pathlib

CODE = pathlib.Path(__file__).resolve().parent.parent


def _home():
    env = os.environ.get("ROOMSMITH_HOME", "").strip()
    if env:
        return pathlib.Path(env).expanduser().resolve()
    if not str(CODE).startswith("/nix/store") and os.access(CODE, os.W_OK):
        return CODE
    xdg = os.environ.get("XDG_DATA_HOME", "").strip() or str(pathlib.Path.home() / ".local/share")
    return pathlib.Path(xdg).expanduser() / "roomsmith"


HOME = _home()
PROJECTS = HOME / "projects"
CATALOG = HOME / "catalog"
CONFIG = HOME / "config"
TEMPLATES = CODE / "config" / "templates"
WEB = CODE / "engine" / "web"
