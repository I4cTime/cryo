"""The Settings view, the accent override's contrast guarantee and the footer:
real Main.qml offscreen against the paused demo daemon (conftest `gui`),
clicked with QTest like a user would. Sound runs in dry run here."""

from __future__ import annotations

import colorsys
import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

from conftest import require_qt  # noqa: E402

require_qt("PySide6.QtQuick")
require_qt("PySide6.QtTest")

from PySide6.QtCore import QObject, QPoint, QPointF, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from conftest import spin  # noqa: E402


# -- helpers -------------------------------------------------------------------

def _variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


def _lin(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(c) -> float:
    return 0.2126 * _lin(c.redF()) + 0.7152 * _lin(c.greenF()) + 0.0722 * _lin(c.blueF())


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def find(gui, name: str):
    """By objectName: the QObject tree, then the visual tree (Repeater
    delegates have no QObject parent)."""
    obj = gui.window.findChild(QObject, name)
    if obj is None:
        stack = [gui.window.contentItem()]
        while stack and obj is None:
            item = stack.pop()
            if item.objectName() == name:
                obj = item
            stack.extend(item.childItems())
    assert obj is not None, name
    return obj


def open_settings(gui):
    gui.window.setProperty("page", "settings")
    spin(400)                  # load plus the crossfade
    return find(gui, "settingsScroller")


def show(gui, item) -> None:
    """Scroll whichever page holds `item` so it is on screen."""
    scroller = item
    while scroller is not None and scroller.objectName() not in ("settingsScroller", "scroller"):
        scroller = scroller.parentItem()
    assert scroller is not None
    content = scroller.property("contentItem")
    y = item.mapToItem(content, QPointF(0, 0)).y() - 40
    top = max(0.0, scroller.property("contentHeight") - scroller.height())
    scroller.setProperty("contentY", max(0.0, min(y, top)))
    spin(30)


def click(gui, item) -> None:
    show(gui, item)
    p = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    QTest.mouseClick(gui.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(round(p.x()), round(p.y())))
    spin(30)


@pytest.fixture
def ui(gui):
    """The gui harness with sound in dry run and every accepted cue recorded."""
    sfx = gui.singleton("Sfx")
    sfx.setProperty("dryRun", True)
    played: list[str] = []
    sfx.played.connect(played.append)
    gui.played = played
    gui.prefs = gui.singleton("Prefs")
    gui.theme = gui.singleton("Theme")
    gui.sfx = sfx
    return gui


# -- accent ----------------------------------------------------------------------

def test_accent_choices_are_data(ui):
    choices = _variant(ui.theme.property("accentChoices"))
    assert 6 <= len(choices) <= 10
    colours = [c["color"].upper() for c in choices]
    assert len(set(colours)) == len(colours)
    assert {"#00D1FF", "#9BE7FF", "#3DF5B4", "#8A5CFF", "#FF4FD8", "#FFB300"} <= set(colours)
    for c in choices:
        assert c["name"] and len(c["color"]) == 7


def test_every_accent_reads_in_every_style(ui):
    """For each style and each choice (and the style default) the accent
    Theme draws with is text-grade on the style's panel (4.5:1) and holds
    3:1 for non-text uses on the panel and the window background."""
    theme, prefs = ui.theme, ui.prefs
    styles = _variant(theme.property("styles"))
    choices = [""] + [c["color"] for c in _variant(theme.property("accentChoices"))]
    failures = []
    for style in _variant(theme.property("styleNames")):
        prefs.setProperty("style", style)
        for choice in choices:
            prefs.setProperty("accent", choice)
            spin(5)
            accent, panel, bg = (theme.property(k) for k in ("accent", "panel", "bg"))
            assert panel.name().upper() == styles[style]["panel"].upper()
            text = contrast(accent, panel)
            if text < 4.5 or contrast(accent, bg) < 3.0:
                failures.append(f"{style} {choice or 'default'} -> {accent.name()} "
                                f"{text:.2f} on panel, {contrast(accent, bg):.2f} on bg")
    assert not failures, "\n".join(failures)
    assert ui.messages == []


def test_readable_override_is_left_alone_or_minimally_deepened(ui):
    theme, prefs = ui.theme, ui.prefs
    prefs.setProperty("style", "cryo")
    prefs.setProperty("accent", "#9BE7FF")
    spin(5)
    assert theme.property("accent").name().upper() == "#9BE7FF"       # already fine on dark
    prefs.setProperty("style", "glacier")
    spin(5)
    accent = theme.property("accent")
    assert accent.name().upper() != "#9BE7FF"
    ratio = contrast(accent, theme.property("panel"))
    assert 4.5 <= ratio < 5.0                                          # the edge, not black
    hue = colorsys.rgb_to_hls(accent.redF(), accent.greenF(), accent.blueF())[0] * 360
    assert abs(hue - 195) < 4                                          # same hue as ice
    assert theme.property("accentOverridden") is True


# -- the page --------------------------------------------------------------------

def test_settings_page_loads_and_escape_goes_back(ui):
    open_settings(ui)
    loader = find(ui, "settingsLoader")
    assert loader.property("item") is not None
    assert loader.property("opacity") == pytest.approx(1.0)
    assert find(ui, "scroller").property("visible") is False
    for name in ("styleCards", "accentDefault", "effectsSwitch", "reduceMotionSwitch",
                 "soundSwitch", "soundSetPicker", "soundVolume", "previewMode",
                 "previewFreeze", "frostLineSwitch", "frostSample", "aboutPanel"):
        find(ui, name)
    ui.window.requestActivate()
    spin(50)
    QTest.keyClick(ui.window, Qt.Key.Key_Escape)
    spin(400)
    assert ui.window.property("page") == "home"
    assert loader.property("item") is None                            # unloaded after the fade
    assert ui.messages == []


def test_close_button_returns_home_with_a_tap(ui):
    ui.prefs.setProperty("soundEnabled", True)
    open_settings(ui)
    click(ui, find(ui, "settingsClose"))
    assert ui.window.property("page") == "home"
    assert ui.played == ["tap"]


def _scene_rect(item):
    r = item.mapRectToScene(item.boundingRect())
    return (r.x(), r.y(), r.width(), r.height())


def test_close_sits_where_the_gear_is(ui):
    # Settings opens and closes in the same spot: the pointer never moves.
    gear = _scene_rect(find(ui, "settingsButton"))
    mark_x = _scene_rect(find(ui, "livingMark"))[0]
    open_settings(ui)
    assert _scene_rect(find(ui, "settingsClose")) == pytest.approx(gear)
    header = find(ui, "settingsHeader")
    assert _scene_rect(header)[0] == pytest.approx(mark_x)      # title at the mark's margin
    stack, back = [ui.window.contentItem()], None
    while stack:
        item = stack.pop()
        back = back or (item if item.objectName() == "settingsBack" else None)
        stack.extend(item.childItems())
    assert back is None


def paint_order(root) -> list:
    """Every item under `root` in the order the scene graph paints it:
    siblings by z (declaration order among equals), a child with negative
    z before its parent, the others after it."""
    out: list = []

    def visit(item) -> None:
        kids = sorted(enumerate(item.childItems()), key=lambda p: (p[1].z(), p[0]))
        for _, kid in kids:
            if kid.z() < 0:
                visit(kid)
        out.append(item)
        for _, kid in kids:
            if kid.z() >= 0:
                visit(kid)

    visit(root)
    return out


def _subtree(item) -> list:
    out, stack = [], [item]
    while stack:
        it = stack.pop()
        out.append(it)
        stack.extend(it.childItems())
    return out


def test_frost_sits_between_the_backdrop_and_both_pages(ui):
    """The window frost is a background layer: above the backdrop washes,
    below every label, icon, control and panel of the home column and of the
    Settings page, in every frost state."""
    from shiboken6 import Shiboken

    def key(item) -> int:
        return Shiboken.getCppPointer(item)[0]

    def check(page_root) -> None:
        order = [key(i) for i in paint_order(ui.window.contentItem())]
        at = {k: n for n, k in enumerate(order)}
        backdrop, frost, ghost = (at[key(find(ui, n))] for n in ("backdrop", "frost", "frostGhost"))
        page = _subtree(page_root)
        texts = [i for i in page if i.property("text") not in (None, "")]
        assert len(texts) > 10                              # the page really is in there
        assert backdrop < frost < ghost < min(at[key(i)] for i in page)

    ambient = ui.singleton("Ambient")
    ambient.setProperty("forceLive", True)
    home = find(ui, "scroller")
    check(home)                                                       # idle
    ui.daemon.set_state(cpu_temp=91.0, gpu_temp=80.0, guard=True)     # sweep, then held
    spin(30)
    assert ambient.property("guardPhase") == "sweep"
    check(home)
    ui.daemon.set_state(connected=False)                              # thaw into dormant
    spin(30)
    assert ambient.property("guardPhase") == "thaw"
    check(home)
    ui.daemon.set_state(connected=True, guard=False)
    open_settings(ui)
    check(find(ui, "settingsLoader").property("item"))
    assert ui.messages == []


def test_page_switch_crossfades_only_with_motion(ui):
    ambient = ui.singleton("Ambient")
    ambient.setProperty("forceLive", True)
    spin(20)
    loader = find(ui, "settingsLoader")
    ui.window.setProperty("page", "settings")
    spin(1)
    assert loader.property("opacity") < 1.0                           # fading in, not a cut
    spin(400)
    assert loader.property("opacity") == pytest.approx(1.0)
    ui.window.setProperty("page", "home")
    spin(300)
    ui.prefs.setProperty("reduceMotion", True)
    spin(20)
    ui.window.setProperty("page", "settings")
    spin(1)
    assert loader.property("opacity") == pytest.approx(1.0)           # instant
    assert ui.messages == []


def test_style_cards_apply_instantly(ui):
    ui.prefs.setProperty("soundEnabled", True)
    open_settings(ui)
    styles = _variant(ui.theme.property("styles"))
    for name in ("glacier", "aurora", "blackout", "cryo"):
        click(ui, find(ui, f"styleCard_{name}"))
        assert ui.prefs.property("style") == name
        assert ui.theme.property("bg").name().upper() == styles[name]["bg"].upper()
    assert ui.played == ["tap"] * 4
    assert ui.messages == []


def test_accent_swatches_and_style_default(ui):
    open_settings(ui)
    click(ui, find(ui, "accentViolet"))
    assert ui.prefs.property("accent").upper() == "#8A5CFF"
    assert ui.theme.property("accent").name().upper() == "#8A5CFF"
    click(ui, find(ui, "accentDefault"))
    assert ui.prefs.property("accent") == ""
    assert ui.theme.property("accentOverridden") is False


def test_switches_write_prefs(ui):
    ui.prefs.setProperty("soundEnabled", True)
    open_settings(ui)
    for name, key in (("effectsSwitch", "effects"), ("reduceMotionSwitch", "reduceMotion"),
                      ("frostLineSwitch", "frostLine")):
        before = ui.prefs.property(key)
        click(ui, find(ui, name))
        assert ui.prefs.property(key) is (not before), key
        spin(70)
    assert ui.played == ["toggle_off", "toggle_on", "toggle_off"]
    assert ui.messages == []


def test_sound_controls_follow_enable_and_availability(ui):
    open_settings(ui)
    picker = find(ui, "soundSetPicker")
    unavailable = find(ui, "soundUnavailable")
    assert picker.property("enabled") is False                        # sound off
    assert unavailable.property("visible") is False
    click(ui, find(ui, "soundSwitch"))
    assert ui.prefs.property("soundEnabled") is True
    assert ui.played == ["toggle_on"]   # cued after sound is on, so it is heard
    assert picker.property("enabled") is True
    assert ui.sfx.property("state") == "off"                          # dry run: nothing built
    click(ui, find(ui, "segment_glass"))
    assert ui.prefs.property("soundSet") == "glass"
    # the unavailable path, as Sfx reports it when QtMultimedia fails
    ui.sfx.setProperty("_state", "unavailable")
    spin(10)
    assert ui.sfx.property("available") is False
    assert unavailable.property("visible") is True
    assert picker.property("enabled") is False
    assert find(ui, "previewMode").property("enabled") is False
    ui.sfx.setProperty("_state", "off")
    spin(70)
    click(ui, find(ui, "soundSwitch"))   # turning it off still plays, then stops
    assert ui.played == ["toggle_on", "tap", "toggle_off"]
    assert ui.prefs.property("soundEnabled") is False
    assert ui.messages == []


def test_preview_buttons_play_their_cue_not_a_tap(ui):
    ui.prefs.setProperty("soundEnabled", True)
    open_settings(ui)
    click(ui, find(ui, "previewMode"))
    click(ui, find(ui, "previewFreeze"))
    assert ui.played == ["mode", "freeze"]


def test_volume_slider_writes_the_pref(ui):
    ui.prefs.setProperty("soundEnabled", True)
    open_settings(ui)
    slider = find(ui, "soundVolume")
    show(ui, slider)
    left = slider.mapToScene(QPointF(slider.property("leftPadding") + 2, slider.height() / 2))
    QTest.mouseClick(ui.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(round(left.x()), round(left.y())))
    spin(30)
    assert ui.prefs.property("soundVolume") == pytest.approx(0.0)


def test_about_block(ui):
    from cryo import __version__

    open_settings(ui)
    assert find(ui, "aboutVersion").property("text") == __version__
    assert find(ui, "demoMarker").property("visible") is True
    assert find(ui, "aboutModel").property("text") == "Alienware m18 R2"
    assert find(ui, "aboutDaemon").property("text") == "cryod · balanced profile"
    ui.daemon.set_state(connected=False)
    spin(10)
    assert "unreachable" in find(ui, "aboutDaemon").property("text")
    assert ui.messages == []


def test_frost_sample_shows_the_live_line(ui):
    open_settings(ui)
    assert find(ui, "frostSampleText").property("text") == ui.daemon.frostLine
    ui.daemon.set_state(guard=True)
    spin(10)
    assert find(ui, "frostSampleText").property("text") == ui.daemon.frostLine
    assert ui.daemon.frostLineKey.startswith("guard:")


# -- footer ----------------------------------------------------------------------

def test_footer_shows_frost_or_the_plain_status(ui):
    line, text, status = (find(ui, n) for n in ("footerFrost", "footerFrostText", "footerStatus"))
    spin(30)
    assert line.property("visible") is True and status.property("visible") is False
    assert text.property("text") == ui.daemon.frostLine
    assert line.property("width") > 100                               # laid out, not collapsed
    ui.daemon.set_state(cpu_temp=88.0, gpu_temp=80.0)
    spin(10)
    assert text.property("text") == ui.daemon.frostLine
    ui.prefs.setProperty("frostLine", False)
    spin(10)
    assert line.property("visible") is False and status.property("visible") is True
    assert status.property("text") == "cryod · balanced profile"
    ui.prefs.setProperty("frostLine", True)
    ui.daemon.set_state(connected=False)
    spin(10)
    assert line.property("visible") is True and status.property("visible") is True
    assert status.property("text") == "sudo systemctl start cryod"
    assert ui.messages == []


def test_footer_crossfades_when_the_wording_changes(ui):
    ambient = ui.singleton("Ambient")
    ambient.setProperty("forceLive", True)
    spin(20)
    text, ghost = find(ui, "footerFrostText"), find(ui, "footerFrostGhost")
    key, old_line = ui.daemon.frostLineKey, ui.daemon.frostLine
    ui.daemon.set_state(cpu_temp=45.0)                  # same wording: no fade
    assert ui.daemon.frostLineKey == key
    assert ghost.property("text") == ""
    ui.daemon.set_state(guard=True)
    assert ui.daemon.frostLineKey != key
    assert ghost.property("text") == old_line            # the old wording fades out
    spin(1)
    assert text.property("opacity") < 1.0
    spin(400)
    assert text.property("opacity") == pytest.approx(1.0)
    assert ghost.property("visible") is False
    assert ui.messages == []


# -- persistence -------------------------------------------------------------------

def test_choices_persist_to_the_settings_file(ui):
    """Prefs is QtCore Settings: what the page sets lands in the app's
    QSettings (here the test's temp XDG config), where the next start reads it."""
    values = {"style": "aurora", "accent": "#FF4FD8", "effects": False, "reduceMotion": True,
              "soundEnabled": True, "soundSet": "deep", "soundVolume": 0.25, "frostLine": False}
    for key, value in values.items():
        ui.prefs.setProperty(key, value)
    spin(800)                          # Settings writes after a 500 ms delay
    stored = QSettings()
    for key, value in values.items():
        raw = stored.value(key)
        if isinstance(value, bool):
            raw = str(raw).lower() == "true"
        elif isinstance(value, float):
            raw = float(raw)
        assert raw == value, key


def _laid_out_lines(text: str, font, width: float) -> list[str]:
    from PySide6.QtGui import QTextLayout, QTextOption

    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    layout.setTextOption(option)
    layout.beginLayout()
    out = []
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        out.append(text[line.textStart():line.textStart() + line.textLength()])
    layout.endLayout()
    return out


@pytest.mark.parametrize("width", [480, 440])
def test_settings_copy_has_no_one_word_last_line(ui, width):
    """Copy that wraps must not leave a single word on its last line at the
    default (480) or minimum (440) window width. Frost's live line is
    excluded (it changes with state)."""
    ui.window.setWidth(width)
    open_settings(ui)
    stack, widows = [find(ui, "settingsScroller")], []
    while stack:
        item = stack.pop()
        stack.extend(item.childItems())
        if not item.inherits("QQuickText") or not item.isVisible():
            continue
        if item.objectName() == "frostSampleText" or (item.property("lineCount") or 0) < 2:
            continue
        lines = _laid_out_lines(item.property("text"), item.property("font"), item.width())
        assert len(lines) == item.property("lineCount"), lines
        if len(lines[-1].split()) < 2:
            widows.append(lines)
    assert widows == []
