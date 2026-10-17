"""Place the Markdown puzzle catalog into sequentially stocked dungeon levels."""

import random
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dungeon_encounters import (
    EncounterArea, EncounterLevel, EncounterRules, basic_roll, generate_encounters,
    monster_encounter, number_areas, puzzle_treasure, treasure_value,
)
from dungeon_games import field as game_field, validate_strategy_game
from dungeon_geometry import (
    Cell, DungeonMap, Stairway, _open_sides, _route, clear_invalid_diagonals,
    is_connected, reachable_cells,
)
from dungeon_map import (
    GeneratedDungeon, GenerationOptions, _buffer, _probability, generate_dungeon,
)


CATALOG_PATH = Path(__file__).with_suffix(".md")
PUZZLE_COUNT = 50
PASSAGE_PUZZLES = frozenset((
    2, 3, 6, 8, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 24, 25, 26, 27, 29, 30,
    33, 34, 36, 38, 39,
    42, 44, 46, 48, 50,
))
REQUIRED_ITEMS = {
    3: ("sun lens",),
    5: ("bronze striker",),
    9: ("ear-of-wheat token", "bandaged-hand token", "lantern token"),
    10: ("brass jailer's badge",),
    12: ("inscribed name fragment",),
    27: ("silver chime", "warm coal crystal", "copper gear"),
    28: ("recipe tablet",),
    30: ("true oath tablet",),
}
STAIR_PUZZLES = frozenset((3, 8, 13, 15, 26, 30, 39))


@dataclass(frozen=True)
class PuzzleDefinition:
    number: int
    name: str
    category: str
    body: str
    passage: bool
    required_items: Tuple[str, ...]
    min_level: int = 1
    max_level: Optional[int] = None
    consequence_rules: str = ""

    def eligible(self, depth: int) -> bool:
        """Report whether this puzzle's supported level range includes the depth."""
        return self.min_level <= depth and (self.max_level is None or depth <= self.max_level)


@dataclass(frozen=True)
class PuzzleItem:
    name: str
    source_level: int
    source_cell: Cell


@dataclass(frozen=True)
class PlacedPuzzle:
    definition: PuzzleDefinition
    cell: Cell
    gate: Optional[Cell] = None
    protected_cells: Tuple[Cell, ...] = ()
    items: Tuple[PuzzleItem, ...] = ()
    next_level: Optional[int] = None
    reward_cell: Optional[Cell] = None


def load_puzzles(path: Path = CATALOG_PATH) -> Tuple[PuzzleDefinition, ...]:
    """Load and validate the complete catalog, replacing example item locations."""
    text = path.read_text(encoding="utf-8")
    consequence_rules = re.search(
        r"(?ms)^(\*\*Running consequences:\*\*.*?)(?=^## |\Z)", text,
    )
    entries = re.findall(
        r"(?ms)^### (\d+)\. ([^\n]+)\n(.*?)(?=^### \d+\. |^## |\Z)", text,
    )
    categories = {
        int(number): (name.strip(), category.strip())
        for number, name, category in re.findall(
            r"(?m)^\| (\d+) \| ([^|]+) \| ([^|]+) \|", text,
        )
    }
    if [int(entry[0]) for entry in entries] != list(range(1, PUZZLE_COUNT + 1)):
        raise ValueError("puzzle catalog must contain puzzles 1 through {} exactly once".format(PUZZLE_COUNT))
    result = []
    for number_text, name, body in entries:
        number = int(number_text)
        if number not in categories or categories[number][0] != name:
            raise ValueError("puzzle catalog index disagrees with puzzle {}".format(number))
        for field in ("Setup", "Solution", "Failure and hints", "Reward"):
            if "**{}:**".format(field) not in body:
                raise ValueError("puzzle {} is missing {}".format(number, field))
        has_consequences = "**Consequences:**" in body
        if has_consequences and consequence_rules is None:
            raise ValueError("puzzle consequences require shared consequence rules")
        min_level, max_level = _puzzle_levels(body)
        # Generated item locations replace the catalog's illustrative locations.
        body = re.sub(
            r"(?ms)^\*\*Required items?:\*\*.*?(?=^\*\*|\Z)", "", body,
        )
        result.append(PuzzleDefinition(
            number, name, categories[number][1], body.strip(),
            number in PASSAGE_PUZZLES, REQUIRED_ITEMS.get(number, ()),
            min_level, max_level,
            consequence_rules[1].strip() if has_consequences else "",
        ))
    return tuple(result)


def _puzzle_levels(body: str) -> Tuple[int, Optional[int]]:
    """Validate a strategy game and parse its inclusive dungeon-level bounds."""
    if "**Game:**" not in body:
        return 1, None
    validate_strategy_game(body)
    levels = re.fullmatch(r"([1-9]\d*)(?:-([1-9]\d*)|(\+))", game_field(body, "Dungeon levels"))
    if levels is None:
        raise ValueError("strategy puzzle levels must be a positive range or minimum+")
    minimum = int(levels[1])
    maximum = int(levels[2]) if levels[2] else None
    if maximum is not None and maximum < minimum:
        raise ValueError("strategy puzzle level range is reversed")
    return minimum, maximum


def _wing_connection(level, descending, blocked):
    """Remove superseded down exits and route around protected features to a wing."""
    old_width, height = level.grid.width, level.grid.height
    rows = [list(row) for row in level.grid.rows]
    removed = tuple(passage for passage in level.stairways
                    if descending and passage.tile in "er")
    for passage in removed:
        for x, y in passage.cells:
            rows[y][x] = "#"
    stairways = tuple(passage for passage in level.stairways if passage not in removed)
    grid = DungeonMap(tuple("".join(row) for row in rows))
    forbidden = set().union(*(passage.clearance for passage in stairways))
    forbidden.update((x + dx, y + dy) for x, y in blocked
                     for dx, dy in ((0, 0), (0, -1), (1, 0), (0, 1), (-1, 0)))
    for y, row in enumerate(grid.rows):
        for x, tile in enumerate(row):
            if tile in "DXC":
                forbidden.update((x + dx, y + dy)
                                 for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    targets = {
        (x, y) for y, row in enumerate(grid.rows) for x, tile in enumerate(row)
        if tile in " .T\\/" and (x, y) not in forbidden
    }
    candidates = []
    for y in range(3, height - 3):
        route = _route((old_width - 2, y), targets, old_width, height, forbidden)
        if route is not None:
            candidates.append(route)
    if not candidates:
        raise ValueError("cannot connect a puzzle wing without damaging protected features; "
                         "increase map height/density or change seed")
    return rows, stairways, removed, min(candidates, key=lambda path: (len(path), path))


def _wing_placements(definitions, depth, old_width, height, descending):
    """Lay out independent puzzle rooms, reward rooms, and in-room spiral stairs."""
    half_height = min(2, (height - 5) // 2)
    y, hall_y = half_height + 1, height - 2
    placements = []
    new_stairs = []
    centers = []
    cursor = old_width
    for definition in definitions:
        center = (cursor + 4, y)
        has_exit = descending and definition.number in STAIR_PUZZLES
        reward = (cursor + 15, y) if definition.passage and not has_exit else None
        gate = (center[0] + 3, y) if reward else None
        centers.append(center)
        end = center[0]
        if reward:
            centers.append(reward)
            end = reward[0]
        if has_exit:
            stairs = Stairway.spiral_at(center[0] - 1, y - 1, size=3, tile="s")
            new_stairs.append(stairs)
            center = (center[0] + 2, y)
        placements.append(PlacedPuzzle(
            definition, center, gate=gate, next_level=depth + 1 if has_exit else None,
            reward_cell=reward,
        ))
        cursor = end + 4
    return placements, new_stairs, centers, cursor, half_height


def _wing_corridors(route, placements, old_width, hall_y):
    """Build the common hall and each chamber's independent access corridor."""
    corridors = {(x, route[0][1]) for x in range(old_width - 2, old_width + 1)}
    corridors.update((old_width, cy) for cy in range(min(route[0][1], hall_y), hall_y + 1))
    corridors.update((x, hall_y) for x in range(old_width, placements[-1].cell[0] + 1))
    for placement in placements:
        cx, cy = placement.cell
        if placement.next_level:
            cx -= 2
        corridors.update((cx, yy) for yy in range(cy, hall_y + 1))
        if placement.reward_cell:
            end = placement.reward_cell[0]
            corridors.update((x, cy) for x in range(cx, end + 1))
    return corridors


def _carve_wing(rows, route, placements, new_stairs, centers, width, half_height):
    """Carve the wing's floor and paint gates and stairs, counting new passages."""
    old_width = len(rows[0])
    for row in rows:
        row.extend(["#"] * (width - old_width))
    added = 0
    for x, cy in route:
        if rows[cy][x] == "#":
            rows[cy][x] = " "
            added += 1
    corridors = _wing_corridors(route, placements, old_width, len(rows) - 2)
    footprints = []
    for cx, cy in centers:
        cells = tuple((x, yy) for x in range(cx - 2, cx + 3)
                      for yy in range(cy - half_height, cy + half_height + 1))
        footprints.append(cells)
        for x, yy in cells:
            rows[yy][x] = " "
    for x, cy in corridors:
        if rows[cy][x] == "#":
            rows[cy][x] = " "
            added += 1
    for placement in placements:
        if placement.gate:
            rows[placement.gate[1]][placement.gate[0]] = "D"
    for stairs in new_stairs:
        stairs.paint(rows)
    return footprints, added


def _wing_protected_cells(grid, placements, entrance):
    """Bind each gate to the floor reachable only after opening that gate."""
    all_floor = {(x, yy) for yy, row in enumerate(grid.rows)
                 for x, tile in enumerate(row) if tile != "#"}
    return tuple(
        replace(placement, protected_cells=tuple(sorted(
            all_floor - reachable_cells(grid, entrance, {placement.gate}) - {placement.gate},
        ))) if placement.gate else placement for placement in placements
    )


def _attach_puzzle_wing(
    level: GeneratedDungeon, definitions: List[PuzzleDefinition],
    options: GenerationOptions, depth: int, blocked: Tuple[Cell, ...] = (),
) -> Tuple[GeneratedDungeon, Tuple[PlacedPuzzle, ...]]:
    """Attach independent puzzle/reward branches to an ungated common corridor."""
    definitions = sorted(definitions, key=lambda definition: not definition.passage)
    descending = any(definition.number in STAIR_PUZZLES for definition in definitions)
    old_width, height = level.grid.width, level.grid.height
    rows, stairways, removed, route = _wing_connection(level, descending, blocked)
    # Short maps need extra height for five-square spiral-stair chambers.
    if descending and height < 9:
        rows.extend([["#"] * old_width for _ in range(9 - height)])
        height = 9
    placements, new_stairs, centers, width, half_height = _wing_placements(
        definitions, depth, old_width, height, descending,
    )
    footprints, added = _carve_wing(
        rows, route, placements, new_stairs, centers, width, half_height,
    )
    stairways += tuple(new_stairs)
    clear_invalid_diagonals(rows)
    grid = DungeonMap(tuple("".join(row) for row in rows))
    if not is_connected(grid):
        raise ValueError("puzzle wing must be connected when its gates are solved")
    placements = _wing_protected_cells(grid, placements, route[-1])
    notes = list(level.layout_notes)
    notes.append("Added independent puzzle branches off a common corridor; "
                 "map width grew from {} to {} squares.".format(
        old_width, width))
    if descending:
        notes.append("Removed {} old down stairways/ramps; {} new 3x3 spiral "
                     "stairway(s) lie inside puzzle chambers.".format(len(removed), len(new_stairs)))
    return replace(
        level, grid=grid, stairways=stairways,
        room_cells=level.room_cells + tuple(footprints),
        room_areas=level.room_areas + tuple(len(cells) for cells in footprints),
        corridor_lengths=level.corridor_lengths + (added,), layout_notes=tuple(notes),
    ), tuple(placements)


def _edge_reward_branch(grid, cells, all_room_cells, stair_clearance, rng):
    """Find a six-square outward passage and isolated five-square reward room."""
    boundaries = [(cell, direction) for cell in cells for direction in ((1, 0), (0, 1))
                  if (cell[0] + direction[0], cell[1] + direction[1]) not in cells]
    rng.shuffle(boundaries)
    for (bx, by), (dx, dy) in boundaries:
        if grid.tile(bx, by) not in " .":
            continue
        # The chamber must be on the outer frontier, not an interior gap.
        if any((x > bx and y == by) if dx else (y > by and x == bx)
               for x, y in all_room_cells - set(cells)):
            continue
        reward = (bx + 9 * dx, by + 9 * dy)
        room = tuple((x, y) for y in range(reward[1] - 2, reward[1] + 3)
                     for x in range(reward[0] - 2, reward[0] + 3))
        corridor = tuple((bx + step * dx, by + step * dy) for step in range(1, 7))
        carved = set(room + corridor)
        buffer = {(x + ox, y + oy) for x, y in carved
                  for ox, oy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))}
        if (min(x for x, y in buffer) < 1 or min(y for x, y in buffer) < 1
                or buffer & stair_clearance
                or any(grid.tile(x, y) != "#" for x, y in buffer - {(bx, by)})):
            continue
        return corridor[0], reward, room, corridor
    return None


def _existing_puzzle_room(level, definition, occupied, rows, all_room_cells, stair_clearance, rng):
    """Select unused labelable floor, requiring a safe edge branch for passage puzzles."""
    choices = [(index, cells) for index, cells in enumerate(level.room_cells) if index not in occupied]
    rng.shuffle(choices)
    grid = DungeonMap(tuple("".join(row) for row in rows))
    for index, cells in choices:
        floor = [cell for cell in cells if grid.tile(*cell) in " .T"]
        if not floor:
            continue
        cx = sum(x for x, y in cells) / len(cells)
        cy = sum(y for x, y in cells) / len(cells)
        center = min(floor, key=lambda cell: (
            grid.tile(*cell) not in " .", (cell[0] - cx) ** 2 + (cell[1] - cy) ** 2, cell,
        ))
        if not definition.passage:
            return index, center, None, None, (), ()
        branch = _edge_reward_branch(grid, cells, all_room_cells, stair_clearance, rng)
        if branch:
            return (index, center) + branch
    return None


def _carve_reward_branch(rows, room, corridor, gate):
    """Grow the map as needed and carve a gated reward chamber without other entrances."""
    width = max(len(rows[0]), max(x for x, y in room) + 2)
    height = max(len(rows), max(y for x, y in room) + 2)
    for row in rows:
        row.extend(["#"] * (width - len(row)))
    rows.extend([["#"] * width for _ in range(height - len(rows))])
    for x, y in room + corridor:
        rows[y][x] = " "
    rows[gate[1]][gate[0]] = "D"
    return tuple(sorted(set(room + corridor) - {gate}))


def _room_spiral_candidates(level, occupied):
    """Find existing five-square chambers with clear floor for an in-room spiral."""
    reserved = set().union(*(passage.clearance for passage in level.stairways))
    candidates = []
    for index, cells in enumerate(level.room_cells):
        if index in occupied:
            continue
        room = set(cells)
        for cx, cy in cells:
            chamber = _buffer({(cx, cy)}, 2)
            if (chamber <= room and not chamber & reserved
                    and all(level.grid.tile(*cell) in " ." for cell in chamber)):
                candidates.append((index, (cx, cy)))
    return candidates


def _place_room_spirals(level, definitions, depth, occupied, rng):
    """Keep stair puzzles in existing chambers instead of sending them down a passage."""
    candidates = _room_spiral_candidates(level, occupied)
    placements, stairs, remaining = [], [], []
    for definition in definitions:
        if definition.number not in STAIR_PUZZLES:
            remaining.append(definition)
            continue
        choices = [candidate for candidate in candidates if candidate[0] not in occupied]
        if not choices:
            remaining.append(definition)
            continue
        index, (cx, cy) = rng.choice(choices)
        occupied.add(index)
        stairs.append(Stairway.spiral_at(cx - 1, cy - 1, size=3, tile="s"))
        placements.append(PlacedPuzzle(definition, (cx, cy + 2), next_level=depth + 1))
    if not placements:
        return level, (), remaining
    rows = [list(row) for row in level.grid.rows]
    removed = tuple(p for p in level.stairways if p.tile in "er")
    for passage in removed:
        for x, y in passage.cells:
            rows[y][x] = "#"
    for passage in stairs:
        passage.paint(rows)
        cx = min(x for x, y in passage.cells) + 1
        cy = min(y for x, y in passage.cells) + 1
        rows[cy][cx] = " "
    notes = level.layout_notes + (
        "Removed {} old down stairways/ramps; {} new 3x3 spiral "
        "stairway(s) lie inside existing puzzle chambers.".format(len(removed), len(stairs)),
    )
    return replace(
        level, grid=DungeonMap(tuple("".join(row) for row in rows)),
        stairways=tuple(p for p in level.stairways if p not in removed) + tuple(stairs),
        layout_notes=notes,
    ), tuple(placements), remaining


def _attach_existing_puzzles(level, definitions, options, depth, occupied, rng):
    """Use existing edge chambers before growing additional independent branches."""
    rows = [list(row) for row in level.grid.rows]
    footprints = list(level.room_cells)
    placements, pending = [], []
    lengths = list(level.corridor_lengths)
    all_room_cells = set().union(*level.room_cells)
    stair_clearance = set().union(*(p.clearance for p in level.stairways))
    for definition in sorted(definitions, key=lambda p: not p.passage):
        chosen = None if definition.number in STAIR_PUZZLES else _existing_puzzle_room(
            level, definition, occupied, rows, all_room_cells, stair_clearance, rng,
        )
        if chosen is None:
            pending.append(definition)
            continue
        index, center, gate, reward, room, corridor = chosen
        occupied.add(index)
        protected = ()
        if reward:
            protected = _carve_reward_branch(rows, room, corridor, gate)
            footprints.append(room)
            lengths.append(len(corridor))
        placements.append(PlacedPuzzle(
            definition, center, gate=gate, reward_cell=reward, protected_cells=protected,
        ))
    level = replace(
        level, grid=DungeonMap(tuple("".join(row) for row in rows)),
        room_cells=tuple(footprints), room_areas=tuple(map(len, footprints)),
        corridor_lengths=tuple(lengths),
    )
    if pending:
        blocked = tuple(cell for p in placements for cell in p.protected_cells + ((p.gate,) if p.gate else ()))
        level, extra = _attach_puzzle_wing(level, pending, options, depth, blocked)
        placements.extend(extra)
    return level, tuple(placements)


def _attach_puzzles(
    level: GeneratedDungeon, definitions: List[PuzzleDefinition],
    options: GenerationOptions, depth: int,
) -> Tuple[GeneratedDungeon, Tuple[PlacedPuzzle, ...]]:
    """Place stair gates in their own rooms and attach only same-level reward branches."""
    rng = random.Random("{}:puzzle-rooms:{}".format(level.seed, depth))
    occupied = {0}  # Keep an accessible encounter available for first-level puzzle items.
    level, stairs, remaining = _place_room_spirals(level, definitions, depth, occupied, rng)
    level, other = _attach_existing_puzzles(level, remaining, options, depth, occupied, rng)
    return level, stairs + other


def _empty_area(cell: Cell) -> EncounterArea:
    """Create an unstocked encounter record for a newly carved puzzle-wing room."""
    return EncounterArea(0, cell, 0, None, None, ("None.",), "None.",
                         debug=("Added puzzle-wing chamber; no random monster or trap rolled.",))


def _move_reward_encounter(areas, available, targets, puzzle, original_count):
    """Relocate the best unused hoard and preserve any displaced edge-room encounter."""
    goal = puzzle.reward_cell
    richest = max(available, key=lambda index: (treasure_value(areas[index]), -index)) if available else None
    if richest is None or treasure_value(areas[richest]) <= (0, 0, Decimal(0)):
        return
    source = areas[richest]
    available.remove(richest)
    areas[targets[goal]] = replace(
        source, cell=goal, trap="None.", notes=(),
        debug=source.debug + ("Encounter and treasure relocated behind puzzle gates.",),
    )
    areas[richest] = replace(
        source, monster=None, treasure=("None.",), container=None,
        chest_trap=None, chest_locked=None,
        debug=source.debug + ("Monster and treasure moved to puzzle reward chamber "
                             "at column {}, row {}.".format(goal[0] + 1, goal[1] + 1),),
    )
    puzzle_index = targets[puzzle.cell]
    displaced = areas[puzzle_index]
    if puzzle_index != richest and puzzle_index < original_count:
        areas[richest] = replace(
            displaced, cell=source.cell, trap=source.trap, notes=source.notes,
            debug=displaced.debug + (
                "Encounter displaced from an edge puzzle chamber into the vacated hoard chamber.",
            ),
        )
        areas[puzzle_index] = replace(
            displaced, monster=None, treasure=("None.",), container=None,
            chest_trap=None, chest_locked=None,
        )
        available.add(richest)
        available.discard(puzzle_index)


def _top_up_reward(area: EncounterArea) -> EncounterArea:
    """Ensure a guarded branch contains magic or at least one hundred silver pieces."""
    value = treasure_value(area)
    if value >= (0, 0, Decimal(1000)):
        return area
    loot = tuple(line for line in area.treasure if line != "None.")
    return replace(
        area, treasure=loot + ("Coins: {} sp.".format((1000 - value[2]) / 10),),
        container=area.container or "chest",
        chest_locked=area.chest_locked if area.container else False,
        debug=area.debug + ("Topped up puzzle reward to a minimum of 100 sp.",),
    )


def _stock_wing(
    before: GeneratedDungeon, after: GeneratedDungeon, contents: EncounterLevel,
    placements: Tuple[PlacedPuzzle, ...],
) -> EncounterLevel:
    """Key added chambers and move existing valuable encounters behind puzzle gates."""
    areas = _bind_existing_puzzle_rooms(before, contents, placements)
    for cells in after.room_cells[len(before.room_cells):]:
        center = (sum(x for x, y in cells) // len(cells),
                  sum(y for x, y in cells) // len(cells))
        center = next((p.cell for p in placements if p.cell in cells), center)
        areas.append(_empty_area(center))
    available = set(range(len(contents.areas)))
    targets = {area.cell: index for index, area in enumerate(areas)}
    for puzzle in placements:
        if puzzle.reward_cell is None:
            continue
        _move_reward_encounter(areas, available, targets, puzzle, len(contents.areas))
        target = targets[puzzle.reward_cell]
        areas[target] = _top_up_reward(areas[target])
    puzzle_cells = {p.cell for p in placements}
    areas = [replace(area, monster=None, trap="None.") if area.cell in puzzle_cells else area
             for area in areas]
    return replace(contents, areas=number_areas(areas), puzzles=placements)


def _bind_existing_puzzle_rooms(before, contents, placements):
    """Move reused chambers' encounter labels off their newly carved spiral stairs."""
    labels = {}
    for puzzle in placements:
        if not puzzle.next_level:
            continue
        room = next((cells for cells in before.room_cells if puzzle.cell in cells), None)
        if room is not None:
            area = next(area for area in contents.areas if area.cell in room)
            labels[area.cell] = puzzle.cell
    return [replace(area, cell=labels[area.cell]) if area.cell in labels else area
            for area in contents.areas]


def _exchange_hoards(
    keys: List[EncounterLevel], first: Tuple[int, EncounterArea], second: Tuple[int, EncounterArea],
) -> None:
    """Swap encounter hoards between keyed rooms while leaving floor-bound features."""
    for (depth, destination), (source_depth, source) in ((first, second), (second, first)):
        moved = replace(
            destination, presence_roll=source.presence_roll, table_roll=source.table_roll,
            monster=source.monster, treasure=source.treasure, container=source.container,
            chest_trap=source.chest_trap, chest_locked=source.chest_locked,
            debug=source.debug + ("Encounter/hoard exchanged from Level {}, Area {}; "
                                 "floor traps and puzzle items stay in place.".format(
                                     source_depth + 1, source.number),),
        )
        keys[depth] = replace(keys[depth], areas=tuple(
            moved if area.cell == destination.cell else area for area in keys[depth].areas
        ))


def _finalize_rewards(keys: List[EncounterLevel], rules: EncounterRules, seed: int) -> None:
    """Rank gated hoards across levels and provide a guardian for each reward branch."""
    final_gate = next((p for p in keys[-1].puzzles if p.gate), None)
    if final_gate:
        goal = next(area for area in keys[-1].areas if area.cell == final_gate.reward_cell)
        richest = max(((index, area) for index, key in enumerate(keys) for area in key.areas),
                      key=lambda item: treasure_value(item[1]))
        if treasure_value(richest[1]) > treasure_value(goal):
            _exchange_hoards(keys, richest, (len(keys) - 1, goal))
    for index in range(len(keys)):
        assigned = set()
        rng = random.Random("{}:puzzle-guards:{}".format(seed, index + 1))
        for puzzle in keys[index].puzzles:
            if not puzzle.gate:
                continue
            goal = next(area for area in keys[index].areas if area.cell == puzzle.reward_cell)
            best = max((area for area in keys[index].areas if area.cell not in assigned),
                       key=treasure_value)
            if treasure_value(best) > treasure_value(goal):
                _exchange_hoards(keys, (index, best), (index, goal))
            assigned.add(goal.cell)
            goal = next(area for area in keys[index].areas if area.cell == goal.cell)
            if goal.monster is None:
                debug = ["Guaranteed guardian for an independent puzzle reward encounter."]
                roll = basic_roll(rng)
                guard = monster_encounter(rules, rng, index + 1, roll, debug)
                guarded = replace(goal, monster=guard, table_roll=roll,
                                  debug=goal.debug + tuple(debug))
                keys[index] = replace(keys[index], areas=tuple(
                    guarded if area.cell == goal.cell else area for area in keys[index].areas
                ))


class _PuzzleNoteWriter:
    """Bind puzzle descriptions and physical items to final numbered encounter areas."""

    def __init__(self, keys, dungeon):
        """Retain the final key, geometry, and per-area description accumulators."""
        self.keys = keys
        self.dungeon = dungeon
        self.locations = [{area.cell: area.number for area in key.areas} for key in keys]
        self.additions = {}  # type: Dict[Tuple[int, Cell], List[str]]
        self.items_found = {}  # type: Dict[Tuple[int, Cell], List[str]]

    def location(self, level, cell):
        """Format a level/area reference, rejecting unkeyed puzzle coordinates."""
        number = self.locations[level - 1].get(cell)
        if number is None:
            raise ValueError("puzzle reference does not identify an encounter area")
        return "Level {}, Area {}".format(level, number)

    def write(self):
        """Collect cross-references before attaching notes and items to their rooms."""
        for depth, contents in enumerate(self.keys, 1):
            gates = [p for p in contents.puzzles if p.gate]
            for puzzle in contents.puzzles:
                self.additions.setdefault((depth, puzzle.cell), []).extend(
                    self.puzzle_notes(puzzle, depth, contents, gates),
                )
        for index, contents in enumerate(self.keys):
            self.keys[index] = replace(contents, areas=tuple(
                replace(area, notes=area.notes + tuple(self.additions.get((index + 1, area.cell), ())),
                        puzzle_items=tuple(self.items_found.get((index + 1, area.cell), ())))
                for area in contents.areas
            ))

    def puzzle_notes(self, puzzle, depth, contents, gates):
        """Compose the placement binding, progression rules, prerequisites, and solution."""
        definition = puzzle.definition
        title = "P{:02d}: {}".format(definition.number, definition.name)
        notes = [
            "**Puzzle {}** ({})".format(title, definition.category),
            "**Generated map binding:** The placement and item locations here override "
            "the catalog's example geography. Furnish this chamber with the described "
            "props and creatures; puzzle creatures replace, rather than join, a random encounter.",
        ]
        if puzzle.gate:
            notes.extend(self.gate_notes(puzzle, depth, contents, gates))
        elif puzzle.next_level:
            notes.append(self.stair_note(puzzle, depth, title))
        else:
            notes.append(
                "**Local challenge:** Apply the catalog's chest lock, temporary room trap, "
                "or item reward here; it does not replace the level's exit stairs. Temporary "
                "seals reopen as described in the solution or emergency-release clues."
            )
        notes.extend(self.item_notes(puzzle, depth, title))
        if definition.consequence_rules:
            notes.append("**Puzzle consequence level:** L = {}.".format(depth))
            notes.append(definition.consequence_rules)
        notes.append(re.sub(
            r"(?ms)^\*\*Reward:\*\*.*?(?=^\*\*|\Z)",
            "**Reward:** Use the exact rolled puzzle reward listed above; "
            "the catalog's illustrative treasure is not an additional award.\n\n",
            definition.body,
        ).strip())
        return notes

    def gate_notes(self, puzzle, depth, contents, gates):
        """Describe a physical gate and the guarded hoard in its independent branch."""
        protected_cells = set(puzzle.protected_cells)
        protected = [area.number for area in contents.areas if area.cell in protected_cells]
        destination = "an isolated section of this level, with no stairs or ramps"
        notes = [
            "**Progression gate:** The D at column {}, row {} stays impassable until "
            "this puzzle is solved, then latches open. It blocks {}. Protected areas: {}. "
            "This branch is independent: other puzzles need not be solved to enter this "
            "puzzle room, and solving this puzzle does not unlock their reward areas. "
            "There is no alternate mapped entrance to its reward area. "
            "Any catalog shortcut, return route, or emergency release "
            "leads back to the accessible side, never around this gate.".format(
                puzzle.gate[0] + 1, puzzle.gate[1] + 1, destination,
                ", ".join(map(str, protected)),
            )
        ]
        reward_area = next(area for area in contents.areas if area.cell == puzzle.reward_cell)
        primary = puzzle == gates[0]
        ranking = ("the highest-ranked generated treasure in the entire dungeon"
                   if primary and depth == len(self.keys) else
                   "the highest-ranked generated treasure remaining on this level"
                   if primary else "one of this level's next-highest-ranked generated hoards")
        notes.append(
            "**Protected reward:** Area {} holds {} and its guarding encounter "
            "(permanent magic first, then potions/scrolls, then money and gems). "
            "Each branch receives at least 100 sp in value or magic, plus a guardian; "
            "existing hoards are moved, not duplicated. Use the catalog reward as descriptive "
            "inspiration, not an extra rolled hoard.".format(reward_area.number, ranking)
        )
        if puzzle.definition.number in (20, 21):
            notes.append("**Key binding:** The key obtained from this creature opens "
                         "this chamber's progression gate; it is not an unassigned key.")
        return notes

    def stair_note(self, puzzle, depth, title):
        """Describe the in-room spiral and mirror its seal on a mapped lower level."""
        room = next(cells for cells in self.dungeon.levels[depth - 1].room_cells
                    if puzzle.cell in cells)
        stairs = next(p for p in self.dungeon.levels[depth - 1].stairways
                      if p.tile == "s" and set(p.cells) <= set(room))
        seal = (
            "**Linked stair seal:** A circular 3x3 spiral staircase IN THIS ROOM "
            "at column {}, row {} descends clockwise to Level {}{}. The chamber is "
            "at least 5x5 squares. The stairway is sealed at both ends until "
            "{} in {} is solved; other exits do not release it. Its corner "
            "landing remains open floor. There is no separate treasure chamber "
            "or passage gate attached to these stairs.".format(
                min(x for x, y in stairs.cells) + 1,
                min(y for x, y in stairs.cells) + 1, puzzle.next_level,
                " (beyond the generated maps)" if puzzle.next_level > len(self.keys) else "",
                title, self.location(depth, puzzle.cell),
            )
        )
        if puzzle.next_level <= len(self.keys):
            lower = self.keys[puzzle.next_level - 1]
            self.keys[puzzle.next_level - 1] = replace(
                lower, stair_notes=lower.stair_notes + (seal,),
            )
        return seal

    def item_notes(self, puzzle, depth, title):
        """Record each prerequisite in both its puzzle notes and physical source loot."""
        notes = []
        for item in puzzle.items:
            source = self.location(item.source_level, item.source_cell)
            destination = self.location(depth, puzzle.cell)
            notes.append("**Required item:** {} -- found at {} before this puzzle; "
                         "collect it with that encounter's loot{}.".format(
                             item.name, source,
                             " after solving its puzzle" if any(
                                 item.source_cell in (other.cell, other.reward_cell)
                                 for other in self.keys[item.source_level - 1].puzzles
                             ) else "",
                         ))
            self.items_found.setdefault((item.source_level, item.source_cell), []).append(
                "**Puzzle item:** {}. Required for the later puzzle {} in {}. "
                "Keep it with this encounter's loot{}; a matching symbol identifies "
                "its later use. This is a physical item, not just a clue.".format(
                    item.name, title, destination,
                    " as a reward for solving the puzzle" if any(
                        item.source_cell in (other.cell, other.reward_cell)
                        for other in self.keys[item.source_level - 1].puzzles
                    ) else "",
                )
            )
        return notes


def _write_puzzle_notes(keys: List[EncounterLevel], dungeon: GeneratedDungeon) -> None:
    """Attach generated puzzle descriptions and reciprocal physical-item references."""
    _PuzzleNoteWriter(keys, dungeon).write()


def _validate_gate_layout(layout, contents, gates, gated):
    """Reject inaccessible puzzle rooms and overlapping independent reward branches."""
    if not gated:
        return
    accessible = reachable_cells(layout.grid, gated[0].cell, gates)
    if any(puzzle.cell not in accessible for puzzle in contents.puzzles):
        raise ValueError("puzzle rooms must be accessible without solving another puzzle")
    protected_sets = [set(p.protected_cells) for p in gated]
    if any(first & second for index, first in enumerate(protected_sets)
           for second in protected_sets[index + 1:]):
        raise ValueError("puzzle reward branches must not overlap or be nested")


def _validate_puzzle_identity(puzzle, depth, contents, seen):
    """Check catalog eligibility, uniqueness, and complete prize/prerequisite bindings."""
    if not puzzle.definition.eligible(depth):
        raise ValueError("puzzle is not eligible at this dungeon depth")
    if puzzle.definition.number in seen:
        raise ValueError("a puzzle may appear only once per dungeon")
    seen.add(puzzle.definition.number)
    area = next((a for a in contents.areas if a.cell == puzzle.cell), None)
    if area is None or not area.puzzle_reward:
        raise ValueError("each puzzle must have an exact rolled treasure reward")
    if tuple(item.name for item in puzzle.items) != puzzle.definition.required_items:
        raise ValueError("each required puzzle item must have a physical source")
    return area


def _validate_passage_puzzle(puzzle, layout, contents, gated, depth, keys):
    """Verify the physical gate, short stair-free branch, guardian, and hoard rank."""
    protected = set(puzzle.protected_cells)
    if layout.grid.tile(*puzzle.gate) != "D" or not protected:
        raise ValueError("passage puzzle has no physical gate/protected section")
    outside = reachable_cells(layout.grid, puzzle.cell, {puzzle.gate})
    if protected & outside:
        raise ValueError("puzzle gate has an alternate route")
    if not any(area.cell in protected for area in contents.areas):
        raise ValueError("puzzle gate must protect at least one chamber")
    if puzzle.next_level:
        raise ValueError("a stair puzzle must put its spiral in the puzzle room")
    reward = next((area for area in contents.areas if area.cell == puzzle.reward_cell), None)
    if (reward is None or reward.cell not in protected or reward.monster is None
            or treasure_value(reward) < (0, 0, Decimal(1000))):
        raise ValueError("each puzzle branch must protect a valuable guarded encounter")
    if any(set(p.cells) & protected for p in layout.stairways):
        raise ValueError("a same-level reward chamber must not contain stairs")
    reward_room = next(set(cells) for cells in layout.room_cells if reward.cell in cells)
    if len(protected - reward_room) + 1 > 10:
        raise ValueError("a puzzle reward passage must be no more than 10 squares")
    if puzzle == gated[0] and treasure_value(reward) != max(map(treasure_value, contents.areas)):
        raise ValueError("the primary branch must protect the level's best hoard")
    if puzzle == gated[0] and depth == len(keys):
        best_in_dungeon = max(treasure_value(area) for key in keys for area in key.areas)
        if not any(area.cell in protected and treasure_value(area) == best_in_dungeon
                   for area in contents.areas):
            raise ValueError("the final gated section must contain the dungeon's best hoard")


def _validate_stair_puzzle(puzzle, layout, downs, depth, keys):
    """Require an in-room three-square spiral, a five-square chamber, and a linked seal."""
    room = next(cells for cells in layout.room_cells if puzzle.cell in cells)
    stairs = [p for p in downs if p.spiral and p.clearance <= set(room)]
    if (puzzle.next_level != depth + 1 or len(stairs) != 1
            or len({x for x, y in stairs[0].cells}) != 3
            or len({y for x, y in stairs[0].cells}) != 3
            or len({x for x, y in room}) < 5 or len({y for x, y in room}) < 5):
        raise ValueError("a stair puzzle requires a 3x3 spiral inside a 5x5 chamber")
    chamber = _buffer(stairs[0].clearance)
    ring = chamber - stairs[0].clearance
    if not chamber <= set(room) or any(layout.grid.tile(*cell) not in " ." for cell in ring):
        raise ValueError("a room spiral requires clear floor between the stairway and walls or doorways")
    marker = "P{:02d}: {}".format(puzzle.definition.number, puzzle.definition.name)
    if depth < len(keys) and not any(marker in note for note in keys[depth].stair_notes):
        raise ValueError("stair puzzle requires a keyed stair seal on the lower level")


def _validate_required_item(dungeon, keys, depth, puzzle, puzzle_area, item, gates, accessible):
    """Verify physical source loot and cache same-level reachability before any gate."""
    if not 1 <= item.source_level <= depth:
        raise ValueError("puzzle item must be on this or an earlier level")
    source_key = keys[item.source_level - 1]
    source_layout = dungeon.levels[item.source_level - 1]
    source_area = next((area for area in source_key.areas if area.cell == item.source_cell), None)
    if source_area is None or (item.source_level == depth and item.source_cell == puzzle.cell):
        raise ValueError("puzzle item must be in another encounter area")
    if not any(
        item.name in entry
        and "P{:02d}:".format(puzzle.definition.number) in entry
        and "Level {}, Area {}".format(depth, puzzle_area.number) in entry
        for entry in source_area.puzzle_items
    ):
        raise ValueError("puzzle item must be listed with its source encounter's loot")
    if any(item.source_cell == other.cell
           and "**Consequences:** Treasure;" in other.definition.body
           for other in source_key.puzzles):
        raise ValueError("required items cannot be permanently sealed after puzzle failure")
    if (item.source_level == depth
            and any(item.source_cell in other.protected_cells for other in source_key.puzzles)):
        raise ValueError("puzzle item is locked behind a source-level puzzle")
    if item.source_level == depth:
        layout, contents = dungeon.levels[depth - 1], keys[depth - 1]
        if accessible is None:
            start = next((passage.entrance for passage in layout.stairways
                          if passage.tile in "ERS"), next(
                              area.cell for area in contents.areas if area.cell in layout.room_cells[0]
                          ))
            accessible = reachable_cells(layout.grid, start, gates)
        if item.source_cell not in accessible:
            raise ValueError("puzzle item is unreachable before solving this level")
    if not _open_sides(source_layout.grid, *item.source_cell):
        raise ValueError("puzzle item is not on walkable floor")
    return accessible


def _validate_reward_order(contents, gated):
    """Ensure every independent guarded branch outranks all unprotected encounters."""
    if not gated:
        return
    reward_cells = {p.reward_cell for p in gated}
    rewards = [treasure_value(area) for area in contents.areas if area.cell in reward_cells]
    remaining = [treasure_value(area) for area in contents.areas if area.cell not in reward_cells]
    if remaining and max(remaining) > min(rewards):
        raise ValueError("independent reward branches must receive the highest-ranked hoards")


def _validate_linked_stairs(layout, next_layout):
    """Match each descending footprint to the corresponding up passage below."""
    down = {(passage.cells, passage.tile, passage.horizontal)
            for passage in layout.stairways if passage.tile in "ers"}
    up = {(passage.cells, {"E": "e", "R": "r", "S": "s"}[passage.tile], passage.horizontal)
          for passage in next_layout.stairways if passage.tile in "ERS"}
    if down != up:
        raise ValueError("puzzle-adjusted stairs do not match the next level")


def validate_puzzle_dungeon(dungeon: GeneratedDungeon, keys: Tuple[EncounterLevel, ...]) -> None:
    """Validate puzzle progression, treasure placement, item access, and interlevel links."""
    if len(keys) != len(dungeon.levels):
        raise ValueError("puzzle key must include every level")
    seen = set()
    for depth, (layout, contents) in enumerate(zip(dungeon.levels, keys), 1):
        if not is_connected(layout.grid):
            raise ValueError("puzzle dungeon is disconnected with gates open")
        gates = {puzzle.gate for puzzle in contents.puzzles if puzzle.gate is not None}
        gated = [puzzle for puzzle in contents.puzzles if puzzle.gate]
        item_accessible = None
        downs = [passage for passage in layout.stairways if passage.tile in "ers"]
        _validate_gate_layout(layout, contents, gates, gated)
        for puzzle in contents.puzzles:
            area = _validate_puzzle_identity(puzzle, depth, contents, seen)
            if puzzle.gate:
                _validate_passage_puzzle(puzzle, layout, contents, gated, depth, keys)
            elif puzzle.next_level:
                _validate_stair_puzzle(puzzle, layout, downs, depth, keys)
            for item in puzzle.items:
                item_accessible = _validate_required_item(
                    dungeon, keys, depth, puzzle, area, item, gates, item_accessible,
                )
        _validate_reward_order(contents, gated)
        if depth < len(keys):
            _validate_linked_stairs(layout, dungeon.levels[depth])


class _AdventureBuilder:
    """Retain catalog and stocking state while dungeon levels are generated in order."""

    def __init__(self, options, probability, slots, rules, encounter_options):
        """Load unused puzzles and initialize the per-adventure generation context."""
        self.options = options
        self.probability = probability
        self.slots = slots
        self.rules = rules
        self.encounter_options = encounter_options
        self.remaining = list(load_puzzles())
        self.catalog_count = len(self.remaining)
        self.keys = []  # type: List[EncounterLevel]
        self.rng = None  # type: Optional[random.Random]

    def finish_level(self, level: GeneratedDungeon, depth: int) -> GeneratedDungeon:
        """Stock one level, attach selected puzzles, and bind their prerequisites."""
        if self.rng is None:
            self.rng = random.Random("{}:puzzles".format(level.seed))
        contents = generate_encounters(
            level, rules=self.rules, start_level=depth, **self.encounter_options,
        )[0]
        successes, definitions = self.select_puzzles(depth)
        count = len(definitions)
        if definitions:
            before = level
            level, placements = _attach_puzzles(level, definitions, self.options, depth)
            contents = _stock_wing(before, level, contents, placements)
            contents = self.bind_required_items(contents, placements, depth)
        elif not self.remaining:
            level = replace(level, layout_notes=level.layout_notes + (
                "All {} unique puzzles have been used; no further puzzles can be placed.".format(
                    self.catalog_count),
            ))
        level = replace(level, layout_notes=level.layout_notes + (
            "Puzzle rolls: {} successes in {} slots at probability {:g}; placed {}{}.".format(
                successes, self.slots, self.probability, count,
                " (limited by unused puzzles eligible at this depth)" if count < successes else "",
            ),
        ))
        self.keys.append(contents)
        return level

    def select_puzzles(self, depth):
        """Roll independent slots and remove a random sample of eligible unused puzzles."""
        successes = sum(self.rng.random() < self.probability for _ in range(self.slots))
        eligible = [definition for definition in self.remaining if definition.eligible(depth)]
        count = min(len(eligible), successes)
        definitions = self.rng.sample(eligible, count)
        for definition in definitions:
            self.remaining.remove(definition)
        return successes, definitions

    def bind_required_items(self, contents, placements, depth):
        """Prefer safe earlier puzzle prizes, otherwise choose accessible encounter loot."""
        candidates = []
        earlier_rewards = [
            (source_depth, other.reward_cell or other.cell)
            for source_depth, source_key in enumerate(self.keys, 1)
            for other in source_key.puzzles
            if "**Consequences:** Treasure;" not in other.definition.body
        ]
        for source_depth, source_key in enumerate(self.keys + [contents], 1):
            protected = {cell for other in source_key.puzzles for cell in other.protected_cells}
            puzzle_cells = {other.cell for other in source_key.puzzles}
            candidates.extend(
                (source_depth, area.cell) for area in source_key.areas
                if area.cell not in protected and area.cell not in puzzle_cells
            )
        placed = []
        for puzzle in placements:
            item_candidates = earlier_rewards or [
                candidate for candidate in candidates if candidate != (depth, puzzle.cell)
            ]
            if puzzle.definition.required_items and not item_candidates:
                raise ValueError("no accessible encounter area for required puzzle items")
            items = tuple(PuzzleItem(name, *self.rng.choice(item_candidates))
                          for name in puzzle.definition.required_items)
            placed.append(replace(puzzle, items=items))
        return replace(contents, puzzles=tuple(placed))


def _roll_puzzle_rewards(keys, rules, seed):
    """Assign exact depth-based puzzle prizes using a separate seeded random stream."""
    for index, contents in enumerate(keys):
        rng = random.Random("{}:puzzle-prizes:{}".format(seed, index + 1))
        rewards = {}
        for puzzle in contents.puzzles:
            debug = []
            rewards[puzzle.cell] = (puzzle_treasure(rules, rng, index + 1, debug), tuple(debug))
        keys[index] = replace(contents, areas=tuple(
            replace(area, puzzle_reward=rewards[area.cell][0],
                    debug=area.debug + rewards[area.cell][1]) if area.cell in rewards else area
            for area in contents.areas
        ))


def generate_adventure(
    options: Optional[GenerationOptions] = None, *, puzzle_probability: float = 0.35,
    max_puzzles_per_level: int = 2, encounter_chance: int = 11,
    treasure_chest_dc: int = 17, chest_trap_dc: int = 19, chest_lock_dc: int = 17,
    rules: Optional[EncounterRules] = None,
) -> Tuple[GeneratedDungeon, Tuple[EncounterLevel, ...]]:
    """Generate and validate stocked levels with unique puzzles and physical rewards."""
    options = options or GenerationOptions()
    _probability("puzzle_probability", puzzle_probability)
    if (isinstance(max_puzzles_per_level, bool) or not isinstance(max_puzzles_per_level, int)
            or not 0 <= max_puzzles_per_level <= PUZZLE_COUNT):
        raise ValueError("max_puzzles_per_level must be an integer from 0 through {}".format(PUZZLE_COUNT))
    encounter_options = dict(
        encounter_chance=encounter_chance, treasure_chest_dc=treasure_chest_dc,
        chest_trap_dc=chest_trap_dc, chest_lock_dc=chest_lock_dc,
    )
    rules = rules or EncounterRules()
    if puzzle_probability == 0 or max_puzzles_per_level == 0:
        dungeon = generate_dungeon(options)
        return dungeon, generate_encounters(dungeon, rules=rules, **encounter_options)
    builder = _AdventureBuilder(options, puzzle_probability, max_puzzles_per_level, rules, encounter_options)
    dungeon = generate_dungeon(options, level_transform=builder.finish_level)
    keys = builder.keys
    _finalize_rewards(keys, rules, dungeon.seed)
    _roll_puzzle_rewards(keys, rules, dungeon.seed)
    _write_puzzle_notes(keys, dungeon)
    result = tuple(keys)
    validate_puzzle_dungeon(dungeon, result)
    return dungeon, result
