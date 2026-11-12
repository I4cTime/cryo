"""Release bundle: tools/build_bundle.py and packaging/bundle/*.sh.

Offline and unprivileged: the uv download and the wheel build are replaced
by fixture bytes, and the shell scripts are only run where they must refuse
(not root) or sourced for their pure helpers. The real install, upgrade and
uninstall run in CI's bundle job and tools/bundle_container_test.sh.
"""

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INSTALL = REPO / "packaging" / "bundle" / "install.sh"
UNINSTALL = REPO / "packaging" / "bundle" / "uninstall.sh"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_bundle", REPO / "tools" / "build_bundle.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_bundle"] = module
    spec.loader.exec_module(module)
    return module


bb = _load_builder()

EPOCH = 1_700_000_000
VERSION = bb.project_version()


def _build(out: Path):
    return bb.make_bundle(
        REPO, out, VERSION, wheel=b"PK fake wheel", requirements="pyusb==1.3.1 \\\n    --hash=sha256:aa\n",
        uv_binary=b"\x7fELF fake uv", epoch=EPOCH,
    )


# ---------------------------------------------------------------- tarball


def test_bundle_layout_modes_and_owner(tmp_path):
    tarball, _ = _build(tmp_path)
    assert tarball.name == f"cryo-{VERSION}-linux-x86_64.tar.gz"
    top = f"cryo-{VERSION}"
    with tarfile.open(tarball) as tar:
        members = tar.getmembers()
    names = [m.name for m in members]
    assert names == sorted(names)
    icons = [f"{top}/share/icons/cryo-{s}.png" for s in (32, 48, 64, 128, 256, 512)]
    expected_files = {
        f"{top}/install.sh", f"{top}/uninstall.sh", f"{top}/README.txt", f"{top}/LICENSE",
        f"{top}/VERSION", f"{top}/requirements.txt", f"{top}/bin/uv",
        f"{top}/wheels/cryo-{VERSION}-py3-none-any.whl",
        f"{top}/share/cryod.service", f"{top}/share/cryod-resume.service", f"{top}/share/mark.svg",
        *icons,
    }
    expected_dirs = {top, f"{top}/bin", f"{top}/wheels", f"{top}/share", f"{top}/share/icons"}
    assert {m.name for m in members if m.isfile()} == expected_files
    assert {m.name for m in members if m.isdir()} == expected_dirs
    executables = {f"{top}/install.sh", f"{top}/uninstall.sh", f"{top}/bin/uv"}
    for m in members:
        assert (m.uid, m.gid, m.uname, m.gname) == (0, 0, "root", "root"), m.name
        assert m.mtime == EPOCH, m.name
        want = 0o755 if m.isdir() or m.name in executables else 0o644
        assert m.mode == want, (m.name, oct(m.mode))


def test_bundle_contents(tmp_path):
    tarball, _ = _build(tmp_path)
    top = f"cryo-{VERSION}"
    with tarfile.open(tarball) as tar:
        read = lambda name: tar.extractfile(f"{top}/{name}").read()  # noqa: E731
        assert read("VERSION") == f"{VERSION}\n".encode()
        assert read("bin/uv") == b"\x7fELF fake uv"
        assert read("install.sh") == INSTALL.read_bytes()
        assert read("share/cryod.service") == (REPO / "packaging" / "cryod.service").read_bytes()
        readme = read("README.txt").decode()
        assert f"Cryo {VERSION}" in readme and "@VERSION@" not in readme


def test_bundle_is_reproducible(tmp_path):
    a, _ = _build(tmp_path / "a")
    b, _ = _build(tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()


def test_sha256sums_matches(tmp_path):
    tarball, sums = _build(tmp_path)
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    assert sums.read_text() == f"{digest}  {tarball.name}\n"


def test_uv_pin_is_well_formed():
    assert len(bb.UV_SHA256) == 64 and int(bb.UV_SHA256, 16) >= 0
    assert bb.UV_ASSET.endswith("x86_64-unknown-linux-musl.tar.gz")
    assert f"/download/{bb.UV_VERSION}/" in bb.UV_URL


def test_uv_checksum_mismatch_fails_loudly(tmp_path, monkeypatch):
    cached = tmp_path / f"uv-{bb.UV_VERSION}-{bb.UV_ASSET}"
    cached.write_bytes(b"not uv")

    class FakeResponse:
        def __init__(self):
            self.data = [b"tampered", b""]

        def read(self, n=-1):
            return self.data.pop(0)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(bb.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    with pytest.raises(bb.BuildError, match="CHECKSUM MISMATCH"):
        bb.fetch_uv(tmp_path)
    assert not cached.exists()
    assert not list(tmp_path.glob("*.part"))


# ---------------------------------------------------------------- version


def test_check_tag():
    assert bb.check_tag("v1.2.3", "1.2.3") is None
    assert bb.check_tag("refs/tags/v1.2.3", "1.2.3") is None
    assert "does not match" in bb.check_tag("v1.2.4", "1.2.3")
    assert "does not match" in bb.check_tag("1.2.3", "1.2.3")


def test_check_tag_cli():
    ok = subprocess.run([sys.executable, REPO / "tools" / "build_bundle.py", "--check-tag", f"v{VERSION}"],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    bad = subprocess.run([sys.executable, REPO / "tools" / "build_bundle.py", "--check-tag", "v0.0.0-nope"],
                         capture_output=True, text=True)
    assert bad.returncode == 1 and "does not match" in bad.stderr


# ---------------------------------------------------------------- requirements

LOCK = {
    "package": [
        {"name": "purelib", "version": "1.0", "wheels": [
            {"url": "https://x/purelib-1.0-py3-none-any.whl", "hash": "sha256:p1"}]},
        {"name": "Qt_Thing", "version": "6.0", "wheels": [
            {"url": "https://x/qt_thing-6.0-cp310-abi3-manylinux_2_34_x86_64.whl", "hash": "sha256:q1"},
            {"url": "https://x/qt_thing-6.0-cp310-abi3-win_amd64.whl", "hash": "sha256:q2"}]},
        {"name": "onlywin", "version": "2.0", "wheels": [
            {"url": "https://x/onlywin-2.0-cp312-cp312-win_amd64.whl", "hash": "sha256:w1"}]},
        {"name": "cp312only", "version": "1.0", "wheels": [
            {"url": "https://x/cp312only-1.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
             "hash": "sha256:c1"}]},
        {"name": "newglibc", "version": "1.0", "wheels": [
            {"url": "https://x/newglibc-1.0-py3-none-manylinux_2_39_x86_64.whl", "hash": "sha256:g1"}]},
        {"name": "muslonly", "version": "1.0", "wheels": [
            {"url": "https://x/muslonly-1.0-py3-none-musllinux_1_2_x86_64.whl", "hash": "sha256:m1"}]},
    ]
}
TARGET = bb.Target(py_minors=(12, 13, 14, 15), glibc_min=(2, 34))


def check(text):
    return bb.check_requirements(bb.parse_requirements(text), LOCK, TARGET)


def test_parse_requirements_handles_continuations_and_markers():
    reqs = bb.parse_requirements(
        "# header\n"
        "qt-thing==6.0 \\\n    --hash=sha256:q1 \\\n    --hash=sha256:q2\n"
        "onlywin==2.0 ; sys_platform == 'win32' \\\n    --hash=sha256:w1\n"
    )
    assert [(r.name, r.version, r.marker, r.hashes) for r in reqs] == [
        ("qt-thing", "6.0", None, ["sha256:q1", "sha256:q2"]),
        ("onlywin", "2.0", "sys_platform == 'win32'", ["sha256:w1"]),
    ]


def test_installable_requirements_pass():
    assert check("purelib==1.0 --hash=sha256:p1\nqt-thing==6.0 --hash=sha256:q1 --hash=sha256:q2\n") == []


def test_marker_excluded_requirement_is_not_checked_for_linux():
    assert check("onlywin==2.0 ; sys_platform == 'win32' --hash=sha256:w1\n") == []
    problems = check("onlywin==2.0 ; sys_platform == 'linux' --hash=sha256:w1\n")
    assert problems and all("no linux x86_64 wheel" in p for p in problems)


def test_version_specific_wheel_fails_for_other_pythons():
    problems = check("cp312only==1.0 --hash=sha256:c1\n")
    assert [p.split(" (")[0] for p in problems] == [
        f"cp312only==1.0: no linux x86_64 wheel for Python 3.{m}" for m in (13, 14, 15)
    ]
    # ...unless a marker limits it to the version that has the wheel.
    assert check("cp312only==1.0 ; python_version < '3.13' --hash=sha256:c1\n") == []


def test_glibc_newer_than_installer_check_fails():
    problems = check("newglibc==1.0 --hash=sha256:g1\n")
    assert problems and "needs glibc 2.39" in problems[0]


def test_unpinned_unhashed_unknown_and_musl_fail():
    assert "not pinned" in check("purelib --hash=sha256:p1\n")[0]
    assert "no --hash" in check("purelib==1.0\n")[0]
    assert "not in uv.lock" in check("purelib==9.9 --hash=sha256:p1\n")[0]
    assert "none of its hashes" in check("purelib==1.0 --hash=sha256:zz\n")[0]
    assert "no linux x86_64 wheel" in check("muslonly==1.0 --hash=sha256:m1\n")[0]


@pytest.mark.parametrize("marker, minor, want", [
    ("sys_platform == 'win32'", 12, False),
    ("sys_platform == 'linux' and platform_machine == 'x86_64'", 12, True),
    ("python_version >= '3.13'", 12, False),
    ("python_version >= '3.13'", 14, True),
    ("(sys_platform == 'darwin' or os_name == 'posix') and python_full_version < '3.16'", 15, True),
    ("platform_machine in 'x86_64 AMD64'", 12, True),
    ("platform_release == '6.1'", 12, None),
])
def test_evaluate_marker(marker, minor, want):
    assert bb.evaluate_marker(marker, bb.marker_env(minor)) is want


def test_installer_target_is_read_from_install_sh():
    target = bb.installer_target()
    text = INSTALL.read_text()
    assert f"MANAGED_PYTHON=3.{target.py_minors[0]}\n" in text and len(target.py_minors) == 1
    assert "PY_MIN_MINOR" not in text and "--no-managed-python" not in text
    assert target.glibc_min >= (2, 17)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_real_lock_export_is_installable_on_every_target():
    """The actual uv.lock: every runtime dependency has a hashed manylinux
    x86_64 wheel for the installer's managed Python (offline: lock only)."""
    proc = subprocess.run(
        ["uv", "export", "--frozen", "--offline", "--no-dev", "--no-emit-project", "--no-header",
         "--no-annotate", "--format", "requirements.txt"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    reqs = bb.parse_requirements(proc.stdout)
    assert {r.name for r in reqs} >= {"pyside6", "pyusb", "nvidia-ml-py"}
    assert "pytest" not in {r.name for r in reqs}
    with open(REPO / "uv.lock", "rb") as f:
        lock = tomllib.load(f)
    assert bb.check_requirements(reqs, lock, bb.installer_target()) == []


# ---------------------------------------------------------------- shell


def bash(script: str, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env={**os.environ, **env}, cwd=REPO)


@pytest.mark.parametrize("path", [INSTALL, UNINSTALL])
def test_scripts_parse(path):
    assert subprocess.run(["bash", "-n", path], capture_output=True).returncode == 0


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_scripts_are_shellcheck_clean():
    scripts = [INSTALL, UNINSTALL, REPO / "tools" / "bundle_check.sh", REPO / "tools" / "bundle_container_test.sh"]
    proc = subprocess.run(["shellcheck", *scripts], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout


needs_non_root = pytest.mark.skipif(os.geteuid() == 0, reason="the refusal is for non-root users")


@needs_non_root
@pytest.mark.parametrize("path, message", [
    (INSTALL, "cryo install: must run as root: sudo ./install.sh"),
    (UNINSTALL, "cryo uninstall: must run as root: sudo /opt/cryo/uninstall.sh"),
])
def test_scripts_refuse_without_root_before_touching_anything(tmp_path, path, message):
    home = tmp_path / "home"
    home.mkdir()
    proc = subprocess.run(["bash", path], capture_output=True, text=True, cwd=tmp_path,
                          env={"PATH": os.environ["PATH"], "HOME": str(home), "SUDO_USER": "someone"})
    assert proc.returncode != 0
    assert proc.stderr.strip() == message
    assert proc.stdout == ""
    assert sorted(p.name for p in tmp_path.rglob("*")) == ["home"]


def test_uninstall_rejects_unknown_arguments():
    proc = subprocess.run(["bash", UNINSTALL, "--bogus"], capture_output=True, text=True)
    assert proc.returncode == 2 and "usage:" in proc.stderr


def source(call: str) -> subprocess.CompletedProcess:
    return bash(f"source {INSTALL}; {call}")


@pytest.mark.parametrize("args, fragment", [
    ("1000 alice x86_64 'glibc 2.39' yes", "must run as root"),
    ("0 '' x86_64 'glibc 2.39' yes", "not as root directly"),
    ("0 root x86_64 'glibc 2.39' yes", "not as root directly"),
    ("0 alice aarch64 'glibc 2.39' yes", "for x86_64 and this machine is aarch64"),
    ("0 alice x86_64 musl yes", "musl"),
    ("0 alice x86_64 unknown yes", "could not find glibc"),
    ("0 alice x86_64 'glibc 2.31' yes", "glibc 2.31 is too old"),
    ("0 alice x86_64 'glibc 2.39' no", "systemd is not running"),
])
def test_installer_refusals(args, fragment):
    out = source(f"refusal_reason {args}").stdout.strip()
    assert fragment in out
    assert "\n" not in out


def test_installer_accepts_a_supported_machine():
    proc = source("refusal_reason 0 alice x86_64 'glibc 2.34' yes")
    assert proc.returncode == 0 and proc.stdout == ""


def test_render_unit_points_into_opt():
    for unit in ("cryod.service", "cryod-resume.service"):
        out = source(f"render_unit packaging/{unit} /opt/cryo/env/bin/python").stdout
        assert "@PYTHON@" not in out
        assert "ExecStart=/opt/cryo/env/bin/python -m cryo." in out
        assert "RestartPreventExitStatus=78" in out or unit == "cryod-resume.service"


def test_desktop_entry_matches_the_source_install():
    out = source("desktop_entry /usr/local/bin/cryo-gui").stdout
    assert "Exec=/usr/local/bin/cryo-gui\n" in out and "Icon=cryo\n" in out
    source_install = (REPO / "packaging" / "install.sh").read_text()
    for line in out.splitlines():
        if not line.startswith("Exec="):
            assert line in source_install, line


def test_takeover_detection(tmp_path):
    unit = tmp_path / "cryod.service"
    unit.write_text("[Service]\nExecStart=/home/a/cryo/.venv/bin/python -m cryo.daemon.main\n")
    assert source(f"is_foreign_unit {unit}").returncode == 0
    assert source(f"unit_exec {unit}").stdout.strip() == "/home/a/cryo/.venv/bin/python"
    unit.write_text("[Service]\nExecStart=/opt/cryo/env/bin/python -m cryo.daemon.main\n")
    assert source(f"is_foreign_unit {unit}").returncode != 0


@pytest.mark.parametrize("exec_line, stale", [
    ("Exec=/home/a/cryo/.venv/bin/cryo-gui", True),
    ("Exec=/usr/local/bin/cryo-gui", False),
    ("Exec=/opt/cryo/env/bin/cryo-gui", False),
    ("Exec=cryo-gui", False),
])
def test_stale_user_desktop_entry(tmp_path, exec_line, stale):
    entry = tmp_path / "cryo.desktop"
    entry.write_text(f"[Desktop Entry]\nName=Cryo\n{exec_line}\n")
    assert (source(f"is_stale_user_desktop {entry}").returncode == 0) is stale


def test_bundle_problem_names_the_missing_piece(tmp_path):
    assert source(f"bundle_problem {tmp_path}").stdout.strip() == "VERSION"


def test_install_and_uninstall_agree_on_paths():
    def consts(path):
        out = {}
        for line in path.read_text().splitlines():
            if "=" in line and line.split("=", 1)[0].isupper() and not line.startswith(" "):
                key, value = line.split("=", 1)
                out[key] = value
        return out

    a, b = consts(INSTALL), consts(UNINSTALL)
    for key in ("PREFIX", "BIN_DIR", "UNIT_DIR", "APP_DIR", "ICON_ROOT", "CONF_DIR", "STATE_DIR",
                "UNITS", "COMMANDS", "ICON_SIZES", "UNSUPPORTED_STATUS"):
        assert a[key] == b[key], key
    assert a["ICON_SIZES"] == "(" + " ".join(map(str, bb.ICON_SIZES)) + ")"
