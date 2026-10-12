import random
import re
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
            self.assertIn(puzzle.definition.body, markdown)
            self.assertEqual(len(puzzle.items), len(puzzle.definition.required_items))
            for item in puzzle.items:
                self.assertIn("**Puzzle item:** " + item.name, markdown)
        self.assertEqual(markdown.count("**Solution:**"), PUZZLE_COUNT)
        self.assertIn("Progression gate:", log)

    def test_pool_exhaustion_does_not_repeat_puzzles(self):
        with self.catalog_only(3, 5, 12):
            dungeon, keys = self.adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=3),
                puzzle_probability=1,
            )
        self.assertEqual([len(key.puzzles) for key in keys], [2, 1, 0])
        self.assertEqual(len({p.definition.number for key in keys for p in key.puzzles}), 3)
        self.assertIn("no further puzzles", " ".join(dungeon.levels[-1].layout_notes))

    def test_drain_and_reward_keys_gate_progression_and_local_rewards_stay_inside(self):
        with self.catalog_only(8, 14, 20, 21):
            dungeon, keys = self.adventure(puzzle_probability=1, max_puzzles_per_level=4)
        puzzles = {p.definition.number: p for p in keys[0].puzzles}
        for number in (8, 20, 21):
            self.assertIsNotNone(puzzles[number].gate)
            self.assertIn(puzzles[14].cell, puzzles[number].protected_cells)
        guide = encounter_document(dungeon, keys, 11)
        self.assertEqual(guide.count("**Key binding:**"), 2)

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
                                    stairs_down=2, ramps_down=1, ramp_probability=100)
        with self.catalog_only(2, 3, 6, 9, 11, 12):
            dungeon, keys = self.adventure(options, puzzle_probability=1)
        for depth, (level, key) in enumerate(zip(dungeon.levels, keys), 1):
            validate_map(level.grid)
            self.assertTrue(is_connected(level.grid))
            entrance = next(p.entrance for p in level.stairways if p.tile in "UI")
            down = [p for p in level.stairways if p.tile in "ER"]
            self.assertEqual(len(down), int(depth < 3))
            for puzzle in key.puzzles:
                reachable = flood(level.grid, entrance, {puzzle.gate})
                self.assertFalse(set(puzzle.protected_cells) & reachable)
                self.assertIn(puzzle.cell, flood(level.grid, entrance))
                for stairs in down:
                    self.assertEqual(stairs.tile, "E")
                    self.assertFalse(set(stairs.cells) & reachable)
                self.assertTrue(any(area.cell not in reachable for area in key.areas))
                for stairs in level.stairways:
                    if stairs.tile in "UI":
                        self.assertTrue(set(stairs.cells) <= reachable)
            if depth < 3:
                upstairs = [p for p in dungeon.levels[depth].stairways if p.tile in "UI"]
                self.assertEqual([p.cells for p in down], [p.cells for p in upstairs])
                self.assertEqual([p.horizontal for p in down], [p.horizontal for p in upstairs])
                for passage in down + upstairs:
                    self.assertEqual(len(passage.cells), options.stair_length)
        self.assertIn("Removed 3 old down", " ".join(dungeon.layout_notes))

    def test_single_level_protects_best_hoard_with_no_stair_bypass(self):
        options = GenerationOptions(seed=42, width=30, height=24, stairs_up=1,
                                    stairs_down=1, ramps_down=1)
        original = generate_dungeon(options)
        original_key = generate_encounters(original, rules=self.rules)[0]
        best = max(original_key.areas, key=treasure_value)
        with self.catalog_only(3, 12):
            dungeon, keys = self.adventure(options, puzzle_probability=1)
        self.assertEqual(dungeon.stairways, original.stairways)
        for puzzle in keys[0].puzzles:
            self.assertIsNone(puzzle.next_level)
            inside = [area for area in keys[0].areas if area.cell in puzzle.protected_cells]
            reward = max(inside, key=treasure_value)
            self.assertGreaterEqual(treasure_value(reward), treasure_value(best))
            if treasure_value(best) > (0, 0, Decimal(0)):
                self.assertEqual(reward.treasure, best.treasure)
                self.assertEqual(reward.monster, best.monster)
                self.assertEqual(reward.container, best.container)
                self.assertEqual(reward.chest_trap, best.chest_trap)
                self.assertEqual(reward.chest_locked, best.chest_locked)
            self.assertFalse(any(set(stairs.cells) & set(puzzle.protected_cells)
                                 for stairs in dungeon.stairways))

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
        with self.catalog_only(3), patch("dungeon_encounters.treasure", return_value=("None.",)):
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
                    entry = next(p.entrance for p in source_level.stairways if p.tile in "UI")
                    blocked = {p.gate for p in source_key.puzzles if p.gate}
                    self.assertIn(source.cell, flood(source_level.grid, entry, blocked))
                    self.assertIn("Level {}, Area {}".format(item.source_level, source.number),
                                  "\n".join(target.notes))
                    self.assertIn("Level {}, Area {}".format(depth, target.number),
                                  "\n".join(source.notes))
                    self.assertIn("**Puzzle item:** " + item.name, "\n".join(source.notes))
                    self.assertIn("P{:02d}:".format(puzzle.definition.number), "\n".join(source.notes))
        self.assertTrue(earlier)
        self.assertTrue(current)

    def test_malformed_catalog_fails_instead_of_silently_losing_puzzles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.md"
            path.write_text("### 1. Missing everything\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "1 through {}".format(PUZZLE_COUNT)):
                load_puzzles(path)


class PuzzleCommandLineTests(unittest.TestCase):
    def run_cli(self, script, *args):
        return subprocess.run([sys.executable, str(script)] + list(map(str, args)),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

    def test_both_entry_points_write_the_same_puzzle_adventure(self):
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
