"""ASCII dungeon geometry, validation, connectivity, and stair footprints."""

import math
from collections import deque
from dataclasses import dataclass
from typing import AbstractSet, Dict, List, Optional, Sequence, Set, Tuple


TILES = frozenset("#~ .\\/|_LdxbCTEeRrclmnSsZ")
FLOORS = frozenset(" .|_LdxbCTEeRrclmnSsZ")
DOORS = frozenset("dxc")
DIAGONALS = frozenset("\\/")
FEATURES = frozenset("dxbCTEeRrclmnSsZ")
DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))  # N, E, S, W
Point = Tuple[float, float]
Cell = Tuple[int, int]


def _finite_positive(name: str, value: float) -> None:
    """Reject a nonfinite or nonpositive named rendering parameter."""
    if not math.isfinite(value) or value <= 0:
        raise ValueError("{} must be finite and greater than zero".format(name))


@dataclass(frozen=True)
class DungeonMap:
    rows: Tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate tile characters and pad ragged rows with solid stone."""
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
        """Return the padded map width in squares."""
        return len(self.rows[0])

    @property
    def height(self) -> int:
        """Return the map height in squares."""
        return len(self.rows)

    def tile(self, x: int, y: int) -> str:
        """Read a tile, treating coordinates beyond the map as stone."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.rows[y][x]
        return "#"

    def to_ascii(self) -> str:
        """Serialize padded rows with a final newline."""
        return "\n".join(self.rows) + "\n"


def parse_ascii(text: str) -> DungeonMap:
    """Preserve spaces, accept LF/CRLF, and pad short rows with stone."""
    rows = text.replace("\r\n", "\n").split("\n")
    if rows[-1] == "":
        rows.pop()
    return DungeonMap(tuple(rows))


def _neighbors(grid: DungeonMap, x: int, y: int) -> Tuple[str, ...]:
    """Read the north, east, south, and west neighboring tiles."""
    return tuple(grid.tile(x + dx, y + dy) for dx, dy in DIRECTIONS)


def _diagonal_sides(tile: str, neighbors: Sequence[str]) -> Set[int]:
    """Return valid open triangle sides, or an empty set for invalid geometry."""
    pairs = ((0, 1), (2, 3)) if tile == "\\" else ((0, 3), (1, 2))
    opened = set()
    for pair in pairs:
        if all(neighbors[side] in " .~" for side in pair):
            opened.update(pair)
        elif not all(neighbors[side] == "#" for side in pair):
            return set()
    return opened


def _paired_doors(grid: DungeonMap) -> Dict[Cell, Tuple[Cell, Cell]]:
    """Index paired b tiles representing one door centered on their shared edge."""
    remaining = {(x, y) for y, row in enumerate(grid.rows)
                 for x, tile in enumerate(row) if tile == "b"}
    result = {}
    for cell in sorted(remaining):
        adjacent = [(cell[0] + dx, cell[1] + dy) for dx, dy in DIRECTIONS
                    if grid.tile(cell[0] + dx, cell[1] + dy) == "b"]
        if len(adjacent) != 1:
            raise ValueError("row {}, column {}: b door requires exactly one adjacent b".format(
                cell[1] + 1, cell[0] + 1))
        other = adjacent[0]
        if sum(grid.tile(other[0] + dx, other[1] + dy) == "b"
               for dx, dy in DIRECTIONS) != 1:
            raise ValueError("b door requires an isolated horizontal or vertical pair")
        result[cell] = tuple(sorted((cell, other)))
    return result


def _door_axis(neighbors: Sequence[str]) -> Optional[str]:
    """Identify a door's opposing floor neighbors and perpendicular stone."""
    if neighbors[0] in " .TC" and neighbors[2] in " .TC" and (
        neighbors[1] == neighbors[3] == "#"
    ):
        return "NS"
    if neighbors[1] in " .TC" and neighbors[3] in " .TC" and (
        neighbors[0] == neighbors[2] == "#"
    ):
        return "EW"
    return None


def clear_invalid_diagonals(rows: List[List[str]]) -> None:
    """Open generated half-squares whose solid side was carved by a connection."""
    height, width = len(rows), len(rows[0])
    pending = deque(
        (x, y) for y, row in enumerate(rows)
        for x, tile in enumerate(row) if tile in DIAGONALS
    )
    while pending:
        x, y = pending.popleft()
        if rows[y][x] not in DIAGONALS:
            continue
        neighbors = tuple(
            rows[y + dy][x + dx] if 0 <= x + dx < width and 0 <= y + dy < height else "#"
            for dx, dy in DIRECTIONS
        )
        if not _diagonal_sides(rows[y][x], neighbors):
            rows[y][x] = " "
            pending.extend((x + dx, y + dy) for dx, dy in DIRECTIONS
                           if 0 <= x + dx < width and 0 <= y + dy < height
                           and rows[y + dy][x + dx] in DIAGONALS)


def validate_map(grid: DungeonMap) -> None:
    """Reject malformed diagonals, doors, partitions, and spiral footprints."""
    _paired_doors(grid)
    _spiral_runs(grid)
    for y, row in enumerate(grid.rows):
        for x, tile in enumerate(row):
            if tile not in "\\/dxc|_Llmn":
                continue
            neighbors = _neighbors(grid, x, y)
            problem = None
            if tile in DIAGONALS and not _diagonal_sides(tile, neighbors):
                problem = (
                    "diagonal needs paired space/period/void neighbors or paired "
                    "stone neighbors on each side, with at least one open side"
                )
            elif tile in DOORS and _door_axis(neighbors) is None:
                problem = (
                    "door needs opposite floor/trap/chest neighbors and "
                    "'#' on both perpendicular sides"
                )
            elif tile in "|L" and neighbors[3] != " ":
                problem = "left partition requires a literal space to its left"
            elif tile in "_L" and neighbors[2] != " ":
                problem = "bottom partition requires a literal space below it"
            elif tile in "ln" and neighbors[3] != " ":
                problem = "left door requires a literal space to its left"
            elif tile in "mn" and neighbors[2] != " ":
                problem = "bottom door requires a literal space below it"
            if problem:
                raise ValueError(
                    "row {}, column {} ({!r}): {}".format(y + 1, x + 1, tile, problem)
                )


def _open_sides(grid: DungeonMap, x: int, y: int) -> Set[int]:
    """Return the traversable sides of floor, void, or diagonal geometry."""
    tile = grid.tile(x, y)
    if tile in FLOORS or tile == "~":
        return {0, 1, 2, 3}
    if tile in DIAGONALS:
        return _diagonal_sides(tile, _neighbors(grid, x, y))
    return set()


def _partition(grid: DungeonMap, x: int, y: int, side: int) -> bool:
    """Check whether a partition blocks movement across the requested side."""
    if side == 0:
        return grid.tile(x, y - 1) in "_L"
    if side == 1:
        return grid.tile(x + 1, y) in "|L"
    if side == 2:
        return grid.tile(x, y) in "_L"
    return grid.tile(x, y) in "|L"


def _room_entrances(grid: DungeonMap, cells: AbstractSet[Cell]) -> Set[Cell]:
    """Find room-side squares with a traversable connection outside the chamber."""
    return {
        (x, y) for x, y in cells
        for side, (dx, dy) in enumerate(DIRECTIONS)
        if (x + dx, y + dy) not in cells
        and side in _open_sides(grid, x, y)
        and (side + 2) % 4 in _open_sides(grid, x + dx, y + dy)
        and not _partition(grid, x, y, side)
    }


def _walk_regions(grid: DungeonMap, cell: Cell):
    """Separate a diagonal's walkable triangles into independent regions."""
    x, y = cell
    sides = _open_sides(grid, x, y)
    if grid.tile(x, y) in DIAGONALS:
        pairs = ((0, 1), (2, 3)) if grid.tile(x, y) == "\\" else ((0, 3), (1, 2))
        return [frozenset(pair) for pair in pairs if set(pair) <= sides]
    return [frozenset(sides)] if sides else []


def _reachable_regions(grid: DungeonMap, start: Cell, blocked: AbstractSet[Cell]):
    """Flood connected tile regions while respecting partitions and blocked cells."""
    if start in blocked or not _open_sides(grid, *start):
        return set()
    visited = {(start, _walk_regions(grid, start)[0])}
    pending = list(visited)
    while pending:
        (x, y), region = pending.pop()
        for side in region:
            dx, dy = DIRECTIONS[side]
            neighbor = (x + dx, y + dy)
            if (
                0 <= neighbor[0] < grid.width and 0 <= neighbor[1] < grid.height
                and neighbor not in blocked
                and not _partition(grid, x, y, side)
            ):
                for next_region in _walk_regions(grid, neighbor):
                    state = (neighbor, next_region)
                    if (side + 2) % 4 in next_region and state not in visited:
                        visited.add(state)
                        pending.append(state)
    return visited


def reachable_cells(
    grid: DungeonMap, start: Cell, blocked: AbstractSet[Cell] = frozenset(),
) -> Set[Cell]:
    """Flood walkable geometry, respecting partitions and temporarily closed gates.

    A start on a two-sided diagonal uses its north-facing triangle.
    """
    return {cell for cell, region in _reachable_regions(grid, start, blocked)}


def is_connected(grid: DungeonMap) -> bool:
    """Check walkable connectivity, treating doors and covered pits as passable."""
    validate_map(grid)
    cells = {
        (x, y)
        for y, row in enumerate(grid.rows)
        for x, tile in enumerate(row)
        if tile not in "#~"
    }
    if not cells:
        return False
    start = next((cell for cell in sorted(cells) if grid.tile(*cell) not in DIAGONALS),
                 next(iter(cells)))
    reached = _reachable_regions(grid, start, frozenset())
    return all((cell, region) in reached for cell in cells
               for region in _walk_regions(grid, cell))


def _route(
    start: Cell, targets: Set[Cell], width: int, height: int, forbidden: Set[Cell],
) -> Optional[Tuple[Cell, ...]]:
    """Find a shortest interior cardinal route avoiding forbidden cells."""
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


def _rough_cells(grid: DungeonMap) -> Set[Cell]:
    """Infer rough terrain for feature clusters bordered solely by cavern floor."""
    rough = {
        (x, y) for y, row in enumerate(grid.rows)
        for x, tile in enumerate(row) if tile == "."
    }
    features = {
        (x, y) for y, row in enumerate(grid.rows)
        for x, tile in enumerate(row) if tile in FEATURES or tile in DIAGONALS
    }
    # Infer touching feature clusters together, without recursive terrain dependencies.
    for start in sorted(features):
        if start not in features:
            continue
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
                elif tile in " .|_L":
                    terrain.add("." if tile == "." else " ")
        if terrain == {"."}:
            rough.update(cluster)
    return rough


@dataclass(frozen=True)
class Stairway:
    """A straight footprint, ordered west-to-east or north-to-south."""

    cells: Tuple[Cell, ...]
    tile: str
    horizontal: bool
    spiral: bool = False
    landing_cells: Tuple[Cell, ...] = ()
    size: int = 0

    def __post_init__(self) -> None:
        """Normalize legacy spiral footprints to canonical cells and landings."""
        if self.spiral and not self.landing_cells:
            left = min(x for x, y in self.cells)
            top = min(y for x, y in self.cells)
            size = max(x for x, y in self.cells) - left + 1
            canonical = self.spiral_at(left, top, size, self.tile)
            object.__setattr__(self, "cells", canonical.cells)
            object.__setattr__(self, "landing_cells", canonical.landing_cells)
            object.__setattr__(self, "size", canonical.size)

    @classmethod
    def spiral_at(cls, left: int, top: int, size: int = 3, tile: str = "S",
                  landing_corner: str = "NW") -> "Stairway":
        """Construct a spiral footprint with a literal-floor corner landing."""
        if size not in (2, 3, 4) or tile not in "SsZ":
            raise ValueError("spiral stair requires size 2, 3, or 4 and tile S, s, or Z")
        if landing_corner not in ("NW", "NE", "SW", "SE"):
            raise ValueError("landing_corner must be NW, NE, SW, or SE")
        extent = 2 if size == 4 else 1
        lx = left + (size - extent if "E" in landing_corner else 0)
        ly = top + (size - extent if "S" in landing_corner else 0)
        landing = tuple((x, y) for y in range(ly, ly + extent)
                        for x in range(lx, lx + extent))
        cells = tuple((x, y) for y in range(top, top + size)
                      for x in range(left, left + size)
                      if (x, y) not in landing
                      and not (size == 3 and (x, y) == (left + 1, top + 1)))
        return cls(cells, tile, True, True, landing, size)

    def paint(self, rows: List[List[str]]) -> None:
        """Write footprint and literal-floor landings into a mutable ASCII map."""
        for x, y in self.cells:
            rows[y][x] = self.tile
        for x, y in self.landing_cells:
            rows[y][x] = " "

    @property
    def landings(self) -> Tuple[Cell, Cell]:
        """Return spiral landing endpoints or the two straight-run end cells."""
        if self.spiral:
            return self.landing_cells[0], self.landing_cells[-1]
        dx, dy = (1, 0) if self.horizontal else (0, 1)
        first, last = self.cells[0], self.cells[-1]
        return ((first[0] - dx, first[1] - dy), (last[0] + dx, last[1] + dy))

    @property
    def entrance(self) -> Cell:
        """Return the landing used to approach this stair or ramp direction."""
        if self.spiral:
            return self.landing_cells[0]
        index = 0 if self.tile in "er" else 1
        return self.landings[index if self.horizontal else 1 - index]

    @property
    def closed_end(self) -> Cell:
        """Return the opposite straight landing, or the spiral entrance."""
        if self.spiral:
            return self.entrance
        first, last = self.landings
        return last if self.entrance == first else first

    @property
    def approach(self) -> Tuple[Cell, Cell]:
        """Return the entrance and its outward corridor connection cell."""
        if self.spiral:
            return self.entrance, self.entrance
        x, y = self.entrance
        endpoint = self.cells[0] if self.entrance == self.landings[0] else self.cells[-1]
        return self.entrance, (2 * x - endpoint[0], 2 * y - endpoint[1])

    @property
    def walls(self) -> Set[Cell]:
        """Return straight stairwell wall cells excluding its entrance."""
        if self.spiral:
            return set()
        return {
            (x + dx, y + dy) for x, y in self.cells
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        } - set(self.cells) - {self.entrance}

    @property
    def clearance(self) -> Set[Cell]:
        """Reserve both levels' approaches, including the currently closed end."""
        if self.spiral:
            left = min(x for x, y in self.cells + self.landing_cells)
            top = min(y for x, y in self.cells + self.landing_cells)
            return {(x, y) for y in range(top, top + self.size)
                    for x in range(left, left + self.size)}
        dx, dy = (1, 0) if self.horizontal else (0, 1)
        first, last = self.landings
        return self.walls | set(self.cells + self.landings) | {
            (first[0] - dx, first[1] - dy), (last[0] + dx, last[1] + dy),
        }


def _spiral_runs(grid: DungeonMap) -> Dict[Cell, Stairway]:
    """Validate contiguous spiral footprints and index their stairway by cell."""
    remaining = {(x, y) for y, row in enumerate(grid.rows)
                 for x, tile in enumerate(row) if tile in "SsZ"}
    result = {}
    while remaining:
        start = min(remaining)
        tile = grid.tile(*start)
        cells = {start}
        pending = [start]
        remaining.remove(start)
        while pending:
            x, y = pending.pop()
            for dx, dy in DIRECTIONS:
                other = (x + dx, y + dy)
                if other in remaining and grid.tile(*other) == tile:
                    remaining.remove(other)
                    cells.add(other)
                    pending.append(other)
        left, top = min(x for x, y in cells), min(y for x, y in cells)
        size = max(x for x, y in cells) - left + 1
        run = None
        if size == max(y for x, y in cells) - top + 1 and size in (2, 3, 4):
            for corner in ("NW", "NE", "SW", "SE"):
                candidate = Stairway.spiral_at(left, top, size, tile, corner)
                if (set(candidate.cells) == cells
                        and all(grid.tile(*cell) == " " for cell in candidate.landing_cells)
                        and (size != 3 or grid.tile(left + 1, top + 1) in " #")):
                    run = candidate
                    break
        if run is None:
            raise ValueError("row {}, column {}: spiral staircase needs a 2x2, 3x3, "
                             "or 4x4 footprint and literal-floor corner landing".format(
                                 top + 1, left + 1))
        result.update((cell, run) for cell in cells)
    return result


def _stair_runs(grid: DungeonMap) -> Dict[Cell, Stairway]:
    """Recognize straight ASCII runs; ambiguous clusters retain per-tile symbols."""
    remaining = {
        (x, y) for y, row in enumerate(grid.rows)
        for x, tile in enumerate(row) if tile in "EeRr"
    }
    result = _spiral_runs(grid)
    for start in sorted(remaining):
        if start not in remaining:
            continue
        remaining.remove(start)
        cells = {start}
        pending = [start]
        tile = grid.tile(*start)
        while pending:
            x, y = pending.pop()
            for dx, dy in DIRECTIONS:
                neighbor = (x + dx, y + dy)
                if neighbor in remaining and grid.tile(*neighbor) == tile:
                    remaining.remove(neighbor)
                    cells.add(neighbor)
                    pending.append(neighbor)
        horizontal = len({y for x, y in cells}) == 1
        vertical = len({x for x, y in cells}) == 1
        if len(cells) > 1 and (horizontal or vertical):
            run = Stairway(tuple(sorted(cells)), tile, horizontal)
            result.update((cell, run) for cell in cells)
    return result
