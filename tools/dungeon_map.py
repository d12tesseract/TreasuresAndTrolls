"""Shared ASCII dungeon model, SVG renderer, and seeded map generation.

Requires Python 3.7 or later; uses only the standard library.
"""

import argparse
import math
import random
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple


SVG_NAMESPACE = "http://www.w3.org/2000/svg"
TILES = frozenset("# .\\/|_LDSCTEURIP")
FLOORS = frozenset(" .|_LDSCTEURIP")
DOORS = frozenset("DSC")
DIAGONALS = frozenset("\\/")
FEATURES = frozenset("DSCTEURIP")
DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))  # N, E, S, W
Point = Tuple[float, float]
Cell = Tuple[int, int]


@dataclass(frozen=True)
class DungeonMap:
    rows: Tuple[str, ...]

    def __post_init__(self) -> None:
        rows = tuple(self.rows)
        if not rows or any(not isinstance(row, str) for row in rows):
            raise ValueError("map must contain string rows")
        width = max(map(len, rows))
        if not width:
            raise ValueError("map must contain at least one square")
        for y, row in enumerate(rows):
            for x, tile in enumerate(row):
                if tile not in TILES:
                    raise ValueError(
                        "row {}, column {}: unsupported character {!r}".format(
                            y + 1, x + 1, tile
                        )
                    )
        object.__setattr__(self, "rows", tuple(row.ljust(width, "#") for row in rows))

    @property
    def width(self) -> int:
        return len(self.rows[0])

    @property
    def height(self) -> int:
        return len(self.rows)

    def tile(self, x: int, y: int) -> str:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.rows[y][x]
        return "#"

    def to_ascii(self) -> str:
        return "\n".join(self.rows) + "\n"


def parse_ascii(text: str) -> DungeonMap:
    """Preserve spaces, accept LF/CRLF, and pad short rows with stone."""
    rows = text.replace("\r\n", "\n").split("\n")
    if rows[-1] == "":
        rows.pop()
    return DungeonMap(tuple(rows))


def _neighbors(grid: DungeonMap, x: int, y: int) -> Tuple[str, ...]:
    return tuple(grid.tile(x + dx, y + dy) for dx, dy in DIRECTIONS)


def _diagonal_sides(tile: str, neighbors: Sequence[str]) -> Set[int]:
    pairs = ((0, 1), (2, 3)) if tile == "\\" else ((0, 3), (1, 2))
    for pair in pairs:
        if all(
            neighbor == (" " if side in pair else "#")
            for side, neighbor in enumerate(neighbors)
        ):
            return set(pair)
    return set()


def _door_axis(neighbors: Sequence[str]) -> Optional[str]:
    if neighbors[0] in " ." and neighbors[2] in " ." and (
        neighbors[1] == neighbors[3] == "#"
    ):
        return "NS"
    if neighbors[1] in " ." and neighbors[3] in " ." and (
        neighbors[0] == neighbors[2] == "#"
    ):
        return "EW"
    return None


def validate_map(grid: DungeonMap) -> None:
    for y, row in enumerate(grid.rows):
        for x, tile in enumerate(row):
            neighbors = _neighbors(grid, x, y)
            problem = None
            if tile in DIAGONALS and not _diagonal_sides(tile, neighbors):
                problem = (
                    "diagonal needs two literal spaces on one open side "
                    "and two '#' neighbors on the solid side"
                )
            elif tile in DOORS and _door_axis(neighbors) is None:
                problem = (
                    "door needs opposite space/period neighbors and "
                    "'#' on both perpendicular sides"
                )
            elif tile in "|L" and neighbors[3] != " ":
                problem = "left partition requires a literal space to its left"
            elif tile in "_L" and neighbors[2] != " ":
                problem = "bottom partition requires a literal space below it"
            if problem:
                raise ValueError(
                    "row {}, column {} ({!r}): {}".format(y + 1, x + 1, tile, problem)
                )


def _open_sides(grid: DungeonMap, x: int, y: int) -> Set[int]:
    tile = grid.tile(x, y)
    if tile in FLOORS:
        return {0, 1, 2, 3}
    if tile in DIAGONALS:
        return _diagonal_sides(tile, _neighbors(grid, x, y))
    return set()


def _partition(grid: DungeonMap, x: int, y: int, side: int) -> bool:
    if side == 0:
        return grid.tile(x, y - 1) in "_L"
    if side == 1:
        return grid.tile(x + 1, y) in "|L"
    if side == 2:
        return grid.tile(x, y) in "_L"
    return grid.tile(x, y) in "|L"


def is_connected(grid: DungeonMap) -> bool:
    """Check walkable connectivity, treating doors and covered pits as passable."""
    validate_map(grid)
    cells = {
        (x, y)
        for y, row in enumerate(grid.rows)
        for x, tile in enumerate(row)
        if tile != "#"
    }
    if not cells:
        return False
    visited = {next(iter(cells))}
    pending = deque(visited)
    while pending:
        x, y = pending.popleft()
        for side in _open_sides(grid, x, y):
            dx, dy = DIRECTIONS[side]
            neighbor = (x + dx, y + dy)
            if (
                neighbor not in visited
                and (side + 2) % 4 in _open_sides(grid, *neighbor)
                and not _partition(grid, x, y, side)
            ):
                visited.add(neighbor)
                pending.append(neighbor)
    return visited == cells


def _rough_cells(grid: DungeonMap) -> Set[Cell]:
    rough = {
        (x, y) for y, row in enumerate(grid.rows)
        for x, tile in enumerate(row) if tile == "."
    }
    features = {
        (x, y) for y, row in enumerate(grid.rows)
        for x, tile in enumerate(row) if tile in FEATURES
    }
    # Infer an entire touching feature cluster together, avoiding recursive
    # terrain dependencies when several feature characters replace the floor.
    while features:
        start = min(features)
        features.remove(start)
        cluster = {start}
        pending = [start]
        terrain = set()
        while pending:
            x, y = pending.pop()
            for dx, dy in DIRECTIONS:
                neighbor = (x + dx, y + dy)
                tile = grid.tile(*neighbor)
                if neighbor in features:
                    features.remove(neighbor)
                    cluster.add(neighbor)
                    pending.append(neighbor)
                elif tile in " .|_L\\/":
                    terrain.add("." if tile == "." else " ")
        if terrain == {"."}:
            rough.update(cluster)
    return rough


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
                if tile == "\\":
                    edges.append(_Edge((x, y), (x + 1, y + 1), False, (0, 0)))
                else:
                    edges.append(_Edge((x, y + 1), (x + 1, y), False, (0, 0)))
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


def _finite_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("{} must be finite and greater than zero".format(name))


def _probability(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("{} must be between zero and one".format(name))


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
            neighbors = _neighbors(grid, x, y)
            if tile in DOORS:
                axis = _door_axis(neighbors)
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


@dataclass(frozen=True)
class GenerationOptions:
    width: int = 60
    height: int = 40
    seed: Optional[int] = None
    room_size: float = 35
    corridor_length: float = 8
    density: float = 0.3
    rough_probability: float = 0.4
    door_probability: float = 0.45
    secret_door_probability: float = 0.1
    concealed_door_probability: float = 0.05
    doors: Optional[int] = None
    secret_doors: Optional[int] = None
    concealed_doors: Optional[int] = None
    traps: int = 0
    pits: int = 0
    stairs_down: Optional[int] = None
    stairs_up: int = 0
    ramps_down: int = 0
    ramps_up: int = 0
    chamfer_probability: float = 0
    meandering: float = 0.6
    levels: int = 1
    stair_length: int = 3
    ramp_probability: float = 0


@dataclass(frozen=True)
class Stairway:
    """A straight footprint, ordered west-to-east or north-to-south."""

    cells: Tuple[Cell, ...]
    tile: str
    horizontal: bool

    @property
    def landings(self) -> Tuple[Cell, Cell]:
        dx, dy = (1, 0) if self.horizontal else (0, 1)
        first, last = self.cells[0], self.cells[-1]
        return ((first[0] - dx, first[1] - dy), (last[0] + dx, last[1] + dy))

    @property
    def entrance(self) -> Cell:
        index = 0 if self.tile in "ER" else 1
        return self.landings[index if self.horizontal else 1 - index]

    @property
    def closed_end(self) -> Cell:
        first, last = self.landings
        return last if self.entrance == first else first

    @property
    def approach(self) -> Tuple[Cell, Cell]:
        x, y = self.entrance
        endpoint = self.cells[0] if self.entrance == self.landings[0] else self.cells[-1]
        return self.entrance, (2 * x - endpoint[0], 2 * y - endpoint[1])

    @property
    def walls(self) -> Set[Cell]:
        return {
            (x + dx, y + dy) for x, y in self.cells
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        } - set(self.cells) - {self.entrance}

    @property
    def clearance(self) -> Set[Cell]:
        """Reserve both levels' approaches, including the currently closed end."""
        dx, dy = (1, 0) if self.horizontal else (0, 1)
        first, last = self.landings
        return self.walls | set(self.cells + self.landings) | {
            (first[0] - dx, first[1] - dy), (last[0] + dx, last[1] + dy),
        }


def _stair_runs(grid: DungeonMap) -> Dict[Cell, Stairway]:
    """Recognize straight ASCII runs; ambiguous clusters retain per-tile symbols."""
    remaining = {
        (x, y) for y, row in enumerate(grid.rows)
        for x, tile in enumerate(row) if tile in "EURI"
    }
    result = {}
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        cells = {start}
        pending = [start]
        while pending:
            x, y = pending.pop()
            for dx, dy in DIRECTIONS:
                neighbor = (x + dx, y + dy)
                if neighbor in remaining and grid.tile(*neighbor) == grid.tile(*start):
                    remaining.remove(neighbor)
                    cells.add(neighbor)
                    pending.append(neighbor)
        horizontal = len({y for x, y in cells}) == 1
        vertical = len({x for x, y in cells}) == 1
        if len(cells) > 1 and (horizontal or vertical):
            run = Stairway(tuple(sorted(cells)), grid.tile(*start), horizontal)
            result.update((cell, run) for cell in cells)
    return result


@dataclass(frozen=True)
class GeneratedDungeon:
    grid: DungeonMap
    seed: int
    room_areas: Tuple[int, ...]
    corridor_lengths: Tuple[int, ...]
    stairways: Tuple[Stairway, ...] = ()
    depth_feet: int = 0
    additional_levels: Tuple["GeneratedDungeon", ...] = ()
    layout_notes: Tuple[str, ...] = ()
    room_cells: Tuple[Tuple[Cell, ...], ...] = ()

    @property
    def levels(self) -> Tuple["GeneratedDungeon", ...]:
        """All levels in surface-to-bottom order; grid remains the first level."""
        return (self,) + self.additional_levels

    @property
    def density(self) -> float:
        area = sum(
            0.5 if tile in DIAGONALS else 1
            for row in self.grid.rows for tile in row if tile != "#"
        )
        return area / (self.grid.width * self.grid.height)


@dataclass
class _Room:
    center: Cell
    cells: Set[Cell]
    rough: bool


@dataclass
class _Corridor:
    cells: Tuple[Cell, ...]
    tile: str


class _PlacementError(ValueError):
    pass


def _validate_generation(options: GenerationOptions) -> None:
    for name in ("width", "height"):
        value = getattr(options, name)
        if not isinstance(value, int) or value < 7:
            raise ValueError("{} must be an integer of at least 7 squares".format(name))
    for name in ("room_size", "corridor_length"):
        _finite_positive(name, getattr(options, name))
    for name in ("levels", "stair_length"):
        value = getattr(options, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("{} must be a positive integer".format(name))
    if not math.isfinite(options.ramp_probability) or not 0 <= options.ramp_probability <= 100:
        raise ValueError("ramp_probability must be a percentage between 0 and 100")
    if options.room_size < 4:
        raise ValueError("room_size must be at least 4 floor squares")
    if not math.isfinite(options.density) or not 0 < options.density < 1:
        raise ValueError("density must be greater than zero and less than one")
    for name in (
        "rough_probability", "door_probability", "secret_door_probability",
        "concealed_door_probability", "chamfer_probability", "meandering",
    ):
        _probability(name, getattr(options, name))
    if sum((options.door_probability, options.secret_door_probability,
            options.concealed_door_probability)) > 1 + 1e-12:
        raise ValueError("door probabilities must sum to at most one")
    for name in (
        "doors", "secret_doors", "concealed_doors", "traps", "pits",
        "stairs_down", "stairs_up", "ramps_down", "ramps_up",
    ):
        value = getattr(options, name)
        if value is None and name in ("doors", "secret_doors", "concealed_doors", "stairs_down"):
            continue
        if not isinstance(value, int) or value < 0:
            raise ValueError("{} must be a nonnegative integer".format(name))
    if options.levels > 1:
        if options.stair_length > max(options.width, options.height) - 6:
            raise ValueError("stair_length must fit inside the map with a corridor approach")
        if options.stairs_up not in (0, 1) or options.ramps_up:
            raise ValueError("multi-level up passages are determined by the level above; "
                             "only one surface stairway is allowed")
        if options.stairs_down == 0 and options.ramps_down == 0:
            raise ValueError("multiple levels require at least one down stairway or ramp")


def _room_shape(options: GenerationOptions, rng: random.Random) -> Tuple[int, int, Set[Cell], bool]:
    rough = rng.random() < options.rough_probability
    area = min(options.room_size, (options.width - 4) * (options.height - 4))
    area *= rng.uniform(0.65, 1.35)
    aspect = rng.uniform(0.65, 1.55)
    box_area = area / (0.75 if rough else 1)
    width = max(3, min(options.width - 4, round(math.sqrt(box_area * aspect))))
    height = max(3, min(options.height - 4, round(math.sqrt(box_area / aspect))))
    if not rough:
        return width, height, {
            (x, y) for y in range(height) for x in range(width)
        }, rough
    cells = set()
    center = width // 2
    for y in range(height):
        normalized_y = (y - (height - 1) / 2) / (height / 2)
        radius = (width / 2) * math.sqrt(max(0, 1 - normalized_y ** 2))
        left = max(0, min(center, round(center - radius + rng.uniform(-0.7, 0.7))))
        right = min(width - 1, max(center, round(center + radius + rng.uniform(-0.7, 0.7))))
        cells.update((x, y) for x in range(left, right + 1))
    return width, height, cells, rough


def _path(start: Cell, end: Cell, horizontal_first: bool) -> List[Cell]:
    x, y = start
    result = [(x, y)]
    for axis in ((0, 1) if horizontal_first else (1, 0)):
        while (x, y)[axis] != end[axis]:
            if axis == 0:
                x += 1 if end[0] > x else -1
            else:
                y += 1 if end[1] > y else -1
            result.append((x, y))
    return result


def _meander_path(
    path: List[Cell],
    occupied: Set[Cell],
    width: int,
    height: int,
    amount: float,
    rng: random.Random,
) -> List[Cell]:
    """Replace short straight spans with bounded detours, advancing along path."""
    if not amount:
        return path
    result = [path[0]]
    reserved = set(path) | occupied
    index = 0
    may_detour = True
    while index < len(path) - 1:
        dx = path[index + 1][0] - path[index][0]
        dy = path[index + 1][1] - path[index][1]
        stop = index + 1
        limit = min(index + rng.randint(2, 3), len(path) - 1)
        while stop < limit and path[stop + 1] == (path[stop][0] + dx, path[stop][1] + dy):
            stop += 1
        direct = path[index:stop + 1]
        replacement = direct
        if (
            may_detour and stop - index >= 2
            and not any(cell in occupied for cell in direct)
            and rng.random() < amount
        ):
            unaffected = (reserved - set(direct)) | set(result[:-1])
            offsets = [-3, -2, 2, 3]
            rng.shuffle(offsets)
            for offset in offsets:
                start, end = direct[0], direct[-1]
                shifted_start = (start[0] - dy * offset, start[1] + dx * offset)
                shifted_end = (end[0] - dy * offset, end[1] + dx * offset)
                candidate = (
                    _path(start, shifted_start, True)
                    + _path(shifted_start, shifted_end, True)[1:]
                    + _path(shifted_end, end, True)[1:]
                )
                # Keep a stone gap to rooms and other route segments, so a
                # detour cannot carve a shortcut or double back into itself.
                if all(
                    1 <= x < width - 1 and 1 <= y < height - 1
                    and (x, y) not in unaffected
                    and not any((x + nx, y + ny) in unaffected for nx, ny in DIRECTIONS)
                    for x, y in candidate[1:-1]
                ):
                    replacement = candidate
                    break
        may_detour = replacement is direct
        result.extend(replacement[1:])
        index = stop
    return result


def _terrain(
    options: GenerationOptions, rng: random.Random,
    excluded_rooms: Optional[Set[Cell]] = None,
):
    rows = [["#"] * options.width for _ in range(options.height)]
    occupied = set()
    rooms = []
    lengths = []
    corridors = []
    excluded_rooms = excluded_rooms or set()
    target = options.width * options.height * options.density
    misses = 0
    while len(occupied) < target and misses < 80:
        width, height, local_cells, rough = _room_shape(options, rng)
        best = None
        for _ in range(24):
            left = rng.randint(1, options.width - width - 1)
            top = rng.randint(1, options.height - height - 1)
            cells = {(left + x, top + y) for x, y in local_cells}
            if cells & excluded_rooms:
                continue
            if any(
                (x + dx, y + dy) in occupied
                for x, y in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            ):
                continue
            center = (left + width // 2, top + height // 2)
            room = _Room(center, cells, rough)
            if not rooms:
                best = (0, room, [], None)
                break
            previous = min(
                rooms,
                key=lambda other: abs(center[0] - other.center[0])
                + abs(center[1] - other.center[1]),
            )
            path = _path(previous.center, center, rng.choice((True, False)))
            length = sum(cell not in occupied and cell not in cells for cell in path)
            score = abs(length - options.corridor_length) + rng.random()
            if best is None or score < best[0]:
                best = (score, room, path, previous)
        if best is None:
            misses += 1
            continue
        misses = 0
        _, room, path, previous = best
        if previous is not None:
            corridor_tile = "." if previous.rough and room.rough else " "
            if corridor_tile == ".":
                path = _meander_path(
                    path, occupied | room.cells, options.width, options.height,
                    options.meandering, rng,
                )
            lengths.append(sum(cell not in occupied and cell not in room.cells for cell in path))
            corridors.append(_Corridor(tuple(path), corridor_tile))
            for x, y in path:
                if rows[y][x] == "#":
                    rows[y][x] = corridor_tile
                occupied.add((x, y))
        for x, y in room.cells:
            rows[y][x] = "." if room.rough else " "
        occupied.update(room.cells)
        rooms.append(room)
    return rows, rooms, lengths, corridors


def _decorate(
    rows, rooms: List[_Room], options: GenerationOptions, rng: random.Random,
    reserved: Optional[Set[Cell]] = None,
) -> DungeonMap:
    width, height = options.width, options.height
    reserved = reserved or set()

    def tile(x, y):
        return rows[y][x] if 0 <= x < width and 0 <= y < height else "#"

    def neighbors(x, y):
        return tuple(tile(x + dx, y + dy) for dx, dy in DIRECTIONS)

    for room in rooms:
        if room.rough:
            continue
        for x, y in sorted(room.cells):
            adjacent = neighbors(x, y)
            if (x, y) in reserved or tile(x, y) != " " or any(value in DIAGONALS for value in adjacent):
                continue
            for diagonal in ("\\", "/"):
                if _diagonal_sides(diagonal, adjacent):
                    if rng.random() < options.chamfer_probability:
                        rows[y][x] = diagonal
                    break

    room_cells = set().union(*(room.cells for room in rooms))
    candidates = [
        (x, y) for y in range(1, height - 1) for x in range(1, width - 1)
        if tile(x, y) in " ." and (x, y) not in room_cells
        and (x, y) not in reserved
        and _door_axis(neighbors(x, y))
        and any((x + dx, y + dy) in room_cells for dx, dy in DIRECTIONS)
    ]
    rng.shuffle(candidates)
    available = []
    blocked = set()
    for cell in candidates:
        if cell not in blocked:
            available.append(cell)
            blocked.add(cell)
            blocked.update((cell[0] + dx, cell[1] + dy) for dx, dy in DIRECTIONS)
    specifications = (
        ("D", options.doors, options.door_probability),
        ("S", options.secret_doors, options.secret_door_probability),
        ("C", options.concealed_doors, options.concealed_door_probability),
    )
    required = sum(count for _, count, _ in specifications if count is not None)
    if required > len(available):
        raise _PlacementError(
            "requested {} exact doors, but only {} valid room entrances were found".format(
                required, len(available)
            )
        )
    for symbol, count, _ in specifications:
        for _ in range(count or 0):
            x, y = available.pop()
            rows[y][x] = symbol
    for x, y in available:
        choice = rng.random()
        cumulative = 0
        for symbol, count, probability in specifications:
            if count is None:
                cumulative += probability
                if choice < cumulative:
                    rows[y][x] = symbol
                    break
    free = [
        (x, y) for y in range(1, height - 1) for x in range(1, width - 1)
        if tile(x, y) in " ."
        and (x, y) not in reserved
        and not any(value in DOORS or value in DIAGONALS for value in neighbors(x, y))
    ]
    rng.shuffle(free)
    features = (
        ("T", options.traps), ("P", options.pits),
    )
    required = sum(count for _, count in features)
    if required > len(free):
        raise _PlacementError(
            "requested {} floor features, but only {} eligible squares were found".format(
                required, len(free)
            )
        )
    for symbol, count in features:
        for _ in range(count):
            x, y = free.pop()
            rows[y][x] = symbol
    return DungeonMap(tuple("".join(row) for row in rows))


def _route(
    start: Cell, targets: Set[Cell], width: int, height: int, forbidden: Set[Cell],
) -> Optional[Tuple[Cell, ...]]:
    if start in forbidden:
        return None
    pending = deque([start])
    previous = {start: None}
    while pending:
        cell = pending.popleft()
        if cell in targets:
            path = []
            while cell is not None:
                path.append(cell)
                cell = previous[cell]
            return tuple(reversed(path))
        for dx, dy in DIRECTIONS:
            neighbor = (cell[0] + dx, cell[1] + dy)
            if (1 <= neighbor[0] < width - 1 and 1 <= neighbor[1] < height - 1
                    and neighbor not in forbidden and neighbor not in previous):
                previous[neighbor] = cell
                pending.append(neighbor)
    return None


def _reroute_corridors(
    corridors: List[_Corridor], forbidden: Set[Cell], width: int, height: int,
) -> Tuple[List[_Corridor], int, int]:
    retained = []
    rerouted = removed = 0
    for corridor in corridors:
        if not forbidden.intersection(corridor.cells):
            retained.append(corridor)
            continue
        route = _route(corridor.cells[0], {corridor.cells[-1]}, width, height, forbidden)
        if route is None:
            removed += 1
        else:
            retained.append(_Corridor(route, corridor.tile))
            rerouted += 1
    return retained, rerouted, removed


def _rebuild_layout(rows, rooms: List[_Room], corridors: List[_Corridor]) -> List[int]:
    for row in rows:
        row[:] = ["#"] * len(row)
    for room in rooms:
        for x, y in room.cells:
            rows[y][x] = "." if room.rough else " "
    lengths = []
    for corridor in corridors:
        length = 0
        for x, y in corridor.cells:
            if rows[y][x] == "#":
                rows[y][x] = corridor.tile
                length += 1
        lengths.append(length)
    return lengths


def _prune_unreachable(
    rows, rooms: List[_Room], corridors: List[_Corridor], entrances: Sequence[Cell],
) -> Tuple[int, int]:
    visited = {entrances[0]}
    pending = list(visited)
    while pending:
        x, y = pending.pop()
        for dx, dy in DIRECTIONS:
            neighbor = (x + dx, y + dy)
            nx, ny = neighbor
            if (0 <= ny < len(rows) and 0 <= nx < len(rows[0])
                    and rows[ny][nx] != "#" and neighbor not in visited):
                visited.add(neighbor)
                pending.append(neighbor)
    if not set(entrances) <= visited:
        raise _PlacementError("stairway entrances cannot be connected without crossing a stairwell")
    removed_rooms = sum(not room.cells <= visited for room in rooms)
    removed_corridors = sum(not set(corridor.cells) <= visited for corridor in corridors)
    rooms[:] = [room for room in rooms if room.cells <= visited]
    corridors[:] = [corridor for corridor in corridors if set(corridor.cells) <= visited]
    for y, row in enumerate(rows):
        for x in range(len(row)):
            if (x, y) not in visited:
                row[x] = "#"
    return removed_rooms, removed_corridors


def _place_stairways(
    rows, options: GenerationOptions, rng: random.Random,
    incoming: Tuple[Stairway, ...], down_count: int,
    rooms: List[_Room], corridors: List[_Corridor],
) -> Tuple[Tuple[Stairway, ...], Set[Cell], Tuple[str, ...]]:
    passages = list(incoming)
    blocked = set()
    room_cells = set().union(*(room.cells for room in rooms))
    floor = {
        (x, y) for y, row in enumerate(rows) for x, tile in enumerate(row) if tile in " ."
    }
    distances = dict.fromkeys(floor, 0)
    pending = deque(sorted(floor))
    while pending:
        x, y = pending.popleft()
        for dx, dy in DIRECTIONS:
            neighbor = (x + dx, y + dy)
            if (1 <= neighbor[0] < options.width - 1
                    and 1 <= neighbor[1] < options.height - 1 and neighbor not in distances):
                distances[neighbor] = distances[(x, y)] + 1
                pending.append(neighbor)
    if not floor:
        raise _PlacementError("no room or corridor is available for stairway access")

    def reserve(passage):
        blocked.update(passage.clearance)

    for passage in passages:
        if room_cells & (set(passage.cells + passage.approach) | passage.walls):
            raise _PlacementError("an inherited stairway overlaps a room")
        reserve(passage)
    if options.levels > 1:
        symbols = ([] if incoming else ["U"]) + [
            "R" if rng.random() * 100 < options.ramp_probability else "E"
            for _ in range(down_count)
        ] + ["R"] * options.ramps_down
        length = options.stair_length
    else:
        symbols = (
            ["E"] * (options.stairs_down or 0) + ["U"] * options.stairs_up
            + ["R"] * options.ramps_down + ["I"] * options.ramps_up
        )
        length = 1
    for symbol in symbols:
        candidates = []
        for horizontal in (True, False):
            dx, dy = (1, 0) if horizontal else (0, 1)
            for y in range(1 + dy, options.height - 1 - length * dy):
                for x in range(1 + dx, options.width - 1 - length * dx):
                    cells = tuple((x + step * dx, y + step * dy)
                                  for step in range(length))
                    passage = Stairway(cells, symbol, horizontal)
                    area = passage.clearance
                    if area & blocked:
                        continue
                    if any(not (1 <= cx < options.width - 1 and 1 <= cy < options.height - 1)
                           for cx, cy in area):
                        continue
                    if area & room_cells:
                        continue
                    collisions = len((set(cells) | passage.walls) & floor)
                    candidates.append(((collisions, distances[passage.approach[-1]]), passage))
        rng.shuffle(candidates)
        candidates.sort(key=lambda item: item[0])
        passage = None
        forbidden = set().union(*(p.walls | set(p.cells) for p in passages))
        for _, candidate in candidates:
            exclusion = forbidden | candidate.walls | set(candidate.cells)
            if _route(candidate.approach[-1], floor - exclusion,
                      options.width, options.height, exclusion) is not None:
                passage = candidate
                break
        if passage is None:
            raise _PlacementError("not enough space for separated stairways and their landings")
        passages.append(passage)
        reserve(passage)

    footprints = {cell for passage in passages for cell in passage.cells}
    approaches = {cell for passage in passages for cell in passage.approach}
    walls = set().union(*(passage.walls for passage in passages))
    if walls & (footprints | approaches):
        raise _PlacementError("stairway walls overlap another passage or its entrance")
    forbidden = walls | footprints
    retained, rerouted, removed = _reroute_corridors(
        corridors, forbidden, options.width, options.height,
    )
    corridors[:] = retained
    _rebuild_layout(rows, rooms, corridors)
    floor = {
        (x, y) for y, row in enumerate(rows) for x, tile in enumerate(row)
        if tile in " ."
    }
    for passage in passages:
        route = _route(passage.approach[-1], floor, options.width, options.height, forbidden)
        if route is None:
            raise _PlacementError("could not route an entry corridor to a stairway")
        access = (passage.entrance,) + route
        corridors.append(_Corridor(access, " "))
        for x, y in access:
            if rows[y][x] == "#":
                rows[y][x] = " "
            floor.add((x, y))
    for passage in passages:
        for x, y in passage.cells:
            rows[y][x] = passage.tile
    removed_rooms, orphaned_corridors = _prune_unreachable(
        rows, rooms, corridors, [passage.entrance for passage in passages],
    )
    notes = []
    if rerouted:
        notes.append("Rerouted {} corridors around stairways.".format(rerouted))
    if removed or orphaned_corridors or removed_rooms:
        notes.append("Removed {} corridors and {} unreachable rooms after stairway collisions.".format(
            removed + orphaned_corridors, removed_rooms,
        ))
    reserved = footprints | approaches | walls
    return tuple(passages), reserved, tuple(notes)


def _generate_level(
    options: GenerationOptions, rng: random.Random, seed: int,
    incoming: Tuple[Stairway, ...] = (), down_count: int = 0, depth_feet: int = 0,
) -> GeneratedDungeon:
    problem = None
    excluded_rooms = set().union(*(
        set(passage.cells + passage.approach) | passage.walls for passage in incoming
    ))
    for _ in range(12):
        rows, rooms, lengths, corridors = _terrain(options, rng, excluded_rooms)
        try:
            stairways, reserved = (), set()
            notes = ()
            decoration = options
            if options.levels > 1 or any((
                options.stairs_down, options.stairs_up, options.ramps_down, options.ramps_up,
            )):
                stairways, reserved, notes = _place_stairways(
                    rows, options, rng, incoming, down_count, rooms, corridors,
                )
                lengths = _rebuild_layout([row[:] for row in rows], rooms, corridors)
                decoration = replace(options, stairs_down=0, stairs_up=0, ramps_down=0, ramps_up=0)
            grid = _decorate(rows, rooms, decoration, rng, reserved)
        except _PlacementError as error:
            problem = error
            continue
        validate_map(grid)
        if not is_connected(grid):
            raise RuntimeError("generated map is unexpectedly disconnected")
        return GeneratedDungeon(
            grid, seed, tuple(len(room.cells) for room in rooms), tuple(lengths),
            stairways, depth_feet, layout_notes=notes,
            room_cells=tuple(tuple(sorted(room.cells)) for room in rooms),
        )
    raise ValueError(
        "could not satisfy feature counts after 12 layouts: {}; "
        "increase map size/density, reduce room size or feature counts, or change seed".format(problem)
    )


def generate_dungeon(
    options: Optional[GenerationOptions] = None,
    level_transform: Optional[Callable[[GeneratedDungeon, int], GeneratedDungeon]] = None,
) -> GeneratedDungeon:
    """Generate connected levels with corridor-only stairs and ramps."""
    options = options or GenerationOptions()
    _validate_generation(options)
    seed = options.seed if options.seed is not None else random.SystemRandom().randrange(2 ** 63)
    rng = random.Random(seed)
    if options.levels == 1:
        level = _generate_level(options, rng, seed)
        return level_transform(level, 1) if level_transform else level
    levels = []
    incoming = ()
    for index in range(options.levels):
        final = index == options.levels - 1
        count = 0 if final else (
            rng.randint(1, 3) if options.stairs_down is None else options.stairs_down
        )
        level_options = replace(options, ramps_down=0) if final else options
        if incoming:
            level_options = replace(level_options, width=max(
                options.width, max(x for passage in incoming for x, y in passage.clearance) + 2,
            ))
        level = _generate_level(
            level_options, rng, seed, incoming, count,
            (index + 1) * options.stair_length * 10,
        )
        if level_transform:
            level = level_transform(level, index + 1)
        levels.append(level)
        incoming = tuple(
            replace(passage, tile="U" if passage.tile == "E" else "I")
            for passage in level.stairways if passage.tile in "ER"
        )
    return replace(levels[0], additional_levels=tuple(levels[1:]))


def positive_number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return number


def probability(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("must be between zero and one")
    return number


def nonnegative_integer(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def add_render_arguments(parser: argparse.ArgumentParser, seed_default=0) -> None:
    parser.add_argument("--feet-per-pixel", "--feet-per-square", type=positive_number, default=10,
                        help="map feet per ASCII square (default: 10)")
    parser.add_argument("--feet-per-inch", type=positive_number, default=50,
                        help="map feet per printed SVG inch (default: 50)")
    parser.add_argument("--line-width", type=positive_number, default=0.01,
                        help="stroke width in inches (default: 0.01)")
    parser.add_argument("--seed", type=int, default=seed_default,
                        help="random seed (ASCII default: 0; generated maps: random)")
    parser.add_argument("--roughness", type=float, default=0.12,
                        help="rough-wall deviation, 0 to 0.2 squares (default: 0.12)")
    parser.add_argument("--rough-segments", type=int, default=6,
                        help="segments per rough tile edge, 2 to 32 (default: 6)")
    parser.add_argument("--corner-radius", type=float,
                        help="rough corner radius, 0 to 0.5 squares (default: automatic, up to 0.35)")
    parser.add_argument("--player-view", action="store_true",
                        help="hide traps/pits and show secret/concealed doors as walls")


def render_options(args: argparse.Namespace) -> Dict:
    return {
        name: getattr(args, name) for name in (
            "feet_per_pixel", "feet_per_inch", "line_width", "seed",
            "roughness", "rough_segments", "player_view", "corner_radius",
        )
    }
