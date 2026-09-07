"""Render a :class:`~iac_review.core.model.Diagram` as a drawio file.

This module knows the drawio file format and nothing else. Which icon a node
gets is decided by the provider that produced the node, so an AWS provider would
reuse this renderer unchanged. Positions come from
:mod:`iac_review.core.layout`, shared with the SVG renderer.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom

from iac_review.core.layout import Box, Layout, place
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


def label(node: Node) -> str:
    """drawio renders cell values as HTML when the style sets ``html=1``."""
    return f"{node.label}<br>{node.kind}" if node.kind else node.label


def render(diagram: Diagram, layout: Layout | None = None) -> str:
    """Return the diagram as pretty-printed, uncompressed drawio XML."""
    placed = layout or place(diagram)
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

    for group in placed.groups:
        _vertex(root, group.id, group.label, GROUP_STYLE, group.box, parent="1")
        for node in (n for n in placed.nodes if n.group_id == group.id):
            style = ICON_STYLE.format(icon=node.node.icon) if node.node.icon else UNMAPPED_STYLE
            _vertex(
                root, node.node.id, label(node.node), style, node.relative, parent=node.group_id
            )

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
    root: ET.Element, cell_id: str, value: str, style: str, box: Box, *, parent: str
) -> None:
    cell = ET.SubElement(
        root,
        "mxCell",
        {"id": cell_id, "value": value, "style": style, "vertex": "1", "parent": parent},
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        {
            "x": str(box.x),
            "y": str(box.y),
            "width": str(box.width),
            "height": str(box.height),
            "as": "geometry",
        },
    )
