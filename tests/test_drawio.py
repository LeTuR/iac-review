from __future__ import annotations

import xml.etree.ElementTree as ET

from iac_review.core.drawio import render
from iac_review.core.model import Diagram, Edge, Node


def _cells(xml: str) -> list[ET.Element]:
    return list(ET.fromstring(xml).iter("mxCell"))


def test_mapped_node_uses_the_azure_shape() -> None:
    diagram = Diagram(
        nodes=(Node("a", "state", "azurerm_storage_account", "img/lib/azure2/storage/x.svg"),)
    )
    xml = render(diagram)
    cell = next(c for c in _cells(xml) if c.get("id") == "a")
    assert "image=img/lib/azure2/storage/x.svg" in cell.get("style", "")
    assert cell.get("value") == "state<br>azurerm_storage_account"


def test_unmapped_node_degrades_to_a_labelled_generic_shape() -> None:
    xml = render(Diagram(nodes=(Node("b", "thing", "azurerm_unknown_thing"),)))
    cell = next(c for c in _cells(xml) if c.get("id") == "b")
    assert "image=" not in cell.get("style", "")
    assert "dashed=1" in cell.get("style", "")
    assert "azurerm_unknown_thing" in cell.get("value", "")


def test_edges_are_rendered_between_nodes() -> None:
    diagram = Diagram(nodes=(Node("a", "a", "t"), Node("b", "b", "t")), edges=(Edge("a", "b"),))
    xml = render(diagram)
    edge = next(c for c in _cells(xml) if c.get("edge") == "1")
    assert (edge.get("source"), edge.get("target")) == ("a", "b")


def test_nodes_are_grouped_into_containers() -> None:
    diagram = Diagram(
        nodes=(Node("a", "a", "t", group="rg-one"), Node("b", "b", "t", group="rg-two"))
    )
    cells = _cells(render(diagram))
    groups = [c.get("value") for c in cells if (c.get("id") or "").startswith("group-")]
    assert groups == ["rg-one", "rg-two"]
    assert next(c for c in cells if c.get("id") == "a").get("parent") == "group-0"


def test_output_is_a_well_formed_mxfile() -> None:
    root = ET.fromstring(render(Diagram(title="Platform", nodes=(Node("a", "a", "t"),))))
    assert root.tag == "mxfile"
    page = root.find("diagram")
    assert page is not None
    assert page.get("name") == "Platform"
