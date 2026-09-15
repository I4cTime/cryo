"""Runtime state the daemon owns: /var/lib/cryo/state.json.

Kept apart from /etc/cryo/config.json on purpose. The config file is the
user's — the daemon never rewrites it, so a two-line partial config stays
partial and keeps tracking future defaults. Anything the daemon changes on
its own (last lighting, the curves-off latch a manual boost sets) lives
here instead.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path

from cryo import paths

log = logging.getLogger(__name__)

DEFAULT_STATE: dict = {
    # {"effect", "color", "brightness"} once the user has set lighting;
    # None means "use config lighting.last".
    "lighting": None,
    # None = follow config fan_curves.enabled; False = a manual boost
    # switched curves off until the user re-enables them.
    "fan_curves_enabled": None,
}


def load(path: Path = paths.STATE_FILE) -> dict:
    state = copy.deepcopy(DEFAULT_STATE)
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return state
    except (OSError, ValueError) as exc:
        log.error("state file %s unreadable (%s); starting fresh", path, exc)
        return state
    if not isinstance(raw, dict):
        log.error("state file %s is not a JSON object; starting fresh", path)
        return state
    for key in state:
        if key in raw:
            state[key] = raw[key]
    return state


def save(state: dict, path: Path = paths.STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    os.replace(tmp, path)
