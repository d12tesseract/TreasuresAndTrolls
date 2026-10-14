"""ASCII dungeon geometry, validation, connectivity, and stair footprints."""

import math
from dataclasses import dataclass
from typing import AbstractSet, Optional, Sequence, Set, Tuple


TILES = frozenset("# .\\/|_LDSCTEURIP")
FLOORS = frozenset(" .|_LDSCTEURIP")
DOORS = frozenset("DSC")
DIAGONALS = frozenset("\\/")
FEATURES = frozenset("DSCTEURIP")
DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))  # N, E, S, W
Point = Tuple[float, float]
Cell = Tuple[int, int]


def _finite_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("{} must be finite and greater than zero".format(name))


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
            if tile not in "\\/DSC|_L":
                continue
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


def reachable_cells(
    grid: DungeonMap, start: Cell, blocked: AbstractSet[Cell] = frozenset(),
) -> Set[Cell]:
    """Flood walkable geometry, respecting partitions and temporarily closed gates."""
    if start in blocked or not _open_sides(grid, *start):
        return set()
    visited = {start}
    pending = [start]
    while pending:
        x, y = pending.pop()
        for side in _open_sides(grid, x, y):
            dx, dy = DIRECTIONS[side]
            neighbor = (x + dx, y + dy)
            if (
                neighbor not in blocked and neighbor not in visited
                and (side + 2) % 4 in _open_sides(grid, *neighbor)
                and not _partition(grid, x, y, side)
            ):
                visited.add(neighbor)
                pending.append(neighbor)
    return visited


def is_connected(grid: DungeonMap) -> bool:
    """Check walkable connectivity, treating doors and covered pits as passable."""
    validate_map(grid)
    cells = {
        (x, y)
        for y, row in enumerate(grid.rows)
        for x, tile in enumerate(row)
        if tile != "#"
    }
    return bool(cells) and reachable_cells(grid, next(iter(cells))) == cells


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
