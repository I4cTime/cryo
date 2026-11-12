"""Labels on the backdrop stay legible over the window frost: a Clearing
(Cryo/Clearing.qml) melts the frost back behind every section title, the
two header subtitles, the dGPU row and Frost's footer line, and the header
gear and the Settings close button are backed keycaps. Real Main.qml
offscreen (software renderer: the frost is its static image there)."""

from __future__ import annotations

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"   # before any Qt application exists

from conftest import require_qt  # noqa: E402

require_qt("PySide6.QtQuick")

from PySide6.QtCore import QObject, QPointF  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402

from conftest import spin  # noqa: E402

HOME_TITLES = {"POWER MODES", "TELEMETRY", "FAN CONTROL", "CPU POWER", "AUTOMATION", "LIGHTING"}
SETTINGS_TITLES = {"APPEARANCE", "EFFECTS", "SOUND", "FROST", "ABOUT"}
# Other backed labels, by objectName: (name, page)
BACKED = [("headerSubtitle", "home"), ("gpuLoadLabel", "home"), ("gpuLoadValue", "home"),
          ("settingsSubtitle", "settings")]


# -- helpers -------------------------------------------------------------------

def items(root) -> list:
    out, stack = [], [root]
    while stack:
        it = stack.pop()
        out.append(it)
        stack.extend(it.childItems())
    return out


def find(gui, name: str):
    obj = gui.window.findChild(QObject, name)
    if obj is None:
        obj = next((i for i in items(gui.window.contentItem()) if i.objectName() == name), None)
    assert obj is not None, name
    return obj


def section_titles(root) -> dict:
    """The section titles under `root`, by text. (Not by QML type name:
    metaObject() wrappers outlive an engine in PySide and can come back as
    a stale QMetaObject for an item at a reused address.)"""
    wanted = HOME_TITLES | SETTINGS_TITLES
    # a Label (the reveal glint repeats a title's text in plain Text items)
    return {i.property("text"): i for i in items(root)
            if i.property("text") in wanted and i.property("implicitBackgroundWidth") is not None}


def test_the_title_lists_cover_every_section_title():
    """Every `SectionTitle {` in the QML is one of the titles checked here."""
    import re
    from pathlib import Path

    qml = Path(__file__).resolve().parents[1] / "src" / "cryo" / "gui" / "qml"
    found = set()
    for path in qml.rglob("*.qml"):
        found |= set(re.findall(r'SectionTitle\s*\{[^}]*?text:\s*"([^"]+)"', path.read_text(encoding="utf-8")))
    assert found == HOME_TITLES | SETTINGS_TITLES
    title = (qml / "Cryo" / "SectionTitle.qml").read_text(encoding="utf-8")
    assert "Clearing {" in title


def clearing_of(label):
    kids = [k for k in label.childItems() if k.objectName() == "clearing"]
    assert len(kids) == 1, label.objectName() or label.property("text")
    return kids[0]


def paint_order(root) -> list:
    """Items in the order the scene graph paints them: siblings by z (then
    declaration order), a child with negative z before its parent."""
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


def open_settings(gui):
    gui.window.setProperty("page", "settings")
    spin(400)                  # load plus the crossfade
    return find(gui, "settingsScroller")


def scroll_to(item) -> None:
    scroller = item
    while scroller is not None and scroller.objectName() not in ("settingsScroller", "scroller"):
        scroller = scroller.parentItem()
    assert scroller is not None
    content = scroller.property("contentItem")
    y = item.mapToItem(content, QPointF(0, 0)).y() - 60
    top = max(0.0, scroller.property("contentHeight") - scroller.height())
    scroller.setProperty("contentY", max(0.0, min(y, top)))
    spin(40)


def hold_guard(gui) -> None:
    """Guard engaged and held (reduce motion: no sweep, the frost jumps)."""
    gui.singleton("Prefs").setProperty("reduceMotion", True)
    gui.daemon.set_state(cpu_temp=91.0, gpu_temp=80.0, guard=True)
    spin(400)                  # past the 280 ms crossfade
    ambient = gui.singleton("Ambient")
    assert ambient.property("guardPhase") == "held"
    assert ambient.property("frostAmount") == pytest.approx(ambient.property("heldAmount"))


def all_backed(gui) -> list:
    """Every label that must carry a Clearing (Settings must be open)."""
    home, settings = find(gui, "scroller"), find(gui, "settingsScroller")
    home_titles, settings_titles = section_titles(home), section_titles(settings)
    assert set(home_titles) == HOME_TITLES
    assert set(settings_titles) == SETTINGS_TITLES
    labels = list(home_titles.values()) + list(settings_titles.values())
    labels += [find(gui, name) for name, _ in BACKED]
    labels.append(find(gui, "footerFrostText").parentItem())
    return labels


# -- structure -------------------------------------------------------------------

def test_every_backdrop_label_has_a_clearing_between_it_and_the_frost(gui):
    from shiboken6 import Shiboken

    def key(item) -> int:
        return Shiboken.getCppPointer(item)[0]

    open_settings(gui)
    order = {key(i): n for n, i in enumerate(paint_order(gui.window.contentItem()))}
    frost = max(order[key(find(gui, n))] for n in ("frost", "frostGhost"))
    labels = all_backed(gui)
    assert len(labels) == len(HOME_TITLES) + len(SETTINGS_TITLES) + len(BACKED) + 1
    for label in labels:
        clearing = clearing_of(label)
        what = label.objectName() or label.property("text")
        assert frost < order[key(clearing)] < order[key(label)], what
        # it reaches around the text
        assert clearing.x() < 0 and clearing.y() < 0, what
        assert clearing.width() > clearing.property("textW") > 0, what
    assert gui.messages == []


def test_clearings_take_no_layout_room(gui):
    """A Clearing is a child: the label's implicit size is its text's."""
    title = section_titles(find(gui, "scroller"))["TELEMETRY"]
    clearing = clearing_of(title)
    assert title.property("implicitWidth") == pytest.approx(title.property("contentWidth"))
    assert title.property("implicitHeight") == pytest.approx(title.property("contentHeight"))
    assert clearing.x() < 0 and clearing.y() < 0       # it reaches out around the text


def test_siblings_it_reaches_under_stay_on_top(gui):
    """The subtitle's Clearing reaches up under the wordmark and the mark,
    the figure's under the dGPU bar: those are painted after it."""
    from shiboken6 import Shiboken

    def key(item) -> int:
        return Shiboken.getCppPointer(item)[0]

    order = {key(i): n for n, i in enumerate(paint_order(gui.window.contentItem()))}
    sub = clearing_of(find(gui, "headerSubtitle"))
    wordmark = next(i for i in items(gui.window.contentItem()) if i.property("text") == "CRYO")
    assert order[key(sub)] < order[key(wordmark)]
    assert order[key(sub)] < order[key(find(gui, "livingMark"))]
    value = clearing_of(find(gui, "gpuLoadValue"))
    bar = find(gui, "gpuLoadBar")
    assert order[key(value)] < order[key(bar)]


# -- when it shows -------------------------------------------------------------------

def home_backed(gui) -> list:
    labels = list(section_titles(find(gui, "scroller")).values())
    labels += [find(gui, name) for name, page in BACKED if page == "home"]
    labels.append(find(gui, "footerFrostText").parentItem())
    return labels


@pytest.mark.parametrize("page", ["home", "settings"])
def test_clearing_follows_the_frost(gui, page):
    prefs, ambient = gui.singleton("Prefs"), gui.singleton("Ambient")
    if page == "settings":
        open_settings(gui)
        labels = list(section_titles(find(gui, "settingsScroller")).values())
        labels.append(find(gui, "settingsSubtitle"))
    else:
        labels = home_backed(gui)

    # No frost (hot, no guard): not drawn.
    gui.daemon.set_state(cpu_temp=90.0, gpu_temp=80.0)
    spin(600)
    assert ambient.property("frostAmount") == pytest.approx(0.0)
    for label in labels:
        clearing = clearing_of(label)
        assert clearing.property("opacity") == pytest.approx(0.0)
        assert not clearing.isVisible()

    # Guard held: whole.
    hold_guard(gui)
    for label in labels:
        clearing = clearing_of(label)
        assert clearing.property("opacity") == pytest.approx(1.0)
        assert clearing.isVisible(), label.objectName() or label.property("text")

    # Effects off: frostAmount is 0 and every clearing goes.
    prefs.setProperty("effects", False)
    spin(30)
    assert ambient.property("frostAmount") == 0
    for label in labels:
        assert clearing_of(label).property("opacity") == pytest.approx(0.0)
        assert not clearing_of(label).isVisible()
    assert gui.messages == []


def test_clearing_is_whole_at_the_idle_frost(gui):
    """Idle frost already reaches some titles (the corners), so a Clearing
    is all there at idleMax; it can be, because it paints in the ground."""
    gui.daemon.set_state(cpu_temp=40.0, gpu_temp=38.0)
    spin(600)
    ambient = gui.singleton("Ambient")
    assert ambient.property("frostAmount") == pytest.approx(ambient.property("idleMax"))
    title = section_titles(find(gui, "scroller"))["POWER MODES"]
    assert clearing_of(title).property("opacity") == pytest.approx(1.0)


# -- colour -------------------------------------------------------------------

def _grab(gui):
    spin(60)
    image = gui.window.grabWindow()
    assert not image.isNull()
    return image


def _dist(a: QColor, b: QColor) -> int:
    return max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue()))


def _eval(gui, obj, expression: str):
    from PySide6.QtQml import QQmlExpression

    value, undefined = QQmlExpression(gui.engine.rootContext(), obj, expression).evaluate()
    assert not undefined, expression
    return value


def _ground(gui, x: float, y: float) -> QColor:
    return QColor(_eval(gui, find(gui, "backdrop"), f"colourAt({x}, {y})"))


def test_ground_colour_matches_the_backdrop_as_drawn(gui):
    """Backdrop.colourAt is the colour the washes really leave, so a
    Clearing over a wash shows no patch. Checked in the side margins, where
    nothing but the backdrop is drawn while there is no frost."""
    prefs, theme = gui.singleton("Prefs"), gui.singleton("Theme")
    gui.daemon.set_state(cpu_temp=90.0, gpu_temp=80.0)        # no frost, hot washes
    spin(600)
    assert gui.singleton("Ambient").property("frostAmount") == pytest.approx(0.0)
    for style in ("cryo", "glacier"):
        prefs.setProperty("style", style)
        image = _grab(gui)
        for x, y in ((6, 40), (6, 220), (6, 520), (474, 120), (474, 300), (474, 700)):
            drawn = image.pixelColor(x, y)
            assert _dist(drawn, _ground(gui, x, y)) <= 3, (style, x, y, drawn.name())
        # away from both washes the ground is the plain window background
        far = _ground(gui, 6, 20000)
        assert far.name() == QColor(theme.property("bg")).name()
    assert gui.messages == []


def test_behind_a_title_the_frost_is_gone_at_the_held_amount(gui):
    """Pixel check (software frost image): at the held frost the strip just
    above the capitals of every visible home title is the ground colour,
    and at least one of those strips is frosted with the Clearing off."""
    hold_guard(gui)
    titles = [t for t in section_titles(find(gui, "scroller")).values() if t.isVisible()]

    def strips(image) -> list:
        out = []
        for t in titles:
            clearing = clearing_of(t)
            top_left = t.mapToScene(QPointF(0, 0))
            y = round(top_left.y()) + 1                       # above the capitals
            if not 0 <= y < image.height():
                continue
            xs = range(round(top_left.x()), round(top_left.x() + t.property("contentWidth")))
            ref = QColor(clearing.property("color"))
            out.append((t.property("text"), max(_dist(image.pixelColor(x, y), ref) for x in xs)))
        return out

    on = strips(_grab(gui))
    assert len(on) >= 3
    for text, worst in on:
        assert worst <= 4, (text, worst)
    for t in titles:
        clearing_of(t).setProperty("active", False)
    off = strips(_grab(gui))
    assert max(worst for _, worst in off) > 20, off   # the frost really was there
    for t in titles:
        clearing_of(t).setProperty("active", True)
    assert gui.messages == []


# -- keycaps -------------------------------------------------------------------

def test_gear_and_close_are_backed_keycaps(gui):
    gear = find(gui, "settingsButton")
    open_settings(gui)
    close = find(gui, "settingsClose")
    theme = gui.singleton("Theme")
    for button in (gear, close):
        assert button.property("backed") is True
        cap = next(k for k in button.childItems() if k.objectName() == "keycap")
        assert cap.property("radius") == pytest.approx(button.width() / 2)
        assert QColor(cap.property("color")).name() == QColor(theme.property("panel")).name()
        border = _eval(gui, cap, "border.color")
        assert QColor(border).name() == QColor(theme.property("panelBorder")).name()
        # hit area unchanged: size + 12 square
        assert button.width() == pytest.approx(button.property("size") + 12)
        assert button.height() == pytest.approx(button.property("size") + 12)
    assert gui.messages == []
