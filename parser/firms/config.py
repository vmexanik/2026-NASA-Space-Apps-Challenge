"""Where the MAP_KEY comes from."""

import os
from pathlib import Path

from .constants import MAP_KEY_ENV
from .errors import FirmsConfigError


def load_map_key(env_file: Path | None = None) -> str:
    """Return the MAP_KEY.

    The FIRMS_MAP_KEY environment variable wins; otherwise the
    FIRMS_MAP_KEY=... line of env_file is used.
    """
    key = os.environ.get(MAP_KEY_ENV, "").strip()
    if key:
        return key
    if env_file is not None and env_file.is_file():
        for line in env_file.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == MAP_KEY_ENV:
                key = value.strip().strip("'\"")
                if key:
                    return key
    where = f" or into {env_file}" if env_file is not None else ""
    raise FirmsConfigError(f"no MAP_KEY: set {MAP_KEY_ENV}{where}")
