"""Winding cavern centerlines and their chamfer-ready floor footprints."""

import math
import random
from collections import Counter
from heapq import heappop, heappush
from typing import List, Optional, Set, Tuple

from dungeon_geometry import Cell, DIRECTIONS


HEADINGS = (
    (0, -1), (1, -2), (1, -1), (2, -1),
    (1, 0), (2, 1), (1, 1), (1, 2),
    (0, 1), (-1, 2), (-1, 1), (-2, 1),
    (-1, 0), (-2, -1), (-1, -1), (-1, -2),
)


class CavernRoutingError(ValueError):
    pass


def _path(start: Cell, end: Cell, horizontal_first: bool) -> List[Cell]:
    """Connect two cells with an axis-aligned, single-elbow centerline."""
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


def _segment_steps(start: Cell, end: Cell) -> Tuple[Cell, ...]:
    """Expand a long heading into its intermediate cell and endpoint."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    if max(abs(dx), abs(dy)) == 2:
        return ((start[0] + (dx // 2 if abs(dx) == 2 else 0),
                 start[1] + (dy // 2 if abs(dy) == 2 else 0)), end)
    return (end,)


def _passage_cells(path: List[Cell]) -> Tuple[Cell, ...]:
    """Fill both elbows of diagonal steps, leaving legal half-square wall corners."""
    cells = dict.fromkeys(path[:1])
    for first, last in zip(path, path[1:]):
        for following in _segment_steps(first, last):
            if first[0] != following[0] and first[1] != following[1]:
                cells[(first[0], following[1])] = None
                cells[(following[0], first[1])] = None
            cells[following] = None
            first = following
    if path:
        cells.pop(path[-1])
        cells[path[-1]] = None
    return tuple(cells)


def _cavern_resistance(
    occupied: Set[Cell], width: int, height: int,
    amount: float, rng: random.Random,
):
    """Interpolate seeded resistance bands over the unoccupied interior."""
    spacing = 6
    noise = [
        [rng.random() for _ in range(width // spacing + 2)]
        for _ in range(height // spacing + 2)
    ] if amount else []
    resistance = {}
    for y in range(1, height - 1):
        row, fy = divmod(y, spacing)
        fy /= spacing
        for x in range(1, width - 1):
            if (x, y) in occupied:
                continue
            value = 0
            if amount:
                column, fx = divmod(x, spacing)
                fx /= spacing
                upper = noise[row][column] * (1 - fx) + noise[row][column + 1] * fx
                lower = noise[row + 1][column] * (1 - fx) + noise[row + 1][column + 1] * fx
                value = upper * (1 - fy) + lower * fy
            resistance[(x, y)] = math.exp(6 * amount * value)
    return resistance


def _cavern_field(
    target: Cell, occupied: Set[Cell], width: int, height: int,
    amount: float, rng: random.Random,
):
    """Measure obstacle-aware target costs through broad resistance bands."""
    resistance = _cavern_resistance(occupied, width, height, amount, rng)
    distances = {}
    if target not in resistance:
        return resistance, distances
    distances[target] = 0
    pending = [(0, target)]
    neighbors = [(dx, dy, math.hypot(dx, dy)) for dx, dy in HEADINGS[::2]]
    while pending:
        distance, cell = heappop(pending)
        if distance != distances[cell]:
            continue
        x, y = cell
        local_cost = resistance[cell]
        for dx, dy, length in neighbors:
            end = (x + dx, y + dy)
            end_cost = resistance.get(end)
            if end_cost is None:
                continue
            if dx and dy:
                side_x = resistance.get((x + dx, y))
                side_y = resistance.get((x, y + dy))
                if side_x is None or side_y is None:
                    continue
                cost = length * (local_cost + end_cost + side_x + side_y) / 4
            else:
                cost = length * (local_cost + end_cost) / 2
            following = distance + cost
            if following < distances.get(end, math.inf):
                distances[end] = following
                heappush(pending, (following, end))
    return resistance, distances


def _cavern_choices(
    cell, previous, target, used, segments, visited, resistance, distances, amount,
):
    """Rank untangled next headings by target cost and forward alignment."""
    dx, dy = target[0] - cell[0], target[1] - cell[1]
    older = set(used)
    for recent in segments[-2:]:
        older.difference_update(recent)
    older.discard(cell)
    result = []
    for sx, sy in HEADINGS:
        end = (cell[0] + sx, cell[1] + sy)
        if end not in distances:
            continue
        steps = _segment_steps(cell, end)
        if any(point in visited for point in steps):
            continue
        footprint = set(_passage_cells([cell, end]))
        if any((x, y) not in resistance or (x, y) in older
               or any((x + nx, y + ny) in older for nx, ny in DIRECTIONS)
               for x, y in footprint):
            continue
        length = math.hypot(sx, sy)
        cost = length * sum(resistance[point] for point in footprint) / len(footprint)
        if previous is not None:
            alignment = (sx * previous[0] + sy * previous[1]) / (length * math.hypot(*previous))
            cost *= 1 + 0.2 * amount * (1 - alignment)
        result.append(((distances[end] + cost, -(dx * sx + dy * sy) / length), end, footprint))
    result.sort(key=lambda choice: choice[0])
    return [(end, footprint) for _, end, footprint in result]


def _cavern_path(
    start: Cell, target: Cell, occupied: Set[Cell], width: int, height: int,
    amount: float, rng: random.Random, heading: Optional[Cell] = None,
) -> Optional[List[Cell]]:
    """Follow low-resistance bends, backtracking around the passage's own footprint."""
    if start == target:
        return [start]
    resistance, distances = _cavern_field(target, occupied, width, height, amount, rng)
    if start not in distances:
        return None
    path = [start]
    segments = []
    used = Counter({start: 1})
    visited = {start}

    def choices(cell, previous):
        """Evaluate headings against the current backtracking footprint."""
        return _cavern_choices(
            cell, previous, target, used, segments, visited, resistance, distances, amount,
        )

    pending = [choices(start, heading)]
    budget = max(128, width * height * 4)
    while path[-1] != target and pending and budget:
        budget -= 1
        if not pending[-1]:
            pending.pop()
            if segments:
                used.subtract(segments.pop())
                used += Counter()
                visited.difference_update(_segment_steps(path[-2], path[-1]))
                path.pop()
            continue
        end, footprint = pending[-1].pop(0)
        previous = (end[0] - path[-1][0], end[1] - path[-1][1])
        path.append(end)
        visited.update(_segment_steps(path[-2], end))
        used.update(footprint)
        segments.append(footprint)
        if end != target:
            pending.append(choices(end, previous))
    return path if path[-1] == target else None


def _meander_path(
    path: List[Cell], occupied: Set[Cell], width: int, height: int,
    amount: float, rng: random.Random,
) -> List[Cell]:
    """Replace a corridor's unoccupied suffix with a winding cavern route."""
    if len(path) < 2:
        return path
    first = next((index for index, cell in enumerate(path) if cell not in occupied), len(path))
    if first == len(path):
        return path
    previous = None if first == 0 else (
        path[first][0] - path[first - 1][0], path[first][1] - path[first - 1][1],
    )
    routed = _cavern_path(
        path[first], path[-1], occupied - set(path[first:]), width, height, amount, rng, previous,
    )
    if routed is None:
        raise CavernRoutingError("no untangled cavern route reaches the room opening")
    return path[:first] + routed
