"""Token discipline for the QML look (docs/THEME.md).

(a) No colour literal in any QML file outside the token blocks: Theme.qml,
    the LED swatch data in Lighting.qml and FrostOverlay.qml's property
    defaults are the only places a "#hex" or a named colour may appear.
    No emoji either: icons come from the SVG set through Icon.qml.
(b) Every style defines exactly the same tokens, and switching Prefs.style
    through all of them (and the accent override) runs without a QML
    warning and re-themes live.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

QML_DIR = Path(__file__).resolve().parents[1] / "src" / "cryo" / "gui" / "qml"
QML_FILES = sorted(QML_DIR.rglob("*.qml"))

HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
QUOTED = re.compile(r"""["']([A-Za-z]+)["']""")
# "transparent" is the absence of a colour, not a palette choice.
NAMED_ALLOWED = {"transparent"}
# Emoji and pictographic symbols (incl. dingbats like the old mode glyphs and
# the variation selector that forces emoji presentation).
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿️‍]"
)


def _named_colours() -> set[str]:
    try:
        from PySide6.QtGui import QColor
    except ImportError:          # no QtGui: a short list still catches the usual ones
        return {"white", "black", "red", "green", "blue", "cyan", "magenta", "yellow",
                "gray", "grey", "orange", "purple", "pink"}
    return {n.lower() for n in QColor.colorNames()}


def _code(line: str) -> str:
    """The line without a trailing // comment (comments may name colours)."""
    out, quote = [], None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                out.append(line[i:i + 2])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif line.startswith("//", i):
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _exempt(path: Path, line: str) -> bool:
    rel = path.relative_to(QML_DIR).as_posix()
    if rel == "Cryo/Theme.qml":
        return True
    if rel == "Cryo/Lighting.qml" and "swatches:" in line:
        return True       # LED colours the keyboard shows: data, not theme
    if rel == "Cryo/fx/FrostOverlay.qml" and re.match(r"\s*property color \w+:", line):
        return True       # the component's own defaults (Main.qml binds Theme)
    return False


def test_there_are_qml_files():
    assert any(p.name == "Main.qml" for p in QML_FILES)
    assert any(p.name == "Theme.qml" for p in QML_FILES)


@pytest.mark.parametrize("path", QML_FILES, ids=lambda p: p.relative_to(QML_DIR).as_posix())
def test_no_colour_literals_outside_tokens(path: Path):
    named = _named_colours() - NAMED_ALLOWED
    bad = []
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = _code(raw)
        if _exempt(path, line):
            continue
        for m in HEX.finditer(line):
            bad.append(f"{no}: {m.group(0)}")
        for m in QUOTED.finditer(line):
            if m.group(1).lower() in named:
                bad.append(f"{no}: {m.group(0)}")
        if re.search(r"Qt\.(rgba|hsla|hsva)\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+", line):
            bad.append(f"{no}: literal Qt colour constructor")
    assert not bad, "colour literals outside Theme.qml (use a Theme token):\n" + "\n".join(bad)


@pytest.mark.parametrize("path", QML_FILES, ids=lambda p: p.relative_to(QML_DIR).as_posix())
def test_no_emoji_in_qml(path: Path):
    hits = [f"{no}: {line.strip()}"
            for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if EMOJI.search(line)]
    assert not hits, "emoji in QML (use an Icon):\n" + "\n".join(hits)


def test_profile_glyphs_are_gone_and_icons_exist():
    theme = (QML_DIR / "Cryo" / "Theme.qml").read_text(encoding="utf-8")
    assert "profileGlyphs" not in theme
    icons = Path(__file__).resolve().parents[1] / "src" / "cryo" / "gui" / "assets" / "icons"
    for name in re.findall(r'"(mode-[a-z-]+)"', theme):
        assert (icons / f"{name}.svg").is_file(), name


# -- through the engine ------------------------------------------------------

def _styles(gui) -> dict:
    theme = gui.singleton("Theme")
    styles = theme.property("styles")
    if hasattr(styles, "toVariant"):
        styles = styles.toVariant()
    return styles


def test_every_style_has_the_same_keys(gui):
    styles = _styles(gui)
    names = gui.singleton("Theme").property("styleNames")
    if hasattr(names, "toVariant"):
        names = names.toVariant()
    assert set(styles) == set(names) == {"cryo", "aurora", "glacier", "blackout"}
    reference = set(styles["cryo"])
    for name, style in styles.items():
        assert set(style) == reference, f"{name}: {set(style) ^ reference}"
    # every key is exposed as a Theme property of the same name
    theme = gui.singleton("Theme")
    for key in reference:
        assert theme.property(key) is not None, key


def test_switching_styles_rethemes_live_without_warnings(gui):
    from conftest import spin

    theme, prefs = gui.singleton("Theme"), gui.singleton("Prefs")
    styles = _styles(gui)
    gui.daemon.set_state(cpu_temp=70, gpu_temp=60, guard=True, gaming=True)
    gui.window.findChild(__import__("PySide6.QtCore").QtCore.QObject, "curveBody").setProperty("visible", True)
    seen_bg = set()
    for name in ("aurora", "glacier", "blackout", "cryo"):
        prefs.setProperty("style", name)
        spin(60)
        assert theme.property("styleName") == name
        assert theme.property("bg").name().upper() == styles[name]["bg"].upper()
        assert gui.window.property("color").name().upper() == styles[name]["bg"].upper()
        assert theme.property("isLight") is styles[name]["isLight"]
        seen_bg.add(theme.property("bg").name())
    assert len(seen_bg) == 4
    prefs.setProperty("style", "no-such-style")       # unknown falls back to cryo
    spin(30)
    assert theme.property("styleName") == "cryo"
    assert gui.messages == []


def test_accent_override_changes_only_the_accent(gui):
    from conftest import spin

    theme, prefs = gui.singleton("Theme"), gui.singleton("Prefs")
    tokens = ["bg", "panel", "fg", "muted", "accent2", "accent2Text", "frost", "hot",
              "ledCyan", "ledViolet"]
    before = {t: theme.property(t).name() for t in tokens}
    prefs.setProperty("accent", "#FF8800")
    spin(30)
    assert theme.property("accent").name().upper() == "#FF8800"
    assert theme.property("accentOverridden") is True
    assert {t: theme.property(t).name() for t in tokens} == before
    prefs.setProperty("accent", "not-a-colour")        # invalid: style default
    spin(30)
    assert theme.property("accent").name().upper() == "#00D1FF"
    prefs.setProperty("accent", "")
    spin(30)
    assert theme.property("accent").name().upper() == "#00D1FF"
    assert gui.messages == []
