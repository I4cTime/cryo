#!/usr/bin/env python3
"""Compile every GLSL shader under src/cryo/gui into a Qt .qsb.

    .venv/bin/python tools/build_shaders.py           # rebuild all
    .venv/bin/python tools/build_shaders.py --check   # exit 1 if any is stale

For each `<name>.frag` / `<name>.vert` it writes `<name>.frag.qsb` with
pyside6-qsb and a sidecar `<name>.frag.qsb.sha256` holding the sha256 of the
source it was built from. tests/test_shaders.py compares that hash with the
current source, so editing a shader without rebuilding fails CI.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI_DIR = ROOT / "src" / "cryo" / "gui"
SUFFIXES = (".frag", ".vert")


def shader_sources(base: Path = GUI_DIR) -> list[Path]:
    return sorted(p for p in base.rglob("*") if p.suffix in SUFFIXES and p.is_file())


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qsb_path(src: Path) -> Path:
    return src.with_name(src.name + ".qsb")


def sidecar_path(src: Path) -> Path:
    return src.with_name(src.name + ".qsb.sha256")


def find_qsb() -> str:
    here = Path(sys.executable).parent / "pyside6-qsb"
    if here.exists():
        return str(here)
    found = shutil.which("pyside6-qsb")
    if not found:
        sys.exit(
            "pyside6-qsb not found: run this with the project venv (.venv/bin/python)"
        )
    return found


def is_stale(src: Path) -> bool:
    side = sidecar_path(src)
    if not qsb_path(src).exists() or not side.exists():
        return True
    return side.read_text().split()[0] != source_hash(src)


def build(src: Path, qsb: str) -> None:
    out = qsb_path(src)
    # GLSL 100es/120/150 + SPIR-V 1.0 + HLSL + MSL: every backend Qt Quick may pick.
    subprocess.run([qsb, "--qt6", "-o", str(out), str(src)], check=True)
    sidecar_path(src).write_text(f"{source_hash(src)}  {src.name}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Qt .qsb shaders")
    ap.add_argument("--check", action="store_true", help="only report stale shaders")
    args = ap.parse_args()

    sources = shader_sources()
    if args.check:
        stale = [s for s in sources if is_stale(s)]
        for s in stale:
            print(f"stale: {s.relative_to(ROOT)}")
        return 1 if stale else 0

    qsb = find_qsb()
    for src in sources:
        build(src, qsb)
        print(f"built {qsb_path(src).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
