import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from dungeon_encounters import (
    EncounterArea, EncounterLevel, encounter_document, encounter_log, place_encounter_features,
)
from dungeon_geometry import (
    DIRECTIONS, DOORS, DungeonMap, Stairway, _room_entrances, parse_ascii,
    reachable_cells, validate_map,
)
from dungeon_map import GeneratedDungeon, GenerationOptions, generate_dungeon
from dungeon_puzzles import generate_adventure, validate_puzzle_dungeon
from dungeon_render import svg_document


NS = {"s": "http://www.w3.org/2000/svg"}
HERE = Path(__file__).resolve().parent


def chamber(door="d"):
    rows = (
        "###########", "###########", "###     ###", "###     ###",
        "# {}     ###".format(door), "###     ###", "###     ###",
        "###########", "###########",
    )
    cells = tuple((x, y) for y in range(2, 7) for x in range(3, 8))
    level = GeneratedDungeon(DungeonMap(rows), 42, (len(cells),), (), room_cells=(cells,))
    area = EncounterArea(
        1, (5, 4), 0, None, None, ("Coins: 10 sp.",), "Pressure plate.",
        container="chest", chest_trap="Poison needle.", chest_locked=False,
    )
    return level, (EncounterLevel((area,), (), ()),)


class TerrainFeatureTests(unittest.TestCase):
    def test_lowercase_doors_and_uppercase_chests_have_distinct_symbols(self):
        for tile, marker in (("d", None), ("x", "S"), ("c", "C")):
            for horizontal in (False, True):
                rows = ("#####", "## ##", "##{}##".format(tile), "##T##", "#####")
                if horizontal:
                    rows = tuple("".join(row) for row in zip(*rows))
                grid = DungeonMap(rows)
                validate_map(grid)
                self.assertEqual(parse_ascii(grid.to_ascii()), grid)
                root = ET.fromstring(svg_document(grid))
                group = root.find(".//s:g[@data-tile='{}']".format(tile), NS)
                text = group.find("s:text", NS)
                if marker is None:
                    self.assertIsNone(text)
                else:
                    self.assertEqual(text.text, marker)
                    self.assertEqual(float(text.attrib["font-size"]), 1.12)
        chest = DungeonMap(("###", "#C#", "###"))
        validate_map(chest)
        root = ET.fromstring(svg_document(chest))
        self.assertIsNotNone(root.find(".//s:g[@data-tile='C']/s:rect", NS))

    def test_boundary_centered_doors_use_b_pairs_and_one_normal_width_symbol(self):
        for rows in (("######", "# bb #", "######"), ("###", "# #", "#b#", "#b#", "# #", "###")):
            grid = DungeonMap(rows)
            validate_map(grid)
            root = ET.fromstring(svg_document(grid))
            self.assertEqual(len(root.findall(".//s:g[@data-tile='b']", NS)), 1)
            rectangle = root.find(".//s:g[@data-tile='b']/s:g/s:rect", NS)
            self.assertEqual(float(rectangle.attrib["width"]), 0.7)
            self.assertEqual(float(rectangle.attrib["y"]), -0.12)
            self.assertEqual(float(rectangle.attrib["height"]), 0.24)
        with self.assertRaisesRegex(ValueError, "isolated|exactly one"):
            validate_map(DungeonMap(("#######", "# bbb #", "#######")))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_map(DungeonMap(("#####", "# b #", "#####")))
        with self.assertRaisesRegex(ValueError, "door"):
            validate_map(DungeonMap(("######", "# dd #", "######")))

    def test_stocked_traps_guard_entrances_and_chests_stay_clear(self):
        for door in ("d", "x", "c", " "):
            with self.subTest(door=door):
                original, contents = chamber(door)
                marked, keys = place_encounter_features(original, contents)
                self.assertEqual((marked, keys), place_encounter_features(original, contents))
                area = keys[0].areas[0]
                room = set(marked.room_cells[0])
                entrances = _room_entrances(original.grid, room)
                self.assertEqual(area.trap_cell, (3, 4))
                self.assertIn(area.trap_cell, entrances)
                self.assertNotIn(area.chest_cell, entrances)
                self.assertNotEqual(area.trap_cell, area.chest_cell)
                self.assertEqual(marked.grid.tile(*area.trap_cell), "T")
                self.assertEqual(marked.grid.tile(*area.chest_cell), "C")
                self.assertEqual(original.grid.tile(*area.trap_cell), " ")
                x, y = area.chest_cell
                self.assertFalse(any(marked.grid.tile(x + dx, y + dy) in DOORS
                                     for dx, dy in DIRECTIONS))
                self.assertTrue(room - {area.chest_cell} <= reachable_cells(
                    marked.grid, (3, 4), {area.chest_cell},
                ))
                for document in (encounter_document(marked, keys, 11),
                                 encounter_log(marked, keys, 11)):
                    self.assertIn("column {}, row {}".format(x + 1, y + 1), document.lower())
                root = ET.fromstring(svg_document(
                    marked.grid, encounter_labels=keys[0].labels,
                    trapped_chests=keys[0].trapped_chests,
                ))
                self.assertIsNotNone(root.find(".//s:g[@data-tile='T']", NS))
                chest = root.find(".//s:g[@data-tile='C']", NS)
                self.assertEqual(chest.attrib["data-trapped"], "true")
                self.assertEqual(chest.find("s:text", NS).text, "T")
                player = ET.fromstring(svg_document(
                    marked.grid, player_view=True, trapped_chests=keys[0].trapped_chests,
                ))
                for hidden in "TCxc":
                    self.assertIsNone(player.find(".//s:g[@data-tile='{}']".format(hidden), NS))

    def test_explicit_traps_keep_their_location_without_duplicate_traps(self):
        level, keys = chamber()
        rows = [list(row) for row in level.grid.rows]
        rows[3][4] = "T"
        level = replace(level, grid=DungeonMap(tuple("".join(row) for row in rows)))
        area = replace(keys[0].areas[0], trap="See the explicit T trap key below.")
        keys = (replace(keys[0], areas=(area,), traps=(((4, 3), "Pressure plate."),)),)
        marked, keys = place_encounter_features(level, keys)
        self.assertEqual(keys[0].areas[0].trap_cell, (4, 3))
        self.assertEqual(marked.grid.to_ascii().count("T"), 1)

    def test_chest_without_a_safe_position_reports_the_placement_error(self):
        level, keys = chamber()
        level = replace(level, room_cells=(((3, 4),),), room_areas=(1,))
        area = replace(keys[0].areas[0], cell=(3, 4), trap="None.")
        with self.assertRaisesRegex(ValueError, "no unobstructed chest location in Level 1, Area 1"):
            place_encounter_features(level, (replace(keys[0], areas=(area,)),))

    def test_chests_preserve_spiral_landings_and_the_clear_floor_ring(self):
        level, keys = chamber()
        stairs = Stairway.spiral_at(4, 3, size=2, tile="s")
        rows = [list(row) for row in level.grid.rows]
        stairs.paint(rows)
        level = replace(
            level, grid=DungeonMap(tuple("".join(row) for row in rows)), stairways=(stairs,),
        )
        area = replace(keys[0].areas[0], cell=(5, 6), trap="None.")
        marked, keys = place_encounter_features(level, (replace(keys[0], areas=(area,)),))
        protected = {(x + dx, y + dy) for x, y in stairs.clearance
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        self.assertNotIn(keys[0].areas[0].chest_cell, protected)
        self.assertTrue(all(marked.grid.tile(*cell) == level.grid.tile(*cell)
                            for cell in protected))

    def test_explicit_generated_traps_prefer_chamber_entrances(self):
        level = generate_dungeon(GenerationOptions(
            width=30, height=24, seed=42, traps=1, doors=0,
            secret_doors=0, concealed_doors=0,
        ))
        entrances = set().union(*(_room_entrances(level.grid, set(room))
                                 for room in level.room_cells))
        trap = next((x, y) for y, row in enumerate(level.grid.rows)
                    for x, tile in enumerate(row) if tile == "T")
        self.assertIn(trap, entrances)

    def test_puzzle_adjusted_encounters_use_final_room_locations(self):
        options = GenerationOptions(seed=42, width=30, height=24, levels=2)
        dungeon, keys = generate_adventure(
            options, puzzle_probability=1, treasure_chest_dc=0, chest_trap_dc=0,
        )
        validate_puzzle_dungeon(dungeon, keys)
        chest_count = 0
        for level, key in zip(dungeon.levels, keys):
            for area in key.areas:
                room = next(set(cells) for cells in level.room_cells if area.cell in cells)
                if area.trap_cell is not None:
                    self.assertIn(area.trap_cell, room)
                    self.assertEqual(level.grid.tile(*area.trap_cell), "T")
                if area.container == "chest":
                    chest_count += 1
                    self.assertIn(area.chest_cell, room)
                    self.assertEqual(level.grid.tile(*area.chest_cell), "C")
                    self.assertNotIn(area.chest_cell, _room_entrances(level.grid, room))
        self.assertGreater(chest_count, 0)

    def test_cli_writes_markers_to_ascii_and_tm_svg_but_not_player_svg(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs = []
            for player in (False, True):
                output = Path(directory) / ("player.svg" if player else "tm.svg")
                command = [
                    sys.executable, str(HERE / "generate_dungeon_map.py"),
                    "--output", str(output), "--seed", "42", "--width", "30", "--height", "24",
                    "--puzzle-probability", "0", "--generate-encounters",
                    "--treasure-chest-dc", "0", "--chest-trap-dc", "0",
                ]
                if player:
                    command.append("--player-view")
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                text = output.with_suffix(".txt").read_text()
                self.assertIn("C", text)
                self.assertIn("T", text)
                self.assertNotIn("D", text)
                self.assertNotIn("X", text)
                validate_map(parse_ascii(text))
                root = ET.parse(str(output)).getroot()
                self.assertEqual(bool(root.findall(".//s:g[@data-tile='C']", NS)), not player)
                self.assertEqual(bool(root.findall(".//s:g[@data-tile='T']", NS)), not player)
                if not player:
                    self.assertTrue(root.findall(".//s:g[@data-trapped='true']", NS))
                outputs.append(text)
            self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
