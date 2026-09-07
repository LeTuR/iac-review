"""Render a diagram as a ``.drawio.svg`` - a picture that is also its own source.

A raw ``.drawio`` file displays nowhere: not in a pull request, not in a file
browser. This emits one artifact that does both jobs. It draws normally wherever
SVG renders, and the drawio XML travels in the root element's ``content``
attribute, which is how drawio itself marks an editable SVG, so opening the file
in drawio reopens the real diagram rather than a picture of one.

Icons are embedded as data URIs. The paths inside ``content`` stay
drawio-relative, because drawio resolves those itself when the file is reopened.
"""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

from iac_review.core.layout import Box, Layout, PlacedNode, place
from iac_review.core.model import Diagram, IconSource

BACKGROUND = "#FFFFFF"
GROUP_STROKE = "#0078D4"
LABEL_COLOR = "#1F1F1F"
KIND_COLOR = "#616161"
UNMAPPED_FILL = "#F5F5F5"
UNMAPPED_STROKE = "#9E9E9E"
EDGE_COLOR = "#7A7A7A"
FONT = "Helvetica,Arial,sans-serif"

_LABEL_CHARS = 24
_KIND_CHARS = 28


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _data_uri(payload: bytes) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(payload).decode("ascii")


def _clip(box: Box, dx: float, dy: float) -> float:
    """Fraction of the centre-to-centre vector at which it leaves ``box``."""
    candidates = []
    if dx:
        candidates.append((box.width / 2) / abs(dx))
    if dy:
        candidates.append((box.height / 2) / abs(dy))
    return min(candidates) if candidates else 0.0


def render(diagram: Diagram, source: str, icons: IconSource | None = None) -> str:
    """Return an SVG carrying ``source`` (the drawio XML) as its editable content."""
    layout = place(diagram)
    width, height = max(layout.width, 200), max(layout.height, 160)

    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "xmlns:xlink": "http://www.w3.org/1999/xlink",
            "version": "1.1",
            "width": str(width),
            "height": str(height),
            "viewBox": f"0 0 {width} {height}",
            "content": source,
        },
    )
    ET.SubElement(svg, "title").text = diagram.title
    _defs(svg)
    ET.SubElement(
        svg,
        "rect",
        {"x": "0", "y": "0", "width": str(width), "height": str(height), "fill": BACKGROUND},
    )

    for group in layout.groups:
        ET.SubElement(
            svg,
            "rect",
            {
                "x": str(group.box.x),
                "y": str(group.box.y),
                "width": str(group.box.width),
                "height": str(group.box.height),
                "rx": "6",
                "fill": "none",
                "stroke": GROUP_STROKE,
                "stroke-dasharray": "6 4",
                "stroke-width": "1.5",
            },
        )
        _text(
            svg,
            group.label,
            group.box.x + 10,
            group.box.y + 22,
            size=13,
            color=GROUP_STROKE,
            anchor="start",
        )

    _edges(svg, diagram, layout)
    for placed in layout.nodes:
        _node(svg, placed, icons)

    ET.indent(svg, space="  ")
    return '<?xml version="1.0" ?>\n' + ET.tostring(svg, encoding="unicode") + "\n"


def _defs(svg: ET.Element) -> None:
    defs = ET.SubElement(svg, "defs")
    marker = ET.SubElement(
        defs,
        "marker",
        {
            "id": "arrow",
            "viewBox": "0 0 10 10",
            "refX": "9",
            "refY": "5",
            "markerWidth": "7",
            "markerHeight": "7",
            "orient": "auto-start-reverse",
        },
    )
    ET.SubElement(marker, "path", {"d": "M 0 0 L 10 5 L 0 10 z", "fill": EDGE_COLOR})


def _edges(svg: ET.Element, diagram: Diagram, layout: Layout) -> None:
    for edge in diagram.edges:
        source = layout.by_id(edge.source)
        target = layout.by_id(edge.target)
        if source is None or target is None:
            continue
        a, b = source.absolute, target.absolute
        dx, dy = b.center_x - a.center_x, b.center_y - a.center_y
        if dx == 0 and dy == 0:
            continue
        start_t, end_t = _clip(a, dx, dy), _clip(b, dx, dy)
        ET.SubElement(
            svg,
            "line",
            {
                "x1": f"{a.center_x + dx * start_t:.1f}",
                "y1": f"{a.center_y + dy * start_t:.1f}",
                "x2": f"{b.center_x - dx * end_t:.1f}",
                "y2": f"{b.center_y - dy * end_t:.1f}",
                "stroke": EDGE_COLOR,
                "stroke-width": "1.4",
                "marker-end": "url(#arrow)",
            },
        )


def _node(svg: ET.Element, placed: PlacedNode, icons: IconSource | None) -> None:
    box, node = placed.absolute, placed.node
    payload = icons.read(node.icon) if icons is not None and node.icon else None
    if payload is not None:
        ET.SubElement(
            svg,
            "image",
            {
                "x": str(box.x),
                "y": str(box.y),
                "width": str(box.width),
                "height": str(box.height),
                "href": _data_uri(payload),
                "preserveAspectRatio": "xMidYMid meet",
            },
        )
    else:
        ET.SubElement(
            svg,
            "rect",
            {
                "x": str(box.x),
                "y": str(box.y),
                "width": str(box.width),
                "height": str(box.height),
                "rx": "6",
                "fill": UNMAPPED_FILL,
                "stroke": UNMAPPED_STROKE,
                "stroke-dasharray": "4 3",
            },
        )

    _text(svg, _truncate(node.label, _LABEL_CHARS), box.center_x, box.y + box.height + 15, size=11)
    if node.kind:
        _text(
            svg,
            _truncate(node.kind, _KIND_CHARS),
            box.center_x,
            box.y + box.height + 28,
            size=9,
            color=KIND_COLOR,
        )


def _text(
    svg: ET.Element,
    value: str,
    x: float,
    y: float,
    *,
    size: int,
    color: str = LABEL_COLOR,
    anchor: str = "middle",
) -> None:
    element = ET.SubElement(
        svg,
        "text",
        {
            "x": f"{x:.1f}",
            "y": f"{y:.1f}",
            "font-family": FONT,
            "font-size": str(size),
            "fill": color,
            "text-anchor": anchor,
        },
    )
    element.text = value
