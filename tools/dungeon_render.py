"""Editable SVG walls and feature symbols for ASCII dungeon maps."""

import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from dungeon_geometry import (
    Cell, DIAGONALS, DIRECTIONS, DOORS, DungeonMap, FEATURES, FLOORS, Point,
    _finite_positive, _open_sides,
    _door_runs, _paired_doors, _rough_cells, _spiral_runs, _stair_runs, validate_map,
)


SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_LABEL_SIZE = 0.9


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
    corner_radius, max_wall_deviation,
):
    """Validate rendering options and compute stroke, physical size, and radius."""
    validate_map(grid)
    for name, value in (
        ("feet_per_pixel", feet_per_pixel),
        ("feet_per_inch", feet_per_inch),
        ("line_width", line_width),
    ):
        _finite_positive(name, value)
    if not math.isfinite(roughness) or not 0 <= roughness <= 0.5:
        raise ValueError("roughness must be between zero and 0.5 map squares")
    if not math.isfinite(max_wall_deviation) or not 0 <= max_wall_deviation <= 0.5:
        raise ValueError("max_wall_deviation must be between zero and 0.5 map squares (0-50%)")
    if not isinstance(rough_segments, int) or not 2 <= rough_segments <= 32:
        raise ValueError("rough_segments must be an integer between 2 and 32")
    if corner_radius is not None and (
        not math.isfinite(corner_radius) or not 0 <= corner_radius <= 0.5
    ):
        raise ValueError("corner_radius must be between zero and 0.5 map squares")
    radius = roughness if corner_radius is None else corner_radius
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


def _rough_wall_chains(edges):
    """Trace rough edges once, stopping at smooth joins or topology junctions."""
    incident = defaultdict(list)
    remaining = set()
    for index, edge in enumerate(edges):
        incident[edge.start].append(index)
        incident[edge.end].append(index)
        if edge.rough:
            remaining.add(index)

    def terminal(point):
        touching = incident[point]
        return len(touching) != 2 or any(not edges[index].rough for index in touching)

    def trace(index, start):
        vertices = [start]
        while index in remaining:
            remaining.remove(index)
            edge = edges[index]
            end = edge.end if edge.start == vertices[-1] else edge.start
            vertices.append(end)
            if end == start or terminal(end):
                break
            index = next(other for other in incident[end] if other != index)
        return vertices

    chains = []
    for index, edge in enumerate(edges):
        if index not in remaining:
            continue
        for point in (edge.start, edge.end):
            if terminal(point):
                chains.append(trace(index, point))
                break
    for index in sorted(remaining):
        if index in remaining:
            chains.append(trace(index, edges[index].start))
    return chains


def _bounded_walk(distances, limits, closed, random):
    """Choose offsets with bounded lateral slope and a reachable exact endpoint."""
    total = distances[-1]
    cap = min(limit + min(distance, total - distance)
              for distance, limit in zip(distances, limits))
    target = (2 * random() - 1) * cap if closed else 0
    lower, upper = [0.0] * len(limits), [0.0] * len(limits)
    lower[-1] = upper[-1] = target
    for index in range(len(limits) - 2, -1, -1):
        step = distances[index + 1] - distances[index]
        lower[index] = max(-limits[index], lower[index + 1] - step)
        upper[index] = min(limits[index], upper[index + 1] + step)
    offsets = [target]
    for index in range(1, len(limits)):
        step = distances[index] - distances[index - 1]
        low = max(lower[index], offsets[-1] - step)
        high = min(upper[index], offsets[-1] + step)
        offsets.append(low + (high - low) * random())
    return offsets


def _corner_guard(point, neighbor, vertex, limit):
    """Keep a corner's spline controls inside its deviation disk."""
    middle = tuple((point[axis] + neighbor[axis]) / 2 for axis in (0, 1))
    if math.hypot(middle[0] - vertex[0], middle[1] - vertex[1]) <= limit:
        return None
    delta = tuple(neighbor[axis] - point[axis] for axis in (0, 1))
    offset = tuple(point[axis] - vertex[axis] for axis in (0, 1))
    a = sum(value * value for value in delta)
    if a == 0:
        return None
    b = sum(offset[axis] * delta[axis] for axis in (0, 1))
    c = sum(value * value for value in offset) - limit * limit
    t = min(1, max(0, (-b + math.sqrt(max(0, b * b - a * c))) / a))
    return tuple(point[axis] + t * delta[axis] for axis in (0, 1))


def _wall_walk(vertices, width, height, amplitude, segments, radius, random, max_deviation=None):
    """Sample edges and corner bisectors, carrying one walk across square borders."""
    if max_deviation is not None:
        amplitude = min(amplitude, max_deviation)
        radius = min(radius, max_deviation)
    closed = vertices[0] == vertices[-1]
    count = len(vertices) - 1
    tangents, normals, lengths = [], [], []
    for start, end in zip(vertices, vertices[1:]):
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        tangent = ((end[0] - start[0]) / length, (end[1] - start[1]) / length)
        tangents.append(tangent)
        normals.append((-tangent[1], tangent[0]))
        lengths.append(length)
    samples, distances, limits, corners = [], [], [], []
    distance = 0
    for index in range(count + 1):
        incoming = (index - 1) % count
        outgoing = index % count
        corner = closed or 0 < index < count
        turn = (tangents[incoming][0] * tangents[outgoing][1] -
                tangents[incoming][1] * tangents[outgoing][0]) if corner else 0
        normal = normals[outgoing if index < count else incoming]
        if abs(turn) > 1e-12:
            nx = normals[incoming][0] + normals[outgoing][0]
            ny = normals[incoming][1] + normals[outgoing][1]
            extent = math.hypot(nx, ny)
            normal = (nx / extent, ny / extent)
        samples.append((vertices[index], normal))
        distances.append(distance)
        limits.append(min(amplitude, radius) if abs(turn) > 1e-12 else amplitude)
        if abs(turn) > 1e-12:
            corners.append((len(samples) - 1, turn))
        if index == count:
            break
        for step in range(1, segments):
            t = step / segments
            samples.append(((vertices[index][0] + tangents[index][0] * lengths[index] * t,
                             vertices[index][1] + tangents[index][1] * lengths[index] * t),
                            normals[index]))
            distances.append(distance + lengths[index] * t)
            limits.append(amplitude)
        distance += lengths[index]
    if not closed:
        limits[0] = limits[-1] = 0
        if len(limits) > 3:
            limits[1] = limits[-2] = 0
    offsets = _bounded_walk(distances, limits, closed, random)
    skipped = set()
    unique = len(samples) - 1 if closed else len(samples)
    for index, turn in corners:
        if turn * offsets[index] > 0:
            for neighbor in (index - 1, index + 1):
                if closed:
                    skipped.add(neighbor % unique)
                elif 0 < neighbor < len(samples) - 1:
                    skipped.add(neighbor)
    points, retained = [], []
    for index, ((point, normal), offset) in enumerate(zip(samples, offsets)):
        if index in skipped or closed and index == len(samples) - 1:
            continue
        points.append((min(width, max(0, point[0] + normal[0] * offset)),
                       min(height, max(0, point[1] + normal[1] * offset))))
        retained.append(index)
    if max_deviation is not None:
        corner_indices = {index for index, _ in corners}
        bounded = []
        for index, point in enumerate(points):
            sample = retained[index]
            if sample not in corner_indices:
                bounded.append(point)
                continue
            vertex = samples[sample][0]
            before = _corner_guard(point, points[index - 1], vertex, max_deviation)
            after = _corner_guard(point, points[(index + 1) % len(points)], vertex, max_deviation)
            # Each corner span lies in this disk; other spans stay in their edge's convex band.
            if before is not None:
                bounded.append(before)
            bounded.append(point)
            if after is not None:
                bounded.append(after)
        return bounded
    return points


def _wall_curve(points, closed):
    """Convert a corner-cutting quadratic B-spline to C1-continuous cubic SVG."""
    def middle(first, last):
        return ((first[0] + last[0]) / 2, (first[1] + last[1]) / 2)

    start = middle(points[-1], points[0]) if closed else points[0]
    commands = ["M {} {}".format(*map(_format, start))]
    for index, point in enumerate(points):
        end = (middle(point, points[(index + 1) % len(points)])
               if closed or index + 1 < len(points) else point)
        first = tuple(start[axis] + (point[axis] - start[axis]) * 2 / 3 for axis in (0, 1))
        second = tuple(end[axis] + (point[axis] - end[axis]) * 2 / 3 for axis in (0, 1))
        commands.append("C " + " ".join(map(_format, first + second + end)))
        start = end
    if closed:
        commands.append("Z")
    return " ".join(commands)


class _SvgRenderer:
    """Keep drawing primitives, wall state, and feature output on one SVG canvas."""

    def __init__(self, grid, dimensions, roughness, rough_segments, seed, feet_per_square,
                 max_wall_deviation):
        """Create ordered wall and feature groups with validated drawing settings."""
        stroke, physical_width, physical_height, radius = dimensions
        self.grid = grid
        self.stroke = stroke
        self.radius = radius
        self.roughness = roughness
        self.rough_segments = rough_segments
        self.max_wall_deviation = max_wall_deviation
        self.seed = seed
        self.feet_per_square = feet_per_square
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
        state = seed & 0xffffffff

        def random():
            nonlocal state
            state = (state * 1664525 + 1013904223) & 0xffffffff
            return state / 4294967296

        self.random = random
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

    def draw_walls(self):
        """Keep worked walls straight and draw whole cavern chains as cubic paths."""
        edges = _wall_edges(self.grid)
        for edge in edges:
            if not edge.rough or self.max_wall_deviation == 0:
                self.line(self.walls, edge.start, edge.end)
        if self.max_wall_deviation == 0:
            return
        for vertices in _rough_wall_chains(edges):
            closed = vertices[0] == vertices[-1]
            points = _wall_walk(vertices, self.grid.width, self.grid.height,
                                self.roughness, self.rough_segments, self.radius, self.random,
                                self.max_wall_deviation)
            ET.SubElement(self.walls, "path", {
                "d": _wall_curve(points, closed), "fill": "none", "stroke": "black",
                "stroke-width": _format(self.stroke), "stroke-linecap": "round",
                "stroke-linejoin": "round", "data-texture": "rough",
            })

    def label(self, parent, text, x=0.5, y=0.82, max_width=None):
        """Append 90%-square text, optionally fitting its width without shrinking its height."""
        fmt = _format
        attributes = {
            "x": fmt(x), "y": fmt(y), "font-family": "sans-serif",
            "font-size": fmt(_LABEL_SIZE), "text-anchor": "middle", "fill": "black",
        }
        if max_width is not None and _LABEL_SIZE * len(text) * 0.6 > max_width:
            # Glyph ink can extend beyond the advance width controlled by textLength.
            attributes.update({"textLength": fmt(max_width * 0.95), "lengthAdjust": "spacingAndGlyphs"})
        element = ET.SubElement(parent, "text", attributes)
        element.text = text
        return element

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
        length = math.hypot(dx, dy)
        group = ET.SubElement(parent, "g", {
            "transform": "translate({} {}){}".format(
                fmt(start[0]), fmt(start[1]), " rotate(90)" if dy else ""),
        })
        self.line(group, (0, 0), (0.15, 0))
        self.line(group, (length - 0.15, 0), (length, 0))
        self.rectangle(group, 0.15, -0.12, length - 0.3, 0.24)

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
        landing_x = sum(cx + 0.5 for cx, cy in run.landing_cells) / len(run.landing_cells)
        landing_y = sum(cy + 0.5 for cx, cy in run.landing_cells) / len(run.landing_cells)
        opposite_landing = math.atan2(
            top + center - landing_y, left + center - landing_x,
        )
        descending = run.tile == "s"
        # Descending treads run clockwise between the two edges of the landing quadrant.
        count = 9 * size + 1 if descending else 12 * size
        for index in range(count):
            angle = index * 2 * math.pi / (12 * size)
            if descending:
                angle += opposite_landing - 3 * math.pi / 4
            inset = (center - inner_radius) * index / (4 * (count - 1)) if descending else 0
            self.line(drawing,
                      (center + (inner_radius + inset) * math.cos(angle),
                       center + (inner_radius + inset) * math.sin(angle)),
                      (center + (center - inset) * math.cos(angle),
                       center + (center - inset) * math.sin(angle)))
        self.spiral_arrows(drawing, run, center, opposite_landing)
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

    def spiral_arrows(self, drawing, run, center, opposite_landing):
        """Draw the spiral's up/down arcs opposite its landing corner."""
        directions = ("up", "down") if run.tile == "Z" else (
            "up" if run.tile == "S" else "down",
        )
        for direction in directions:
            self.spiral_arrow(drawing, direction, center * 0.75, opposite_landing, center,
                              run.tile == "Z")

    def spiral_arrow(self, drawing, direction, radius, opposite_landing, center, bidirectional):
        """Append one directional spiral arc followed by its two arrowhead lines."""
        fmt, stroke = _format, self.stroke
        clockwise = direction == "down"
        first, last = opposite_landing - 1.2, opposite_landing + 1.2
        if bidirectional:
            if clockwise:
                first = opposite_landing + 0.15
            else:
                last = opposite_landing - 0.15
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

    def draw_door(self, x, y, tile, player_view, run):
        """Draw a centered door, or hide a secret/concealed door as a wall."""
        cells, axis = run
        length = len(cells)
        if player_view and tile in "xc":
            endpoints = (
                ((x, y + 0.5), (x + length, y + 0.5)) if axis == "NS"
                else ((x + 0.5, y), (x + 0.5, y + length))
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
        self.line(group, (length - 0.15, 0.5), (length, 0.5))
        self.rectangle(group, 0.15, 0.38, length - 0.3, 0.24)
        if tile != "d":
            self.label(group, "S" if tile == "x" else "C", x=length / 2)

    def draw_edge_doors(self, group, x, y, tile, paired_doors):
        """Draw partition doors and one correctly oriented centered door line."""
        if tile == "b":
            cells = paired_doors[(x, y)]
            first, second = cells[0], cells[-1]
            if (x, y) != first:
                self.symbols.remove(group)
                return
            dx, dy = second[0] - first[0], second[1] - first[1]
            self.edge_door(group, (0.5, 0.5), (dx + 0.5, dy + 0.5))
            self.line(group, (0, 0.5) if dy == 0 else (0.5, 0), (0.5, 0.5))
            self.line(group, (dx + 0.5, dy + 0.5),
                      (dx + 1, 0.5) if dy == 0 else (0.5, dy + 1))
        else:
            if tile in "ln":
                self.edge_door(group, (0, 0), (0, 1))
            if tile in "mn":
                self.edge_door(group, (0, 1), (1, 1))

    def straight_symbol(self, group, run):
        """Draw one explicitly directed symbol clipped to its entire footprint."""
        tile, cells, horizontal = run.tile, run.cells, run.horizontal
        left, top = min(x for x, y in cells), min(y for x, y in cells)
        right, bottom = max(x for x, y in cells) + 1, max(y for x, y in cells) + 1
        length = right - left if horizontal else bottom - top
        width = bottom - top if horizontal else right - left
        direction = "up" if tile.isupper() else "down"
        cardinal = ("north" if tile in "EeOo" else "east" if tile in "FfPp"
                    else "south" if tile in "GgQq" else "west")
        group.attrib.update({
            "transform": "translate({} {})".format(left, top),
            "data-length": str(length), "data-width": str(width),
            "data-direction": direction, "data-facing": cardinal,
            "data-elevation": _format(length * self.feet_per_square *
                                      (1 if direction == "up" else -1)),
        })
        identifier = "straight-{}-{}".format(*cells[0])
        clip = ET.SubElement(group, "clipPath", {"id": identifier})
        for x, y in cells:
            ET.SubElement(clip, "rect", {
                "x": str(x - left), "y": str(y - top), "width": "1", "height": "1",
            })
        footprint = ET.SubElement(group, "g", {"clip-path": "url(#{})".format(identifier)})
        transform = {
            "north": "rotate(0)",
            "east": "translate({} 0) rotate(90)".format(length),
            "south": "translate({} {}) rotate(180)".format(width, length),
            "west": "translate(0 {}) rotate(270)".format(width),
        }[cardinal]
        drawing = ET.SubElement(footprint, "g", {"transform": transform})
        if tile in "EeFfGgHh":
            for index in range(5 * length):
                ordinate = 0.2 + index * (length - 0.44) / (5 * length - 1)
                inset = ((width - 0.3) * (1 - index / (5 * length - 1)) / 4
                         if direction == "down" else 0)
                self.line(drawing, (0.15 + inset, ordinate),
                          (width - 0.15 - inset, ordinate))
        else:
            self.line(drawing, (0.15, 0.18), (0.15, length - 0.18))
            self.line(drawing, (width - 0.15, 0.18), (width - 0.15, length - 0.18))
        center = width / 2
        self.line(drawing, (center, length - 0.18), (center, 0.18))
        self.line(drawing, (center - 0.1, 0.3), (center, 0.18))
        self.line(drawing, (center + 0.1, 0.3), (center, 0.18))
        if tile in "OoPpQqRr":
            text = "ramp " + direction
            reverse = cardinal in ("south", "west")
            annotation = ET.SubElement(drawing, "g", {
                "transform": "translate({} {}) rotate({})".format(
                    _format(min(center + _LABEL_SIZE / 2, width - _LABEL_SIZE / 2 - 0.05)),
                    _format(length / 2), 90 if reverse else -90,
                ),
            })
            self.label(annotation, text, x=0, y=0, max_width=length - 0.4).set(
                "dominant-baseline", "central",
            )

    def draw_feature(self, x, y, tile, run, paired_doors):
        """Dispatch one visible feature without altering SVG element order."""
        group = ET.SubElement(self.symbols, "g", {
            "data-tile": tile, "transform": "translate({} {})".format(x, y),
        })
        if run and run.spiral:
            self.spiral_symbol(group, run)
            return
        if tile in "blmn":
            self.draw_edge_doors(group, x, y, tile, paired_doors)
            return
        if tile == "T":
            self.line(group, (0.18, 0.18), (0.82, 0.82))
            self.line(group, (0.18, 0.82), (0.82, 0.18))
            self.label(group, "T", x=0.65, y=0.9)
        elif tile == "C":
            self.rectangle(group, 0.2, 0.28, 0.6, 0.44)
            self.line(group, (0.2, 0.44), (0.8, 0.44))
            self.rectangle(group, 0.45, 0.4, 0.1, 0.12)
        else:
            self.straight_symbol(group, run)

    def draw_features(self, player_view):
        """Draw visible feature symbols in row order, once per recognized stair."""
        stair_runs = _stair_runs(self.grid)
        paired_doors = _paired_doors(self.grid)
        doors = _door_runs(self.grid)
        for y, row in enumerate(self.grid.rows):
            for x, tile in enumerate(row):
                if tile not in FEATURES or (player_view and tile in "TC"):
                    continue
                run = stair_runs.get((x, y))
                if run and (x, y) != run.cells[0]:
                    continue
                if tile in DOORS:
                    if (x, y) == doors[(x, y)][0][0]:
                        self.draw_door(x, y, tile, player_view, doors[(x, y)])
                    continue
                self.draw_feature(x, y, tile, run, paired_doors)

    def draw_encounters(self, encounter_labels):
        """Append map labels in supplied order, keeping trap labels legible."""
        grid = self.grid
        encounters = ET.SubElement(self.root, "g", {"id": "encounters"})
        for (x, y), number in encounter_labels.items():
            if (type(x) is not int or type(y) is not int
                    or not 0 <= x < grid.width or not 0 <= y < grid.height):
                raise ValueError("label coordinates must be integers inside the map")
            group = ET.SubElement(encounters, "g", {
                "data-area": str(number), "data-column": str(x + 1), "data-row": str(y + 1),
                "transform": "translate({} {})".format(x, y),
            })
            occupied = grid.tile(x, y) in "TC"
            self.label(group, str(number), y=0.75 if occupied else 0.82, max_width=0.8)


def svg_document(
    grid: DungeonMap,
    feet_per_pixel: float = 5,
    feet_per_inch: float = 50,
    line_width: float = 0.01,
    seed: int = 0,
    roughness: float = 0.5,
    rough_segments: int = 4,
    player_view: bool = False,
    corner_radius: Optional[float] = None,
    encounter_labels: Optional[Dict[Cell, str]] = None,
    max_wall_deviation: float = 0.5,
) -> str:
    """Render a validated map with independently editable black wall segments."""
    dimensions = _render_dimensions(
        grid, feet_per_pixel, feet_per_inch, line_width, roughness, rough_segments,
        corner_radius, max_wall_deviation,
    )
    renderer = _SvgRenderer(
        grid, dimensions, roughness, rough_segments, seed, feet_per_pixel, max_wall_deviation,
    )
    renderer.draw_walls()
    renderer.draw_features(player_view)
    labels = dict(grid.labels)
    if encounter_labels is not None:
        labels.update(encounter_labels)
    if labels:
        renderer.draw_encounters(labels)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        renderer.root, encoding="unicode"
    ) + "\n"


def render_rows(rows: Sequence[str], **options) -> str:
    """Convenience API for an array of row strings instead of a text file."""
    return svg_document(DungeonMap(tuple(rows)), **options)
