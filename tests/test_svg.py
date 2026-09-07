"""The displayable artifact: a picture that is also its own drawio source."""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

from iac_review.core import layout
from iac_review.core.drawio import render as render_drawio
from iac_review.core.model import Diagram, Edge, Node
from iac_review.core.svg import render

SVG_NS = "{http://www.w3.org/2000/svg}"
ICON = "img/lib/azure2/storage/Storage_Accounts.svg"
PAYLOAD = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    b'<rect width="10" height="10"/></svg>'
)


class _Icons:
    def __init__(self, known: dict[str, bytes] | None = None) -> None:
        self.known = known if known is not None else {ICON: PAYLOAD}
        self.asked: list[str] = []

    def read(self, reference: str) -> bytes | None:
        self.asked.append(reference)
        return self.known.get(reference)


def _find(root: ET.Element, tag: str) -> list[ET.Element]:
    return list(root.iter(f"{SVG_NS}{tag}"))


def _diagram() -> Diagram:
    return Diagram(
        title="Platform",
        nodes=(
            Node("a", "state", "azurerm_storage_account", ICON, group="platform"),
            Node("b", "tfstate", "azurerm_storage_container", None, group="platform"),
        ),
        edges=(Edge("b", "a"),),
    )


def test_the_drawio_source_travels_in_the_content_attribute() -> None:
    diagram = _diagram()
    source = render_drawio(diagram)
    root = ET.fromstring(render(diagram, source, _Icons()))
    assert root.tag == f"{SVG_NS}svg"
    assert root.get("content") == source, "the embedded source must be the drawio file itself"
    assert ET.fromstring(root.get("content") or "").tag == "mxfile"


def test_a_mapped_node_embeds_its_icon_as_a_data_uri() -> None:
    root = ET.fromstring(render(_diagram(), "<mxfile/>", _Icons()))
    images = _find(root, "image")
    assert len(images) == 1
    href = images[0].get("href") or ""
    assert href.startswith("data:image/svg+xml;base64,")
    assert base64.b64decode(href.split(",", 1)[1]) == PAYLOAD


def test_an_unmapped_node_degrades_to_a_labelled_box() -> None:
    root = ET.fromstring(render(_diagram(), "<mxfile/>", _Icons()))
    dashed = [r for r in _find(root, "rect") if r.get("stroke") == "#9E9E9E"]
    assert len(dashed) == 1, "the unmapped node is drawn, not dropped"
    labels = {t.text for t in _find(root, "text")}
    assert "tfstate" in labels
    assert "azurerm_storage_container" in labels


def test_an_icon_that_cannot_be_resolved_still_renders() -> None:
    root = ET.fromstring(render(_diagram(), "<mxfile/>", _Icons(known={})))
    assert _find(root, "image") == []
    assert len([r for r in _find(root, "rect") if r.get("stroke") == "#9E9E9E"]) == 2
    assert "state" in {t.text for t in _find(root, "text")}


def test_no_icon_source_at_all_is_not_an_error() -> None:
    root = ET.fromstring(render(_diagram(), "<mxfile/>", None))
    assert _find(root, "image") == []


def test_edges_are_drawn_with_an_arrow_head() -> None:
    root = ET.fromstring(render(_diagram(), "<mxfile/>", _Icons()))
    lines = _find(root, "line")
    assert len(lines) == 1
    assert lines[0].get("marker-end") == "url(#arrow)"
    assert _find(root, "marker")[0].get("id") == "arrow"


def test_an_edge_stops_at_the_box_rather_than_the_centre() -> None:
    root = ET.fromstring(render(_diagram(), "<mxfile/>", _Icons()))
    line = _find(root, "line")[0]
    x1, x2 = float(line.get("x1") or 0), float(line.get("x2") or 0)
    assert x1 != x2, "the two nodes sit side by side, so the edge is horizontal"
    # The two icons are one grid cell apart; clipping removes half an icon at
    # each end, so the drawn line is shorter than centre-to-centre by exactly
    # one icon width.
    assert abs(x1 - x2) == layout.CELL_W - layout.ICON


def test_groups_are_drawn_and_named() -> None:
    root = ET.fromstring(render(_diagram(), "<mxfile/>", _Icons()))
    assert "platform" in {t.text for t in _find(root, "text")}
    assert [r for r in _find(root, "rect") if r.get("stroke") == "#0078D4"]


def test_the_canvas_is_painted_so_it_reads_in_a_dark_viewer() -> None:
    root = ET.fromstring(render(_diagram(), "<mxfile/>", _Icons()))
    assert (_find(root, "rect")[0]).get("fill") == "#FFFFFF"


def test_long_labels_are_truncated_rather_than_overflowing() -> None:
    diagram = Diagram(nodes=(Node("a", "x" * 60, "y" * 60, None),))
    labels = [
        t.text or ""
        for t in ET.fromstring(render(diagram, "<mxfile/>")).iter()
        if t.tag == f"{SVG_NS}text"
    ]
    assert any(text.endswith("…") for text in labels)
    assert all(len(text) <= 30 for text in labels)


def test_an_empty_diagram_still_produces_a_valid_document() -> None:
    root = ET.fromstring(render(Diagram(), "<mxfile/>"))
    assert root.tag == f"{SVG_NS}svg"
    assert int(root.get("width") or 0) > 0
