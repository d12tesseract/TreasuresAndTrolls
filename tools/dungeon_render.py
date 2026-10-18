"""Editable SVG walls and feature symbols for ASCII dungeon maps."""

import math
import random
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set

from dungeon_geometry import (
    Cell, DIAGONALS, DIRECTIONS, DOORS, DungeonMap, FEATURES, FLOORS, Point,
    _door_axis, _finite_positive, _neighbors, _open_sides, _partition,
    _paired_doors, _rough_cells, _spiral_runs, _stair_runs, validate_map,
)


SVG_NAMESPACE = "http://www.w3.org/2000/svg"


@dataclass(frozen=True)
class _Edge:
    start: Point
    end: Point
    rough: bool
    inward: Point


def _spiral_center_cells(grid: DungeonMap):
    """Locate three-square spiral centers whose walls need circular outlines."""
    return {
        (min(x for x, y in run.clearance) + 1,
         min(y for x, y in run.clearance) + 1)
        for cell, run in _spiral_runs(grid).items()
        if run.size == 3 and cell == run.cells[0]
    }


def _wall_edges(grid: DungeonMap) -> List[_Edge]:
    """Collect oriented wall boundaries and their inward roughness directions."""
    rough = _rough_cells(grid)
    spiral_centers = _spiral_center_cells(grid)
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
                    if (grid.tile(x + dx, y + dy) == "~"
                            or (x + dx, y + dy) in spiral_centers):
                        continue
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


def _render_dimensions(
    grid, feet_per_pixel, feet_per_inch, line_width, roughness, rough_segments,
    corner_radius,
):
    """Validate rendering options and compute stroke, physical size, and radius."""
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
    return stroke, physical_width, physical_height, radius


def _format(value):
    """Format an SVG coordinate with the renderer's stable numeric precision."""
    return format(value, ".12g")


class _SvgRenderer:
    """Keep drawing primitives, wall state, and feature output on one SVG canvas."""

    def __init__(self, grid, dimensions, roughness, rough_segments, seed):
        """Create ordered wall and feature groups with validated drawing settings."""
        stroke, physical_width, physical_height, radius = dimensions
        self.grid = grid
        self.stroke = stroke
        self.radius = radius
        self.roughness = roughness
        self.rough_segments = rough_segments
        self.seed = seed
        self.root = ET.Element("svg", {
            "xmlns": SVG_NAMESPACE,
            "width": _format(physical_width) + "in",
            "height": _format(physical_height) + "in",
            "viewBox": " ".join(map(_format, (
                -stroke / 2, -stroke / 2, grid.width + stroke, grid.height + stroke,
            ))),
        })
        self.walls = ET.SubElement(self.root, "g", {"id": "walls"})
        self.symbols = ET.SubElement(self.root, "g", {"id": "features"})
        self.clip_voids()

    def clip_voids(self):
        """Exclude void squares from walls and symbols without clipping the border."""
        grid, stroke, fmt = self.grid, self.stroke, _format
        voids = [(x, y) for y, row in enumerate(grid.rows)
                 for x, tile in enumerate(row) if tile == "~"]
        if not voids:
            return
        definitions = ET.SubElement(self.root, "defs")
        clip = ET.SubElement(definitions, "clipPath", {"id": "non-void"})
        boundary = "M {} {} H {} V {} H {} Z".format(
            fmt(-stroke), fmt(-stroke), fmt(grid.width + stroke),
            fmt(grid.height + stroke), fmt(-stroke),
        )
        holes = ["M {} {} h 1 v 1 h -1 Z".format(x, y) for x, y in voids]
        ET.SubElement(clip, "path", {
            "d": " ".join([boundary] + holes),
            "clip-rule": "evenodd", "fill-rule": "evenodd",
        })
        self.walls.set("clip-path", "url(#non-void)")
        self.symbols.set("clip-path", "url(#non-void)")

    def line(self, parent, start, end, texture="smooth"):
        """Append an editable line with the shared stroke and texture metadata."""
        fmt, stroke = _format, self.stroke
        return ET.SubElement(parent, "line", {
            "x1": fmt(start[0]), "y1": fmt(start[1]),
            "x2": fmt(end[0]), "y2": fmt(end[1]),
            "stroke": "black", "stroke-width": fmt(stroke),
            "stroke-linecap": "round", "data-texture": texture,
        })

    def wall_joins(self, edges):
        """Draw transitions and rounded corners in incident-edge insertion order."""
        incident = defaultdict(list)
        for edge in edges:
            incident[edge.start].append(edge)
            incident[edge.end].append(edge)
        joins = {}
        rounded_ends = {}
        self.rng = random.Random(self.seed)
        for point, touching in incident.items():
            if self.roughness and len(touching) == 2 and touching[0].rough != touching[1].rough:
                smooth = next(edge for edge in touching if not edge.rough)
                shifted = (
                    point[0] + self.roughness * smooth.inward[0],
                    point[1] + self.roughness * smooth.inward[1],
                )
                joins[point] = shifted
                self.line(self.walls, point, shifted, "transition")
            elif self.radius and len(touching) == 2 and all(edge.rough for edge in touching):
                self.round_corner(point, touching, rounded_ends)
        return joins, rounded_ends

    def round_corner(self, point, touching, rounded_ends):
        """Trim perpendicular rough edges and draw their connecting quarter circle."""
        radius = self.radius
        directions = []
        for edge in touching:
            other = edge.end if edge.start == point else edge.start
            directions.append((other[0] - point[0], other[1] - point[1]))
        if directions[0][0] * directions[1][1] == directions[0][1] * directions[1][0]:
            return
        if directions[0][0] * directions[1][0] + directions[0][1] * directions[1][1]:
            return
        # At radius 0.5, neighboring quarter circles meet at tile-edge midpoints.
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
        self.corner_arc(first, last, center, directions)

    def corner_arc(self, first, last, center, directions):
        """Draw bounded radial jitter along one quarter-circle corner."""
        radius, roughness = self.radius, self.roughness
        previous = first
        steps = max(6, self.rough_segments)
        for step in range(1, steps + 1):
            angle = math.pi * step / (2 * steps)
            radial = radius
            if step < steps and roughness:
                offset = self.rng.uniform(-roughness, roughness) * math.sin(2 * angle) ** 2
                # Bound radial jitter to this corner's square.
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
            self.line(self.walls, previous, following, "rough")
            previous = following

    def rough_edge(self, edge, joins, rounded_ends):
        """Draw a trimmed rough boundary with jitter fading near rounded ends."""
        grid, roughness = self.grid, self.roughness
        rough_segments = self.rough_segments
        start = rounded_ends.get((edge, edge.start), joins.get(edge.start, edge.start))
        end = rounded_ends.get((edge, edge.end), joins.get(edge.end, edge.end))
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if not length:
            return
        if not roughness:
            self.line(self.walls, start, end, "rough")
            return
        # Fade jitter on the shrinking straight remainder near maximum
        # rounding, rather than leaving spikes between almost-touching arcs.
        amplitude = roughness * min(1, length / 0.3)
        points = [start]
        for step in range(1, rough_segments):
            t = step / rough_segments
            offset = self.rng.uniform(-amplitude, amplitude) * math.sin(math.pi * t) ** 2
            points.append((
                min(grid.width, max(0, start[0] * (1 - t) + end[0] * t
                                    + edge.inward[0] * offset)),
                min(grid.height, max(0, start[1] * (1 - t) + end[1] * t
                                     + edge.inward[1] * offset)),
            ))
        points.append(end)
        for first, second in zip(points, points[1:]):
            self.line(self.walls, first, second, "rough")

    def draw_walls(self):
        """Draw corner joins before the ordered smooth and rough edge segments."""
        edges = _wall_edges(self.grid)
        joins, rounded_ends = self.wall_joins(edges)
        for edge in edges:
            if not edge.rough:
                self.line(self.walls, edge.start, edge.end)
            else:
                self.rough_edge(edge, joins, rounded_ends)

    def label(self, parent, text, x=0.5, y=0.61, size=0.32):
        """Append a centered sans-serif label at local symbol coordinates."""
        fmt = _format
        element = ET.SubElement(parent, "text", {
            "x": fmt(x), "y": fmt(y), "font-family": "sans-serif",
            "font-size": fmt(size), "text-anchor": "middle", "fill": "black",
        })
        element.text = text

    def rectangle(self, parent, x, y, width, height, dashed=False):
        """Append an unfilled rectangle with optional dashed outline."""
        fmt, stroke = _format, self.stroke
        attributes = {
            "x": fmt(x), "y": fmt(y), "width": fmt(width), "height": fmt(height),
            "fill": "none", "stroke": "black", "stroke-width": fmt(stroke),
        }
        if dashed:
            attributes["stroke-dasharray"] = "0.08 0.06"
        ET.SubElement(parent, "rect", attributes)

    def edge_door(self, parent, start, end):
        """Draw a door centered on a horizontal or vertical shared tile edge."""
        fmt = _format
        dx, dy = end[0] - start[0], end[1] - start[1]
        group = ET.SubElement(parent, "g", {
            "transform": "translate({} {}){}".format(
                fmt(start[0]), fmt(start[1]), " rotate(90)" if dy else ""),
        })
        self.line(group, (0, 0), (0.15, 0))
        self.line(group, (0.85, 0), (1, 0))
        self.rectangle(group, 0.15, -0.12, 0.7, 0.24)

    def spiral_symbol(self, group, run):
        """Clip a circular spiral and its treads to the recognized footprint."""
        fmt, stroke = _format, self.stroke
        size = run.size
        center = size / 2
        group.set("data-size", str(size))
        group.set("data-spiral", "true")
        left = min(cx for cx, cy in run.clearance)
        top = min(cy for cx, cy in run.clearance)
        group.set("transform", "translate({} {})".format(left, top))
        clip_id = "spiral-{}-{}".format(left, top)
        clip = ET.SubElement(group, "clipPath", {"id": clip_id})
        clip_cells = run.cells + ((left + 1, top + 1),) if size == 3 else run.cells
        for cx, cy in clip_cells:
            ET.SubElement(clip, "rect", {
                "x": fmt(cx - left), "y": fmt(cy - top),
                "width": "1", "height": "1",
            })
        drawing = ET.SubElement(group, "g", {"clip-path": "url(#{})".format(clip_id)})
        ET.SubElement(drawing, "circle", {
            "cx": fmt(center), "cy": fmt(center), "r": fmt(center),
            "fill": "none", "stroke": "black", "stroke-width": fmt(stroke),
        })
        inner_radius = 0.5 if size == 3 else 0.12
        for index in range(12 * size):
            angle = index * 2 * math.pi / (12 * size)
            self.line(drawing,
                      (center + inner_radius * math.cos(angle),
                       center + inner_radius * math.sin(angle)),
                      (center + center * math.cos(angle), center + center * math.sin(angle)))
        self.spiral_arrows(drawing, run, left, top, center)
        self.spiral_center(group, run, left, top)

    def spiral_center(self, group, run, left, top):
        """Outline a three-square center, opening floor circles toward the landing."""
        if run.size != 3:
            return
        fmt = _format
        attributes = {
            "fill": "none", "stroke": "black", "stroke-width": fmt(self.stroke),
        }
        if self.grid.tile(left + 1, top + 1) == "#":
            attributes.update({
                "cx": "1.5", "cy": "1.5", "r": "0.5",
                "data-spiral-center": "stone",
            })
            ET.SubElement(group, "circle", attributes)
            return
        landing_x, landing_y = run.entrance
        angle = math.atan2(landing_y - top - 1, landing_x - left - 1)
        first, last = angle + math.pi / 4, angle - math.pi / 4
        start = (1.5 + 0.5 * math.cos(first), 1.5 + 0.5 * math.sin(first))
        end = (1.5 + 0.5 * math.cos(last), 1.5 + 0.5 * math.sin(last))
        attributes.update({
            "d": "M {} {} A 0.5 0.5 0 1 1 {} {}".format(
                fmt(start[0]), fmt(start[1]), fmt(end[0]), fmt(end[1])),
            "data-spiral-center": "open",
        })
        ET.SubElement(group, "path", attributes)

    def spiral_arrows(self, drawing, run, left, top, center):
        """Draw the spiral's up/down arcs opposite its landing corner."""
        size = run.size
        directions = ("up", "down") if run.tile == "Z" else (
            "up" if run.tile == "S" else "down",
        )
        landing_x = sum(cx + 0.5 for cx, cy in run.landing_cells) / len(run.landing_cells)
        landing_y = sum(cy + 0.5 for cx, cy in run.landing_cells) / len(run.landing_cells)
        opposite_landing = math.atan2(
            top + center - landing_y, left + center - landing_x,
        )
        for index, direction in enumerate(directions):
            radius = size * (0.28 + index * 0.12)
            self.spiral_arrow(drawing, direction, radius, opposite_landing, center)

    def spiral_arrow(self, drawing, direction, radius, opposite_landing, center):
        """Append one directional spiral arc followed by its two arrowhead lines."""
        fmt, stroke = _format, self.stroke
        clockwise = direction == "down"
        first, last = opposite_landing - 1.2, opposite_landing + 1.2
        if not clockwise:
            first, last = last, first
        start = (center + radius * math.cos(first), center + radius * math.sin(first))
        end = (center + radius * math.cos(last), center + radius * math.sin(last))
        ET.SubElement(drawing, "path", {
            "d": "M {} {} A {} {} 0 0 {} {} {}".format(
                fmt(start[0]), fmt(start[1]), fmt(radius), fmt(radius),
                int(clockwise), fmt(end[0]), fmt(end[1])),
            "fill": "none", "stroke": "black", "stroke-width": fmt(stroke * 1.5),
            "data-direction": direction,
        })
        sign = 1 if clockwise else -1
        tangent = (-math.sin(last) * sign, math.cos(last) * sign)
        radial = (math.cos(last), math.sin(last))
        for side in (-1, 1):
            self.line(drawing, end, (
                end[0] - 0.18 * tangent[0] + side * 0.1 * radial[0],
                end[1] - 0.18 * tangent[1] + side * 0.1 * radial[1],
            ))

    def draw_door(self, x, y, tile, player_view):
        """Draw a centered door, or hide a secret/concealed door as a wall."""
        axis = _door_axis(_neighbors(self.grid, x, y))
        if player_view and tile in "xc":
            endpoints = (
                ((x, y + 0.5), (x + 1, y + 0.5)) if axis == "NS"
                else ((x + 0.5, y), (x + 0.5, y + 1))
            )
            self.line(self.walls, *endpoints)
            return
        group = ET.SubElement(self.symbols, "g", {
            "data-tile": tile,
            "transform": "translate({} {}){}".format(
                x, y, " rotate(90 .5 .5)" if axis == "EW" else ""
            ),
        })
        self.line(group, (0, 0.5), (0.15, 0.5))
        self.line(group, (0.85, 0.5), (1, 0.5))
        self.rectangle(group, 0.15, 0.38, 0.7, 0.24)
        if tile != "d":
            self.label(group, "S" if tile == "x" else "C", y=0.9, size=1.12)

    def draw_edge_doors(self, group, x, y, tile, paired_doors):
        """Draw partition doors and one normal-width door per pair of b tiles."""
        if tile == "b":
            first, second = paired_doors[(x, y)]
            if (x, y) != first:
                self.symbols.remove(group)
                return
            if first[0] == second[0]:
                self.edge_door(group, (0, 1), (1, 1))
            else:
                self.edge_door(group, (1, 0), (1, 1))
        else:
            if tile in "ln":
                self.edge_door(group, (0, 0), (0, 1))
            if tile in "mn":
                self.edge_door(group, (0, 1), (1, 1))

    def stair_horizontal(self, x, y, run):
        """Infer a stair symbol's orientation, preferring a recognized run."""
        grid = self.grid
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
        return horizontal

    def straight_symbol(self, group, tile, length, horizontal):
        """Draw the full-length treads or ramp sides and their directional arrow."""
        transform = "rotate(90 .5 .5)" if horizontal else "rotate(0)"
        if horizontal and length > 1:
            transform = "translate({} 0) rotate(90)".format(length)
        drawing = ET.SubElement(group, "g", {
            "transform": transform,
        })
        if tile in "Ee":
            for index in range(5 * length):
                half_width = 0.14 + index * 0.18 / (5 * length - 1)
                ordinate = 0.2 + index * (length - 0.44) / (5 * length - 1)
                self.line(drawing, (0.42 - half_width, ordinate),
                          (0.42 + half_width, ordinate))
        else:
            self.line(drawing, (0.28, 0.18), (0.12, length - 0.18))
            self.line(drawing, (0.56, 0.18), (0.72, length - 0.18))
        tip, tail = (0.18, length - 0.18) if tile in "er" else (length - 0.18, 0.18)
        self.line(drawing, (0.42, tail), (0.42, tip))
        back = tip + (0.12 if tip < tail else -0.12)
        self.line(drawing, (0.32, back), (0.42, tip))
        self.line(drawing, (0.52, back), (0.42, tip))
        self.label(group, tile, x=length - 0.14 if horizontal else 0.86,
                   y=0.6, size=0.26)

    def draw_feature(self, x, y, tile, run, paired_doors, player_view, trapped_chests):
        """Dispatch one visible feature without altering SVG element order."""
        if tile in DOORS:
            self.draw_door(x, y, tile, player_view)
            return
        group = ET.SubElement(self.symbols, "g", {
            "data-tile": tile, "transform": "translate({} {})".format(x, y),
        })
        if run and run.spiral:
            self.spiral_symbol(group, run)
            return
        if tile in "blmn":
            self.draw_edge_doors(group, x, y, tile, paired_doors)
            return
        length = len(run.cells) if run else 1
        if length > 1:
            group.set("data-length", str(length))
        if tile == "T":
            self.line(group, (0.18, 0.18), (0.82, 0.82))
            self.line(group, (0.18, 0.82), (0.82, 0.18))
            self.label(group, "T", x=0.82, y=0.28, size=0.24)
        elif tile == "C":
            self.rectangle(group, 0.18, 0.3, 0.64, 0.44)
            self.line(group, (0.18, 0.43), (0.82, 0.43))
            self.rectangle(group, 0.46, 0.39, 0.08, 0.14)
            if (x, y) in trapped_chests:
                group.set("data-trapped", "true")
                self.label(group, "T", x=0.82, y=0.25, size=0.24)
        else:
            horizontal = self.stair_horizontal(x, y, run)
            self.straight_symbol(group, tile, length, horizontal)

    def draw_features(self, player_view, trapped_chests):
        """Draw visible feature symbols in row order, once per recognized stair."""
        stair_runs = _stair_runs(self.grid)
        paired_doors = _paired_doors(self.grid)
        for y, row in enumerate(self.grid.rows):
            for x, tile in enumerate(row):
                if tile not in FEATURES or (player_view and tile in "TC"):
                    continue
                run = stair_runs.get((x, y))
                if run and (x, y) != run.cells[0]:
                    continue
                self.draw_feature(x, y, tile, run, paired_doors, player_view, trapped_chests)

    def draw_encounters(self, encounter_labels):
        """Append chamber numbers in supplied order, keeping trap labels legible."""
        grid = self.grid
        encounters = ET.SubElement(self.root, "g", {"id": "encounters"})
        for (x, y), number in encounter_labels.items():
            if grid.tile(x, y) not in " .TC":
                raise ValueError("encounter labels must be on chamber floor")
            group = ET.SubElement(encounters, "g", {
                "data-area": str(number), "data-column": str(x + 1), "data-row": str(y + 1),
                "transform": "translate({} {})".format(x, y),
            })
            occupied = grid.tile(x, y) in "TC"
            self.label(group, str(number), y=0.14 if occupied else 0.66,
                       size=min(0.22 if occupied else 0.46, 0.8 / max(1, len(str(number)))))


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
    trapped_chests: Optional[Set[Cell]] = None,
) -> str:
    """Render a validated map with independently editable black wall segments."""
    dimensions = _render_dimensions(
        grid, feet_per_pixel, feet_per_inch, line_width, roughness, rough_segments,
        corner_radius,
    )
    renderer = _SvgRenderer(grid, dimensions, roughness, rough_segments, seed)
    renderer.draw_walls()
    renderer.draw_features(player_view, trapped_chests or set())
    if encounter_labels:
        renderer.draw_encounters(encounter_labels)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        renderer.root, encoding="unicode"
    ) + "\n"


def render_rows(rows: Sequence[str], **options) -> str:
    """Convenience API for an array of row strings instead of a text file."""
    return svg_document(DungeonMap(tuple(rows)), **options)
