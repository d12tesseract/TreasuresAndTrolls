"""Editable SVG walls and feature symbols for ASCII dungeon maps."""

import math
import random
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from dungeon_geometry import (
    Cell, DIAGONALS, DIRECTIONS, DOORS, DungeonMap, FEATURES, FLOORS, Point,
    _door_axis, _finite_positive, _neighbors, _open_sides, _partition,
    _rough_cells, _stair_runs, validate_map,
)


SVG_NAMESPACE = "http://www.w3.org/2000/svg"


@dataclass(frozen=True)
class _Edge:
    start: Point
    end: Point
    rough: bool
    inward: Point


def _wall_edges(grid: DungeonMap) -> List[_Edge]:
    rough = _rough_cells(grid)
    edges = []
    for y, row in enumerate(grid.rows):
        for x, tile in enumerate(row):
            if tile in DIAGONALS:
                natural = (x, y) in rough
                sides = _open_sides(grid, x, y)
                inward = tuple(
                    sum(DIRECTIONS[side][axis] for side in sides) / math.sqrt(2)
                    for axis in (0, 1)
                ) if natural else (0, 0)
                if tile == "\\":
                    edges.append(_Edge((x, y), (x + 1, y + 1), natural, inward))
                else:
                    edges.append(_Edge((x, y + 1), (x + 1, y), natural, inward))
            elif tile in FLOORS:
                endpoints = (
                    ((x, y), (x + 1, y)),
                    ((x + 1, y), (x + 1, y + 1)),
                    ((x, y + 1), (x + 1, y + 1)),
                    ((x, y), (x, y + 1)),
                )
                for side, (start, end) in enumerate(endpoints):
                    dx, dy = DIRECTIONS[side]
                    boundary = (side + 2) % 4 not in _open_sides(
                        grid, x + dx, y + dy
                    )
                    forced = (side == 3 and tile in "|L") or (
                        side == 2 and tile in "_L"
                    )
                    if boundary or forced:
                        edges.append(
                            _Edge(start, end, (x, y) in rough and not forced, (-dx, -dy))
                        )
    return edges


def svg_document(
    grid: DungeonMap,
    feet_per_pixel: float = 10,
    feet_per_inch: float = 50,
    line_width: float = 0.01,
    seed: int = 0,
    roughness: float = 0.12,
    rough_segments: int = 6,
    player_view: bool = False,
    corner_radius: Optional[float] = None,
    encounter_labels: Optional[Dict[Cell, str]] = None,
) -> str:
    """Render a validated map with independently editable black wall segments."""
    validate_map(grid)
    for name, value in (
        ("feet_per_pixel", feet_per_pixel),
        ("feet_per_inch", feet_per_inch),
        ("line_width", line_width),
    ):
        _finite_positive(name, value)
    if not math.isfinite(roughness) or not 0 <= roughness <= 0.2:
        raise ValueError("roughness must be between zero and 0.2 map squares")
    if not isinstance(rough_segments, int) or not 2 <= rough_segments <= 32:
        raise ValueError("rough_segments must be an integer between 2 and 32")
    if corner_radius is not None and (
        not math.isfinite(corner_radius) or not 0 <= corner_radius <= 0.5
    ):
        raise ValueError("corner_radius must be between zero and 0.5 map squares")
    radius = min(0.35, roughness * 3) if corner_radius is None else corner_radius
    inches_per_square = feet_per_pixel / feet_per_inch
    _finite_positive("map scale", inches_per_square)
    stroke = line_width / inches_per_square
    physical_width = grid.width * inches_per_square + line_width
    physical_height = grid.height * inches_per_square + line_width
    for value in (stroke, physical_width, physical_height,
                  grid.width + stroke, grid.height + stroke):
        _finite_positive("SVG dimension", value)
    fmt = lambda value: format(value, ".12g")
    root = ET.Element("svg", {
        "xmlns": SVG_NAMESPACE,
        "width": fmt(physical_width) + "in",
        "height": fmt(physical_height) + "in",
        "viewBox": " ".join(map(fmt, (
            -stroke / 2, -stroke / 2, grid.width + stroke, grid.height + stroke,
        ))),
    })
    walls = ET.SubElement(root, "g", {"id": "walls"})
    symbols = ET.SubElement(root, "g", {"id": "features"})

    def line(parent, start, end, texture="smooth"):
        return ET.SubElement(parent, "line", {
            "x1": fmt(start[0]), "y1": fmt(start[1]),
            "x2": fmt(end[0]), "y2": fmt(end[1]),
            "stroke": "black", "stroke-width": fmt(stroke),
            "stroke-linecap": "round", "data-texture": texture,
        })

    edges = _wall_edges(grid)
    incident = defaultdict(list)
    for edge in edges:
        incident[edge.start].append(edge)
        incident[edge.end].append(edge)
    joins = {}
    rounded_ends = {}
    rng = random.Random(seed)
    for point, touching in incident.items():
        if roughness and len(touching) == 2 and touching[0].rough != touching[1].rough:
            smooth = next(edge for edge in touching if not edge.rough)
            shifted = (
                point[0] + roughness * smooth.inward[0],
                point[1] + roughness * smooth.inward[1],
            )
            joins[point] = shifted
            line(walls, point, shifted, "transition")
        elif radius and len(touching) == 2 and all(edge.rough for edge in touching):
            directions = []
            for edge in touching:
                other = edge.end if edge.start == point else edge.start
                directions.append((other[0] - point[0], other[1] - point[1]))
            if directions[0][0] * directions[1][1] == directions[0][1] * directions[1][0]:
                continue
            if directions[0][0] * directions[1][0] + directions[0][1] * directions[1][1]:
                continue
            # At radius 0.5, neighboring quarter circles meet at tile-edge
            # midpoints, replacing an isolated square's entire boundary.
            first, last = [
                (point[0] + radius * dx, point[1] + radius * dy)
                for dx, dy in directions
            ]
            rounded_ends[(touching[0], point)] = first
            rounded_ends[(touching[1], point)] = last
            center = (
                point[0] + radius * (directions[0][0] + directions[1][0]),
                point[1] + radius * (directions[0][1] + directions[1][1]),
            )
            previous = first
            steps = max(6, rough_segments)
            for step in range(1, steps + 1):
                angle = math.pi * step / (2 * steps)
                radial = radius
                if step < steps and roughness:
                    offset = rng.uniform(-roughness, roughness) * math.sin(2 * angle) ** 2
                    # Bound radial jitter to this corner's square so it cannot
                    # cross neighboring arcs or extend beyond the map.
                    radial = min(
                        radius / max(math.cos(angle), math.sin(angle)),
                        max(radius * 0.65, radius + offset),
                    )
                following = last if step == steps else (
                    center[0] - radial * (
                        directions[1][0] * math.cos(angle) + directions[0][0] * math.sin(angle)
                    ),
                    center[1] - radial * (
                        directions[1][1] * math.cos(angle) + directions[0][1] * math.sin(angle)
                    ),
                )
                line(walls, previous, following, "rough")
                previous = following
    for edge in edges:
        if not edge.rough:
            line(walls, edge.start, edge.end)
            continue
        start = rounded_ends.get((edge, edge.start), joins.get(edge.start, edge.start))
        end = rounded_ends.get((edge, edge.end), joins.get(edge.end, edge.end))
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if not length:
            continue
        if not roughness:
            line(walls, start, end, "rough")
            continue
        # Fade jitter on the shrinking straight remainder near maximum
        # rounding, rather than leaving spikes between almost-touching arcs.
        amplitude = roughness * min(1, length / 0.3)
        points = [start]
        for step in range(1, rough_segments):
            t = step / rough_segments
            offset = rng.uniform(-amplitude, amplitude) * math.sin(math.pi * t) ** 2
            points.append((
                min(grid.width, max(0, start[0] * (1 - t) + end[0] * t
                                    + edge.inward[0] * offset)),
                min(grid.height, max(0, start[1] * (1 - t) + end[1] * t
                                     + edge.inward[1] * offset)),
            ))
        points.append(end)
        for first, second in zip(points, points[1:]):
            line(walls, first, second, "rough")

    def label(parent, text, x=0.5, y=0.61, size=0.32):
        element = ET.SubElement(parent, "text", {
            "x": fmt(x), "y": fmt(y), "font-family": "sans-serif",
            "font-size": fmt(size), "text-anchor": "middle", "fill": "black",
        })
        element.text = text

    def rectangle(parent, x, y, width, height, dashed=False):
        attributes = {
            "x": fmt(x), "y": fmt(y), "width": fmt(width), "height": fmt(height),
            "fill": "none", "stroke": "black", "stroke-width": fmt(stroke),
        }
        if dashed:
            attributes["stroke-dasharray"] = "0.08 0.06"
        ET.SubElement(parent, "rect", attributes)

    stair_runs = _stair_runs(grid)
    for y, row in enumerate(grid.rows):
        for x, tile in enumerate(row):
            if tile not in FEATURES or (player_view and tile in "TP"):
                continue
            run = stair_runs.get((x, y))
            if run and (x, y) != run.cells[0]:
                continue
            if tile in DOORS:
                axis = _door_axis(_neighbors(grid, x, y))
                if player_view and tile in "SC":
                    endpoints = (
                        ((x, y + 0.5), (x + 1, y + 0.5)) if axis == "NS"
                        else ((x + 0.5, y), (x + 0.5, y + 1))
                    )
                    line(walls, *endpoints)
                    continue
                group = ET.SubElement(symbols, "g", {
                    "data-tile": tile,
                    "transform": "translate({} {}){}".format(
                        x, y, " rotate(90 .5 .5)" if axis == "EW" else ""
                    ),
                })
                line(group, (0, 0.5), (0.15, 0.5))
                line(group, (0.85, 0.5), (1, 0.5))
                rectangle(group, 0.15, 0.38, 0.7, 0.24)
                if tile != "D":
                    label(group, tile, y=0.61, size=0.28)
                continue
            group = ET.SubElement(symbols, "g", {
                "data-tile": tile, "transform": "translate({} {})".format(x, y),
            })
            length = len(run.cells) if run else 1
            if length > 1:
                group.set("data-length", str(length))
            if tile == "T":
                line(group, (0.18, 0.18), (0.82, 0.82))
                line(group, (0.18, 0.82), (0.82, 0.18))
                label(group, "T", x=0.82, y=0.28, size=0.24)
            elif tile == "P":
                rectangle(group, 0.16, 0.16, 0.68, 0.68, dashed=True)
                label(group, "P")
            else:
                open_neighbors = [
                    (side + 2) % 4 in _open_sides(
                        grid, x + DIRECTIONS[side][0], y + DIRECTIONS[side][1]
                    ) and not _partition(grid, x, y, side)
                    for side in range(4)
                ]
                horizontal = (
                    open_neighbors[1] and open_neighbors[3]
                    and not (open_neighbors[0] and open_neighbors[2])
                ) or (
                    (open_neighbors[1] or open_neighbors[3])
                    and not (open_neighbors[0] or open_neighbors[2])
                )
                if run:
                    horizontal = run.horizontal
                transform = "rotate(90 .5 .5)" if horizontal else "rotate(0)"
                if horizontal and length > 1:
                    transform = "translate({} 0) rotate(90)".format(length)
                drawing = ET.SubElement(group, "g", {
                    "transform": transform,
                })
                if tile in "EU":
                    for index in range(5 * length):
                        half_width = 0.14 + index * 0.18 / (5 * length - 1)
                        ordinate = 0.2 + index * (length - 0.44) / (5 * length - 1)
                        line(drawing, (0.42 - half_width, ordinate),
                             (0.42 + half_width, ordinate))
                else:
                    line(drawing, (0.28, 0.18), (0.12, length - 0.18))
                    line(drawing, (0.56, 0.18), (0.72, length - 0.18))
                tip, tail = (0.18, length - 0.18) if tile in "ER" else (length - 0.18, 0.18)
                line(drawing, (0.42, tail), (0.42, tip))
                back = tip + (0.12 if tip < tail else -0.12)
                line(drawing, (0.32, back), (0.42, tip))
                line(drawing, (0.52, back), (0.42, tip))
                label(group, tile, x=length - 0.14 if horizontal else 0.86,
                      y=0.6, size=0.26)
    if encounter_labels:
        encounters = ET.SubElement(root, "g", {"id": "encounters"})
        for (x, y), number in encounter_labels.items():
            if grid.tile(x, y) not in " .TP":
                raise ValueError("encounter labels must be on chamber floor")
            group = ET.SubElement(encounters, "g", {
                "data-area": str(number), "data-column": str(x + 1), "data-row": str(y + 1),
                "transform": "translate({} {})".format(x, y),
            })
            occupied = grid.tile(x, y) in "TP"
            label(group, str(number), y=0.14 if occupied else 0.66,
                  size=min(0.22 if occupied else 0.46, 0.8 / max(1, len(str(number)))))
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    ) + "\n"


def render_rows(rows: Sequence[str], **options) -> str:
    """Convenience API for an array of row strings instead of a text file."""
    return svg_document(DungeonMap(tuple(rows)), **options)
