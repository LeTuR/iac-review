"""Where the boxes go.

Both renderers - the drawio file and the displayable SVG - place nodes from this
one module, so the picture a reviewer sees and the diagram they reopen in drawio
cannot drift apart.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from iac_review.core.model import Diagram, Node

ICON = 68
CELL_W, CELL_H = 150, 110
COLUMNS = 4
PAD_X, PAD_TOP, PAD_BOTTOM = 24, 40, 16
MARGIN = 40


@dataclass(frozen=True, slots=True)
class Box:
    x: int
    y: int
    width: int
    height: int

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


@dataclass(frozen=True, slots=True)
class PlacedNode:
    node: Node
    group_id: str
    relative: Box
    """Position within the group, which is what the drawio format stores."""
    absolute: Box
    """Position on the page, which is what a standalone SVG needs."""


@dataclass(frozen=True, slots=True)
class PlacedGroup:
    id: str
    label: str
    box: Box


@dataclass(frozen=True, slots=True)
class Layout:
    groups: tuple[PlacedGroup, ...] = ()
    nodes: tuple[PlacedNode, ...] = ()

    @property
    def width(self) -> int:
        return max((g.box.x + g.box.width for g in self.groups), default=0) + MARGIN

    @property
    def height(self) -> int:
        return max((g.box.y + g.box.height for g in self.groups), default=0) + MARGIN

    def by_id(self, node_id: str) -> PlacedNode | None:
        return next((placed for placed in self.nodes if placed.node.id == node_id), None)


def place(diagram: Diagram) -> Layout:
    """Lay the diagram out: one dashed container per group, a grid of icons inside."""
    grouped: OrderedDict[str, list[Node]] = OrderedDict()
    for node in diagram.nodes:
        grouped.setdefault(node.group or diagram.title, []).append(node)

    groups: list[PlacedGroup] = []
    nodes: list[PlacedNode] = []
    y = MARGIN

    for index, (label, members) in enumerate(grouped.items()):
        rows = (len(members) + COLUMNS - 1) // COLUMNS
        box = Box(
            x=MARGIN,
            y=y,
            width=PAD_X * 2 + min(len(members), COLUMNS) * CELL_W,
            height=PAD_TOP + rows * CELL_H + PAD_BOTTOM,
        )
        group_id = f"group-{index}"
        groups.append(PlacedGroup(group_id, label, box))

        for position, node in enumerate(members):
            column, row = position % COLUMNS, position // COLUMNS
            relative = Box(
                x=PAD_X + column * CELL_W + (CELL_W - ICON) // 2,
                y=PAD_TOP + row * CELL_H,
                width=ICON,
                height=ICON,
            )
            nodes.append(
                PlacedNode(
                    node=node,
                    group_id=group_id,
                    relative=relative,
                    absolute=Box(box.x + relative.x, box.y + relative.y, ICON, ICON),
                )
            )
        y += box.height + MARGIN

    return Layout(tuple(groups), tuple(nodes))
