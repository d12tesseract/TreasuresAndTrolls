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
    place_encounter_features, puzzle_treasure,
)
from dungeon_geometry import reachable_cells
from dungeon_map import GenerationOptions, generate_dungeon, is_connected, parse_ascii, validate_map
from dungeon_puzzles import PUZZLE_COUNT, generate_adventure, load_puzzles, treasure_value, validate_puzzle_dungeon
from dungeon_render import svg_document


HERE = Path(__file__).resolve().parent


def flood(grid, start, blocked=()):
    """Traverse generated maps using their diagonal and partition geometry."""
    return reachable_cells(grid, start, blocked)


class PuzzleGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = EncounterRules()
        cls.catalog = load_puzzles()

    def adventure(self, options=None, **kwargs):
        return generate_adventure(options or GenerationOptions(seed=42, width=30, height=24),
                                  rules=self.rules, **kwargs)

    def catalog_only(self, *numbers):
        return patch("dungeon_puzzles.load_puzzles",
                     return_value=tuple(p for p in self.catalog if p.number in numbers))

    def test_disabled_puzzles_preserve_layout_and_stocking(self):
        options = GenerationOptions(seed=42, width=30, height=24, levels=2)
        original = generate_dungeon(options)
        contents = generate_encounters(original, rules=self.rules)
        original, contents = place_encounter_features(original, contents)
        for kwargs in (dict(puzzle_probability=0), dict(max_puzzles_per_level=0)):
            with self.subTest(kwargs=kwargs):
                actual, keys = self.adventure(options, **kwargs)
                self.assertEqual(actual, original)
                self.assertEqual(keys, contents)
                self.assertFalse(any(key.puzzles for key in keys))

    def test_default_probability_can_produce_zero_one_and_two(self):
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
            self.assertIn(puzzle.definition.body.split("**Reward:**")[0].rstrip(), markdown)
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
        with self.catalog_only(3, 5, 12):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=3),
                puzzle_probability=1,
            )
        self.assertEqual([len(key.puzzles) for key in keys], [2, 1, 0])
        self.assertEqual(len({p.definition.number for key in keys for p in key.puzzles}), 3)
        self.assertIn("no further puzzles", " ".join(dungeon.levels[-1].layout_notes))

    def test_gate_and_local_puzzles_are_independently_accessible(self):
        with self.catalog_only(2, 14, 20, 21):
            dungeon, keys = self.adventure(puzzle_probability=1, max_puzzles_per_level=4)
        puzzles = {p.definition.number: p for p in keys[0].puzzles}
        for number in (2, 20, 21):
            self.assertIsNotNone(puzzles[number].gate)
            self.assertNotIn(puzzles[14].cell, puzzles[number].protected_cells)
        closed = {p.gate for p in puzzles.values() if p.gate}
        accessible = flood(dungeon.grid, puzzles[2].cell, closed)
        self.assertTrue(all(p.cell in accessible for p in puzzles.values()))
        for puzzle in puzzles.values():
            if puzzle.gate:
                self.assertNotIn(puzzle.reward_cell, accessible)
        guide = encounter_document(dungeon, keys, 11)
        self.assertEqual(guide.count("**Key binding:**"), 2)
        self.assertNotIn("All passage puzzles on this level must be solved", guide)

    def test_each_level_is_stocked_before_the_next_layout(self):
        events = []
        generate_level = dungeon_map._generate_level
        stock = dungeon_puzzles.generate_encounters

        def layout(*args, **kwargs):
            events.append("layout")
            return generate_level(*args, **kwargs)

        def contents(*args, **kwargs):
            events.append("stock")
            return stock(*args, **kwargs)

        with patch("dungeon_map._generate_level", side_effect=layout), patch(
            "dungeon_puzzles.generate_encounters", side_effect=contents,
        ):
            self.adventure(GenerationOptions(seed=42, width=30, height=24, levels=3),
                           puzzle_probability=1)
        self.assertEqual(events, ["layout", "stock"] * 3)

    def test_passage_puzzles_replace_all_down_exits_and_preserve_alignment(self):
        options = GenerationOptions(seed=42, width=30, height=24, levels=3,
                                    stairs_up=1, stairs_down=2, ramps_down=1,
                                    ramp_probability=100)
        with self.catalog_only(3, 8, 13, 15, 26, 30):
            dungeon, keys = self.adventure(options, puzzle_probability=1)
        for depth, (level, key) in enumerate(zip(dungeon.levels, keys), 1):
            validate_map(level.grid)
            self.assertTrue(is_connected(level.grid))
            entrance = next(p.entrance for p in level.stairways if p.tile in "ERS")
            down = [p for p in level.stairways if p.tile in "ers"]
            self.assertEqual(len(down), 2)
            for puzzle in key.puzzles:
                self.assertIsNone(puzzle.gate)
                self.assertIsNone(puzzle.reward_cell)
                self.assertEqual(puzzle.next_level, depth + 1)
                room = next(set(cells) for cells in level.room_cells if puzzle.cell in cells)
                stairs = [p for p in down if p.clearance <= room]
                self.assertEqual(len(stairs), 1)
                self.assertTrue(stairs[0].spiral)
                self.assertEqual(stairs[0].size, 2)
                self.assertGreaterEqual(len({x for x, y in room}), 5)
                self.assertGreaterEqual(len({y for x, y in room}), 5)
                self.assertIn(puzzle.cell, flood(level.grid, entrance))
            if depth < 3:
                upstairs = [p for p in dungeon.levels[depth].stairways if p.tile in "ERS"]
                self.assertEqual([p.cells for p in down], [p.cells for p in upstairs])
                self.assertEqual([p.horizontal for p in down], [p.horizontal for p in upstairs])
                for passage in down + upstairs:
                    self.assertEqual(passage.size, 2)
                    self.assertEqual(len(passage.clearance), 4)
                self.assertEqual(len(keys[depth].stair_notes), 2)
                for puzzle in key.puzzles:
                    note = next(note for note in keys[depth].stair_notes
                                if "P{:02d}:".format(puzzle.definition.number) in note)
                    area = next(area for area in key.areas if area.cell == puzzle.cell)
                    self.assertIn("ascends counterclockwise to Level {}, Area {}".format(
                        depth, area.number,
                    ), note)
                    self.assertNotIn("IN THIS ROOM", note)
                    self.assertNotIn("descends", note)
                    room = next(set(cells) for cells in level.room_cells if puzzle.cell in cells)
                    stairs = next(p for p in down if p.clearance <= room)
                    self.assertIn("column {}, row {}".format(
                        min(x for x, y in stairs.cells) + 1,
                        min(y for x, y in stairs.cells) + 1,
                    ), note)
        self.assertIn("Removed 3 old down", " ".join(dungeon.layout_notes))

    def test_single_level_protects_best_hoard_with_no_stair_bypass(self):
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

    def test_one_exit_leaves_extra_gates_as_separate_guarded_reward_branches(self):
        options = GenerationOptions(seed=42, width=30, height=24, levels=2, stairs_down=1)
        with self.catalog_only(3, 6, 12):
            dungeon, keys = self.adventure(options, puzzle_probability=1, max_puzzles_per_level=3)
            self.assertEqual((dungeon, keys), self.adventure(
                options, puzzle_probability=1, max_puzzles_per_level=3))
        puzzles = keys[0].puzzles
        self.assertEqual([p.next_level for p in puzzles], [2, None, None])
        entrance = next(area.cell for area in keys[0].areas if area.cell in dungeon.room_cells[0])
        gated = [p for p in puzzles if p.gate]
        for chosen in gated:
            reachable = flood(dungeon.grid, entrance, {p.gate for p in gated if p != chosen})
            self.assertTrue(all(p.cell in reachable for p in puzzles))
            self.assertIn(chosen.reward_cell, reachable)
            self.assertTrue(all(p.reward_cell not in reachable for p in gated if p != chosen))
            reward = next(a for a in keys[0].areas if a.cell == chosen.reward_cell)
            self.assertIsNotNone(reward.monster)
            self.assertGreaterEqual(treasure_value(reward), (0, 0, Decimal(1000)))
        self.assertEqual(len(keys[1].stair_notes), 1)
        note = keys[1].stair_notes[0]
        self.assertIn("2x2 spiral staircase", note)
        self.assertIn("lower landing", note)
        self.assertNotIn("IN THIS ROOM", note)
        puzzle = next(p for p in puzzles if p.next_level)
        area = next(a for a in keys[0].areas if a.cell == puzzle.cell)
        self.assertIn("ascends counterclockwise to Level 1, Area {}".format(area.number), note)
        self.assertTrue(any("IN THIS ROOM" in entry and "descends clockwise to Level 2" in entry
                            for entry in area.notes))
        self.assertIn(note, encounter_document(dungeon, keys, 11).split("## Level 2\n", 1)[1])

    def test_separate_branches_fit_minimum_height_without_a_corridor_bypass(self):
        options = GenerationOptions(seed=42, width=30, height=7, room_size=4)
        with self.catalog_only(2, 6, 11):
            dungeon, keys = self.adventure(options, puzzle_probability=1, max_puzzles_per_level=3)
        self.assertGreaterEqual(dungeon.grid.height, 7)
        for puzzle in keys[0].puzzles:
            reachable = flood(dungeon.grid, keys[0].puzzles[0].cell, {puzzle.gate})
            self.assertFalse(set(puzzle.protected_cells) & reachable)
            self.assertTrue(all(p.cell in reachable for p in keys[0].puzzles))

    def test_branch_hoards_are_ranked_and_not_duplicated(self):
        awarded = []

        def loot(*args):
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
        with self.catalog_only(2, 3, 6):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=2, stairs_down=2),
                puzzle_probability=1, max_puzzles_per_level=3)
        first, second = [p for p in keys[0].puzzles if p.gate]
        nested = replace(first, protected_cells=first.protected_cells + second.protected_cells)
        invalid = (replace(keys[0], puzzles=tuple(
            nested if p == first else p for p in keys[0].puzzles)), keys[1])
        with self.assertRaisesRegex(ValueError, "overlap or be nested"):
            validate_puzzle_dungeon(dungeon, invalid)
        with self.assertRaisesRegex(ValueError, "stair seal"):
            validate_puzzle_dungeon(dungeon, (keys[0], replace(keys[1], stair_notes=())))

    def test_magic_priority_over_consumables_and_monetary_values(self):
        def area(*loot):
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
        with self.catalog_only(2), patch("dungeon_encounters.treasure", return_value=("None.",)):
            dungeon, keys = self.adventure(puzzle_probability=1, max_puzzles_per_level=1)
        puzzle = keys[0].puzzles[0]
        inside = [area for area in keys[0].areas if area.cell in puzzle.protected_cells]
        self.assertEqual(max(inside, key=treasure_value).treasure, ("Coins: 100 sp.",))
        validate_puzzle_dungeon(dungeon, keys)

    def test_final_section_receives_best_hoard_from_an_earlier_level_without_duplication(self):
        best_loot = ("Magic Staff: Healing; 12 charges (maximum 24) (power +4)",)
        awarded = []

        def loot(rules, rng, depth, encounter, debug):
            if depth == 1 and not awarded:
                awarded.append(True)
                return best_loot
            return ("Coins: 10 sp.",)

        with self.catalog_only(3, 12), patch("dungeon_encounters.treasure", side_effect=loot):
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
                    entry = next(area.cell for area in source_key.areas
                                 if area.cell in source_level.room_cells[0])
                    blocked = {p.gate for p in source_key.puzzles if p.gate}
                    self.assertIn(source.cell, flood(source_level.grid, entry, blocked))
                    self.assertIn("Level {}, Area {}".format(item.source_level, source.number),
                                  "\n".join(target.notes))
                    self.assertIn("Level {}, Area {}".format(depth, target.number),
                                  "\n".join(source.puzzle_items))
                    self.assertIn("**Puzzle item:** " + item.name, "\n".join(source.puzzle_items))
                    self.assertIn("P{:02d}:".format(puzzle.definition.number),
                                  "\n".join(source.puzzle_items))
        self.assertTrue(earlier)
        self.assertTrue(current)

    def test_required_item_prefers_an_earlier_solved_only_puzzle_reward(self):
        definitions = {p.number: p for p in self.catalog}
        with patch.object(dungeon_puzzles._AdventureBuilder, "select_puzzles", side_effect=[
            (1, [definitions[2]]), (1, [definitions[5]]),
        ]):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=2),
                puzzle_probability=1,
            )
        earlier, later = keys[0].puzzles[0], keys[1].puzzles[0]
        item = later.items[0]
        self.assertEqual((item.source_level, item.source_cell), (1, earlier.cell))
        self.assertNotEqual(item.source_cell, earlier.reward_cell)
        source = next(area for area in keys[0].areas if area.cell == item.source_cell)
        target = next(area for area in keys[1].areas if area.cell == later.cell)
        guide = encounter_document(dungeon, keys, 11)
        level_text = guide.split("\n## Level 1\n", 1)[1].split("\n## Level 2\n", 1)[0]
        source_text = level_text.split("\n### {}\n".format(source.number), 1)[1].split("\n### ", 1)[0]
        before_prize, prize = source_text.split("**Puzzle reward (released only when solved):**")
        self.assertNotIn("**Puzzle item:** bronze striker", before_prize)
        self.assertIn("**Puzzle item:** bronze striker", prize)
        self.assertIn("Required for the later puzzle P05:", prize)
        self.assertIn("Level 2, Area {}".format(target.number), prize)
        self.assertIn("Level 1, Area {}".format(source.number), "\n".join(target.notes))

    def test_required_items_fall_back_to_loot_when_earlier_prize_can_be_sealed(self):
        definitions = {p.number: p for p in self.catalog}
        with patch.object(dungeon_puzzles._AdventureBuilder, "select_puzzles", side_effect=[
            (1, [definitions[9]]), (1, [definitions[5]]),
        ]):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=2),
                puzzle_probability=1,
            )
        guide = encounter_document(dungeon, keys, 11)
        for depth, key in enumerate(keys, 1):
            for puzzle in key.puzzles:
                for item in puzzle.items:
                    source_key = keys[item.source_level - 1]
                    self.assertNotIn(item.source_cell, {p.cell for p in source_key.puzzles})
                    source = next(a for a in source_key.areas if a.cell == item.source_cell)
                    level_text = guide.split("\n## Level {}\n".format(item.source_level), 1)[1]
                    level_text = level_text.split("\n## Level ", 1)[0]
                    source_text = level_text.split(
                        "\n### {}\n".format(source.number), 1,
                    )[1].split("\n### ", 1)[0]
                    self.assertIn("**Treasure:**", source_text)
                    self.assertIn("**Puzzle item:** " + item.name, source_text)
                    target = next(a for a in key.areas if a.cell == puzzle.cell)
                    self.assertIn("Level {}, Area {}".format(depth, target.number), source_text)

    def test_puzzle_prize_categories_counts_and_depth_values(self):
        for choice, category, count in (
            (0, "Jewelry", 3), (0.399999, "Jewelry", 3),
            (0.4, "Gem", 6), (0.799999, "Gem", 6),
        ):
            for depth, value in ((1, "12 cp"), (7, "12 gp"), (12, "48 gp")):
                with self.subTest(choice=choice, depth=depth):
                    rng = random.Random(42)
                    with patch.object(rng, "random", return_value=choice), patch.object(
                        rng, "randint", side_effect=lambda low, high: high,
                    ):
                        reward = puzzle_treasure(self.rules, rng, depth)
                    self.assertEqual(len(reward), count)
                    self.assertTrue(all(line.startswith(category + ": ") for line in reward))
                    self.assertTrue(all(line.endswith("worth " + value + ".") for line in reward))
        for choice in (0.8, 0.999999):
            rng = random.Random(42)
            with patch.object(rng, "random", return_value=choice), patch(
                "dungeon_encounters.magic_item", return_value="Magic Ring: Protection (power +2)",
            ) as magic:
                self.assertEqual(puzzle_treasure(self.rules, rng, 7),
                                 ("Magic Ring: Protection (power +2)",))
                magic.assert_called_once_with(self.rules, rng, 7, None)

    def test_interior_room_cannot_be_used_for_a_same_level_reward_branch(self):
        inner = tuple((x, y) for y in range(8, 13) for x in range(8, 13))
        edge = tuple((x, y) for y in range(16, 21) for x in range(22, 27))
        rooms = set(inner + edge)
        grid = parse_ascii("\n".join(
            "".join(" " if (x, y) in rooms else "#" for x in range(32))
            for y in range(24)
        ))
        self.assertIsNone(dungeon_puzzles._edge_reward_branch(
            grid, inner, rooms, set(), random.Random(42),
        ))
        branch = dungeon_puzzles._edge_reward_branch(grid, edge, rooms, set(), random.Random(42))
        self.assertIsNotNone(branch)
        gate, reward, room, corridor = branch
        self.assertEqual(len(corridor), 6)
        self.assertEqual(gate, corridor[0])
        self.assertNotIn(reward, corridor)

    def test_small_map_stair_puzzle_enlarges_chamber_for_two_square_spiral(self):
        with self.catalog_only(3):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=7, room_size=4),
                puzzle_probability=1,
            )
        puzzle = keys[0].puzzles[0]
        room = next(set(cells) for cells in dungeon.room_cells if puzzle.cell in cells)
        stair = next(p for p in dungeon.stairways if p.tile == "s")
        self.assertEqual(stair.size, 2)
        self.assertEqual(len(stair.clearance), 4)
        self.assertTrue(stair.clearance <= room)
        self.assertGreaterEqual(len({x for x, y in room}), 5)
        self.assertGreaterEqual(len({y for x, y in room}), 5)
        validate_puzzle_dungeon(dungeon, keys)

    def test_malformed_catalog_fails_instead_of_silently_losing_puzzles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.md"
            path.write_text("### 1. Missing everything\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "1 through {}".format(PUZZLE_COUNT)):
                load_puzzles(path)

    def test_consequence_coverage_and_retry_classes(self):
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
            self.assertIn(puzzle.definition.body.split("**Reward:**")[0].rstrip(), guide)
            self.assertEqual(puzzle.gate is not None, puzzle.definition.number == 20)

    def test_consequences_without_shared_rules_are_rejected(self):
        text = dungeon_puzzles.CATALOG_PATH.read_text(encoding="utf-8")
        text = re.sub(r"(?ms)^## Consequence Rules\n.*?(?=^## )", "", text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.md"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "shared consequence rules"):
                load_puzzles(path)

    def test_escape_clues_have_search_dcs_fair_decoys_and_correct_codes(self):
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
                number = puzzle.number
                if number == 41:
                    lookup = dict(re.findall(r"([A-Z]+)=(\d)", body))
                    decoded = "".join(lookup[value] for value in real)
                elif number == 42:
                    alphabets = re.search(r"```text\n([A-Z]+)\n([A-Z]+)\n```", body)
                    lookup = dict(zip(alphabets[1], alphabets[2]))
                    decoded = "".join(lookup[letter] for value in real for letter in value)
                elif number == 43:
                    decoded = "".join(real)[::-1]
                elif number == 44:
                    grid = re.search(r"```text\n(.*?)\n```", body, re.S)[1].splitlines()[1:]
                    letters = [row.split()[1:] for row in grid]
                    decoded = "".join(letters[int(value[0]) - 1][int(value[1]) - 1] for value in real)
                elif number == 45:
                    book = re.search(r"```text\n(.*?)\n```", body, re.S)[1].splitlines()
                    decoded = ""
                    for value in real:
                        line, word = map(int, value.split("/"))
                        decoded += book[line - 1].split()[word][0].upper()
                elif number == 46:
                    decoded = "".join(str(int(value, 2)) for value in real)
                elif number == 47:
                    lookup = {signals: letter for letter, signals in re.findall(r"([A-Z])=([.-]+)", body)}
                    decoded = "".join(lookup[value] for value in real)
                elif number == 48:
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
                    decoded = " ".join(lookup[value] for value in solutions[0])
                elif number == 49:
                    windows = re.findall(r"(?:PULSE|BREATH): (\d),(\d)", body)
                    decoded = "".join(word[int(index) - 1]
                                      for word, indices in zip(real, windows) for index in indices)
                elif number == 50:
                    decoded = "".join(value if row % 2 == 0 else value[::-1]
                                      for row, value in enumerate(real))
                else:
                    self.fail("escape puzzle needs a decoding regression case")
                self.assertEqual(decoded, expected)

    def test_all_escape_puzzles_reach_tm_key_and_keep_solutions_off_svg(self):
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
            self.assertIn(puzzle.definition.body.split("**Reward:**")[0].rstrip(), guide)
            self.assertEqual(puzzle.items, ())
        validate_puzzle_dungeon(dungeon, keys)


class PuzzleCommandLineTests(unittest.TestCase):
    def run_cli(self, script, *args):
        return subprocess.run([sys.executable, str(script)] + list(map(str, args)),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

    def test_cli_writes_the_same_puzzle_adventure_as_the_python_api(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            output = folder / "dungeon.svg"
            result = self.run_cli(
                HERE / "generate_dungeon_map.py", "--output", output, "--seed", 42,
                "--levels", 2, "--width", 30, "--height", 24,
                "--puzzle-probability", 1, "--player-view",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            files = {path.name: path.read_text(encoding="utf-8") for path in folder.iterdir()}
            self.assertEqual(len(files), 6)
            dungeon, keys = generate_adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=2),
                puzzle_probability=1,
            )
            self.assertEqual(files["dungeon-encounters.md"], encounter_document(dungeon, keys, 11))
            self.assertEqual(files["dungeon-encounters.log"], encounter_log(dungeon, keys, 11))
            guide = files["dungeon-encounters.md"]
            self.assertEqual(len(re.findall(r"\*\*Puzzle P\d\d:", guide)), 4)
            self.assertIn("Progression gate:", guide)
            self.assertIn("**Solution:**", guide)
            for depth, (level, key) in enumerate(zip(dungeon.levels, keys), 1):
                text = files["dungeon-level-{}.txt".format(depth)]
                self.assertEqual(text, level.grid.to_ascii())
                self.assertTrue(is_connected(parse_ascii(text)))
                svg = files["dungeon-level-{}.svg".format(depth)]
                self.assertEqual(svg, svg_document(
                    level.grid, seed=42, player_view=True,
                    encounter_labels=key.labels, trapped_chests=key.trapped_chests,
                ))
                self.assertIn('id="encounters"', svg)
                self.assertNotIn("Solution", svg)
                self.assertNotIn("Required item", svg)

    def test_default_enables_stocking_and_zero_restores_unstocked_cli(self):
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
