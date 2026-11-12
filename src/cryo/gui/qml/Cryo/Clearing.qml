import QtQuick

// The frost melted back around a label that sits straight on the backdrop
// (section titles, the header subtitles, the dGPU row, Frost's footer
// line), so it reads over the ice in every frost state.
//
// Put it inside the Text it backs: `Label { text: ...; Clearing {} }`. It
// covers the painted text (contentWidth x contentHeight, wherever the
// alignment puts it; inside any other Item, the whole item) plus `padX` /
// `padY` fully, and fades out over `featherX` / `featherY` beyond that on a
// soft curve with a long tail, so it reads as a halo and never shows an
// edge. It is a child at z -1: drawn
// below its label and above everything painted before it (the backdrop and
// the frost; a sibling it reaches under that must stay on top takes z 1).
// It takes no part in layout: a child never changes its parent's implicit
// size.
//
// It paints in the ground the window shows at that spot before the frost
// (Theme.bg with the backdrop washes over it, Backdrop.colourAt), so with
// no frost behind a label there is nothing to see, over a wash or not; with
// frost behind it, the ice thins out around the lettering. Its opacity
// follows Ambient.frostAmount (see `startAt`, `fullAt`): 0, and not drawn,
// with no frost or with effects off.
//
// Software renderer safe (a Canvas, no shader). Static: it paints only when
// its size or its ground colour changes (rounded to 8 bits, so scrolling
// repaints it only where the washes shade by a step); following the frost
// changes only its opacity.
Canvas {
    id: clearing

    // Fully clear margin around the painted text, then the fade.
    property real padX: 2
    property real padY: 0
    property real featherX: 40
    property real featherY: 18
    // Off: not drawn (a label whose neighbour's Clearing already backs it).
    property bool active: true
    // Eases in (smoothstep) as frostAmount goes from `startAt` to `fullAt`:
    // whole before the idle frost (idleMax 0.48) and the dormant one (0.42),
    // so it is all there wherever ice can be.
    property real startAt: 0.0
    property real fullAt: 0.36
    readonly property real strength: {
        const k = Math.max(0, Math.min(1, (Ambient.frostAmount - startAt) / (fullAt - startAt)))
        return k * k * (3 - 2 * k)
    }

    // The Flickable it scrolls with (the page), if any.
    function scroller() {
        for (let p = parent; p; p = p.parent) {
            if (p.contentY !== undefined && p.contentItem !== undefined)
                return p
        }
        return null
    }
    // The ground under its centre, followed through scrolling, relayout and
    // resizes (the reads of the scroller below are what re-run it). Only
    // worked out while it shows.
    readonly property color ground: {
        const b = Ambient.backdrop
        if (!b || !visible)
            return Theme.bg
        const f = scroller()
        if (f)
            void (f.contentY + f.contentHeight + f.width + f.height)
        const at = mapToItem(null, width / 2, height / 2)
        return b.colourAt(at.x, at.y)
    }
    property color color: ground

    readonly property Item label: parent
    // A Text parent: its painted text. Any other Item: the whole item.
    readonly property bool isText: label !== null && label.contentWidth !== undefined
                                   && label.effectiveHorizontalAlignment !== undefined
    // The painted text box in the label's coordinates.
    readonly property real textW: !label ? 0
                                  : isText ? Math.max(0, Math.min(label.width, label.contentWidth)) : label.width
    readonly property real textH: !label ? 0
                                  : isText ? Math.max(0, Math.min(label.height, label.contentHeight)) : label.height
    readonly property real textX: {
        if (!isText)
            return 0
        const room = label.width - textW
        const a = label.effectiveHorizontalAlignment
        return a === Text.AlignRight ? room : a === Text.AlignHCenter ? room / 2 : 0
    }

    z: -1
    enabled: false
    x: Math.round(textX - padX - featherX)
    y: Math.round(-padY - featherY)
    width: Math.round(textW + 2 * (padX + featherX))
    height: Math.round(textH + 2 * (padY + featherY))
    opacity: strength
    visible: active && strength > 0.004 && textW > 0

    // The fade, sampled: alpha by distance out from the core (0..1).
    readonly property var profile: {
        const out = []
        const n = 12
        for (let i = 0; i <= n; i++) {
            const u = i / n
            out.push([u, (1 - u) * (1 - u) * (1 + 2 * u) * (1 - 0.35 * u)])
        }
        return out
    }

    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onColorChanged: requestPaint()
    onVisibleChanged: if (visible) requestPaint()

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        const w = Math.round(width), h = Math.round(height)
        const fx = Math.round(featherX), fy = Math.round(featherY)
        if (w <= 2 * fx || h <= 2 * fy)
            return
        const c = clearing.color
        const ink = a => Qt.rgba(c.r, c.g, c.b, a)
        const stops = g => {
            for (const s of clearing.profile)
                g.addColorStop(s[0], ink(s[1]))
            return g
        }
        // core (text plus pad), opaque
        const x0 = fx, y0 = fy, x1 = w - fx, y1 = h - fy
        ctx.fillStyle = ink(1)
        ctx.fillRect(x0, y0, x1 - x0, y1 - y0)
        // the four sides: linear fades outward from the core
        ctx.fillStyle = stops(ctx.createLinearGradient(x0, 0, 0, 0))
        ctx.fillRect(0, y0, fx, y1 - y0)
        ctx.fillStyle = stops(ctx.createLinearGradient(x1, 0, w, 0))
        ctx.fillRect(x1, y0, fx, y1 - y0)
        ctx.fillStyle = stops(ctx.createLinearGradient(0, y0, 0, 0))
        ctx.fillRect(x0, 0, x1 - x0, fy)
        ctx.fillStyle = stops(ctx.createLinearGradient(0, y1, 0, h))
        ctx.fillRect(x0, y1, x1 - x0, fy)
        // the four corners: elliptical fades around the core's corners (a
        // unit radial gradient scaled to fx by fy), so the field is
        // continuous with the sides and shows no seam
        for (const p of [[x0, y0, -1, -1], [x1, y0, 0, -1], [x0, y1, -1, 0], [x1, y1, 0, 0]]) {
            ctx.save()
            ctx.translate(p[0], p[1])
            ctx.scale(fx, fy)
            ctx.fillStyle = stops(ctx.createRadialGradient(0, 0, 0, 0, 0, 1))
            ctx.fillRect(p[2], p[3], 1, 1)
            ctx.restore()
        }
    }
}
