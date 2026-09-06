"""Render a :class:`~iac_review.core.model.Diagram` as a drawio file.

This module knows the drawio file format and nothing else. Which icon a node
gets is decided by the provider that produced the node, so an AWS provider would
reuse this renderer unchanged.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import OrderedDict
from xml.dom import minidom

from iac_review.core.model import Diagram, Node

ICON_STYLE = (
    "image;aspect=fixed;html=1;points=[];align=center;fontSize=12;"
    "verticalLabelPosition=bottom;verticalAlign=top;labelBackgroundColor=none;"
    "image={icon}"
)
UNMAPPED_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;dashed=1;fillColor=#F5F5F5;"
    "strokeColor=#9E9E9E;fontColor=#616161;align=center;verticalAlign=middle;"
)
GROUP_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#0078D4;"
    "dashed=1;verticalAlign=top;align=left;spacingLeft=8;fontColor=#0078D4;fontSize=13;"
)
EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;"

_ICON_W, _ICON_H = 68, 68
_CELL_W, _CELL_H = 150, 110
_COLS = 4
_PAD_X, _PAD_TOP, _PAD_BOTTOM = 24, 40, 16


def _label(node: Node) -> str:
    """drawio renders cell values as HTML when the style sets ``html=1``."""
    return f"{node.label}<br>{node.kind}" if node.kind else node.label


def render(diagram: Diagram) -> str:
    """Return the diagram as pretty-printed, uncompressed drawio XML."""
    mxfile = ET.Element("mxfile", {"host": "iac-review", "agent": "iac-review", "type": "device"})
    page = ET.SubElement(mxfile, "diagram", {"id": "iac-review", "name": diagram.title})
    model = ET.SubElement(
        page,
        "mxGraphModel",
        {
            "dx": "1200",
            "dy": "800",
            "grid": "1",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": "1169",
            "pageHeight": "826",
            "math": "0",
            "shadow": "0",
        },
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    groups: OrderedDict[str, list[Node]] = OrderedDict()
    for node in diagram.nodes:
        groups.setdefault(node.group or diagram.title, []).append(node)

    y = 40
    for index, (name, members) in enumerate(groups.items()):
        rows = (len(members) + _COLS - 1) // _COLS
        height = _PAD_TOP + rows * _CELL_H + _PAD_BOTTOM
        width = _PAD_X * 2 + min(len(members), _COLS) * _CELL_W
        group_id = f"group-{index}"
        _vertex(root, group_id, name, GROUP_STYLE, 40, y, width, height, parent="1")
        for position, node in enumerate(members):
            col, row = position % _COLS, position // _COLS
            _vertex(
                root,
                node.id,
                _label(node),
                ICON_STYLE.format(icon=node.icon) if node.icon else UNMAPPED_STYLE,
                _PAD_X + col * _CELL_W + (_CELL_W - _ICON_W) // 2,
                _PAD_TOP + row * _CELL_H,
                _ICON_W,
                _ICON_H,
                parent=group_id,
            )
        y += height + 40

    for number, edge in enumerate(diagram.edges):
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": f"edge-{number}",
                "value": edge.label,
                "style": EDGE_STYLE,
                "edge": "1",
                "parent": "1",
                "source": edge.source,
                "target": edge.target,
            },
        )
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})

    raw = ET.tostring(mxfile, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    return "\n".join(line for line in pretty.splitlines() if line.strip()) + "\n"


def _vertex(
    root: ET.Element,
    cell_id: str,
    value: str,
    style: str,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    parent: str,
) -> None:
    cell = ET.SubElement(
        root,
        "mxCell",
        {"id": cell_id, "value": value, "style": style, "vertex": "1", "parent": parent},
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        {"x": str(x), "y": str(y), "width": str(width), "height": str(height), "as": "geometry"},
    )
