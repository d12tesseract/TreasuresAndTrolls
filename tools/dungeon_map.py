"""Seeded dungeon generation, with compatibility exports for the map API.

Requires Python 3.7 or later; uses only the standard library.
"""

import math
import random
from collections import deque
from dataclasses import dataclass, replace
from heapq import heappop, heappush
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
    """Reject a named probability outside the finite unit interval."""
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
        """Return the walkable fraction, counting diagonal tiles as half squares."""
        area = sum(
            0.5 if tile in DIAGONALS else 1
            for row in self.grid.rows for tile in row if tile not in "#~"
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
    room_pair: Optional[Tuple[int, int]] = None
    centerline: Tuple[Cell, ...] = ()
    junctions: Tuple[Cell, ...] = ()


@dataclass(frozen=True)
class _PassageState:
    """Read-only geometry for one unchanged corridor list."""

    room_floor: Set[Cell]
    corridor_floor: Set[Cell]
    room_clearance: Set[Cell]
    corridor_clearance: Set[Cell]
    groups: List[Tuple[Set[Cell], Set[int]]]
    connected: Set[Tuple[int, int]]


class _PlacementError(ValueError):
    pass


def _validate_generation(options: GenerationOptions) -> None:
    """Validate map dimensions, probabilities, feature counts, and level links."""
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
    if not math.isfinite(options.density) or not 0 < options.density <= 0.4:
        raise ValueError("density must be greater than zero and no more than 0.4")
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
    """Sample a worked rectangle or irregular cavern footprint."""
    rough = rng.random() < options.rough_probability
    area = min(options.room_size, (options.width - 4) * (options.height - 4))
    area *= rng.uniform(0.65, 1.35)
    aspect = rng.uniform(0.65, 1.55)
    box_area = area / (0.65 if rough else 1)
    width = max(3, min(options.width - 4, round(math.sqrt(box_area * aspect))))
    height = max(3, min(options.height - 4, round(math.sqrt(box_area / aspect))))
    if not rough:
        return width, height, {
            (x, y) for y in range(height) for x in range(width)
        }, rough
    lobes = [
        (rng.uniform(0.1, 0.9) * (width - 1),
         rng.uniform(0.1, 0.9) * (height - 1),
         rng.uniform(0.2, 0.45) * width,
         rng.uniform(0.2, 0.45) * height)
        for _ in range(rng.randint(3, 6))
    ]
    resistance = {
        (x, y): min(
            ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
            for cx, cy, rx, ry in lobes
        ) + rng.uniform(-0.35, 0.35)
        for y in range(height) for x in range(width)
    }
    center = (width // 2, height // 2)
    cells = {center}
    frontier = [(resistance[center], center)]
    queued = {center}
    target = max(4, min(round(area), round(width * height * 0.85)))
    # Grow through adjacent floor only; low-resistance lobes need not touch.
    while len(cells) < target:
        _, (x, y) = heappop(frontier)
        cells.add((x, y))
        for dx, dy in DIRECTIONS:
            cell = (x + dx, y + dy)
            if cell in resistance and cell not in queued:
                heappush(frontier, (resistance[cell], cell))
                queued.add(cell)
    return width, height, cells, rough


def _position_room(options, rng, excluded_rooms, room_exclusion, rooms=()):
    """Sample clear positions, softly favoring nearby rooms of the same terrain."""
    width, height, local_cells, rough = _room_shape(options, rng)
    for _ in range(24):
        left = rng.randint(2, options.width - width - 2)
        top = rng.randint(2, options.height - height - 2)
        cells = {(left + x, top + y) for x, y in local_cells}
        if not cells.isdisjoint(excluded_rooms):
            continue
        if not cells.isdisjoint(room_exclusion):
            continue
        center = (left + width // 2, top + height // 2)
        if rooms and 0 < options.rough_probability < 1:
            distance, index = min(
                (math.hypot(center[0] - room.center[0], center[1] - room.center[1]), index)
                for index, room in enumerate(rooms)
            )
            radius = 4 * math.sqrt(min(
                options.room_size, (options.width - 4) * (options.height - 4),
            ))
            # A terrain boundary is less attractive, never forbidden.
            if (distance < radius and rooms[index].rough != rough
                    and rng.random() < 0.8 * (1 - distance / radius)):
                continue
        return _Room(center, cells, rough)
    return None


def _buffer(cells, radius=1):
    """Reserve rock on all sides, including diagonally adjacent squares."""
    return {
        (x + dx, y + dy) for x, y in cells
        for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)
    }


def _cardinal_contacts(cells, floor):
    return {
        (x + dx, y + dy) for x, y in cells for dx, dy in DIRECTIONS
    } & floor


def _place_rooms(options, rng, excluded):
    """Spend the room-area budget before any corridor affects placement."""
    rooms = []
    exclusion = set(excluded)
    area = misses = 0
    target = (options.width - 4) * (options.height - 4) * options.density
    while area < target and misses < 80:
        room = _position_room(options, rng, excluded, exclusion, rooms)
        if room is None:
            misses += 1
            continue
        misses = 0
        rooms.append(room)
        area += len(room.cells)
        exclusion.update(_buffer(room.cells, 3))
    if not rooms:
        raise _PlacementError("not enough space for a room outside stairway clearances")
    return rooms


def _openings(room, room_floor, corridor_floor, options, corridor_clearance=None):
    """Find exterior cells with exactly one room contact and no passage contact."""
    result = []
    unavailable = (_buffer(corridor_floor) if corridor_clearance is None
                   else corridor_clearance)
    other_rooms = room_floor - room.cells
    for inside in sorted(room.cells):
        for dx, dy in DIRECTIONS:
            outside = (inside[0] + dx, inside[1] + dy)
            if not (1 <= outside[0] < options.width - 1
                    and 1 <= outside[1] < options.height - 1):
                continue
            if outside in room_floor or outside in unavailable:
                continue
            contacts = {
                (outside[0] + nx, outside[1] + ny) for nx, ny in DIRECTIONS
            } & room_floor
            if contacts == {inside} and not (
                _buffer({outside}) & other_rooms
            ):
                result.append((outside, inside))
    return result


def _passage_groups(rooms, corridors):
    """Find direct room contacts through passage floor, without transiting rooms."""
    owners = {cell: index for index, room in enumerate(rooms) for cell in room.cells}
    remaining = set().union(*(set(c.cells) for c in corridors)) - set(owners)
    groups = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        cells, contacts = {start}, set()
        pending = [start]
        while pending:
            x, y = pending.pop()
            for dx, dy in DIRECTIONS:
                neighbor = (x + dx, y + dy)
                if neighbor in owners:
                    contacts.add(owners[neighbor])
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    cells.add(neighbor)
                    pending.append(neighbor)
        groups.append((cells, contacts))
    return groups


def _direct_pairs(rooms, corridors, groups=None):
    """Shared junctions also directly connect all incident room pairs."""
    return {
        (first, last) for _, contacts in (
            _passage_groups(rooms, corridors) if groups is None else groups
        )
        for first in contacts for last in contacts if first < last
    }


def _passage_state(rooms, corridors):
    room_floor = set().union(*(room.cells for room in rooms))
    corridor_floor = set().union(*(set(c.cells) for c in corridors)) - room_floor
    groups = _passage_groups(rooms, corridors)
    return _PassageState(
        room_floor, corridor_floor, _buffer(room_floor), _buffer(corridor_floor),
        groups, _direct_pairs(rooms, corridors, groups),
    )


def _room_passage(pair, rooms, corridors, options, rng, forbidden, max_length=None, state=None):
    """Route a unique direct link without touching unrelated floor."""
    pair = tuple(sorted(pair))
    state = _passage_state(rooms, corridors) if state is None else state
    if pair in state.connected:
        return None
    first, last = (rooms[index] for index in pair)
    room_floor, corridor_floor = state.room_floor, state.corridor_floor
    tile = "." if first.rough and last.rough else " "
    shared = []
    unavailable = room_floor | state.corridor_clearance | set(forbidden)
    other_rooms = room_floor - first.cells - last.cells
    for entrance in sorted(first.cells):
        for dx, dy in DIRECTIONS:
            outside = (entrance[0] + dx, entrance[1] + dy)
            if (outside in unavailable or not 1 <= outside[0] < options.width - 1
                    or not 1 <= outside[1] < options.height - 1):
                continue
            contacts = {
                (outside[0] + nx, outside[1] + ny) for nx, ny in DIRECTIONS
            } & room_floor
            exits = contacts & last.cells
            if (len(exits) == 1 and contacts == {entrance} | exits
                    and not _buffer({outside}) & other_rooms):
                shared.append((entrance, outside, next(iter(exits))))
    if shared and (max_length is None or max_length >= 1):
        centerline = rng.choice(shared)
        return _Corridor(centerline, tile, pair, centerline)
    blocked = state.room_clearance | state.corridor_clearance | set(forbidden)
    starts = _openings(first, room_floor, corridor_floor, options, state.corridor_clearance)
    ends = _openings(last, room_floor, corridor_floor, options, state.corridor_clearance)
    candidates = [
        (a, b) for a in starts for b in ends if a[0] != b[0]
        and (max_length is None or
             abs(a[0][0] - b[0][0]) + abs(a[0][1] - b[0][1]) + 1 <= max_length)
    ]
    rng.shuffle(candidates)
    candidates.sort(key=lambda item: (
        math.hypot(item[0][0][0] - item[1][0][0], item[0][0][1] - item[1][0][1]),
        abs(abs(item[0][0][0] - item[1][0][0])
            + abs(item[0][0][1] - item[1][0][1]) + 1 - options.corridor_length),
    ))
    for (start, entrance), (end, exit_cell) in candidates[:16]:
        if start in forbidden or end in forbidden:
            continue
        obstacles = blocked - {start, end}
        route = _route(start, {end}, options.width, options.height, obstacles)
        if route is None or (max_length is not None and len(route) > max_length):
            continue
        if tile == ".":
            try:
                route = tuple(_meander_path(
                    list(route), obstacles, options.width, options.height,
                    options.meandering, rng,
                ))
            except CavernRoutingError:
                continue
        footprint = set(_passage_cells(list(route)))
        if footprint & obstacles:
            continue
        if max_length is not None and len(footprint) > max_length:
            continue
        centerline = (entrance,) + tuple(route) + (exit_cell,)
        return _Corridor(_passage_cells(list(centerline)), tile, pair, centerline)
    return None


def _attachment_route(start, floor, options, forbidden, targets=None, max_length=None):
    """Attach to one preselected floor contact, never crossing earlier floor."""
    targets = floor if targets is None else targets
    if start in floor:
        return (start,), start
    nearby = _buffer({start}) & floor
    start_contacts = _cardinal_contacts({start}, floor)
    landings = {}
    for target in sorted(targets - forbidden):
        if (max_length is not None
                and abs(start[0] - target[0]) + abs(start[1] - target[1]) > max_length):
            continue
        neighbors = {(target[0] + dx, target[1] + dy) for dx, dy in DIRECTIONS}
        if len(neighbors & floor) >= 4:
            continue
        target_clearance = _buffer({target})
        if (nearby - target_clearance
                or (start_contacts and start_contacts != {target})):
            continue
        for landing in sorted(neighbors - floor - forbidden):
            contacts = {
                (landing[0] + dx, landing[1] + dy) for dx, dy in DIRECTIONS
            } & floor
            if contacts == {target}:
                if not (_buffer({landing}) & floor) - target_clearance:
                    landings[landing] = target
    if start in landings:
        return (start, landings[start]), landings[start]
    if not landings:
        return None
    obstacles = set(forbidden) | (_buffer(floor) - set(landings) - {start})
    route = _route(start, set(landings), options.width, options.height, obstacles)
    if route is None or (max_length is not None and len(route) > max_length):
        return None
    target = landings[route[-1]]
    return route + (target,), target


def _room_branch(source, target, rooms, corridors, options, rng, forbidden, max_length=None,
                 state=None):
    """Plan a single junction on a passage already incident to the target room."""
    pair = tuple(sorted((source, target)))
    state = _passage_state(rooms, corridors) if state is None else state
    connected = state.connected
    if pair in connected:
        return None
    room_floor, corridor_floor = state.room_floor, state.corridor_floor
    floor = room_floor | corridor_floor
    room_clearance = state.room_clearance
    targets = set().union(*(
        set(c.cells) for c in corridors if c.room_pair and target in c.room_pair
    )) - room_clearance
    for cells, contacts in state.groups:
        if source in contacts or any(tuple(sorted((source, other))) in connected
                                     for other in contacts):
            targets.difference_update(cells)
    starts = _openings(
        rooms[source], room_floor, corridor_floor, options, state.corridor_clearance,
    )
    rng.shuffle(starts)
    if not targets:
        return None
    tile = "." if rooms[source].rough and rooms[target].rough else " "
    floor_clearance = state.room_clearance | state.corridor_clearance
    starts.sort(key=lambda opening: math.hypot(
        opening[0][0] - rooms[target].center[0],
        opening[0][1] - rooms[target].center[1],
    ))
    for start, entrance in starts[:16]:
        obstacles = set(forbidden) | (room_clearance - {start})
        result = _attachment_route(
            start, floor - rooms[source].cells, options, obstacles, targets, max_length,
        )
        if result is None:
            continue
        route, junction = result
        if tile == ".":
            blocked = (obstacles | floor_clearance) - set(route)
            try:
                route = tuple(_meander_path(
                    list(route[:-1]), blocked | {junction},
                    options.width, options.height, options.meandering, rng,
                )) + (junction,)
            except CavernRoutingError:
                continue
            if set(_passage_cells(list(route[:-1]))) & blocked:
                continue
        centerline = (entrance,) + route
        footprint = _passage_cells(list(centerline))
        if max_length is not None and len(set(footprint) - floor) > max_length:
            continue
        return _Corridor(
            footprint, tile, pair, centerline, (junction,),
        )
    return None


def _connect_rooms(rooms, options, rng, forbidden, existing=None):
    """Give rooms one or two initial links; reserve long links for connectivity."""
    corridors = list(existing or ())
    components = list(range(len(rooms)))
    for _, contacts in _passage_groups(rooms, corridors):
        if contacts:
            group = {components[index] for index in contacts}
            representative = min(group)
            components[:] = [
                representative if item in group else item for item in components
            ]
    pairs = []
    pair_distances = {}
    for first, room in enumerate(rooms):
        for last in range(first + 1, len(rooms)):
            distance = min(
                (x - a) ** 2 + (y - b) ** 2
                for x, y in room.cells for a, b in rooms[last].cells
            )
            pair = (first, last)
            pairs.append((distance, rng.random(), pair))
            pair_distances[pair] = distance
    pairs.sort()
    neighbors = [[] for _ in rooms]
    for _, _, pair in pairs:
        for index in pair:
            neighbors[index].append(pair)
    attempted = {}
    linked = {corridor.room_pair for corridor in corridors if corridor.room_pair is not None}
    state = None

    def connect(pair, short_only):
        nonlocal state
        key = (pair, short_only)
        if pair in linked or attempted.get(key) == len(corridors):
            return False
        attempted[key] = len(corridors)
        if state is None:
            state = _passage_state(rooms, corridors)
        limit = options.corridor_length if short_only else None
        passage = None
        if limit is None or math.sqrt(pair_distances[pair]) - 1 <= limit:
            passage = _room_passage(pair, rooms, corridors, options, rng, forbidden, limit, state)
        if passage is None:
            for source, target in (pair, pair[::-1]):
                passage = _room_branch(
                    source, target, rooms, corridors, options, rng, forbidden, limit, state,
                )
                if passage is not None:
                    break
        if passage is None:
            return False
        try:
            _validate_network(rooms, corridors + [passage])
        except _PlacementError:
            return False
        corridors.append(passage)
        state = None
        linked.add(pair)
        first, last = pair
        old, new = components[last], components[first]
        components[:] = [new if item == old else item for item in components]
        return True

    order = list(range(len(rooms))) if existing is None else []
    rng.shuffle(order)
    earlier = set()
    for index in order:
        quota = 2 if rng.random() < 0.25 else 1
        candidates = [pair for pair in neighbors[index]
                      if (pair[1] if pair[0] == index else pair[0]) in earlier]
        local = candidates[:3]
        rng.shuffle(local)
        made = 0
        for pair in local + candidates[3:]:
            made += connect(pair, True)
            if made == quota:
                break
        earlier.add(index)
    while len(set(components)) > 1:
        joined = False
        for _, _, pair in pairs:
            if components[pair[0]] != components[pair[1]]:
                joined |= connect(pair, True)
        if joined:
            continue
        for _, _, pair in pairs:
            if components[pair[0]] != components[pair[1]] and connect(pair, False):
                joined = True
                break
        if not joined:
            raise _PlacementError("could not connect room components without crossing existing floor")
    return corridors


def _terrain(
    options: GenerationOptions, rng: random.Random,
    excluded_rooms: Optional[Set[Cell]] = None,
):
    """Place every room first, then carve a connected, contact-safe network."""
    rows = [["#"] * options.width for _ in range(options.height)]
    excluded_rooms = excluded_rooms or set()
    rooms = _place_rooms(options, rng, excluded_rooms)
    corridors = _connect_rooms(rooms, options, rng, excluded_rooms)
    _validate_network(rooms, corridors)
    lengths = _rebuild_layout(rows, rooms, corridors)
    return rows, rooms, lengths, corridors


def _validate_network(rooms, corridors):
    """Check physical contacts, not just the intended room graph."""
    room_floor = set().union(*(room.cells for room in rooms))
    room_owners = {cell: index for index, room in enumerate(rooms) for cell in room.cells}
    previous = set()
    pairs = set()
    for corridor in corridors:
        if corridor.room_pair is not None:
            if corridor.room_pair in pairs:
                raise _PlacementError("duplicate direct room connection")
            pairs.add(corridor.room_pair)
        if not corridor.centerline:
            previous.update(set(corridor.cells) - room_floor)
            continue
        cells = set(corridor.cells)
        outside = cells - room_floor
        endpoints = {corridor.centerline[0], corridor.centerline[-1]}
        if cells & room_floor != endpoints & room_floor:
            raise _PlacementError("a passage crosses an unrelated room")
        room_contacts = set()
        for first, last in zip(corridor.centerline, corridor.centerline[1:]):
            if first in room_floor and last not in room_floor:
                room_contacts.update(_buffer({last}) & rooms[room_owners[first]].cells)
            elif last in room_floor and first not in room_floor:
                room_contacts.update(_buffer({first}) & rooms[room_owners[last]].cells)
        if (_cardinal_contacts(outside, room_floor) != endpoints & room_floor
                or (_buffer(outside) & room_floor) - room_contacts):
            raise _PlacementError("a passage opens an unplanned room entrance")
        added = outside - previous
        contacts = _cardinal_contacts(added, previous)
        allowed = set(corridor.junctions)
        if (contacts != allowed - room_floor or (outside & previous) - allowed
                or (_buffer(added) & previous) - _buffer(allowed - room_floor)):
            raise _PlacementError("a passage makes an unplanned corridor contact")
        if len(contacts) > 1:
            raise _PlacementError("a passage rejoins the existing network more than once")
        previous.update(outside)
    direct = set()
    for _, contacts in _passage_groups(rooms, corridors):
        for first in sorted(contacts):
            for last in sorted(contacts):
                if first >= last:
                    continue
                pair = (first, last)
                if pair in direct:
                    raise _PlacementError("duplicate physical connection between rooms")
                direct.add(pair)


def _chamfer_rooms(rows, rooms, options, rng, reserved, tile, neighbors):
    """Chamfer worked rooms probabilistically and natural corners unconditionally."""
    width, height = options.width, options.height
    for room in rooms:
        if room.rough:
            continue
        for x, y in sorted(room.cells):
            adjacent = neighbors(x, y)
            if (x, y) in reserved or tile(x, y) not in " ." or any(value in DIAGONALS for value in adjacent):
                continue
            for diagonal in ("\\", "/"):
                if len(_diagonal_sides(diagonal, adjacent)) == 2:
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
                if len(_diagonal_sides(diagonal, adjacent)) == 2:
                    rows[y][x] = diagonal
                    break


def _door_candidates(rooms, options, rng, reserved, tile, neighbors):
    """Shuffle valid room entrances and retain nonadjacent door candidates."""
    width, height = options.width, options.height
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
    return available


def _decorate_doors(rows, available, options, rng):
    """Place exact door counts before rolling unspecified door probabilities."""
    specifications = (
        ("d", options.doors, options.door_probability),
        ("x", options.secret_doors, options.secret_door_probability),
        ("c", options.concealed_doors, options.concealed_door_probability),
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


def _decorate_floor(rows, options, rng, reserved, tile, neighbors):
    """Place exact floor features on eligible, shuffled floor squares."""
    width, height = options.width, options.height
    free = [
        (x, y) for y in range(1, height - 1) for x in range(1, width - 1)
        if tile(x, y) in " ."
        and (x, y) not in reserved
        and not any(value in DOORS or value in DIAGONALS for value in neighbors(x, y))
    ]
    rng.shuffle(free)
    features = (
        ("T", options.traps + options.pits),
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


def _decorate(
    rows, rooms: List[_Room], options: GenerationOptions, rng: random.Random,
    reserved: Optional[Set[Cell]] = None,
) -> DungeonMap:
    """Apply chamfers, doors, and floor features without disturbing stairways."""
    width, height = options.width, options.height
    reserved = reserved or set()

    def tile(x, y):
        """Read the mutable layout with solid stone outside its bounds."""
        return rows[y][x] if 0 <= x < width and 0 <= y < height else "#"

    def neighbors(x, y):
        """Read mutable neighboring tiles in cardinal direction order."""
        return tuple(tile(x + dx, y + dy) for dx, dy in DIRECTIONS)

    _chamfer_rooms(rows, rooms, options, rng, reserved, tile, neighbors)
    available = _door_candidates(rooms, options, rng, reserved, tile, neighbors)
    _decorate_doors(rows, available, options, rng)
    _decorate_floor(rows, options, rng, reserved, tile, neighbors)
    clear_invalid_diagonals(rows)
    return DungeonMap(tuple("".join(row) for row in rows))


def _reroute_corridors(
    corridors: List[_Corridor], forbidden: Set[Cell], width: int, height: int,
    rooms=None, options=None, rng=None,
) -> Tuple[List[_Corridor], int, int]:
    """Retain, reroute, or remove corridors colliding with stairwell cells."""
    retained = []
    rerouted = removed = 0
    for index, corridor in enumerate(corridors):
        if not forbidden.intersection(corridor.cells):
            retained.append(corridor)
            continue
        if corridor.room_pair is not None and rooms is not None:
            others = retained + [
                other for other in corridors[index + 1:]
                if not forbidden.intersection(other.cells)
            ]
            replacement = _room_passage(
                corridor.room_pair, rooms, others, options, rng, forbidden,
                options.corridor_length,
            )
        else:
            route = _route(corridor.cells[0], {corridor.cells[-1]}, width, height, forbidden)
            replacement = None if route is None else _Corridor(route, corridor.tile)
        if replacement is None:
            removed += 1
        else:
            retained.append(replacement)
            rerouted += 1
    return retained, rerouted, removed


def _rebuild_layout(rows, rooms: List[_Room], corridors: List[_Corridor]) -> List[int]:
    """Repaint rooms and corridors and count newly carved corridor squares."""
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
    """Remove rooms and corridors disconnected from the stairway entrances."""
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


def _floor_distances(rows, options):
    """Measure interior cardinal distances from the existing carved floor."""
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
    return floor, distances


def _stairway_symbols(options, rng, incoming, down_count):
    """Choose the ordered stair and ramp symbols and their footprint length."""
    if options.levels > 1:
        symbols = ([] if incoming else ["E"]) + [
            "r" if rng.random() * 100 < options.ramp_probability else "e"
            for _ in range(down_count)
        ] + ["r"] * options.ramps_down
        length = options.stair_length
    else:
        symbols = (
            ["e"] * (options.stairs_down or 0) + ["E"] * options.stairs_up
            + ["r"] * options.ramps_down + ["R"] * options.ramps_up
        )
        length = 1
    return symbols, length


def _stair_walls(passage):
    """Keep inherited spirals isolated except at their corner landing."""
    if not passage.spiral:
        return passage.walls
    x, y = passage.entrance
    approaches = {(x + dx, y + dy) for dx, dy in DIRECTIONS} - passage.clearance
    return _buffer(passage.clearance) - passage.clearance - approaches


def _stairway_candidates(symbol, length, blocked, room_cells, floor, distances, options, rng):
    """Rank shuffled straight footprints by floor collisions and access distance."""
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
    return candidates


def _choose_stairway(candidates, symbol, length, passages, floor, options):
    """Choose the first ranked footprint whose entrance can reach existing floor."""
    forbidden = set().union(*(_stair_walls(p) | set(p.cells + p.approach) for p in passages))
    for _, (x, y, horizontal) in candidates:
        dx, dy = (1, 0) if horizontal else (0, 1)
        candidate = Stairway(tuple((x + step * dx, y + step * dy)
                                  for step in range(length)), symbol, horizontal)
        exclusion = forbidden | candidate.walls | set(candidate.cells)
        if _stair_access(candidate, floor - exclusion, options, exclusion) is not None:
            return candidate
    raise _PlacementError("not enough space for separated stairways and their landings")


def _reserve_stairways(rows, options, rng, incoming, down_count, rooms):
    """Reserve inherited stairways and place new, separated straight footprints."""
    passages = list(incoming)
    blocked = set()
    room_cells = set().union(*(room.cells for room in rooms))
    floor, distances = _floor_distances(rows, options)
    for passage in passages:
        if room_cells & (set(passage.cells + passage.approach) | _stair_walls(passage)):
            raise _PlacementError("an inherited stairway overlaps a room")
        blocked.update(passage.clearance | _stair_walls(passage))
    symbols, length = _stairway_symbols(options, rng, incoming, down_count)
    for symbol in symbols:
        candidates = _stairway_candidates(
            symbol, length, blocked, room_cells, floor, distances, options, rng,
        )
        passage = _choose_stairway(candidates, symbol, length, passages, floor, options)
        passages.append(passage)
        blocked.update(passage.clearance)
    return passages


def _stair_access(passage, floor, options, forbidden):
    """Connect a protected two-cell stair approach to one existing floor contact."""
    entrance, start = passage.approach
    if set(passage.approach) & forbidden:
        return None
    if entrance in floor:
        if start in floor:
            return (entrance, start), start
        access, junction = (start, entrance), entrance
    else:
        if entrance != start and _cardinal_contacts({entrance}, floor) - {start}:
            return None
        prefix = {entrance} | {
            (entrance[0] + dx, entrance[1] + dy) for dx, dy in DIRECTIONS
        }
        obstacles = forbidden | (prefix - {start} if entrance != start else set())
        result = _attachment_route(start, floor, options, obstacles)
        if result is None:
            return None
        route, junction = result
        access = route if entrance == start else (entrance,) + route
    added = set(access) - floor
    if (_cardinal_contacts(added, floor) != {junction}
            or (_buffer(added) & floor) - _buffer({junction})):
        return None
    return access, junction


def _connect_stairways(rows, options, passages, rooms, corridors, forbidden, rng):
    """Reroute collisions, carve stair approaches, and prune inaccessible terrain."""
    generated = any(corridor.room_pair is not None for corridor in corridors)
    retained, rerouted, removed = _reroute_corridors(
        corridors, forbidden, options.width, options.height, rooms, options, rng,
    )
    corridors[:] = retained
    if generated and removed:
        corridors[:] = _connect_rooms(
            rooms, options, rng,
            forbidden | {cell for passage in passages for cell in passage.approach},
            existing=corridors,
        )
    _rebuild_layout(rows, rooms, corridors)
    floor = {
        (x, y) for y, row in enumerate(rows) for x, tile in enumerate(row)
        if tile in " ."
    }
    for passage in passages:
        blocked = forbidden | {
            cell for other in passages if other is not passage
            for cell in other.approach if cell not in floor
        }
        result = _stair_access(passage, floor, options, blocked)
        if result is None:
            raise _PlacementError("could not route a collision-free entry corridor to a stairway")
        access, junction = result
        if set(access) <= floor:
            continue
        corridors.append(_Corridor(access, " ", centerline=access, junctions=(junction,)))
        for x, y in access:
            if rows[y][x] == "#":
                rows[y][x] = " "
            floor.add((x, y))
    for passage in passages:
        passage.paint(rows)
    removed_rooms, orphaned_corridors = _prune_unreachable(
        rows, rooms, corridors, [passage.entrance for passage in passages],
    )
    if generated and removed_rooms:
        raise _PlacementError("stairway repairs disconnected the room network")
    _validate_network(rooms, corridors)
    return rerouted, removed + orphaned_corridors, removed_rooms


def _place_stairways(
    rows, options: GenerationOptions, rng: random.Random,
    incoming: Tuple[Stairway, ...], down_count: int,
    rooms: List[_Room], corridors: List[_Corridor],
) -> Tuple[Tuple[Stairway, ...], Set[Cell], Tuple[str, ...]]:
    """Place stairways, reconnect their approaches, and report layout repairs."""
    passages = _reserve_stairways(rows, options, rng, incoming, down_count, rooms)
    footprints = {cell for passage in passages for cell in passage.cells}
    approaches = {cell for passage in passages for cell in passage.approach}
    walls = set().union(*(_stair_walls(passage) for passage in passages))
    if walls & (footprints | approaches):
        raise _PlacementError("stairway walls overlap another passage or its entrance")
    rerouted, removed, removed_rooms = _connect_stairways(
        rows, options, passages, rooms, corridors, walls | footprints, rng,
    )
    notes = []
    if rerouted:
        notes.append("Rerouted {} corridors around stairways.".format(rerouted))
    if removed or removed_rooms:
        notes.append("Removed {} corridors and {} unreachable rooms after stairway collisions.".format(
            removed, removed_rooms,
        ))
    reserved = footprints | approaches | walls
    reserved.update(cell for passage in passages if passage.spiral
                    for cell in passage.clearance)
    return tuple(passages), reserved, tuple(notes)


def _generate_level(
    options: GenerationOptions, rng: random.Random, seed: int,
    incoming: Tuple[Stairway, ...] = (), down_count: int = 0, depth_feet: int = 0,
) -> GeneratedDungeon:
    """Retry layouts until all requested features and inherited stairs fit."""
    problem = None
    excluded_rooms = set().union(*(
        _buffer(passage.clearance) for passage in incoming
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
        "increase map size, adjust room density/size or reduce feature counts, "
        "or change seed".format(problem)
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
            replace(passage, tile={"e": "E", "r": "R", "s": "S", "Z": "Z"}[passage.tile])
            for passage in level.stairways if passage.tile in "ersZ"
        )
    return replace(levels[0], additional_levels=tuple(levels[1:]))
