"""Place the Markdown puzzle catalog into sequentially stocked dungeon levels."""

import random
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from dungeon_encounters import (
    EncounterArea, EncounterLevel, EncounterRules, generate_encounters,
)
from dungeon_games import field as game_field, validate_strategy_game
from dungeon_map import (
    Cell, DIRECTIONS, DungeonMap, GeneratedDungeon, GenerationOptions, Stairway,
    _open_sides, _partition, _probability, _route, generate_dungeon, is_connected,
    validate_map,
)


CATALOG_PATH = Path(__file__).with_suffix(".md")
PUZZLE_COUNT = 40
PASSAGE_PUZZLES = frozenset((
    2, 3, 4, 6, 8, 9, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 24, 25, 26, 27, 29, 30,
    33, 34, 36, 38, 39,
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

    def eligible(self, depth: int) -> bool:
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


def load_puzzles(path: Path = CATALOG_PATH) -> Tuple[PuzzleDefinition, ...]:
    text = path.read_text(encoding="utf-8")
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
        min_level, max_level = 1, None
        if "**Game:**" in body:
            validate_strategy_game(body)
            levels = re.fullmatch(r"([1-9]\d*)(?:-([1-9]\d*)|(\+))", game_field(body, "Dungeon levels"))
            if levels is None:
                raise ValueError("strategy puzzle levels must be a positive range or minimum+")
            min_level = int(levels[1])
            max_level = int(levels[2]) if levels[2] else None
            if max_level is not None and max_level < min_level:
                raise ValueError("strategy puzzle level range is reversed")
        # Generated item locations replace the catalog's illustrative locations.
        body = re.sub(
            r"(?ms)^\*\*Required items?:\*\*.*?(?=^\*\*|\Z)", "", body,
        )
        result.append(PuzzleDefinition(
            number, name, categories[number][1], body.strip(),
            number in PASSAGE_PUZZLES, REQUIRED_ITEMS.get(number, ()),
            min_level, max_level,
        ))
    return tuple(result)


def treasure_value(area: EncounterArea) -> Tuple[int, int, Decimal]:
    """Lexicographic priority: permanent magic, consumable magic, then money."""
    permanent = consumable = 0
    money = Decimal(0)
    factors = {"cp": 1, "sp": 10, "gp": 100, "pp": 1000}
    for line in area.treasure:
        if "(power +" in line:
            if line.startswith(("Magic Potion", "Magic Scroll")):
                consumable += 1
            else:
                permanent += 1
        if line.startswith(("Coins:", "Gems/jewelry:")):
            for amount, currency in re.findall(r"(\d+(?:\.\d+)?) (cp|sp|gp|pp)\b", line):
                money += Decimal(amount) * factors[currency]
    return permanent, consumable, money


def reachable_cells(grid: DungeonMap, start: Cell, blocked: Set[Cell]) -> Set[Cell]:
    if start in blocked or not _open_sides(grid, *start):
        return set()
    seen = {start}
    pending = [start]
    while pending:
        x, y = pending.pop()
        for side in _open_sides(grid, x, y):
            dx, dy = DIRECTIONS[side]
            neighbor = (x + dx, y + dy)
            if (neighbor not in blocked and neighbor not in seen
                    and (side + 2) % 4 in _open_sides(grid, *neighbor)
                    and not _partition(grid, x, y, side)):
                seen.add(neighbor)
                pending.append(neighbor)
    return seen


def _attach_puzzles(
    level: GeneratedDungeon, definitions: List[PuzzleDefinition],
    options: GenerationOptions, depth: int,
) -> Tuple[GeneratedDungeon, Tuple[PlacedPuzzle, ...], Optional[Cell]]:
    """Append a one-entry wing so no old corridor can bypass a puzzle gate."""
    definitions = sorted(definitions, key=lambda definition: not definition.passage)
    gated = any(definition.passage for definition in definitions)
    descending = gated and depth < options.levels
    old_width, height = level.grid.width, level.grid.height
    rows = [list(row) for row in level.grid.rows]
    removed = tuple(passage for passage in level.stairways
                    if descending and passage.tile in "ER")
    for passage in removed:
        for x, y in passage.cells:
            rows[y][x] = "#"
    stairways = tuple(passage for passage in level.stairways if passage not in removed)
    grid = DungeonMap(tuple("".join(row) for row in rows))
    forbidden = set().union(*(passage.clearance for passage in stairways))
    for y, row in enumerate(grid.rows):
        for x, tile in enumerate(row):
            if tile in "DSC\\/":
                forbidden.update((x + dx, y + dy)
                                 for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    targets = {
        (x, y) for y, row in enumerate(grid.rows) for x, tile in enumerate(row)
        if tile in " .TP" and (x, y) not in forbidden
    }
    candidates = []
    for y in range(3, height - 3):
        route = _route((old_width - 2, y), targets, old_width, height, forbidden)
        if route is not None:
            candidates.append(route)
    if not candidates:
        raise ValueError("cannot connect a puzzle wing without damaging protected features; "
                         "increase map height/density or change seed")
    route = min(candidates, key=lambda path: (len(path), path))
    y = route[0][1]
    centers = [(old_width + 3 + 8 * index, y)
               for index in range(len(definitions) + int(gated))]
    last_x = centers[-1][0]
    new_stairs = None
    if descending:
        new_stairs = Stairway(tuple((last_x + 6 + offset, y)
                                   for offset in range(options.stair_length)), "E", True)
        width = new_stairs.cells[-1][0] + 4
    else:
        width = last_x + 4
    for row in rows:
        row.extend(["#"] * (width - old_width))
    lengths = list(level.corridor_lengths)
    added = 0
    for x, cy in route:
        if rows[cy][x] == "#":
            rows[cy][x] = " "
            added += 1
    footprints = []
    for cx, cy in centers:
        cells = tuple((x, yy) for x in range(cx - 2, cx + 3)
                      for yy in range(cy - 2, cy + 3))
        footprints.append(cells)
        for x, yy in cells:
            rows[yy][x] = " "
    end = new_stairs.entrance[0] if new_stairs else last_x
    for x in range(old_width - 1, end + 1):
        if rows[y][x] == "#":
            rows[y][x] = " "
            added += 1
    lengths.append(added)
    placements = []
    for definition, center in zip(definitions, centers):
        gate = (center[0] + 3, y) if definition.passage else None
        if gate:
            rows[gate[1]][gate[0]] = "D"
        placements.append(PlacedPuzzle(
            definition, center, gate=gate, next_level=depth + 1 if descending else None,
        ))
    if new_stairs:
        for x, cy in new_stairs.cells:
            rows[cy][x] = new_stairs.tile
        stairways += (new_stairs,)
    grid = DungeonMap(tuple("".join(row) for row in rows))
    validate_map(grid)
    if not is_connected(grid):
        raise ValueError("puzzle wing must be connected when its gates are solved")
    all_floor = {(x, yy) for yy, row in enumerate(grid.rows)
                 for x, tile in enumerate(row) if tile != "#"}
    placements = [
        replace(placement, protected_cells=tuple(sorted(
            all_floor - reachable_cells(grid, route[-1], {placement.gate}) - {placement.gate},
        ))) if placement.gate else placement
        for placement in placements
    ]
    notes = list(level.layout_notes)
    notes.append("Added a single-entry puzzle wing; map width grew from {} to {} squares.".format(
        old_width, width))
    if descending:
        notes.append("Removed {} old down stairways/ramps; one new exit stairway lies "
                     "behind all passage puzzles.".format(len(removed)))
    return replace(
        level, grid=grid, stairways=stairways,
        room_cells=level.room_cells + tuple(footprints),
        room_areas=level.room_areas + tuple(len(cells) for cells in footprints),
        corridor_lengths=tuple(lengths), layout_notes=tuple(notes),
    ), tuple(placements), centers[-1] if gated else None


def _empty_area(cell: Cell) -> EncounterArea:
    return EncounterArea(0, cell, 0, None, None, ("None.",), "None.",
                         debug=("Added puzzle-wing chamber; no random monster or trap rolled.",))


def _stock_wing(
    before: GeneratedDungeon, after: GeneratedDungeon, contents: EncounterLevel,
    placements: Tuple[PlacedPuzzle, ...], goal: Optional[Cell],
) -> EncounterLevel:
    areas = list(contents.areas)
    for cells in after.room_cells[len(before.room_cells):]:
        center = (sum(x for x, y in cells) // len(cells),
                  sum(y for x, y in cells) // len(cells))
        areas.append(_empty_area(center))
    if goal is not None:
        richest = max(range(len(contents.areas)), key=lambda index: treasure_value(areas[index]))
        source = areas[richest]
        target = next(index for index, area in enumerate(areas) if area.cell == goal)
        if treasure_value(source) > (0, 0, Decimal(0)):
            areas[target] = replace(
                source, cell=goal, trap="None.", notes=(),
                debug=source.debug + ("Encounter and treasure relocated behind puzzle gates.",),
            )
            areas[richest] = replace(
                source, monster=None, treasure=("None.",), container=None,
                chest_trap=None, chest_locked=None,
                debug=source.debug + ("Monster and treasure moved to puzzle reward chamber "
                                     "at column {}, row {}.".format(goal[0] + 1, goal[1] + 1),),
            )
        else:
            areas[target] = replace(
                areas[target], treasure=("Coins: 100 sp.",), container="chest", chest_locked=False,
                debug=areas[target].debug + ("No rolled loot; supplied a 100 sp puzzle reward.",),
            )
    areas = [replace(area, number=number) for number, area in enumerate(
        sorted(areas, key=lambda area: (area.cell[1], area.cell[0])), 1)]
    return replace(contents, areas=tuple(areas), puzzles=placements)


def _location(level: int, cell: Cell, keys: List[EncounterLevel]) -> str:
    area = next((area for area in keys[level - 1].areas if area.cell == cell), None)
    if area is None:
        raise ValueError("puzzle reference does not identify an encounter area")
    return "Level {}, Area {}".format(level, area.number)


def _exchange_hoards(
    keys: List[EncounterLevel], first: Tuple[int, EncounterArea], second: Tuple[int, EncounterArea],
) -> None:
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


def _finalize_rewards(keys: List[EncounterLevel]) -> None:
    if not any(puzzle.gate for puzzle in keys[-1].puzzles):
        return
    final_index = len(keys) - 1
    goal = max(keys[-1].areas, key=lambda area: area.cell[0])
    richest = max(((index, area) for index, key in enumerate(keys) for area in key.areas),
                  key=lambda item: treasure_value(item[1]))
    if treasure_value(richest[1]) > treasure_value(goal):
        _exchange_hoards(keys, richest, (final_index, goal))
    # An earlier gated hoard may have moved downstairs; keep its best remaining
    # local encounter behind its gate too, without duplicating either hoard.
    for index, contents in enumerate(keys[:-1]):
        if any(puzzle.gate for puzzle in contents.puzzles):
            goal = max(contents.areas, key=lambda area: area.cell[0])
            best = max(contents.areas, key=treasure_value)
            if treasure_value(best) > treasure_value(goal):
                _exchange_hoards(keys, (index, best), (index, goal))


def _write_puzzle_notes(keys: List[EncounterLevel]) -> None:
    additions = {}  # type: Dict[Tuple[int, Cell], List[str]]
    for depth, contents in enumerate(keys, 1):
        for puzzle in contents.puzzles:
            definition = puzzle.definition
            title = "P{:02d}: {}".format(definition.number, definition.name)
            notes = [
                "**Puzzle {}** ({})".format(title, definition.category),
                "**Generated map binding:** The placement and item locations here override "
                "the catalog's example geography. Furnish this chamber with the described "
                "props and creatures; puzzle creatures replace, rather than join, a random encounter.",
            ]
            if puzzle.gate:
                protected = [area.number for area in contents.areas
                             if area.cell in puzzle.protected_cells]
                destination = (
                    "the only exit stairway to Level {}".format(puzzle.next_level)
                    if puzzle.next_level else "an isolated section of this level, with no stairs or ramps"
                )
                notes.append(
                    "**Progression gate:** The D at column {}, row {} stays impassable until "
                    "this puzzle is solved, then latches open. It blocks {}. Protected areas: {}. "
                    "All passage puzzles on this level must be solved; there is no alternate "
                    "mapped entrance. Any catalog shortcut, return route, or emergency release "
                    "leads back to the accessible side, never around this gate.".format(
                        puzzle.gate[0] + 1, puzzle.gate[1] + 1, destination,
                        ", ".join(map(str, protected)),
                    )
                )
                reward_area = max(contents.areas, key=lambda area: area.cell[0])
                notes.append(
                    "**Protected reward:** Area {} holds the highest-ranked generated treasure "
                    "{} and its guarding encounter (permanent magic first, then "
                    "potions/scrolls, then money and gems). An otherwise empty protected "
                    "reward room receives 100 sp. Use the catalog reward as descriptive "
                    "inspiration, not an extra rolled hoard.".format(
                        reward_area.number,
                        "in the entire dungeon" if depth == len(keys) else "remaining on this level",
                    )
                )
                if definition.number in (20, 21):
                    notes.append("**Key binding:** The key obtained from this creature opens "
                                 "this chamber's progression gate; it is not an unassigned key.")
            else:
                notes.append(
                    "**Local challenge:** Apply the catalog's chest lock, temporary room trap, "
                    "or item reward here; it does not replace the level's exit stairs. Temporary "
                    "seals reopen as described in the solution or emergency-release clues."
                )
            for item in puzzle.items:
                source = _location(item.source_level, item.source_cell, keys)
                destination = _location(depth, puzzle.cell, keys)
                notes.append("**Required item:** {} -- found at {} before this puzzle; "
                             "it is not part of a treasure container or locked behind a puzzle "
                             "on its source level.".format(item.name, source))
                additions.setdefault((item.source_level, item.source_cell), []).append(
                    "**Puzzle item:** {}. Place it visibly among the room's furnishings, outside "
                    "locked containers; no secret-door or search roll is required to recognize it. "
                    "It is used for {} in {}. Include a matching symbol or diagram pointing to "
                    "that later use; do not remove it with ordinary treasure.".format(
                        item.name, title, destination,
                    )
                )
            notes.append(definition.body)
            additions.setdefault((depth, puzzle.cell), []).extend(notes)
    for index, contents in enumerate(keys):
        keys[index] = replace(contents, areas=tuple(
            replace(area, notes=area.notes + tuple(additions.get((index + 1, area.cell), ())))
            for area in contents.areas
        ))


def validate_puzzle_dungeon(dungeon: GeneratedDungeon, keys: Tuple[EncounterLevel, ...]) -> None:
    if len(keys) != len(dungeon.levels):
        raise ValueError("puzzle key must include every level")
    seen = set()
    for depth, (layout, contents) in enumerate(zip(dungeon.levels, keys), 1):
        if not is_connected(layout.grid):
            raise ValueError("puzzle dungeon is disconnected with gates open")
        gates = {puzzle.gate for puzzle in contents.puzzles if puzzle.gate is not None}
        for puzzle in contents.puzzles:
            if not puzzle.definition.eligible(depth):
                raise ValueError("puzzle is not eligible at this dungeon depth")
            if puzzle.definition.number in seen:
                raise ValueError("a puzzle may appear only once per dungeon")
            seen.add(puzzle.definition.number)
            if puzzle.gate:
                protected = set(puzzle.protected_cells)
                if layout.grid.tile(*puzzle.gate) != "D" or not protected:
                    raise ValueError("passage puzzle has no physical gate/protected section")
                outside = reachable_cells(layout.grid, puzzle.cell, {puzzle.gate})
                if protected & outside:
                    raise ValueError("puzzle gate has an alternate route")
                if not any(area.cell in protected for area in contents.areas):
                    raise ValueError("puzzle gate must protect at least one chamber")
                downs = [passage for passage in layout.stairways if passage.tile in "ER"]
                if puzzle.next_level:
                    if len(downs) != 1 or not set(downs[0].cells) <= protected:
                        raise ValueError("all descending access must be behind the puzzle")
                for passage in layout.stairways:
                    if set(passage.cells) & protected and (
                        not puzzle.next_level or passage.tile in "UI"
                    ):
                        raise ValueError("a stairway bypasses the protected section")
                best = max(map(treasure_value, contents.areas))
                if not any(area.cell in protected and treasure_value(area) == best
                           for area in contents.areas):
                    raise ValueError("the most valuable encounter must be behind the puzzle")
                if depth == len(keys):
                    best_in_dungeon = max(treasure_value(area) for key in keys for area in key.areas)
                    if not any(area.cell in protected and treasure_value(area) == best_in_dungeon
                               for area in contents.areas):
                        raise ValueError("the final gated section must contain the dungeon's best hoard")
            for item in puzzle.items:
                if not 1 <= item.source_level <= depth:
                    raise ValueError("puzzle item must be on this or an earlier level")
                source_key = keys[item.source_level - 1]
                source_layout = dungeon.levels[item.source_level - 1]
                source_area = next((area for area in source_key.areas
                                    if area.cell == item.source_cell), None)
                if source_area is None or (item.source_level == depth and item.source_cell == puzzle.cell):
                    raise ValueError("puzzle item must be in another encounter area")
                if any(item.source_cell in other.protected_cells for other in source_key.puzzles):
                    raise ValueError("puzzle item is locked behind a source-level puzzle")
                if item.source_level == depth:
                    start = next((passage.entrance for passage in layout.stairways
                                  if passage.tile in "UI"), next(
                                      area.cell for area in contents.areas
                                      if area.cell in layout.room_cells[0]
                                  ))
                    if item.source_cell not in reachable_cells(layout.grid, start, gates):
                        raise ValueError("puzzle item is unreachable before solving this level")
                if not _open_sides(source_layout.grid, *item.source_cell):
                    raise ValueError("puzzle item is not on walkable floor")
        if depth < len(keys):
            down = {(passage.cells, passage.tile, passage.horizontal)
                    for passage in layout.stairways if passage.tile in "ER"}
            up = {(passage.cells, "E" if passage.tile == "U" else "R", passage.horizontal)
                  for passage in dungeon.levels[depth].stairways if passage.tile in "UI"}
            if down != up:
                raise ValueError("puzzle-adjusted stairs do not match the next level")


def generate_adventure(
    options: Optional[GenerationOptions] = None, *, puzzle_probability: float = 0.35,
    max_puzzles_per_level: int = 2, encounter_chance: int = 11,
    treasure_chest_dc: int = 17, chest_trap_dc: int = 19, chest_lock_dc: int = 17,
    rules: Optional[EncounterRules] = None,
) -> Tuple[GeneratedDungeon, Tuple[EncounterLevel, ...]]:
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
    remaining = list(load_puzzles())
    catalog_count = len(remaining)
    keys = []  # type: List[EncounterLevel]
    puzzle_rng = None  # type: Optional[random.Random]

    def finish_level(level: GeneratedDungeon, depth: int) -> GeneratedDungeon:
        nonlocal puzzle_rng
        if puzzle_rng is None:
            puzzle_rng = random.Random("{}:puzzles".format(level.seed))
        contents = generate_encounters(
            level, rules=rules, start_level=depth, **encounter_options,
        )[0]
        successes = sum(puzzle_rng.random() < puzzle_probability
                        for _ in range(max_puzzles_per_level))
        eligible = [definition for definition in remaining if definition.eligible(depth)]
        count = min(len(eligible), successes)
        definitions = puzzle_rng.sample(eligible, count)
        for definition in definitions:
            remaining.remove(definition)
        if definitions:
            before = level
            level, placements, goal = _attach_puzzles(level, definitions, options, depth)
            contents = _stock_wing(before, level, contents, placements, goal)
            placed = []
            for puzzle in placements:
                candidates = [
                    (source_depth, area.cell)
                    for source_depth, source_key in enumerate(keys + [contents], 1)
                    for area in source_key.areas
                    if not (source_depth == depth and area.cell == puzzle.cell)
                    and not any(area.cell in other.protected_cells for other in source_key.puzzles)
                ]
                if puzzle.definition.required_items and not candidates:
                    raise ValueError("no accessible encounter area for required puzzle items")
                items = tuple(PuzzleItem(name, *puzzle_rng.choice(candidates))
                              for name in puzzle.definition.required_items)
                placed.append(replace(puzzle, items=items))
            contents = replace(contents, puzzles=tuple(placed))
        elif not remaining:
            level = replace(level, layout_notes=level.layout_notes + (
                "All {} unique puzzles have been used; no further puzzles can be placed.".format(catalog_count),
            ))
        level = replace(level, layout_notes=level.layout_notes + (
            "Puzzle rolls: {} successes in {} slots at probability {:g}; placed {}{}.".format(
                successes, max_puzzles_per_level, puzzle_probability, count,
                " (limited by unused puzzles eligible at this depth)" if count < successes else "",
            ),
        ))
        keys.append(contents)
        return level

    dungeon = generate_dungeon(options, level_transform=finish_level)
    _finalize_rewards(keys)
    _write_puzzle_notes(keys)
    result = tuple(keys)
    validate_puzzle_dungeon(dungeon, result)
    return dungeon, result
