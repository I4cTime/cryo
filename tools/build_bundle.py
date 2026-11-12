#!/usr/bin/env python3
"""Build the Cryo release bundle: dist/cryo-<version>-linux-x86_64.tar.gz + SHA256SUMS.

The bundle is a net installer (see docs/INSTALL.md): the Cryo wheel, the
runtime requirements exported from uv.lock with hashes, a pinned static uv,
the unit templates, icons and packaging/bundle/{install,uninstall}.sh. The
dependencies and, when needed, a Python are fetched at install time.

Stdlib only. Needs `uv` on PATH (for `uv build` and `uv export`) and network
access for the first uv download (cached in --uv-cache afterwards).

    uv run --no-project tools/build_bundle.py [--out DIR] [--uv-cache DIR]
    uv run --no-project tools/build_bundle.py --check-tag v0.7.0

The tarball is reproducible for a given commit, uv.lock and toolchain: files
in sorted order, every mtime set to SOURCE_DATE_EPOCH (default: the commit
time), owner 0:0, normalized modes, and a gzip header without name or time.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The uv shipped inside the bundle. The static musl build runs on any x86_64
# distro. Bump the version and the checksum together (the checksum is the
# release's uv-x86_64-unknown-linux-musl.tar.gz.sha256).
UV_VERSION = "0.13.7"
UV_SHA256 = "287491da03f2a785c70fa75b13e1f849918c2f2b5415fe84876b8214eeb792f9"
UV_ASSET = "uv-x86_64-unknown-linux-musl.tar.gz"
UV_URL = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{UV_ASSET}"

PLATFORM = "linux-x86_64"
ICON_SIZES = (32, 48, 64, 128, 256, 512)
INSTALLER = REPO / "packaging" / "bundle" / "install.sh"


class BuildError(Exception):
    """A build step failed; the message says which and why."""


# --------------------------------------------------------------------------
# Version and tag


def project_version(repo: Path = REPO) -> str:
    with open(repo / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def check_tag(tag: str, version: str) -> str | None:
    """None when the release tag matches the project version, else the reason."""
    tag = tag.removeprefix("refs/tags/")
    if tag != f"v{version}":
        return f"tag {tag!r} does not match pyproject.toml version {version!r} (expected 'v{version}')"
    return None


def source_date_epoch(repo: Path = REPO) -> int:
    env = os.environ.get("SOURCE_DATE_EPOCH")
    if env:
        return int(env)
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=repo, check=True, capture_output=True, text=True,
        ).stdout.strip()
        return int(out)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise BuildError(f"no SOURCE_DATE_EPOCH and no git commit time ({exc})") from exc


# --------------------------------------------------------------------------
# Installer constants (install.sh is the single source for these)


@dataclass(frozen=True)
class Target:
    py_minors: tuple[int, ...]  # the installer's MANAGED_PYTHON: (13,) for 3.13
    glibc_min: tuple[int, int]


def installer_target(installer: Path = INSTALLER) -> Target:
    text = installer.read_text()

    def const(name: str) -> str:
        m = re.search(rf"^{name}=([0-9.]+)$", text, re.M)
        if not m:
            raise BuildError(f"{installer} does not define {name}")
        return m.group(1)

    py_major, py_minor = const("MANAGED_PYTHON").split(".")
    if py_major != "3":
        raise BuildError(f"MANAGED_PYTHON={py_major}.{py_minor} is not a Python 3 version")
    major, minor = const("GLIBC_MIN").split(".")
    return Target((int(py_minor),), (int(major), int(minor)))


# --------------------------------------------------------------------------
# Requirements: parse the export, evaluate markers, check against the lock


@dataclass
class Requirement:
    name: str
    version: str | None
    marker: str | None
    hashes: list[str] = field(default_factory=list)


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(text: str) -> list[Requirement]:
    """Parse a hashed requirements.txt as `uv export` writes it."""
    joined = re.sub(r"\\\n", " ", text)
    reqs: list[Requirement] = []
    for raw in joined.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        hashes = re.findall(r"--hash=(\S+)", line)
        spec = re.sub(r"--hash=\S+", "", line).strip()
        marker = None
        if ";" in spec:
            spec, marker = (part.strip() for part in spec.split(";", 1))
        m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:==\s*(\S+))?", spec)
        if not m:
            reqs.append(Requirement(spec, None, marker, hashes))
            continue
        reqs.append(Requirement(normalize(m.group(1)), m.group(2), marker, hashes))
    return reqs


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", v)[:3])


def marker_env(minor: int) -> dict[str, str]:
    """The PEP 508 environment of the installer's target for one Python minor."""
    return {
        "os_name": "posix",
        "sys_platform": "linux",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
        "platform_python_implementation": "CPython",
        "implementation_name": "cpython",
        "python_version": f"3.{minor}",
        "python_full_version": f"3.{minor}.0",
        "implementation_version": f"3.{minor}.0",
        "extra": "",
    }


_MARKER_TOKEN = re.compile(
    r"\s*(?:(?P<op>===|==|!=|<=|>=|~=|<|>|not in|in)|(?P<kw>and|or)\b|(?P<paren>[()])"
    r"|(?P<str>'[^']*'|\"[^\"]*\")|(?P<var>[A-Za-z_][A-Za-z0-9_.]*))"
)


def evaluate_marker(marker: str, env: dict[str, str]) -> bool | None:
    """Evaluate a PEP 508 marker. None when it uses a variable we cannot know."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(marker):
        if marker[pos:].strip() == "":
            break
        m = _MARKER_TOKEN.match(marker, pos)
        if not m:
            raise BuildError(f"cannot parse marker {marker!r}")
        kind = m.lastgroup or ""
        tokens.append((kind, m.group(kind)))
        pos = m.end()

    def value(tok: tuple[str, str]) -> str | None:
        kind, text = tok
        if kind == "str":
            return text[1:-1]
        return env.get(text)

    def compare(left: str | None, op: str, right: str | None, version_like: bool) -> bool | None:
        if left is None or right is None:
            return None
        if op == "in":
            return left in right
        if op == "not in":
            return left not in right
        if version_like:
            a, b = _version_tuple(left), _version_tuple(right)
            return {
                "==": a == b, "!=": a != b, "<": a < b, "<=": a <= b,
                ">": a > b, ">=": a >= b, "~=": a >= b, "===": left == right,
            }[op]
        return {"==": left == right, "!=": left != right, "===": left == right}.get(op)

    i = 0

    def expr() -> bool | None:
        nonlocal i
        result = term()
        while i < len(tokens) and tokens[i] == ("kw", "or"):
            i += 1
            rhs = term()
            result = True if (result is True or rhs is True) else (None if None in (result, rhs) else False)
        return result

    def term() -> bool | None:
        nonlocal i
        result = atom()
        while i < len(tokens) and tokens[i] == ("kw", "and"):
            i += 1
            rhs = atom()
            result = False if (result is False or rhs is False) else (None if None in (result, rhs) else True)
        return result

    def atom() -> bool | None:
        nonlocal i
        if tokens[i] == ("paren", "("):
            i += 1
            result = expr()
            i += 1  # ")"
            return result
        left, op, right = tokens[i], tokens[i + 1], tokens[i + 2]
        i += 3
        version_like = any(
            t[0] == "var" and ("version" in t[1]) for t in (left, right)
        )
        return compare(value(left), op[1], value(right), version_like)

    return expr()


_WHEEL = re.compile(
    r"^(?P<name>[^-]+)-(?P<ver>[^-]+)(?:-\d[^-]*)?-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$"
)
_MANYLINUX = {"manylinux1": (2, 5), "manylinux2010": (2, 12), "manylinux2014": (2, 17)}


def wheel_glibc(plat: str) -> tuple[int, int] | None:
    """The glibc a linux x86_64 platform tag needs, (0, 0) for 'any', None if not for us."""
    if plat == "any":
        return (0, 0)
    best: tuple[int, int] | None = None
    for tag in plat.split("."):
        if not tag.endswith("_x86_64"):
            continue
        base = tag.removesuffix("_x86_64")
        if base in _MANYLINUX:
            need = _MANYLINUX[base]
        elif m := re.fullmatch(r"manylinux_(\d+)_(\d+)", base):
            need = (int(m.group(1)), int(m.group(2)))
        else:
            continue  # musllinux, plain linux: not portable to our targets
        best = need if best is None or need < best else best
    return best


def wheel_fits_python(py: str, abi: str, minor: int) -> bool:
    for tag in py.split("."):
        if tag in ("py3", f"py3{minor}"):
            return True
        if m := re.fullmatch(r"cp3(\d+)", tag):
            built = int(m.group(1))
            if "abi3" in abi.split(".") and built <= minor:
                return True
            if built == minor and abi in (f"cp3{minor}", "none"):
                return True
    return False


def lock_wheels(lock: dict) -> dict[tuple[str, str], list[dict]]:
    """(normalized name, version) -> the wheels uv.lock records for it."""
    out: dict[tuple[str, str], list[dict]] = {}
    for pkg in lock.get("package", []):
        out[(normalize(pkg["name"]), pkg["version"])] = pkg.get("wheels", [])
    return out


def check_requirements(reqs: list[Requirement], lock: dict, target: Target) -> list[str]:
    """Problems that would make `uv pip install --require-hashes` fail on a target."""
    problems: list[str] = []
    wheels_by_pkg = lock_wheels(lock)
    if not reqs:
        problems.append("the export has no requirements")
    for req in reqs:
        if req.version is None:
            problems.append(f"{req.name}: not pinned with ==")
            continue
        if not req.hashes:
            problems.append(f"{req.name}=={req.version}: no --hash")
            continue
        wheels = wheels_by_pkg.get((req.name, req.version))
        if wheels is None:
            problems.append(f"{req.name}=={req.version}: not in uv.lock")
            continue
        lock_hashes = {w.get("hash") for w in wheels}
        if not set(req.hashes) & lock_hashes:
            problems.append(f"{req.name}=={req.version}: none of its hashes is a wheel hash in uv.lock")
        for minor in target.py_minors:
            if req.marker is not None and evaluate_marker(req.marker, marker_env(minor)) is False:
                continue  # uv skips it on this target
            fits: list[tuple[int, int]] = []
            for w in wheels:
                fname = w.get("url", "").rsplit("/", 1)[-1]
                m = _WHEEL.match(fname)
                if not m or w.get("hash") not in req.hashes:
                    continue
                glibc = wheel_glibc(m.group("plat"))
                if glibc is not None and wheel_fits_python(m.group("py"), m.group("abi"), minor):
                    fits.append(glibc)
            if not fits:
                problems.append(
                    f"{req.name}=={req.version}: no linux x86_64 wheel for Python 3.{minor}"
                    " (the installer refuses to build from source)"
                )
            elif min(fits) > target.glibc_min:
                need = ".".join(map(str, min(fits)))
                have = ".".join(map(str, target.glibc_min))
                problems.append(
                    f"{req.name}=={req.version}: needs glibc {need} but install.sh only checks for"
                    f" {have} (raise GLIBC_MIN)"
                )
    return problems


def export_requirements(repo: Path = REPO) -> str:
    """Runtime requirements from uv.lock, hash-pinned, markers kept for uv to evaluate."""
    proc = run(
        ["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-header",
         "--no-annotate", "--format", "requirements.txt"],
        cwd=repo,
    )
    return proc.stdout


def requirements_file(version: str, exported: str) -> str:
    header = (
        f"# Cryo {version} runtime dependencies, exported from uv.lock with hashes.\n"
        "# install.sh installs them with: uv pip install --require-hashes --no-build -r requirements.txt\n"
    )
    return header + exported


# --------------------------------------------------------------------------
# External steps (uv build, uv download)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)
    except FileNotFoundError as exc:
        raise BuildError(f"{cmd[0]} not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"{' '.join(cmd)} failed:\n{exc.stderr.strip()}") from exc


def build_wheel(repo: Path, version: str, workdir: Path, epoch: int) -> Path:
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch))
    run(["uv", "build", "--wheel", "--out-dir", str(workdir)], cwd=repo, env=env)
    wheel = workdir / f"cryo-{version}-py3-none-any.whl"
    if not wheel.is_file():
        raise BuildError(f"uv build did not produce {wheel.name}")
    return wheel


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_uv(cache_dir: Path) -> Path:
    """The pinned uv archive, from the cache or downloaded, checksum verified."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive = cache_dir / f"uv-{UV_VERSION}-{UV_ASSET}"
    if archive.is_file():
        if sha256_file(archive) == UV_SHA256:
            return archive
        print(f"cached {archive.name} has the wrong checksum; downloading again", file=sys.stderr)
        archive.unlink()
    partial = archive.with_suffix(".part")
    try:
        with urllib.request.urlopen(UV_URL, timeout=60) as resp, open(partial, "wb") as out:
            shutil.copyfileobj(resp, out)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise BuildError(f"downloading {UV_URL} failed: {exc}") from exc
    got = sha256_file(partial)
    if got != UV_SHA256:
        partial.unlink(missing_ok=True)
        raise BuildError(
            f"CHECKSUM MISMATCH for {UV_URL}\n  expected {UV_SHA256}\n  got      {got}\n"
            "Refusing to build. If uv was bumped on purpose, update UV_SHA256 in tools/build_bundle.py."
        )
    partial.rename(archive)
    return archive


def extract_uv_binary(archive: Path) -> bytes:
    member = f"{UV_ASSET.removesuffix('.tar.gz')}/uv"
    with tarfile.open(archive, "r:gz") as tar:
        try:
            info = tar.getmember(member)
        except KeyError as exc:
            raise BuildError(f"{archive.name} has no {member}") from exc
        f = tar.extractfile(info)
        if f is None:
            raise BuildError(f"{member} in {archive.name} is not a file")
        return f.read()


# --------------------------------------------------------------------------
# Layout and the reproducible tarball


@dataclass(frozen=True)
class Entry:
    name: str  # path inside cryo-<version>/
    data: bytes
    mode: int


def bundle_entries(
    repo: Path, version: str, wheel: bytes, requirements: str, uv_binary: bytes
) -> list[Entry]:
    pkg = repo / "packaging"
    bundle_src = pkg / "bundle"
    readme = (bundle_src / "README.txt").read_text().replace("@VERSION@", version)
    entries = [
        Entry("install.sh", (bundle_src / "install.sh").read_bytes(), 0o755),
        Entry("uninstall.sh", (bundle_src / "uninstall.sh").read_bytes(), 0o755),
        Entry("README.txt", readme.encode(), 0o644),
        Entry("LICENSE", (repo / "LICENSE").read_bytes(), 0o644),
        Entry("VERSION", f"{version}\n".encode(), 0o644),
        Entry("requirements.txt", requirements.encode(), 0o644),
        Entry(f"wheels/cryo-{version}-py3-none-any.whl", wheel, 0o644),
        Entry("bin/uv", uv_binary, 0o755),
        Entry("share/cryod.service", (pkg / "cryod.service").read_bytes(), 0o644),
        Entry("share/cryod-resume.service", (pkg / "cryod-resume.service").read_bytes(), 0o644),
        Entry("share/mark.svg", (repo / "assets" / "brand" / "mark.svg").read_bytes(), 0o644),
    ]
    for size in ICON_SIZES:
        icon = repo / "assets" / "icons" / f"cryo-{size}.png"
        entries.append(Entry(f"share/icons/cryo-{size}.png", icon.read_bytes(), 0o644))
    return entries


def tarball_name(version: str) -> str:
    return f"cryo-{version}-{PLATFORM}.tar.gz"


def write_tarball(entries: list[Entry], version: str, out: Path, epoch: int) -> None:
    top = f"cryo-{version}"
    dirs = {top}
    for e in entries:
        parts = e.name.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add(f"{top}/{'/'.join(parts[:i])}")
    files = {f"{top}/{e.name}": e for e in entries}

    def info(name: str, kind: bytes, mode: int, size: int = 0) -> tarfile.TarInfo:
        ti = tarfile.TarInfo(name)
        ti.type, ti.mode, ti.size, ti.mtime = kind, mode, size, epoch
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = "root"
        return ti

    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name in sorted(dirs | files.keys()):
                if name in files:
                    e = files[name]
                    tar.addfile(info(name, tarfile.REGTYPE, e.mode, len(e.data)), io.BytesIO(e.data))
                else:
                    tar.addfile(info(name, tarfile.DIRTYPE, 0o755))
    out.write_bytes(raw.getvalue())


def write_sha256sums(paths: list[Path], out: Path) -> None:
    out.write_text("".join(f"{sha256_file(p)}  {p.name}\n" for p in sorted(paths)))


def make_bundle(
    repo: Path, out_dir: Path, version: str, wheel: bytes, requirements: str,
    uv_binary: bytes, epoch: int,
) -> tuple[Path, Path]:
    """Lay out and write the tarball and SHA256SUMS from already-built inputs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tarball = out_dir / tarball_name(version)
    write_tarball(bundle_entries(repo, version, wheel, requirements, uv_binary), version, tarball, epoch)
    sums = out_dir / "SHA256SUMS"
    write_sha256sums([tarball], sums)
    return tarball, sums


# --------------------------------------------------------------------------


def default_uv_cache() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "cryo-bundle"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=REPO / "dist", help="output directory (default: dist/)")
    ap.add_argument("--uv-cache", type=Path, default=None,
                    help="where the pinned uv download is kept between builds"
                         " (default: $XDG_CACHE_HOME/cryo-bundle)")
    ap.add_argument("--check-tag", metavar="TAG",
                    help="only check that TAG is v<pyproject version>, then exit")
    args = ap.parse_args(argv)

    try:
        version = project_version()
        if args.check_tag is not None:
            problem = check_tag(args.check_tag, version)
            if problem:
                print(f"build_bundle: {problem}", file=sys.stderr)
                return 1
            print(f"tag {args.check_tag} matches version {version}")
            return 0

        epoch = source_date_epoch()
        target = installer_target()
        with open(REPO / "uv.lock", "rb") as f:
            lock = tomllib.load(f)
        exported = export_requirements()
        problems = check_requirements(parse_requirements(exported), lock, target)
        if problems:
            raise BuildError("requirements export is not installable on every target:\n  "
                             + "\n  ".join(problems))
        uv_binary = extract_uv_binary(fetch_uv(args.uv_cache or default_uv_cache()))
        with tempfile.TemporaryDirectory(prefix="cryo-bundle-") as tmp:
            wheel = build_wheel(REPO, version, Path(tmp), epoch).read_bytes()
        tarball, sums = make_bundle(
            REPO, args.out, version, wheel, requirements_file(version, exported), uv_binary, epoch
        )
    except BuildError as exc:
        print(f"build_bundle: {exc}", file=sys.stderr)
        return 1

    size = tarball.stat().st_size
    print(f"{tarball} ({size / 1e6:.1f} MB, uv {UV_VERSION}, SOURCE_DATE_EPOCH={epoch})")
    print(sums.read_text(), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
