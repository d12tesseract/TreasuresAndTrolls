"""Seeded dungeon generation, with compatibility exports for the map API.

Requires Python 3.7 or later; uses only the standard library.
"""

import math
import random
from collections import deque
from dataclasses import dataclass, replace
from typing import Callable, List, Optional, Sequence, Set, Tuple

from dungeon_geometry import (
    Cell, DIAGONALS, DIRECTIONS, DOORS, DungeonMap, FEATURES, FLOORS, Point,
    Stairway, TILES, _diagonal_sides, _door_axis, _finite_positive, _neighbors,
    _open_sides, _partition, _rough_cells, _route, _stair_runs,
    clear_invalid_diagonals, is_connected, parse_ascii, validate_map,
)
from dungeon_render import (
    SVG_NAMESPACE, _Edge, _wall_edges,
    render_rows, svg_document,
)
from dungeon_cli import (
    add_render_arguments, nonnegative_integer, positive_number, probability,
    render_options,
)
from dungeon_passages import CavernRoutingError, _meander_path, _passage_cells, _path


def _probability(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("{} must be between zero and one".format(name))


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


def _terrain(
    options: GenerationOptions, rng: random.Random,
    excluded_rooms: Optional[Set[Cell]] = None,
):
    rows = [["#"] * options.width for _ in range(options.height)]
    occupied = set()
    room_exclusion = set()
    rooms = []
    lengths = []
    corridors = []
    excluded_rooms = excluded_rooms or set()
    target = options.width * options.height * options.density
    misses = 0
    while len(occupied) < target and misses < 80:
        width, height, local_cells, rough = _room_shape(options, rng)
        room = None
        for _ in range(24):
            left = rng.randint(1, options.width - width - 1)
            top = rng.randint(1, options.height - height - 1)
            cells = {(left + x, top + y) for x, y in local_cells}
            if not cells.isdisjoint(excluded_rooms):
                continue
            if not cells.isdisjoint(room_exclusion):
                continue
            room = _Room((left + width // 2, top + height // 2), cells, rough)
            break
        if room is None:
            misses += 1
            continue
        misses = 0
        path = []
        if rooms:
            connection = None
            for previous in rooms:
                route = _path(previous.center, room.center, rng.choice((True, False)))
                length = sum(cell not in occupied and cell not in room.cells for cell in route)
                score = (abs(length - options.corridor_length), len(route))
                if connection is None or score < connection[0]:
                    connection = (score, route, previous)
            _, path, previous = connection
            corridor_tile = "." if previous.rough and room.rough else " "
            if corridor_tile == ".":
                opening = next(index for index, cell in enumerate(path) if cell in room.cells)
                centerline = _meander_path(
                    path[:opening], occupied | room.cells, options.width, options.height,
                    options.meandering, rng,
                )
                path = list(_passage_cells(centerline + path[opening:]))
            lengths.append(sum(cell not in occupied and cell not in room.cells for cell in path))
            corridors.append(_Corridor(tuple(path), corridor_tile))
            for x, y in path:
                if rows[y][x] == "#":
                    rows[y][x] = corridor_tile
                occupied.add((x, y))
        for x, y in room.cells:
            rows[y][x] = "." if room.rough else " "
        occupied.update(room.cells)
        room_exclusion.update(
            (x + dx, y + dy) for x, y in room.cells.union(path)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        )
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
            if (x, y) in reserved or tile(x, y) not in " ." or any(value in DIAGONALS for value in adjacent):
                continue
            for diagonal in ("\\", "/"):
                if _diagonal_sides(diagonal, adjacent):
                    if rng.random() < options.chamfer_probability:
                        rows[y][x] = diagonal
                    break

    for y in range(1, height - 1):
        for x in range(1, width - 1):
            if (x, y) in reserved or tile(x, y) != ".":
                continue
            adjacent = neighbors(x, y)
            if any(value in DIAGONALS for value in adjacent):
                continue
            for diagonal in ("\\", "/"):
                if _diagonal_sides(diagonal, adjacent):
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
    clear_invalid_diagonals(rows)
    return DungeonMap(tuple("".join(row) for row in rows))


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
    room_count, corridor_count = len(rooms), len(corridors)
    rooms[:] = [room for room in rooms if room.cells <= visited]
    corridors[:] = [corridor for corridor in corridors if visited.issuperset(corridor.cells)]
    for y, row in enumerate(rows):
        for x in range(len(row)):
            if (x, y) not in visited:
                row[x] = "#"
    return room_count - len(rooms), corridor_count - len(corridors)


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
        unavailable = blocked | room_cells
        for horizontal in (True, False):
            dx, dy = (1, 0) if horizontal else (0, 1)
            template = Stairway(tuple((step * dx, step * dy) for step in range(length)),
                                symbol, horizontal)
            clearance = template.clearance
            solid = set(template.cells) | template.walls
            ax, ay = template.approach[-1]
            # Leave side walls and two-square approaches inside the stone border.
            for y in range(2 + dy, options.height - 2 - length * dy):
                for x in range(2 + dx, options.width - 2 - length * dx):
                    if any((x + ox, y + oy) in unavailable for ox, oy in clearance):
                        continue
                    collisions = sum((x + ox, y + oy) in floor for ox, oy in solid)
                    candidates.append(((collisions, distances[(x + ax, y + ay)]),
                                       (x, y, horizontal)))
        rng.shuffle(candidates)
        candidates.sort(key=lambda item: item[0])
        passage = None
        forbidden = set().union(*(p.walls | set(p.cells) for p in passages))
        for _, (x, y, horizontal) in candidates:
            dx, dy = (1, 0) if horizontal else (0, 1)
            candidate = Stairway(tuple((x + step * dx, y + step * dy)
                                      for step in range(length)), symbol, horizontal)
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
        try:
            rows, rooms, lengths, corridors = _terrain(options, rng, excluded_rooms)
            stairways, reserved = (), set()
            notes = ()
            if options.levels > 1 or any((
                options.stairs_down, options.stairs_up, options.ramps_down, options.ramps_up,
            )):
                stairways, reserved, notes = _place_stairways(
                    rows, options, rng, incoming, down_count, rooms, corridors,
                )
                lengths = _rebuild_layout([row[:] for row in rows], rooms, corridors)
            grid = _decorate(rows, rooms, options, rng, reserved)
        except (_PlacementError, CavernRoutingError) as error:
            problem = error
            continue
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
