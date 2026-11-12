"""Compiled shaders must match their sources (no Qt needed).

Every *.frag / *.vert under src/cryo/gui ships with a .qsb built by
tools/build_shaders.py and a .qsb.sha256 sidecar holding the hash of the
source it was built from. If a shader is edited without rebuilding, the
committed binary is stale and these tests fail.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

GUI_DIR = Path(__file__).resolve().parents[1] / "src" / "cryo" / "gui"
SOURCES = sorted(
    p for p in GUI_DIR.rglob("*") if p.suffix in (".frag", ".vert") and p.is_file()
)


def test_there_are_shaders() -> None:
    assert SOURCES, "expected at least one shader under src/cryo/gui"


@pytest.mark.parametrize("src", SOURCES, ids=lambda p: str(p.relative_to(GUI_DIR)))
def test_shader_has_qsb(src: Path) -> None:
    qsb = src.with_name(src.name + ".qsb")
    assert qsb.is_file() and qsb.stat().st_size > 0, (
        f"{qsb.name} missing: run .venv/bin/python tools/build_shaders.py"
    )


@pytest.mark.parametrize("src", SOURCES, ids=lambda p: str(p.relative_to(GUI_DIR)))
def test_qsb_is_current(src: Path) -> None:
    side = src.with_name(src.name + ".qsb.sha256")
    assert side.is_file(), (
        f"{side.name} missing: run .venv/bin/python tools/build_shaders.py"
    )
    recorded = side.read_text().split()[0]
    current = hashlib.sha256(src.read_bytes()).hexdigest()
    assert recorded == current, (
        f"{src.name} changed since its .qsb was built: run .venv/bin/python tools/build_shaders.py"
    )
