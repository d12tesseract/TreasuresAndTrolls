import unittest
import xml.etree.ElementTree as ET
from collections import Counter

from dungeon_encounters import generate_encounters
from dungeon_geometry import DOORS, DungeonMap, parse_ascii, validate_map
from dungeon_map import GenerationOptions, generate_dungeon
from dungeon_render import svg_document


NS = {"s": "http://www.w3.org/2000/svg"}


class TerrainContractTests(unittest.TestCase):
    def test_lowercase_doors_keep_uppercase_svg_labels_on_both_axes(self):
        self.assertEqual(DOORS, frozenset("dxc"))
        for tile, marker in (("d", None), ("x", "S"), ("c", "C")):
            for horizontal in (False, True):
                rows = ("#####", "## ##", "##{}##".format(tile), "##C##", "#####")
                if horizontal:
                    rows = tuple("".join(row) for row in zip(*rows))
                grid = DungeonMap(rows)
                validate_map(grid)
                self.assertEqual(parse_ascii(grid.to_ascii()), grid)
                root = ET.fromstring(svg_document(grid))
                group = root.find(".//s:g[@data-tile='{}']".format(tile), NS)
                label = group.find("s:text", NS)
                self.assertEqual(label.text if label is not None else None, marker)
                player = ET.fromstring(svg_document(grid, player_view=True))
                self.assertEqual(player.find(".//s:g[@data-tile='{}']".format(tile), NS) is None,
                                 tile != "d")

    def test_b_pairs_draw_one_normal_width_door_and_python_rejects_drafts(self):
        for rows in (("######", "# bb #", "######"),
                     ("###", "# #", "#b#", "#b#", "# #", "###")):
            grid = DungeonMap(rows)
            validate_map(grid)
            root = ET.fromstring(svg_document(grid))
            self.assertEqual(len(root.findall(".//s:g[@data-tile='b']", NS)), 1)
            rectangle = root.find(".//s:g[@data-tile='b']/s:g/s:rect", NS)
            self.assertEqual(float(rectangle.attrib["width"]), 0.7)
        for text in ("# b #", "# bbb #", "# dd #"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                svg_document(parse_ascii(text))
        for tile in "DX":
            with self.assertRaises(ValueError):
                parse_ascii(tile)

    def test_C_is_walkable_chest_not_concealed_door(self):
        grid = DungeonMap(("#####", "# C #", "#####"))
        validate_map(grid)
        root = ET.fromstring(svg_document(grid, encounter_labels={(2, 1): "1"}))
        chest = root.find(".//s:g[@data-tile='C']", NS)
        self.assertIsNotNone(chest.find("s:rect", NS))
        self.assertIsNone(chest.find("s:text", NS))
        player = ET.fromstring(svg_document(grid, player_view=True))
        self.assertIsNone(player.find(".//s:g[@data-tile='C']", NS))

    def test_generation_and_encounter_classification_use_corrected_keys(self):
        for rough in (0, 0.5, 1):
            dungeon = generate_dungeon(GenerationOptions(
                seed=42, doors=3, secret_doors=2, concealed_doors=2,
                rough_probability=rough,
            ))
            counts = Counter(dungeon.grid.to_ascii())
            self.assertEqual({tile: counts[tile] for tile in "dxc"}, {"d": 3, "x": 2, "c": 2})
            self.assertFalse(set("DX") & set(counts))
            validate_map(dungeon.grid)
            key = generate_encounters(dungeon)[0]
            self.assertEqual(Counter(item[1] for item in key.doors),
                             {"Secret": 2, "Concealed": 2})


if __name__ == "__main__":
    unittest.main()
