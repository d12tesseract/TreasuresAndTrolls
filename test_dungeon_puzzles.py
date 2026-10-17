import random
import re
import itertools
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import dungeon_map
import dungeon_puzzles
from dungeon_encounters import (
    EncounterArea, EncounterRules, encounter_document, encounter_log, generate_encounters,
    puzzle_treasure,
)
from dungeon_map import GenerationOptions, generate_dungeon, is_connected, parse_ascii, validate_map
from dungeon_puzzles import PUZZLE_COUNT, generate_adventure, load_puzzles, treasure_value, validate_puzzle_dungeon


HERE = Path(__file__).resolve().parent


def flood(grid, start, blocked=()):
    """Independent four-way traversal for fixtures without diagonal/partition tiles."""
    seen = {start}
    pending = [start]
    while pending:
        x, y = pending.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cell = (x + dx, y + dy)
            if cell not in seen and cell not in blocked and grid.tile(*cell) != "#":
                seen.add(cell)
                pending.append(cell)
    return seen


class PuzzleGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Load encounter rules and puzzle definitions shared by generation fixtures."""
        cls.rules = EncounterRules()
        cls.catalog = load_puzzles()

    def adventure(self, options=None, **kwargs):
        """Generate a stocked adventure with shared rules and reproducible defaults."""
        return generate_adventure(options or GenerationOptions(seed=42, width=30, height=24),
                                  rules=self.rules, **kwargs)

    def catalog_only(self, *numbers):
        """Restrict puzzle loading to the requested catalog numbers during a fixture."""
        return patch("dungeon_puzzles.load_puzzles",
                     return_value=tuple(p for p in self.catalog if p.number in numbers))

    def test_disabled_puzzles_preserve_layout_and_stocking(self):
        """Disabling probability or slots preserves the original layout and encounters."""
        options = GenerationOptions(seed=42, width=30, height=24, levels=2)
        original = generate_dungeon(options)
        contents = generate_encounters(original, rules=self.rules)
        for kwargs in (dict(puzzle_probability=0), dict(max_puzzles_per_level=0)):
            with self.subTest(kwargs=kwargs):
                actual, keys = self.adventure(options, **kwargs)
                self.assertEqual(actual, original)
                self.assertEqual(keys, contents)
                self.assertFalse(any(key.puzzles for key in keys))

    def test_default_probability_can_produce_zero_one_and_two(self):
        """Default puzzle rolls reproducibly allow zero, one, or two placements."""
        seeds = {}
        for seed in range(100):
            rng = random.Random("{}:puzzles".format(seed))
            count = sum(rng.random() < 0.35 for _ in range(2))
            seeds.setdefault(count, seed)
        self.assertEqual(set(seeds), {0, 1, 2})
        for expected, seed in seeds.items():
            with self.subTest(expected=expected):
                options = GenerationOptions(seed=seed, width=24, height=20)
                dungeon, keys = self.adventure(options)
                self.assertEqual(len(keys[0].puzzles), expected)
                self.assertEqual((dungeon, keys), self.adventure(options))

    def test_invalid_probability_and_slot_counts(self):
        """Reject invalid puzzle probabilities, slot counts, and encounter start levels."""
        for value in (-0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(probability=value), self.assertRaises(ValueError):
                self.adventure(puzzle_probability=value)
        for value in (-1, PUZZLE_COUNT + 1, 1.5, True):
            with self.subTest(slots=value), self.assertRaises(ValueError):
                self.adventure(max_puzzles_per_level=value)
        for value in (0, -1, True):
            with self.subTest(start_level=value), self.assertRaises(ValueError):
                generate_encounters(generate_dungeon(GenerationOptions(seed=1)),
                                    rules=self.rules, start_level=value)

    def test_entire_catalog_is_unique_and_playable_in_key(self):
        """Every catalog puzzle appears once with playable text, items, and consequences."""
        dungeon, keys = self.adventure(
            GenerationOptions(seed=42, width=24, height=16, levels=4),
            puzzle_probability=1, max_puzzles_per_level=PUZZLE_COUNT,
        )
        puzzles = [p for key in keys for p in key.puzzles]
        self.assertEqual({p.definition.number for p in puzzles}, set(range(1, PUZZLE_COUNT + 1)))
        self.assertEqual(len(puzzles), PUZZLE_COUNT)
        validate_puzzle_dungeon(dungeon, keys)
        markdown = encounter_document(dungeon, keys, 11)
        log = encounter_log(dungeon, keys, 11)
        for puzzle in puzzles:
            self.assertIn("**Puzzle P{:02d}: {}**".format(
                puzzle.definition.number, puzzle.definition.name), markdown)
            self.assertIn(puzzle.definition.body.split("**Reward:**")[0].strip(), markdown)
            self.assertEqual(len(puzzle.items), len(puzzle.definition.required_items))
            for item in puzzle.items:
                self.assertIn("**Puzzle item:** " + item.name, markdown)
        self.assertEqual(markdown.count("**Solution:**"), PUZZLE_COUNT)
        self.assertIn("Progression gate:", log)
        for depth, key in enumerate(keys, 1):
            for puzzle in key.puzzles:
                if puzzle.definition.consequence_rules:
                    area = next(a for a in key.areas if a.cell == puzzle.cell)
                    self.assertIn("**Puzzle consequence level:** L = {}.".format(depth),
                                  area.notes)

    def test_pool_exhaustion_does_not_repeat_puzzles(self):
        """Exhausting the puzzle pool leaves later levels empty instead of repeating."""
        with self.catalog_only(3, 5, 12):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=3),
                puzzle_probability=1,
            )
        self.assertEqual([len(key.puzzles) for key in keys], [2, 1, 0])
        self.assertEqual(len({p.definition.number for key in keys for p in key.puzzles}), 3)
        self.assertIn("no further puzzles", " ".join(dungeon.levels[-1].layout_notes))

    def test_gate_and_local_puzzles_are_independently_accessible(self):
        """Closed gates protect rewards without blocking access to other puzzles."""
        with self.catalog_only(6, 14, 20, 21):
            dungeon, keys = self.adventure(puzzle_probability=1, max_puzzles_per_level=4)
        puzzles = {p.definition.number: p for p in keys[0].puzzles}
        for number in (6, 20, 21):
            self.assertIsNotNone(puzzles[number].gate)
            self.assertNotIn(puzzles[14].cell, puzzles[number].protected_cells)
        closed = {p.gate for p in puzzles.values() if p.gate}
        accessible = flood(dungeon.grid, puzzles[6].cell, closed)
        self.assertTrue(all(p.cell in accessible for p in puzzles.values()))
        for puzzle in puzzles.values():
            if puzzle.gate:
                self.assertNotIn(puzzle.reward_cell, accessible)
        guide = encounter_document(dungeon, keys, 11)
        self.assertEqual(guide.count("**Key binding:**"), 2)
        self.assertNotIn("All passage puzzles on this level must be solved", guide)

    def test_each_level_is_stocked_before_the_next_layout(self):
        """Generation alternates each level's layout with its encounter stocking."""
        events = []
        generate_level = dungeon_map._generate_level
        stock = dungeon_puzzles.generate_encounters

        def layout(*args, **kwargs):
            """Record layout generation before forwarding its original arguments."""
            events.append("layout")
            return generate_level(*args, **kwargs)

        def contents(*args, **kwargs):
            """Record encounter stocking before forwarding its original arguments."""
            events.append("stock")
            return stock(*args, **kwargs)

        with patch("dungeon_map._generate_level", side_effect=layout), patch(
            "dungeon_puzzles.generate_encounters", side_effect=contents,
        ):
            self.adventure(GenerationOptions(seed=42, width=30, height=24, levels=3),
                           puzzle_probability=1)
        self.assertEqual(events, ["layout", "stock"] * 3)

    def test_stair_puzzles_put_spirals_in_the_room_and_preserve_alignment(self):
        """Stair puzzles use aligned in-room spirals while gates protect separate loot."""
        options = GenerationOptions(seed=42, width=30, height=24, levels=3,
                                    stairs_down=2, ramps_down=1, ramp_probability=100)
        with self.catalog_only(2, 3, 6, 8, 11, 12):
            dungeon, keys = self.adventure(options, puzzle_probability=1)
        for depth, (level, key) in enumerate(zip(dungeon.levels, keys), 1):
            validate_map(level.grid)
            self.assertTrue(is_connected(level.grid))
            entrance = next(p.entrance for p in level.stairways if p.tile in "ERS")
            down = [p for p in level.stairways if p.tile in "ers"]
            spiral_puzzles = [p for p in key.puzzles if p.next_level]
            self.assertEqual(sum(p.spiral for p in down), len(spiral_puzzles))
            all_closed = {p.gate for p in key.puzzles if p.gate}
            self.assertTrue(all(p.cell in flood(level.grid, entrance, all_closed) for p in key.puzzles))
            for puzzle in key.puzzles:
                if puzzle.next_level:
                    self.assertIsNone(puzzle.gate)
                    self.assertIsNone(puzzle.reward_cell)
                    room = next(c for c in level.room_cells if puzzle.cell in c)
                    stairs = next(p for p in down if set(p.cells) <= set(room))
                    self.assertTrue(stairs.spiral)
                    self.assertEqual(stairs.tile, "s")
                    self.assertEqual(len({x for x, y in stairs.cells}), 3)
                    self.assertGreaterEqual(len({x for x, y in room}), 5)
                    self.assertGreaterEqual(len({y for x, y in room}), 5)
                    continue
                reachable = flood(level.grid, entrance, {puzzle.gate})
                self.assertFalse(set(puzzle.protected_cells) & reachable)
                self.assertIn(puzzle.cell, flood(level.grid, entrance))
                for stairs in down:
                    self.assertFalse(set(stairs.cells) & set(puzzle.protected_cells))
                self.assertTrue(any(area.cell not in reachable for area in key.areas))
                for stairs in level.stairways:
                    if stairs.tile in "ERS":
                        self.assertTrue(set(stairs.cells) <= reachable)
            if depth < 3:
                upstairs = [p for p in dungeon.levels[depth].stairways if p.tile in "ERS"]
                self.assertEqual([p.cells for p in down], [p.cells for p in upstairs])
                self.assertEqual([p.horizontal for p in down], [p.horizontal for p in upstairs])
                for passage in down + upstairs:
                    if not passage.spiral:
                        self.assertEqual(len(passage.cells), options.stair_length)
                self.assertEqual(len(keys[depth].stair_notes), len(spiral_puzzles))
                for puzzle in spiral_puzzles:
                    self.assertTrue(any("P{:02d}:".format(puzzle.definition.number) in note
                                        for note in keys[depth].stair_notes))
        if keys[0].puzzles and any(p.next_level for p in keys[0].puzzles):
            self.assertIn("Removed 3 old down", " ".join(dungeon.layout_notes))

    def test_single_level_protects_best_hoard_with_no_stair_bypass(self):
        """Single-level gates protect guarded hoards without relocating or bypassing stairs."""
        options = GenerationOptions(seed=42, width=30, height=24, stairs_up=1,
                                    stairs_down=1, ramps_down=1)
        original = generate_dungeon(options)
        original_key = generate_encounters(original, rules=self.rules)[0]
        best = max(original_key.areas, key=treasure_value)
        with self.catalog_only(2, 12):
            dungeon, keys = self.adventure(options, puzzle_probability=1)
        self.assertEqual(dungeon.stairways, original.stairways)
        for index, puzzle in enumerate(keys[0].puzzles):
            self.assertIsNone(puzzle.next_level)
            inside = [area for area in keys[0].areas if area.cell in puzzle.protected_cells]
            reward = max(inside, key=treasure_value)
            self.assertGreaterEqual(treasure_value(reward), (0, 0, Decimal(1000)))
            self.assertIsNotNone(reward.monster)
            if index == 0:
                self.assertGreaterEqual(treasure_value(reward), treasure_value(best))
            if index == 0 and treasure_value(best) >= (0, 0, Decimal(1000)):
                self.assertEqual(reward.treasure, best.treasure)
                if best.monster:
                    self.assertEqual(reward.monster, best.monster)
                self.assertEqual(reward.container, best.container)
                self.assertEqual(reward.chest_trap, best.chest_trap)
                self.assertEqual(reward.chest_locked, best.chest_locked)
            self.assertFalse(any(set(stairs.cells) & set(puzzle.protected_cells)
                                 for stairs in dungeon.stairways))

    def test_final_level_stair_puzzle_keeps_its_in_room_spiral(self):
        """A final-level stair puzzle retains its in-room spiral to ungenerated depths."""
        with self.catalog_only(3):
            dungeon, keys = self.adventure(puzzle_probability=1, max_puzzles_per_level=1)
        puzzle = keys[0].puzzles[0]
        self.assertEqual(puzzle.next_level, 2)
        self.assertIsNone(puzzle.reward_cell)
        stairs = next(p for p in dungeon.stairways if p.tile == "s")
        room = next(set(c) for c in dungeon.room_cells if puzzle.cell in c)
        self.assertTrue(stairs.spiral)
        self.assertTrue(set(stairs.cells) <= room)
        self.assertIn("beyond the generated maps", encounter_document(dungeon, keys, 11))

    def test_stair_gate_uses_the_existing_puzzle_chamber_not_a_remote_wing(self):
        """Put a stair gate and its entire spiral in one existing encounter chamber."""
        options = GenerationOptions(seed=42, width=30, height=24, levels=2)
        original = generate_dungeon(options)
        with self.catalog_only(3):
            dungeon, keys = self.adventure(
                options, puzzle_probability=1, max_puzzles_per_level=1)
        puzzle = keys[0].puzzles[0]
        room = next((set(cells) for cells in original.room_cells if puzzle.cell in cells), None)
        self.assertIsNotNone(room, "the puzzle must stay in an existing chamber")
        stairs = next(p for p in dungeon.stairways if p.tile == "s")
        self.assertTrue(stairs.clearance <= room)
        self.assertEqual(len(dungeon.room_cells), len(original.room_cells))
        self.assertEqual(dungeon.grid.width, original.grid.width)
        self.assertIsNone(puzzle.gate)
        self.assertIsNone(puzzle.reward_cell)
        self.assertIn(dungeon.grid.tile(*puzzle.cell), " .")
        self.assertIn(puzzle.cell, keys[0].labels)
        upstairs = next(p for p in dungeon.levels[1].stairways if p.tile == "S")
        self.assertEqual(stairs.cells, upstairs.cells)

    def test_in_room_spiral_has_a_valid_center_on_rough_cavern_floor(self):
        """Convert a rough cavern's central period to valid open spiral-center floor."""
        options = GenerationOptions(seed=1, width=40, height=30, room_size=55,
                                    rough_probability=1)
        original = generate_dungeon(options)
        with self.catalog_only(3):
            dungeon, keys = self.adventure(
                options, puzzle_probability=1, max_puzzles_per_level=1)
        puzzle = keys[0].puzzles[0]
        self.assertTrue(any(puzzle.cell in room for room in original.room_cells))
        stairs = next(p for p in dungeon.stairways if p.tile == "s")
        center = (min(x for x, y in stairs.cells) + 1,
                  min(y for x, y in stairs.cells) + 1)
        self.assertEqual(original.grid.tile(*center), ".")
        self.assertEqual(dungeon.grid.tile(*center), " ")
        validate_map(dungeon.grid)

    def test_room_spirals_require_a_complete_five_by_five_floor_area(self):
        for width, height in ((4, 4), (4, 5), (5, 4), (5, 5)):
            room = tuple((x, y) for y in range(2, height + 2)
                         for x in range(2, width + 2))
            rows = [["#"] * 10 for _ in range(10)]
            for x, y in room:
                rows[y][x] = " "
            level = dungeon_map.GeneratedDungeon(
                dungeon_map.DungeonMap(tuple("".join(row) for row in rows)),
                1, (len(room),), (), room_cells=(room,),
            )
            candidates = dungeon_puzzles._room_spiral_candidates(level, set())
            self.assertEqual(bool(candidates), width >= 5 and height >= 5)
            if candidates:
                for tile in "#D":
                    rows[2][2] = tile
                    blocked = replace(level, grid=dungeon_map.DungeonMap(
                        tuple("".join(row) for row in rows)))
                    self.assertFalse(dungeon_puzzles._room_spiral_candidates(blocked, set()))

    def test_spiral_validation_rejects_walls_or_doorways_in_its_clear_floor_ring(self):
        room = tuple((x, y) for y in range(2, 7) for x in range(2, 7))
        rows = [["#"] * 10 for _ in range(10)]
        for x, y in room:
            rows[y][x] = " "
        stairs = dungeon_map.Stairway.spiral_at(3, 3, tile="s")
        stairs.paint(rows)
        level = dungeon_map.GeneratedDungeon(
            dungeon_map.DungeonMap(tuple("".join(row) for row in rows)),
            1, (len(room),), (), stairways=(stairs,), room_cells=(room,),
        )
        puzzle = dungeon_puzzles.PlacedPuzzle(
            next(p for p in self.catalog if p.number == 3), (4, 6), next_level=2,
        )
        dungeon_puzzles._validate_stair_puzzle(puzzle, level, [stairs], 1, ())
        for tile in "#D":
            rows[2][2] = tile
            blocked = replace(level, grid=dungeon_map.DungeonMap(
                tuple("".join(row) for row in rows)))
            with self.assertRaisesRegex(ValueError, "clear floor"):
                dungeon_puzzles._validate_stair_puzzle(puzzle, blocked, [stairs], 1, ())

    def test_one_exit_leaves_extra_gates_as_separate_guarded_reward_branches(self):
        """One exit uses one stair puzzle and leaves independent guarded reward gates."""
        options = GenerationOptions(seed=42, width=30, height=24, levels=2, stairs_down=1)
        with self.catalog_only(3, 6, 12):
            dungeon, keys = self.adventure(options, puzzle_probability=1, max_puzzles_per_level=3)
            self.assertEqual((dungeon, keys), self.adventure(
                options, puzzle_probability=1, max_puzzles_per_level=3))
        puzzles = keys[0].puzzles
        self.assertCountEqual([p.next_level for p in puzzles], [2, None, None])
        entrance = next(p.entrance for p in dungeon.stairways if p.tile == "E")
        for chosen in puzzles:
            reachable = flood(dungeon.grid, entrance, {p.gate for p in puzzles if p != chosen})
            self.assertTrue(all(p.cell in reachable for p in puzzles))
            if chosen.next_level:
                self.assertIsNone(chosen.reward_cell)
                continue
            self.assertIn(chosen.reward_cell, reachable)
            self.assertTrue(all(p.reward_cell not in reachable for p in puzzles
                                if p != chosen and p.reward_cell))
            reward = next(a for a in keys[0].areas if a.cell == chosen.reward_cell)
            self.assertIsNotNone(reward.monster)
            self.assertGreaterEqual(treasure_value(reward), (0, 0, Decimal(1000)))
        self.assertEqual(len(keys[1].stair_notes), 1)

    def test_separate_branches_fit_minimum_height_without_a_corridor_bypass(self):
        """Minimum-height maps fit separate reward branches without bypassing gates."""
        options = GenerationOptions(seed=42, width=30, height=7, room_size=4)
        with self.catalog_only(2, 6, 11):
            dungeon, keys = self.adventure(options, puzzle_probability=1, max_puzzles_per_level=3)
        self.assertGreaterEqual(dungeon.grid.height, 7)
        for puzzle in keys[0].puzzles:
            reachable = flood(dungeon.grid, keys[0].puzzles[0].cell, {puzzle.gate})
            self.assertFalse(set(puzzle.protected_cells) & reachable)
            self.assertTrue(all(p.cell in reachable for p in keys[0].puzzles))

    def test_branch_hoards_are_ranked_and_not_duplicated(self):
        """Separate branches receive ranked, nonduplicated hoards in disjoint regions."""
        awarded = []

        def loot(*args):
            """Issue a uniquely ranked ring and coin hoard for each stocking call."""
            rank = len(awarded) + 1
            treasure = ("Magic Ring: Unique reward {} (power +{})".format(rank, rank),
                        "Coins: {} pp.".format(rank))
            awarded.append(treasure)
            return treasure

        with self.catalog_only(2, 6, 11), patch("dungeon_encounters.treasure", side_effect=loot):
            dungeon, keys = self.adventure(puzzle_probability=1, max_puzzles_per_level=3)
        actual = [area.treasure for area in keys[0].areas if area.treasure != ("None.",)]
        self.assertCountEqual(actual, awarded)
        ordered = sorted((treasure_value(area) for area in keys[0].areas), reverse=True)
        rewards = [next(area for area in keys[0].areas if area.cell == p.reward_cell)
                   for p in keys[0].puzzles]
        self.assertEqual([treasure_value(a) for a in rewards], ordered[:3])
        for puzzle in keys[0].puzzles:
            self.assertFalse(any(set(puzzle.protected_cells) & set(other.protected_cells)
                                 for other in keys[0].puzzles if other != puzzle))

    def test_validator_rejects_nested_rewards_and_missing_lower_stair_seals(self):
        """Reject overlapping reward regions and lower stairs without puzzle seals."""
        with self.catalog_only(2, 6):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=2, stairs_down=2),
                puzzle_probability=1)
        first, second = keys[0].puzzles
        nested = replace(first, protected_cells=first.protected_cells + second.protected_cells)
        invalid = (replace(keys[0], puzzles=(nested, second)), keys[1])
        with self.assertRaisesRegex(ValueError, "overlap or be nested"):
            validate_puzzle_dungeon(dungeon, invalid)
        with self.catalog_only(3):
            stairs, stair_keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=2),
                puzzle_probability=1)
        with self.assertRaisesRegex(ValueError, "stair seal"):
            validate_puzzle_dungeon(stairs, (stair_keys[0], replace(stair_keys[1], stair_notes=())))

    def test_magic_priority_over_consumables_and_monetary_values(self):
        """Treasure ranking favors permanent magic over consumables and monetary value."""
        def area(*loot):
            """Wrap supplied treasure descriptions in an otherwise empty encounter area."""
            return EncounterArea(1, (1, 1), 0, None, None, loot, "None.")
        money = area("Coins: 10000 pp.", "Gems/jewelry: 2 pieces, worth 500 gp, 25 sp individually.")
        potions = area("Magic Potion: Healing (power +4)", "Magic Scroll: Protection (power +1)")
        staff = area("Magic Staff: Healing; 1 charges (maximum 24) (power +1)")
        armor = area("Magic Armor: Plate; +1 toughness (power +1)", "Coins: 1 cp.")
        self.assertEqual(treasure_value(money), (0, 0, Decimal(10050250)))
        self.assertGreater(treasure_value(potions), treasure_value(money))
        self.assertGreater(treasure_value(staff), treasure_value(potions))
        self.assertGreater(treasure_value(armor), treasure_value(staff))

    def test_no_rolled_treasure_still_provides_a_protected_reward(self):
        """A gate receives a protected fallback reward when stocking rolls no treasure."""
        with self.catalog_only(2), patch("dungeon_encounters.treasure", return_value=("None.",)):
            dungeon, keys = self.adventure(puzzle_probability=1, max_puzzles_per_level=1)
        puzzle = keys[0].puzzles[0]
        inside = [area for area in keys[0].areas if area.cell in puzzle.protected_cells]
        self.assertEqual(max(inside, key=treasure_value).treasure, ("Coins: 100 sp.",))
        validate_puzzle_dungeon(dungeon, keys)

    def test_final_section_receives_best_hoard_from_an_earlier_level_without_duplication(self):
        """The final puzzle receives the dungeon's best earlier hoard exactly once."""
        best_loot = ("Magic Staff: Healing; 12 charges (maximum 24) (power +4)",)
        awarded = []

        def loot(rules, rng, depth, encounter, debug):
            """Award the unique best hoard once on level one, then ordinary coins."""
            if depth == 1 and not awarded:
                awarded.append(True)
                return best_loot
            return ("Coins: 10 sp.",)

        with self.catalog_only(2, 12), patch("dungeon_encounters.treasure", side_effect=loot):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=2),
                puzzle_probability=1, max_puzzles_per_level=1,
            )
        holders = [(depth, area) for depth, key in enumerate(keys, 1)
                   for area in key.areas if area.treasure == best_loot]
        self.assertEqual(len(holders), 1)
        self.assertEqual(holders[0][0], 2)
        self.assertIn(holders[0][1].cell, keys[-1].puzzles[0].protected_cells)
        validate_puzzle_dungeon(dungeon, keys)
        self.assertIn("in the entire dungeon", encounter_document(dungeon, keys, 11))

    def test_required_items_are_reachable_and_referenced_in_both_areas(self):
        """Required items remain reachable and cross-reference source and puzzle areas."""
        with self.catalog_only(3, 5, 9, 10, 12, 27):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=3),
                puzzle_probability=1,
            )
        earlier = current = False
        for depth, (level, key) in enumerate(zip(dungeon.levels, keys), 1):
            for puzzle in key.puzzles:
                target = next(area for area in key.areas if area.cell == puzzle.cell)
                for item in puzzle.items:
                    earlier |= item.source_level < depth
                    current |= item.source_level == depth
                    source_key = keys[item.source_level - 1]
                    source_level = dungeon.levels[item.source_level - 1]
                    source = next(area for area in source_key.areas if area.cell == item.source_cell)
                    entry = next(p.entrance for p in source_level.stairways if p.tile in "ERS")
                    blocked = {p.gate for p in source_key.puzzles if p.gate}
                    if item.source_level == depth:
                        self.assertIn(source.cell, flood(source_level.grid, entry, blocked))
                    self.assertIn("Level {}, Area {}".format(item.source_level, source.number),
                                  "\n".join(target.notes))
                    self.assertIn("Level {}, Area {}".format(depth, target.number),
                                  "\n".join(source.puzzle_items))
                    self.assertIn("**Puzzle item:** " + item.name, "\n".join(source.puzzle_items))
                    self.assertIn("P{:02d}:".format(puzzle.definition.number), "\n".join(source.puzzle_items))
        self.assertTrue(earlier)
        self.assertTrue(current)

    def test_required_items_prefer_earlier_puzzle_reward_and_are_physical_loot(self):
        """Required items prefer earlier rewards and must exist in the source area's loot."""
        catalog = tuple(replace(p, min_level=1 if p.number == 2 else 2,
                                max_level=1 if p.number == 2 else 2)
                        for p in self.catalog if p.number in (2, 3))
        with patch("dungeon_puzzles.load_puzzles", return_value=catalog):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=2),
                puzzle_probability=1, max_puzzles_per_level=1)
        earlier = keys[0].puzzles[0]
        later = keys[1].puzzles[0]
        self.assertEqual(later.items[0].source_level, 1)
        self.assertEqual(later.items[0].source_cell, earlier.reward_cell)
        source = next(a for a in keys[0].areas if a.cell == earlier.reward_cell)
        target = next(a for a in keys[1].areas if a.cell == later.cell)
        self.assertIn("sun lens", source.puzzle_items[0])
        self.assertIn("Level 2, Area {}".format(target.number), source.puzzle_items[0])
        markdown = encounter_document(dungeon, keys, 11)
        source_md = markdown.split("### {}\n".format(source.number), 1)[1].split("\n### ", 1)[0]
        self.assertIn("- **Puzzle item:** sun lens", source_md)
        self.assertIn("Level 1, Area {}".format(source.number), "\n".join(target.notes))
        self.assertTrue(all(a.puzzle_reward for k in keys for a in k.areas
                            if any(p.cell == a.cell for p in k.puzzles)))
        missing_item = replace(keys[0], areas=tuple(
            replace(a, puzzle_items=()) if a.cell == source.cell else a for a in keys[0].areas))
        with self.assertRaisesRegex(ValueError, "source encounter's loot"):
            validate_puzzle_dungeon(dungeon, (missing_item, keys[1]))

    def test_puzzle_prizes_use_weighted_categories_and_depth_value_table(self):
        """Prize category boundaries select jewelry, gems, or depth-scaled magic."""
        rng = random.Random(42)
        expression, currency = self.rules.gems[7][0].rsplit(" ", 1)
        for chance, kind, count_expression in (
            (0.0, "Jewelry", "d3"), (0.399999, "Jewelry", "d3"),
            (0.4, "Gem", "d6"), (0.799999, "Gem", "d6"),
        ):
            with self.subTest(chance=chance), patch.object(rng, "random", return_value=chance), patch(
                "dungeon_encounters._dice", side_effect=(2, 7, 11),
            ) as roll:
                result = puzzle_treasure(self.rules, rng, 7)
                self.assertEqual(len(result), 2)
                self.assertTrue(all(line.startswith(kind + ":") for line in result))
                self.assertIn("7 " + currency, result[0])
                self.assertIn("11 " + currency, result[1])
                self.assertEqual([call[0][1] for call in roll.call_args_list],
                                 [count_expression, expression, expression])
        with patch.object(rng, "random", return_value=0.8), patch(
            "dungeon_encounters.magic_item", return_value="Magic Ring: Protection (power +2)",
        ) as magic:
            self.assertEqual(puzzle_treasure(self.rules, rng, 7),
                             ("Magic Ring: Protection (power +2)",))
            magic.assert_called_once_with(self.rules, rng, 7, None)

    def test_same_level_gates_reuse_edge_rooms_and_have_short_stairless_branches(self):
        """Local gates reuse edge rooms and protect short branches without stairs."""
        options = GenerationOptions(seed=42, width=30, height=24)
        original = generate_dungeon(options)
        with self.catalog_only(2):
            dungeon, keys = self.adventure(options, puzzle_probability=1, max_puzzles_per_level=1)
        puzzle = keys[0].puzzles[0]
        self.assertTrue(any(puzzle.cell in room for room in original.room_cells))
        self.assertEqual(len(dungeon.room_cells), len(original.room_cells) + 1)
        reward_room = next(set(room) for room in dungeon.room_cells if puzzle.reward_cell in room)
        self.assertFalse(any(set(s.cells) & reward_room for s in dungeon.stairways))
        corridor = set(puzzle.protected_cells) - reward_room
        self.assertLessEqual(len(corridor) + 1, 10)
        self.assertFalse(set(puzzle.protected_cells) & flood(dungeon.grid, puzzle.cell, {puzzle.gate}))

    def test_malformed_catalog_fails_instead_of_silently_losing_puzzles(self):
        """Incomplete catalog entries fail explicitly rather than silently disappearing."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.md"
            path.write_text("### 1. Missing everything\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "1 through {}".format(PUZZLE_COUNT)):
                load_puzzles(path)

    def test_consequence_coverage_and_retry_classes(self):
        """Consequence coverage and treasure, trap, and access retry rules match the catalog."""
        affected = [p for p in self.catalog if "**Consequences:**" in p.body]
        self.assertGreaterEqual(100 * len(affected) / len(self.catalog), 69)
        self.assertLessEqual(100 * len(affected) / len(self.catalog), 70)
        traps = set()
        for puzzle in affected:
            with self.subTest(puzzle=puzzle.number):
                kind = re.search(r"\*\*Consequences:\*\* (Treasure|Trap|Access);", puzzle.body)[1]
                self.assertTrue(puzzle.consequence_rules)
                self.assertIn("S = min(f, L + 2)", puzzle.consequence_rules)
                self.assertIn("A party wipe remains", puzzle.consequence_rules)
                self.assertIn("including for the last surviving character", puzzle.consequence_rules)
                if kind == "Treasure":
                    self.assertFalse(puzzle.passage)
                    self.assertRegex(puzzle.body, r"\*\*\d+ (?:failed|wrong|lost|mismatched)")
                    self.assertIn("permanent", puzzle.body)
                else:
                    self.assertIn("unlimited retries", puzzle.body)
                    if kind == "Trap":
                        traps.add(puzzle.number)
                    else:
                        self.assertTrue(puzzle.passage)
        self.assertEqual(traps, {5, 10, 23, 47})
        self.assertTrue(all(not p.consequence_rules for p in self.catalog if p not in affected))

    def test_generated_key_carries_consequence_rules_at_actual_dungeon_level(self):
        """Generated keys include shared consequences at the puzzle's actual depth."""
        with self.catalog_only(4, 9, 20, 35, 41, 47):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24),
                puzzle_probability=1, max_puzzles_per_level=6,
            )
        self.assertEqual({p.definition.number for p in keys[0].puzzles}, {4, 9, 20, 35, 41, 47})
        guide = encounter_document(dungeon, keys, 11)
        for puzzle in keys[0].puzzles:
            area = next(a for a in keys[0].areas if a.cell == puzzle.cell)
            notes = "\n".join(area.notes)
            self.assertIn("**Puzzle consequence level:** L = 1.", notes)
            self.assertIn(puzzle.definition.consequence_rules, notes)
            self.assertIn(puzzle.definition.body.split("**Reward:**")[0].strip(), guide)
            self.assertEqual(puzzle.gate is not None, puzzle.definition.number == 20)

    def test_consequences_without_shared_rules_are_rejected(self):
        """Reject consequence-bearing catalogs that omit their shared consequence rules."""
        text = dungeon_puzzles.CATALOG_PATH.read_text(encoding="utf-8")
        text = re.sub(r"(?ms)^## Consequence Rules\n.*?(?=^## )", "", text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.md"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "shared consequence rules"):
                load_puzzles(path)

    def test_escape_clues_have_search_dcs_fair_decoys_and_correct_codes(self):
        """Escape clues have fair search DCs and decoys and decode to advertised codes."""
        for puzzle in self.catalog[40:]:
            with self.subTest(puzzle=puzzle.number):
                body = puzzle.body
                rows = re.findall(
                    r"(?m)^\| (Genuine|Decoy) \| ([^|]+) \| (\d+) \| ([^|]+) \| ([^|]+) \|$",
                    body,
                )
                real = [payload.strip() for kind, _, _, payload, _ in rows if kind == "Genuine"]
                decoys = [row for row in rows if row[0] == "Decoy"]
                self.assertTrue(2 <= len(real) <= 4)
                self.assertTrue(2 <= len(decoys) <= 4)
                self.assertTrue(all(int(row[2]) in (17, 20) for row in rows))
                self.assertEqual(len({row[1] for row in rows}), len(rows))
                self.assertIn("**Cipher key:**", body)
                self.assertIn("**Search:**", body)
                self.assertIn("WIS modifier", body)
                self.assertTrue(all(row[4].strip() for row in decoys))
                expected = re.search(r"(?m)^\*\*Escape code:\*\* (.+)$", body)[1]
                self.assertEqual(self._decode_escape_clues(puzzle.number, body, real), expected)

    def _decode_escape_clues(self, number, body, real):
        """Independently decode each escape puzzle's genuine clues using its cipher key."""
        if number == 41:
            lookup = dict(re.findall(r"([A-Z]+)=(\d)", body))
            return "".join(lookup[value] for value in real)
        if number == 42:
            alphabets = re.search(r"```text\n([A-Z]+)\n([A-Z]+)\n```", body)
            lookup = dict(zip(alphabets[1], alphabets[2]))
            return "".join(lookup[letter] for value in real for letter in value)
        if number == 43:
            return "".join(real)[::-1]
        if number == 44:
            grid = re.search(r"```text\n(.*?)\n```", body, re.S)[1].splitlines()[1:]
            letters = [row.split()[1:] for row in grid]
            return "".join(letters[int(value[0]) - 1][int(value[1]) - 1] for value in real)
        if number == 45:
            book = re.search(r"```text\n(.*?)\n```", body, re.S)[1].splitlines()
            decoded = ""
            for value in real:
                line, word = map(int, value.split("/"))
                decoded += book[line - 1].split()[word][0].upper()
            return decoded
        if number == 46:
            return "".join(str(int(value, 2)) for value in real)
        if number == 47:
            lookup = {signals: letter for letter, signals in re.findall(r"([A-Z])=([.-]+)", body)}
            return "".join(lookup[value] for value in real)
        if number == 48:
            return self._decode_ordered_escape_clues(body, real)
        if number == 49:
            windows = re.findall(r"(?:PULSE|BREATH): (\d),(\d)", body)
            return "".join(word[int(index) - 1]
                           for word, indices in zip(real, windows) for index in indices)
        if number == 50:
            return "".join(value if row % 2 == 0 else value[::-1]
                           for row, value in enumerate(real))
        self.fail("escape puzzle needs a decoding regression case")

    def _decode_ordered_escape_clues(self, body, real):
        """Require one valid clue ordering before translating its words into the code."""
        lookup = dict(re.findall(r"([A-Z]+)=([A-Z]+)", body))
        first = real[0].split()[0]
        after, before = real[1].split()[0], real[1].split()[-1]
        last = real[2].split()[0]
        solutions = [
            order for order in itertools.permutations(lookup)
            if order[0] == first and order[-1] == last
            and order.index(after) == order.index(before) + 1
        ]
        self.assertEqual(len(solutions), 1)
        return " ".join(lookup[value] for value in solutions[0])

    def test_all_escape_puzzles_reach_tm_key_and_keep_solutions_off_svg(self):
        """All escape puzzles reach the TM key without exposing clues or codes in SVG."""
        with self.catalog_only(*range(41, 51)):
            dungeon, keys = self.adventure(puzzle_probability=1, max_puzzles_per_level=10)
        self.assertEqual({p.definition.number for p in keys[0].puzzles}, set(range(41, 51)))
        self.assertEqual({p.definition.number for p in keys[0].puzzles if p.gate},
                         {42, 44, 46, 48, 50})
        guide = encounter_document(dungeon, keys, 11)
        svg = dungeon_map.svg_document(dungeon.grid, encounter_labels=keys[0].labels, player_view=True)
        self.assertEqual(guide.count("**Escape code:**"), 10)
        self.assertEqual(guide.count("**Cipher key:**"), 10)
        self.assertEqual(guide.count("**Search:**"), 10)
        self.assertNotIn("Escape code", svg)
        self.assertNotIn("Genuine", svg)
        self.assertNotIn("Decoy", svg)
        for puzzle in keys[0].puzzles:
            self.assertIn(puzzle.definition.body.split("**Reward:**")[0].strip(), guide)
            self.assertEqual(puzzle.items, ())
        validate_puzzle_dungeon(dungeon, keys)


class PuzzleCommandLineTests(unittest.TestCase):
    def run_cli(self, script, *args):
        """Run a puzzle CLI entry point and capture its text output and status."""
        return subprocess.run([sys.executable, str(script)] + list(map(str, args)),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

    def test_both_entry_points_write_the_same_puzzle_adventure(self):
        """Shared and campaign entry points write identical playable puzzle adventures."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = []
            for name, script in (
                ("tools", HERE / "generate_dungeon_map.py"),
                ("campaign", HERE.parent / "campaigns" / "ur" / "generate_dungeon_map.py"),
            ):
                folder = root / name
                folder.mkdir()
                output = folder / "dungeon.svg"
                result = self.run_cli(
                    script, "--output", output, "--seed", 42, "--levels", 2,
                    "--width", 30, "--height", 24, "--puzzle-probability", 1,
                    "--player-view",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                files = {path.name: path.read_bytes() for path in folder.iterdir()}
                self.assertEqual(len(files), 6)
                guide = files["dungeon-encounters.md"].decode("utf-8")
                self.assertEqual(len(re.findall(r"\*\*Puzzle P\d\d:", guide)), 4)
                self.assertIn("Progression gate:", guide)
                self.assertIn("**Solution:**", guide)
                for level in (1, 2):
                    grid = parse_ascii(files["dungeon-level-{}.txt".format(level)].decode("ascii"))
                    self.assertTrue(is_connected(grid))
                    svg = files["dungeon-level-{}.svg".format(level)].decode("utf-8")
                    self.assertIn('id="encounters"', svg)
                    self.assertNotIn("Solution", svg)
                    self.assertNotIn("Required item", svg)
                outputs.append(files)
            self.assertEqual(outputs[0], outputs[1])

    def test_default_enables_stocking_and_zero_restores_unstocked_cli(self):
        """Default generation stocks encounters while zero puzzle probability opts out."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            output = folder / "default.svg"
            result = self.run_cli(HERE / "generate_dungeon_map.py", "--seed", 42, "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((folder / "default-encounters.md").exists())
            result = self.run_cli(
                HERE / "generate_dungeon_map.py", "--seed", 42, "--output", folder / "plain.svg",
                "--puzzle-probability", 0,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((folder / "plain-encounters.md").exists())
            self.assertNotIn('id="encounters"', (folder / "plain.svg").read_text())

    def test_invalid_controls_and_output_collisions_write_nothing(self):
        """Invalid puzzle controls and colliding paths fail without creating outputs."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            output = folder / "dungeon.svg"
            for args in (("--puzzle-probability", "nan"), ("--puzzle-probability", 1.1),
                         ("--puzzle-probability", -1), ("--max-puzzles-per-level", PUZZLE_COUNT + 1),
                         ("--max-puzzles-per-level", -1), ("--max-puzzles-per-level", "1.5"),
                         ("--ascii-output", folder / "dungeon-encounters.md"),
                         ("--ascii-output", folder / "dungeon-encounters.log")):
                with self.subTest(args=args):
                    result = self.run_cli(HERE / "generate_dungeon_map.py", "--seed", 42,
                                          "--output", output, *args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(list(folder.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
