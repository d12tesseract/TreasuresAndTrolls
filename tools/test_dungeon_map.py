import math
import random
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from dungeon_encounters import (
    EncounterRules,
    MonsterEncounter,
    basic_roll,
    encounter_document,
    encounter_log,
    generate_encounters,
    magic_item,
    monster_encounter,
    trap_description,
    treasure,
)

from dungeon_map import (
    DungeonMap,
    GeneratedDungeon,
    GenerationOptions,
    Stairway,
    generate_dungeon,
    is_connected,
    parse_ascii,
    render_rows,
    svg_document,
    validate_map,
    _meander_path,
    _path,
    _place_stairways,
    _Corridor,
    _Room,
    _prune_unreachable,
    _rebuild_layout,
    _reroute_corridors,
)


NS = {"s": "http://www.w3.org/2000/svg"}
HERE = Path(__file__).resolve().parent


def xml(grid, **options):
    return ET.fromstring(svg_document(grid, **options))


def walls(root):
    return root.findall("s:g[@id='walls']/s:line", NS)


def endpoints(line):
    return (
        (float(line.attrib["x1"]), float(line.attrib["y1"])),
        (float(line.attrib["x2"]), float(line.attrib["y2"])),
    )


def door_map(symbol="D", horizontal=False):
    rows = ["#####", "## ##", "##{}##".format(symbol), "##.##", "#####"]
    if horizontal:
        rows = ["".join(row) for row in zip(*rows)]
    return DungeonMap(tuple(rows))


class InputTests(unittest.TestCase):
    def test_spaces_padding_and_newline_roundtrip(self):
        grid = parse_ascii("  # \r\n.\r\n\r\n###\r\n")
        self.assertEqual(grid.rows, ("  # ", ".###", "####", "####"))
        self.assertEqual(parse_ascii(grid.to_ascii()), grid)
        self.assertEqual(parse_ascii(" "), DungeonMap((" ",)))
        self.assertEqual(parse_ascii(" \n\n").rows, (" ", "#"))

    def test_invalid_characters_and_empty_input(self):
        for text in ("", "\n", "\t", "#\r#", "#X#", "\u00e9"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_ascii(text)
        with self.assertRaisesRegex(ValueError, "row 2, column 2"):
            parse_ascii("###\n#?")

    def test_all_diagonal_orientations(self):
        examples = (
            ("\\", (" ", " ", "#", "#")),
            ("\\", ("#", "#", " ", " ")),
            ("/", (" ", "#", "#", " ")),
            ("/", ("#", " ", " ", "#")),
        )
        for symbol, (north, east, south, west) in examples:
            with self.subTest(symbol=symbol, north=north, west=west):
                grid = DungeonMap((
                    "#" + north + "#", west + symbol + east, "#" + south + "#",
                ))
                validate_map(grid)
                self.assertTrue(is_connected(grid))
                expected = (
                    ((1, 1), (2, 2)) if symbol == "\\"
                    else ((1, 2), (2, 1))
                )
                self.assertIn(expected, [endpoints(line) for line in walls(xml(grid))])
                self.assertEqual(len(walls(xml(grid))), 7)

    def test_reject_invalid_diagonals(self):
        for rows in (
            ("#.#", "#\\.", "###"),
            ("# #", "#\\.", "###"),
            ("# #", " \\ ", "# #"),
            ("###", "#\\ ", "###"),
        ):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "diagonal"):
                validate_map(DungeonMap(rows))

    def test_doors_accept_both_axes_and_mixed_terrain(self):
        for symbol in "DSC":
            for horizontal in (False, True):
                with self.subTest(symbol=symbol, horizontal=horizontal):
                    validate_map(door_map(symbol, horizontal))

    def test_reject_door_junctions_rough_sides_and_feature_neighbors(self):
        for rows in (
            ("# #", " D ", "# #"),
            ("# #", ".D#", "# #"),
            ("#T#", "#D#", "# #"),
            ("###", "#D#", "###"),
            ("###", "#S#", "# #"),
            ("# #", "#C#", "###"),
        ):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "door"):
                validate_map(DungeonMap(rows))

    def test_partition_adjacency(self):
        for rows in ((" |",), ("_", " "), (" L", "# ")):
            validate_map(DungeonMap(rows))
        for rows in (("#|",), ("_", "."), (" L", "##"), ("#L", "# ")):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "partition"):
                validate_map(DungeonMap(rows))


class RenderingTests(unittest.TestCase):
    def test_smooth_edges_scale_and_array_api(self):
        root = ET.fromstring(render_rows(["  "]))
        lines = walls(root)
        self.assertEqual(len(lines), 6)
        self.assertEqual(root.attrib["width"], "0.41in")
        self.assertEqual(root.attrib["height"], "0.21in")
        self.assertEqual(root.attrib["viewBox"], "-0.025 -0.025 2.05 1.05")
        self.assertTrue(all(float(line.attrib["stroke-width"]) == 0.05 for line in lines))
        self.assertNotIn(((1, 0), (1, 1)), [endpoints(line) for line in lines])
        scaled = xml(DungeonMap((" ",)), feet_per_pixel=5, feet_per_inch=100, line_width=0.02)
        self.assertEqual(scaled.attrib["width"], "0.07in")
        self.assertEqual(float(walls(scaled)[0].attrib["stroke-width"]), 0.4)

    def test_rough_walls_meander_reproducibly_and_stay_bounded(self):
        grid = DungeonMap(("..", ".."))
        first = svg_document(grid, seed=4)
        self.assertEqual(first, svg_document(grid, seed=4))
        self.assertNotEqual(first, svg_document(grid, seed=5))
        lines = walls(ET.fromstring(first))
        self.assertGreater(len(lines), 8 * 6)
        points = [point for line in lines for point in endpoints(line)]
        self.assertTrue(all(0 <= x <= 2 and 0 <= y <= 2 for x, y in points))
        self.assertTrue(any(0 < x < 0.12 or 0 < y < 0.12 for x, y in points))
        self.assertTrue(all(count == 2 for count in Counter(points).values()))
        self.assertEqual(len(walls(xml(grid, roughness=0))), 8)

    def test_rough_convex_and_concave_corners_are_rounded_not_chamfered(self):
        grid = DungeonMap(("#####", "#..##", "#.###", "#####"))
        lines = walls(xml(grid, roughness=0, corner_radius=0.35))
        neighbors = {}
        for line in lines:
            first, last = endpoints(line)
            neighbors.setdefault(first, []).append(last)
            neighbors.setdefault(last, []).append(first)
        self.assertTrue(all(len(adjacent) == 2 for adjacent in neighbors.values()))
        for corner in ((1, 1), (3, 1), (3, 2), (2, 2), (2, 3), (1, 3)):
            self.assertNotIn(corner, neighbors)
        for cx, cy in ((1, 1), (2, 2)):
            arc_points = [
                point for point in neighbors
                if cx < point[0] < cx + 0.35 and cy < point[1] < cy + 0.35
            ]
            self.assertGreaterEqual(len(arc_points), 4)
            for point in arc_points:
                first, last = neighbors[point]
                incoming = (point[0] - first[0], point[1] - first[1])
                outgoing = (last[0] - point[0], last[1] - point[1])
                cosine = sum(a * b for a, b in zip(incoming, outgoing)) / (
                    math.hypot(*incoming) * math.hypot(*outgoing)
                )
                self.assertLess(math.degrees(math.acos(max(-1, min(1, cosine)))), 30)
        straight = [point for line in walls(xml(grid, roughness=0)) for point in endpoints(line)]
        self.assertIn((1, 1), straight)
        self.assertIn((2, 2), straight)

    def test_rounding_preserves_stone_islands_and_corner_contacts(self):
        for grid in (
            DungeonMap((".....", ".....", "..#..", ".....", ".....")),
            DungeonMap((".#", "#.")),
        ):
            lines = walls(xml(grid, roughness=0.2))
            counts = Counter(point for line in lines for point in endpoints(line))
            self.assertTrue(all(count in (2, 4) for count in counts.values()))
            self.assertNotIn((2.5, 2.5), counts)
            self.assertTrue(all(
                0 <= x <= grid.width and 0 <= y <= grid.height for x, y in counts
            ))
        contacts = Counter(
            point for line in walls(xml(DungeonMap((".#", "#.")))) for point in endpoints(line)
        )
        self.assertEqual(contacts[(1, 1)], 4)

    def test_maximum_radius_makes_an_isolated_square_circular(self):
        for roughness in (0, 0.12, 0.2):
            for segments in (2, 6, 16):
                with self.subTest(roughness=roughness, segments=segments):
                    root = xml(DungeonMap((".",)), corner_radius=0.5,
                               roughness=roughness, rough_segments=segments)
                    lines = walls(root)
                    points = Counter(point for line in lines for point in endpoints(line))
                    self.assertTrue(all(count == 2 for count in points.values()))
                    self.assertTrue({(0, 0.5), (1, 0.5), (0.5, 0), (0.5, 1)} <= set(points))
                    self.assertEqual(root.attrib["width"], "0.21in")
                    distances = [math.hypot(x - 0.5, y - 0.5) for x, y in points]
                    self.assertTrue(all(0 <= x <= 1 and 0 <= y <= 1 for x, y in points))
                    if roughness:
                        self.assertTrue(any(abs(distance - 0.5) > 0.01 for distance in distances))
                        self.assertTrue(all(0.325 - 1e-10 <= distance <= 0.71 for distance in distances))
                        self.assertNotEqual(
                            svg_document(DungeonMap((".",)), corner_radius=0.5, seed=1),
                            svg_document(DungeonMap((".",)), corner_radius=0.5, seed=2),
                        )
                    else:
                        for distance in distances:
                            self.assertAlmostEqual(distance, 0.5, places=10)
                    for line in lines:
                        first, last = endpoints(line)
                        self.assertNotEqual(first, last)
                        midpoint = ((first[0] + last[0]) / 2, (first[1] + last[1]) / 2)
                        if not roughness:
                            self.assertGreater(math.hypot(midpoint[0] - 0.5, midpoint[1] - 0.5), 0.495)

    def test_maximum_radius_preserves_openings_and_rounds_stone_islands(self):
        root = xml(DungeonMap(("..",)), corner_radius=0.5, roughness=0)
        lines = walls(root)
        points = Counter(point for line in lines for point in endpoints(line))
        self.assertTrue(all(count == 2 for count in points.values()))
        for line in lines:
            first, last = endpoints(line)
            self.assertNotEqual(first, last)
            self.assertFalse(first[0] == last[0] == 1 and first[1] != last[1])
            for x, y in (first, last):
                if x < 0.5 or x > 1.5:
                    cx = 0.5 if x < 0.5 else 1.5
                    self.assertAlmostEqual(math.hypot(x - cx, y - 0.5), 0.5, places=10)
                else:
                    self.assertIn(y, (0, 1))
        island = xml(DungeonMap((".....", ".....", "..#..", ".....", ".....")),
                     corner_radius=0.5, roughness=0)
        inner = [
            point for line in walls(island) for point in endpoints(line)
            if 2 <= point[0] <= 3 and 2 <= point[1] <= 3
        ]
        self.assertTrue(inner)
        for x, y in inner:
            self.assertAlmostEqual(math.hypot(x - 2.5, y - 2.5), 0.5, places=10)

    def test_radius_controls_rounding_independently_of_jitter(self):
        grid = DungeonMap((".",))
        automatic = [point for line in walls(xml(grid, roughness=0)) for point in endpoints(line)]
        unrounded = [
            point for line in walls(xml(grid, roughness=0.12, corner_radius=0))
            for point in endpoints(line)
        ]
        rounded = [
            point for line in walls(xml(grid, roughness=0, corner_radius=0.25))
            for point in endpoints(line)
        ]
        self.assertIn((0, 0), automatic)
        self.assertIn((0, 0), unrounded)
        self.assertNotIn((0, 0), rounded)
        self.assertIn((0.25, 0), rounded)
        self.assertIn((0, 0.25), rounded)
        self.assertEqual(svg_document(grid), svg_document(grid, corner_radius=0.35))
        smooth = DungeonMap(("# #", "#\\ ", "###"))
        self.assertEqual(svg_document(smooth), svg_document(smooth, corner_radius=0.5))
        near_maximum = walls(xml(grid, roughness=0.2, corner_radius=0.499, seed=4))
        for line in near_maximum:
            self.assertNotEqual(*endpoints(line))
            for x, y in endpoints(line):
                if 0.499 <= x <= 0.501 or 0.499 <= y <= 0.501:
                    self.assertLess(abs(math.hypot(x - 0.5, y - 0.5) - 0.5), 0.005)

    def test_rough_internal_wall_offsets_both_sides_of_grid_line(self):
        grid = DungeonMap(("#####", "#...#", "#...#", "#####"))
        points = [
            point for line in walls(xml(grid, seed=8)) for point in endpoints(line)
            if 1 < point[0] < 4 and 0.8 <= point[1] <= 1.2
        ]
        self.assertTrue(any(y < 1 for x, y in points))
        self.assertTrue(any(y > 1 for x, y in points))

    def test_rough_smooth_joins_are_connected_and_perpendicular(self):
        for rows in (("#####", "# .##", "#####"),
                     ("#####", "#  ##", "##.##", "#####")):
            with self.subTest(rows=rows):
                lines = walls(xml(DungeonMap(rows), corner_radius=0.5))
                counts = Counter(point for line in lines for point in endpoints(line))
                self.assertTrue(all(count == 2 for count in counts.values()), counts)
                joins = [line for line in lines if line.attrib["data-texture"] == "transition"]
                self.assertEqual(len(joins), 2)
                for join in joins:
                    a, b = endpoints(join)
                    self.assertAlmostEqual(math.hypot(b[0] - a[0], b[1] - a[1]), 0.12)
                    smooth = next(
                        line for line in lines
                        if line.attrib["data-texture"] == "smooth" and a in endpoints(line)
                    )
                    c, d = endpoints(smooth)
                    dot = (b[0] - a[0]) * (d[0] - c[0]) + (b[1] - a[1]) * (d[1] - c[1])
                    self.assertAlmostEqual(dot, 0)

    def test_partition_is_drawn_once_and_blocks_connectivity(self):
        grid = DungeonMap((" |",))
        self.assertEqual(len(walls(xml(grid))), 7)
        segments = [endpoints(line) for line in walls(xml(grid))]
        self.assertEqual(segments.count(((1, 0), (1, 1))), 1)
        self.assertFalse(is_connected(grid))
        grid = DungeonMap((" L", "# "))
        self.assertEqual(len(walls(xml(grid))), 10)
        self.assertFalse(is_connected(grid))

    def test_feature_cluster_inherits_rough_terrain(self):
        rough = xml(DungeonMap(("#####", "#.TP#", "#####")))
        self.assertTrue(all(line.attrib["data-texture"] == "rough" for line in walls(rough)))
        mixed = xml(DungeonMap(("######", "#.TP #", "######")))
        self.assertTrue(any(line.attrib["data-texture"] == "smooth" for line in walls(mixed)))
        isolated = xml(DungeonMap(("###", "#T#", "###")))
        self.assertTrue(all(line.attrib["data-texture"] == "smooth" for line in walls(isolated)))

    def test_secret_and_concealed_doors_hidden_as_walls(self):
        for symbol in "SC":
            for horizontal in (False, True):
                with self.subTest(symbol=symbol, horizontal=horizontal):
                    grid = door_map(symbol, horizontal)
                    gm = xml(grid)
                    player = xml(grid, player_view=True)
                    self.assertEqual(len(gm.findall(".//s:g[@data-tile='{}']".format(symbol), NS)), 1)
                    self.assertEqual(len(player.findall(".//s:text", NS)), 0)
                    self.assertEqual(len(walls(player)), len(walls(gm)) + 1)
                    expected = (
                        ((2.5, 2), (2.5, 3)) if horizontal else ((2, 2.5), (3, 2.5))
                    )
                    self.assertIn(expected, [endpoints(line) for line in walls(player)])
                    self.assertNotIn("data-tile", svg_document(grid, player_view=True))
        self.assertEqual(
            len(xml(door_map("D"), player_view=True).findall(".//s:g[@data-tile='D']", NS)), 1
        )

    def test_traps_hidden_but_stairs_and_ramps_remain(self):
        grid = DungeonMap(("########", "#TPEURI#", "########"))
        gm = xml(grid)
        player = xml(grid, player_view=True)
        self.assertEqual(
            {group.attrib["data-tile"] for group in gm.findall(".//s:g[@data-tile]", NS)},
            set("TPEURI"),
        )
        self.assertEqual(
            {group.attrib["data-tile"] for group in player.findall(".//s:g[@data-tile]", NS)},
            set("EURI"),
        )
        self.assertEqual(
            [endpoints(line) for line in walls(gm)],
            [endpoints(line) for line in walls(player)],
        )

    def test_stair_and_ramp_passage_orientation(self):
        for symbol in "EURI":
            for rows, expected in (
                (("#####", "# {} #".format(symbol), "#####"), "rotate(90 .5 .5)"),
                (("###", "# #", "#{}#".format(symbol), "# #", "###"), "rotate(0)"),
                (("#####", "# {}##".format(symbol), "#####"), "rotate(90 .5 .5)"),
                (("#####", "##{} #".format(symbol), "#####"), "rotate(90 .5 .5)"),
                (("###", "# #", "#{}#".format(symbol), "###"), "rotate(0)"),
                (("###", "#{}#".format(symbol), "# #", "###"), "rotate(0)"),
            ):
                root = xml(DungeonMap(rows))
                drawing = root.find(".//s:g[@data-tile='{}']/s:g".format(symbol), NS)
                self.assertEqual(drawing.attrib["transform"], expected)

    def test_multi_square_stairs_and_ramps_render_as_one_full_length_symbol(self):
        for symbol in "EURI":
            for horizontal in (False, True):
                rows = ("#####", "#   #", "#" + symbol * 3 + "#", "#   #", "#####")
                if not horizontal:
                    rows = tuple("".join(row) for row in zip(*rows))
                grid = parse_ascii("\n".join(rows))
                root = xml(grid, player_view=True)
                groups = root.findall(".//s:g[@data-tile='{}']".format(symbol), NS)
                self.assertEqual(len(groups), 1)
                self.assertEqual(groups[0].attrib["data-length"], "3")
                drawing = groups[0].find("s:g", NS)
                self.assertEqual(drawing.attrib["transform"],
                                 "translate(3 0) rotate(90)" if horizontal else "rotate(0)")
                lines = drawing.findall("s:line", NS)
                self.assertEqual(len(lines), 18 if symbol in "EU" else 5)
                arrow = endpoints(lines[-3])
                self.assertEqual(arrow, ((0.42, 2.82), (0.42, 0.18)) if symbol in "ER"
                                 else ((0.42, 0.18), (0.42, 2.82)))
                self.assertTrue(all(
                    0 <= x <= 1 and 0 <= y <= 3
                    for line in lines for x, y in endpoints(line)
                ))

    def test_invalid_render_options(self):
        for options in (
            {"feet_per_pixel": 0}, {"feet_per_inch": float("inf")},
            {"line_width": -1}, {"roughness": float("nan")}, {"roughness": 0.21},
            {"rough_segments": 1}, {"rough_segments": 33}, {"rough_segments": 3.5},
            {"feet_per_pixel": 1e-300, "feet_per_inch": 1e300},
            {"feet_per_pixel": 1e300, "feet_per_inch": 1e-300},
            {"corner_radius": -0.1}, {"corner_radius": 0.501},
            {"corner_radius": float("nan")}, {"corner_radius": float("inf")},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                svg_document(DungeonMap((" ",)), **options)


class MeanderingTests(unittest.TestCase):
    @staticmethod
    def run_lengths(path):
        runs = []
        previous = None
        for first, last in zip(path, path[1:]):
            direction = (last[0] - first[0], last[1] - first[1])
            if direction == previous:
                runs[-1] += 1
            else:
                runs.append(1)
                previous = direction
        return runs

    def test_detours_have_short_runs_and_reach_the_goal_without_shortcuts(self):
        for start, end in (((3, 15), (57, 15)), ((15, 57), (15, 3)),
                           ((3, 10), (50, 45))):
            for seed in range(5):
                with self.subTest(start=start, end=end, seed=seed):
                    direct = _path(start, end, True)
                    path = _meander_path(direct, set(), 61, 61, 1, random.Random(seed))
                    self.assertEqual((path[0], path[-1]), (start, end))
                    self.assertEqual(len(path), len(set(path)))
                    self.assertGreater(len(path), len(direct))
                    self.assertLessEqual(len(path) - 1, 4 * (len(direct) - 1))
                    positions = {cell: index for index, cell in enumerate(path)}
                    for index, (x, y) in enumerate(path):
                        self.assertTrue(1 <= x < 60 and 1 <= y < 60)
                        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                            if (x + dx, y + dy) in positions:
                                self.assertEqual(abs(positions[(x + dx, y + dy)] - index), 1)
                    self.assertTrue(all(
                        abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1
                        for a, b in zip(path, path[1:])
                    ))
                    if start[0] == end[0] or start[1] == end[1]:
                        self.assertTrue(all(2 <= run <= 3 for run in self.run_lengths(path)[1:-1]))
                    self.assertTrue(set(direct) - set(path), "the bypass must replace the straight route")
                    self.assertEqual(
                        path, _meander_path(direct, set(), 61, 61, 1, random.Random(seed))
                    )

    def test_meandering_strength_and_zero_preserve_direct_route(self):
        direct = _path((3, 15), (57, 15), True)
        rng = random.Random(9)
        before = rng.getstate()
        self.assertEqual(_meander_path(direct, set(), 61, 31, 0, rng), direct)
        self.assertEqual(rng.getstate(), before)
        lengths = []
        for amount in (0.2, 0.9):
            lengths.append(sum(
                len(_meander_path(direct, set(), 61, 31, amount, random.Random(seed)))
                for seed in range(20)
            ))
        self.assertGreater(lengths[1], lengths[0] * 1.3)

    def test_bounds_and_occupied_rooms_can_limit_detours(self):
        direct = _path((1, 2), (1, 18), True)
        self.assertEqual(
            _meander_path(direct, set(), 3, 21, 1, random.Random(4)), direct
        )
        direct = _path((3, 5), (25, 5), True)
        occupied = {(x, y) for x in range(1, 29) for y in range(1, 12)} - set(direct)
        self.assertEqual(
            _meander_path(direct, occupied, 30, 13, 1, random.Random(4)), direct
        )
        self.assertEqual(
            _meander_path([(2, 2)], set(), 5, 5, 1, random.Random(4)), [(2, 2)]
        )


class GenerationTests(unittest.TestCase):
    def test_repeatable_ascii_and_svg(self):
        options = GenerationOptions(width=30, height=24, seed=31, traps=2)
        first, second = generate_dungeon(options), generate_dungeon(options)
        self.assertEqual(first, second)
        self.assertEqual(parse_ascii(first.grid.to_ascii()), first.grid)
        self.assertEqual(
            svg_document(first.grid, seed=first.seed), svg_document(second.grid, seed=second.seed)
        )
        self.assertNotEqual(first.grid, generate_dungeon(GenerationOptions(
            width=30, height=24, seed=32, traps=2
        )).grid)

    def test_generated_seed_can_be_replayed(self):
        result = generate_dungeon(GenerationOptions(width=20, height=20))
        self.assertEqual(result, generate_dungeon(GenerationOptions(
            width=20, height=20, seed=result.seed
        )))

    def test_exact_features_valid_diagonals_and_connected_layouts(self):
        expected = Counter({"D": 3, "S": 2, "C": 2, "T": 4, "P": 2,
                            "E": 1, "U": 1, "R": 1, "I": 1})
        for seed in range(8):
            with self.subTest(seed=seed):
                result = generate_dungeon(GenerationOptions(
                    seed=seed, doors=3, secret_doors=2, concealed_doors=2,
                    traps=4, pits=2, stairs_down=1, stairs_up=1,
                    ramps_down=1, ramps_up=1, chamfer_probability=1,
                    meandering=seed % 2,
                ))
                grid = result.grid
                self.assertEqual((grid.width, grid.height), (60, 40))
                self.assertTrue(is_connected(grid))
                actual = Counter("".join(grid.rows))
                self.assertEqual({tile: actual[tile] for tile in expected}, dict(expected))
                self.assertGreater(actual["/"] + actual["\\"], 0)
                self.assertTrue(all(tile == "#" for tile in grid.rows[0] + grid.rows[-1]))
                self.assertTrue(all(row[0] == row[-1] == "#" for row in grid.rows))
                xml(grid)

    def test_meandering_changes_only_rough_corridors(self):
        for rough in (0, 1):
            routes = {0: [], 1: []}

            def observe(path, occupied, width, height, amount, rng):
                result = _meander_path(path, occupied, width, height, amount, rng)
                routes[amount].append((path, result, occupied))
                return result

            with patch("dungeon_map._meander_path", side_effect=observe):
                results = [
                    generate_dungeon(GenerationOptions(
                        seed=7, rough_probability=rough, meandering=amount,
                        doors=0, secret_doors=0, concealed_doors=0,
                    )) for amount in (0, 1)
                ]
            for result in results:
                self.assertTrue(is_connected(result.grid))
            if rough:
                self.assertNotEqual(results[0].grid, results[1].grid)
                self.assertTrue(any(direct != path for direct, path, occupied in routes[1]))
                for amount, result in enumerate(results):
                    self.assertEqual(result.corridor_lengths, tuple(
                        sum(cell not in occupied for cell in path)
                        for direct, path, occupied in routes[amount]
                    ))
                    self.assertTrue(all(
                        result.grid.tile(x, y) == "."
                        for direct, path, occupied in routes[amount] for x, y in path
                    ))
            else:
                self.assertEqual(results[0], results[1])
                self.assertFalse(routes[0] or routes[1])

    def test_probability_endpoints_and_exact_zero_override(self):
        for rough in (0, 1):
            result = generate_dungeon(GenerationOptions(
                width=35, height=25, seed=9, rough_probability=rough,
                doors=0, secret_doors=0, concealed_doors=0,
            ))
            self.assertNotIn(" " if rough else ".", result.grid.to_ascii())
            self.assertFalse(set("DSC") & set(result.grid.to_ascii()))
        for symbol, probabilities in (
            ("D", (1, 0, 0)), ("S", (0, 1, 0)), ("C", (0, 0, 1)),
        ):
            result = generate_dungeon(GenerationOptions(
                seed=7, door_probability=probabilities[0],
                secret_door_probability=probabilities[1],
                concealed_door_probability=probabilities[2],
            ))
            actual = set(result.grid.to_ascii()) & set("DSC")
            self.assertEqual(actual, {symbol})
            self.assertTrue(is_connected(result.grid))

    def test_density_room_size_and_corridor_length_controls(self):
        def totals(**values):
            results = [
                generate_dungeon(GenerationOptions(
                    seed=seed, width=60, height=40, doors=0,
                    secret_doors=0, concealed_doors=0, **values
                )) for seed in range(4)
            ]
            return (
                sum(result.density for result in results) / len(results),
                sum(sum(result.room_areas) for result in results)
                / sum(len(result.room_areas) for result in results),
                sum(sum(result.corridor_lengths) for result in results)
                / sum(len(result.corridor_lengths) for result in results),
            )
        sparse, dense = totals(density=0.15), totals(density=0.4)
        self.assertGreater(dense[0] - sparse[0], 0.15)
        small, large = totals(room_size=16), totals(room_size=60)
        self.assertGreater(large[1], small[1] * 2)
        short, long = totals(corridor_length=2), totals(corridor_length=15)
        self.assertGreater(long[2], short[2] * 1.5)

    def test_small_map_and_large_room_request(self):
        result = generate_dungeon(GenerationOptions(width=7, height=7, seed=2, room_size=1e308))
        self.assertTrue(is_connected(result.grid))
        self.assertEqual(result.grid.width, 7)
        self.assertLess(result.density, 0.3)

    def test_invalid_generation_parameters(self):
        for values in (
            {"width": 6}, {"height": 0}, {"room_size": 0},
            {"room_size": float("inf")}, {"corridor_length": -1},
            {"density": 0}, {"density": 1}, {"density": float("nan")},
            {"rough_probability": 1.1}, {"door_probability": 0.95},
            {"chamfer_probability": -1}, {"traps": -1}, {"secret_doors": 2.5},
            {"meandering": -0.1}, {"meandering": 1.1}, {"meandering": float("nan")},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                generate_dungeon(GenerationOptions(**values))

    def test_impossible_counts_fail_explicitly(self):
        for values in ({"secret_doors": 50}, {"traps": 50}):
            with self.subTest(values=values), self.assertRaisesRegex(
                ValueError, "could not satisfy feature counts"
            ):
                generate_dungeon(GenerationOptions(width=7, height=7, seed=1, **values))


class MultiLevelTests(unittest.TestCase):
    def test_stairs_terminate_existing_corridors_without_isolating_floor(self):
        for symbol in "EURI":
            for horizontal in (False, True):
                with self.subTest(symbol=symbol, horizontal=horizontal):
                    rows = [["#"] * 13 for _ in range(9)]
                    rows[4][1:12] = [" "] * 11
                    cells = ((5, 4), (6, 4), (7, 4))
                    entrance = (4, 4) if symbol in "ER" else (8, 4)
                    closed_end = (8, 4) if symbol in "ER" else (4, 4)
                    if not horizontal:
                        rows = [list(row) for row in zip(*rows)]
                        cells = tuple((y, x) for x, y in cells)
                        entrance = (4, 8) if symbol in "ER" else (4, 4)
                        closed_end = (4, 4) if symbol in "ER" else (4, 8)
                    options = GenerationOptions(width=len(rows[0]), height=len(rows), levels=2)
                    route = tuple((x, 4) if horizontal else (4, x) for x in range(1, 12))
                    passages, reserved, notes = _place_stairways(
                        rows, options, random.Random(0),
                        (Stairway(cells, symbol, horizontal),), 0, [],
                        [_Corridor(route, " ")],
                    )
                    grid = DungeonMap(tuple("".join(row) for row in rows))
                    self.assertTrue(is_connected(grid))
                    self.assertEqual(grid.tile(*entrance), " ")
                    self.assertEqual(grid.tile(*closed_end), "#")
                    self.assertEqual(passages[0].entrance, entrance)
                    self.assertEqual(passages[0].closed_end, closed_end)
                    for x, y in cells:
                        self.assertEqual(grid.tile(x, y), symbol)
                        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                            neighbor = (x + dx, y + dy)
                            if neighbor not in cells and neighbor != entrance:
                                self.assertEqual(grid.tile(*neighbor), "#")
                                self.assertIn(neighbor, reserved)
                    for cell in (route[0], route[-1]):
                        self.assertEqual(grid.tile(*cell), " ")
                    self.assertEqual(notes, ("Rerouted 1 corridors around stairways.",))

    def test_new_stairs_relocate_into_rock_instead_of_cutting_rooms_or_corridors(self):
        rows = [["#"] * 30 for _ in range(16)]
        rooms = [
            _Room((cx, 7), {(x, y) for x in range(cx - 1, cx + 2)
                           for y in range(6, 9)}, False)
            for cx in (3, 26)
        ]
        corridors = [_Corridor(tuple((x, 7) for x in range(3, 27)), " ")]
        _rebuild_layout(rows, rooms, corridors)
        original_floor = {
            (x, y) for y, row in enumerate(rows) for x, tile in enumerate(row) if tile == " "
        }
        original_route = corridors[0]
        passages, _, notes = _place_stairways(
            rows, GenerationOptions(width=30, height=16, levels=2, stair_length=5),
            random.Random(3), (), 1, rooms, corridors,
        )
        self.assertEqual(len(passages), 2)
        self.assertFalse(notes)
        self.assertIs(corridors[0], original_route)
        room_cells = set().union(*(room.cells for room in rooms))
        for passage in passages:
            self.assertFalse((set(passage.cells) | passage.walls) & original_floor)
            self.assertFalse(set(passage.cells + passage.approach) & room_cells)
        self.assertTrue(is_connected(DungeonMap(tuple("".join(row) for row in rows))))

    def test_collision_reroutes_full_corridor_or_removes_it_and_orphaned_room(self):
        corridor = _Corridor(tuple((x, 4) for x in range(2, 13)), ".")
        untouched = _Corridor(((1, 1), (2, 1)), " ")
        obstacle = {(7, y) for y in range(3, 6)}
        retained, rerouted, removed = _reroute_corridors([corridor, untouched], obstacle, 15, 9)
        self.assertEqual((rerouted, removed), (1, 0))
        self.assertEqual(retained[0].cells[0], corridor.cells[0])
        self.assertEqual(retained[0].cells[-1], corridor.cells[-1])
        self.assertFalse(obstacle.intersection(retained[0].cells))
        self.assertEqual(retained[0].tile, ".")
        self.assertIs(retained[1], untouched)

        barrier = {(7, y) for y in range(9)}
        retained, rerouted, removed = _reroute_corridors([corridor], barrier, 15, 9)
        self.assertEqual((retained, rerouted, removed), ([], 0, 1))
        rooms = [
            _Room((cx, 4), {(x, y) for x in range(cx - 1, cx + 2)
                           for y in range(3, 6)}, False)
            for cx in (2, 12)
        ]
        rows = [["#"] * 15 for _ in range(9)]
        _rebuild_layout(rows, rooms, retained)
        with self.assertRaisesRegex(ValueError, "entrances cannot be connected"):
            _prune_unreachable(rows, rooms, retained, [(2, 4), (12, 4)])
        removed_rooms, _ = _prune_unreachable(rows, rooms, retained, [(2, 4)])
        self.assertEqual(removed_rooms, 1)
        self.assertEqual([room.center for room in rooms], [(2, 4)])
        self.assertTrue(all(rows[y][x] == "#" for y in range(9) for x in range(4, 15)))
        self.assertTrue(is_connected(DungeonMap(tuple("".join(row) for row in rows))))

    def test_all_stair_types_have_corner_clearance_and_corridor_approaches(self):
        observed = []

        def observe(rows, options, rng, incoming, down_count, rooms, corridors):
            result = _place_stairways(rows, options, rng, incoming, down_count, rooms, corridors)
            observed.append((result[0], set().union(*(room.cells for room in rooms))))
            return result

        for levels in (1, 3):
            observed.clear()
            with patch("dungeon_map._place_stairways", side_effect=observe):
                result = generate_dungeon(GenerationOptions(
                    seed=5, levels=levels, stairs_down=2, ramps_down=1,
                    stairs_up=1, ramps_up=1 if levels == 1 else 0,
                    stair_length=5, chamfer_probability=1, traps=8, pits=4,
                ))
            self.assertEqual(len(observed), levels)
            for level, (passages, room_cells) in zip(result.levels, observed):
                self.assertTrue(is_connected(level.grid))
                self.assertTrue(all(level.grid.tile(*cell) != "#" for cell in room_cells))
                for passage in passages:
                    self.assertFalse((set(passage.cells + passage.approach) | passage.walls) & room_cells)
                    for x, y in passage.cells:
                        for dx in (-1, 0, 1):
                            for dy in (-1, 0, 1):
                                neighbor = (x + dx, y + dy)
                                if neighbor not in passage.cells and neighbor != passage.entrance:
                                    self.assertEqual(level.grid.tile(*neighbor), "#")
                    for cell in passage.approach:
                        self.assertIn(level.grid.tile(*cell), " .")
                root = xml(level.grid)
                symbols = [g for g in root.findall(".//s:g[@data-tile]", NS)
                           if g.attrib["data-tile"] in "EURI"]
                self.assertEqual(len(symbols), len(passages))

    def test_linked_footprints_lengths_depths_and_feature_protection(self):
        for seed, length in ((0, 1), (2, 3), (7, 6)):
            with self.subTest(seed=seed, length=length):
                options = GenerationOptions(
                    seed=seed, levels=4, stair_length=length, stairs_down=2,
                    ramps_down=1, ramp_probability=50, traps=3, pits=2,
                    doors=2, secret_doors=1, concealed_doors=1,
                    chamfer_probability=1,
                )
                result = generate_dungeon(options)
                self.assertEqual(result, generate_dungeon(options))
                self.assertEqual(len(result.levels), 4)
                for index, level in enumerate(result.levels):
                    self.assertEqual(level.depth_feet, (index + 1) * length * 10)
                    self.assertTrue(is_connected(level.grid))
                    self.assertEqual(parse_ascii(level.grid.to_ascii()), level.grid)
                    counts = Counter("".join(level.grid.rows))
                    self.assertEqual({tile: counts[tile] for tile in "TPDSC"},
                                     {"T": 3, "P": 2, "D": 2, "S": 1, "C": 1})
                    self.assertEqual(counts["E"] + counts["R"],
                                     0 if index == 3 else 3 * length)
                    used = set()
                    for passage in level.stairways:
                        self.assertEqual(len(passage.cells), length)
                        self.assertFalse(used.intersection(passage.cells))
                        used.update(passage.cells)
                        for first, second in zip(passage.cells, passage.cells[1:]):
                            self.assertEqual((second[0] - first[0], second[1] - first[1]),
                                             (1, 0) if passage.horizontal else (0, 1))
                        for x, y in passage.cells:
                            self.assertEqual(level.grid.tile(x, y), passage.tile)
                            self.assertTrue(0 < x < level.grid.width - 1)
                            self.assertTrue(0 < y < level.grid.height - 1)
                        self.assertIn(level.grid.tile(*passage.entrance), " .")
                        self.assertEqual(level.grid.tile(*passage.closed_end), "#")
                        accessible = {
                            (x + dx, y + dy) for x, y in passage.cells
                            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0))
                            if (x + dx, y + dy) not in passage.cells
                            and level.grid.tile(x + dx, y + dy) != "#"
                        }
                        self.assertEqual(accessible, {passage.entrance})
                    up = [s for s in level.stairways if s.tile in "UI"]
                    if index == 0:
                        self.assertEqual(len(up), 1)
                        self.assertEqual(up[0].tile, "U")
                    else:
                        above = [replace(s, tile="U" if s.tile == "E" else "I")
                                 for s in result.levels[index - 1].stairways if s.tile in "ER"]
                        self.assertEqual(up, above)
                        descents = [s for s in result.levels[index - 1].stairways if s.tile in "ER"]
                        for descent, ascent in zip(descents, up):
                            self.assertEqual(descent.entrance, ascent.closed_end)
                            self.assertEqual(descent.closed_end, ascent.entrance)
                    root = xml(level.grid)
                    if length > 1:
                        rendered = root.findall(".//s:g[@data-length]", NS)
                        self.assertEqual(len(rendered), len(level.stairways))
                        self.assertTrue(all(g.attrib["data-length"] == str(length) for g in rendered))

    def test_ramp_percentage_endpoints_and_surface_stair(self):
        for chance, down, up in ((0, "E", "U"), (100, "R", "I")):
            result = generate_dungeon(GenerationOptions(
                seed=23, levels=3, stairs_down=2, ramp_probability=chance,
            ))
            for index, level in enumerate(result.levels):
                counts = Counter(s.tile for s in level.stairways)
                expected = Counter({"U": 1}) if index == 0 else Counter({up: 2})
                if index < 2:
                    expected[down] += 2
                self.assertEqual(counts, expected)
        ramps_only = generate_dungeon(GenerationOptions(
            seed=23, levels=2, stairs_down=0, ramps_down=2,
        ))
        self.assertEqual(Counter(s.tile for s in ramps_only.stairways), {"U": 1, "R": 2})
        self.assertEqual(Counter(s.tile for s in ramps_only.levels[-1].stairways), {"I": 2})

    def test_defaults_random_seed_replay_and_single_level_compatibility(self):
        result = generate_dungeon(GenerationOptions(width=30, height=24, levels=3))
        self.assertEqual(result, generate_dungeon(GenerationOptions(
            width=30, height=24, levels=3, seed=result.seed,
        )))
        for level in result.levels[:-1]:
            self.assertIn(sum(s.tile in "ER" for s in level.stairways), (1, 2, 3))
            self.assertTrue(all(len(s.cells) == 3 for s in level.stairways))
        options = GenerationOptions(seed=31, stairs_down=2, stairs_up=2, ramps_up=1)
        original = generate_dungeon(options)
        explicit = generate_dungeon(replace(options, levels=1, stair_length=8, ramp_probability=100))
        self.assertEqual(original, explicit)
        self.assertEqual(original.levels, (original,))
        self.assertEqual(Counter(original.grid.to_ascii())["E"], 2)
        self.assertEqual(generate_dungeon(GenerationOptions(seed=31)),
                         generate_dungeon(GenerationOptions(seed=31, stairs_down=0)))

    def test_invalid_and_impossible_linked_passages(self):
        for values in (
            {"levels": 0}, {"levels": -1}, {"levels": 1.5}, {"levels": True},
            {"stair_length": 0}, {"stair_length": 2.5},
            {"ramp_probability": -1}, {"ramp_probability": 101},
            {"ramp_probability": float("nan")}, {"ramp_probability": float("inf")},
            {"levels": 2, "width": 10, "height": 10, "stair_length": 7},
            {"levels": 2, "stairs_up": 2}, {"levels": 2, "ramps_up": 1},
            {"levels": 2, "stairs_down": 0},
            {"levels": 2, "width": 7, "height": 7, "stairs_down": 20},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                generate_dungeon(GenerationOptions(seed=1, **values))


class EncounterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = EncounterRules()

    def chamber(self, seed=42):
        cells = tuple((x, y) for y in range(1, 4) for x in range(1, 4))
        return GeneratedDungeon(
            DungeonMap(("#####", "#   #", "#   #", "#   #", "#####")),
            seed, (9,), (), room_cells=(cells,),
        )

    def test_basic_roll_has_three_zero_based_dice_and_no_symbol_rerolls(self):
        for values, expected in (((0, 0, 0), 0), ((11, 11, 11), 33), ((11, 0, 4), 15)):
            rng = Mock()
            rng.randint.side_effect = values
            self.assertEqual(basic_roll(rng), expected)
            self.assertEqual(rng.randint.call_count, 3)
            self.assertTrue(all(call[0] == (0, 11) for call in rng.randint.call_args_list))

    def test_source_table_bands_counts_and_typo_rulings(self):
        for depth, expected in ((1, "Mummy"), (3, "Mummy"), (4, "Gargoyles"),
                                (6, "Gargoyles"), (7, "Ogres"), (9, "Ogres"),
                                (10, "Ogres"), (25, "Ogres")):
            monster = monster_encounter(self.rules, random.Random(42), depth, 22)
            self.assertIn(expected, monster.description)
        self.assertEqual(self.rules.categories[12], ["Misc"])
        self.assertEqual(self.rules.classes[28], ["Cleric"])
        for depth in (1, 4, 7, 10):
            for roll in range(34):
                monster = monster_encounter(self.rules, random.Random(roll), depth, roll)
                self.assertTrue(monster.levels)
                self.assertTrue(all(level >= 1 for level in monster.levels))
        rng = Mock()
        rng.randint.return_value = 4
        skeletons = monster_encounter(self.rules, rng, 1, 20)
        self.assertEqual(skeletons.levels, (1,) * 5)
        slimes = monster_encounter(self.rules, rng, 4, 21)
        self.assertEqual(slimes.levels, (1,) * 4)
        self.assertEqual(self.rules.creature_level("Sphynx", 9), (8, False))
        self.assertEqual(self.rules.creature_level("Mummys", 9), (6, False))
        self.assertEqual(self.rules.creature_level("Balrog", 9), (9, True))

    def test_dragon_and_monster_treasure_stay_in_the_encounter_chamber(self):
        debug = []
        monster = monster_encounter(self.rules, random.Random(42), 7, 1, debug)
        self.assertTrue(monster.dragon)
        self.assertIn("in its lair in this chamber", monster.description)
        self.assertNotIn("miles", monster.description)
        self.assertFalse(any("Dragon location" in line or "lair distance" in line for line in debug))
        with patch("dungeon_encounters.basic_roll", side_effect=[21, 0, 0]):
            loot = treasure(self.rules, random.Random(42), 1, MonsterEncounter("Goblin", (1,)))
        self.assertEqual(loot[0], "Lair cache in this chamber.")
        self.assertNotIn("must be located", " ".join(loot))

    def test_container_thresholds_are_inclusive_and_only_chests_can_be_trapped(self):
        dungeon = self.chamber()
        for chest_roll, trap_roll, trapped in ((16, None, False), (17, 18, False), (17, 19, True)):
            rolls = [0, 0, chest_roll] + ([] if trap_roll is None else [trap_roll, 0])
            with self.subTest(chest_roll=chest_roll, trap_roll=trap_roll), \
                    patch("dungeon_encounters.basic_roll", side_effect=rolls) as roll, \
                    patch("dungeon_encounters.treasure", return_value=("Coins: 2 cp.",)):
                key = generate_encounters(dungeon, rules=self.rules)[0]
            area = key.areas[0]
            self.assertEqual(roll.call_count, len(rolls))
            self.assertEqual(area.container == "chest", chest_roll >= 17)
            self.assertEqual(area.chest_trap is not None, trapped)
            if area.container != "chest":
                self.assertIn(area.container, ("bag", "pack"))
            guide = encounter_document(dungeon, (key,), 11)
            label = "Unlocked chest" if area.container == "chest" else area.container.capitalize()
            self.assertIn("- {}.".format(label), guide)
            self.assertEqual("**Chest trap:**" in guide, trapped)
            log = encounter_log(dungeon, (key,), 11)
            self.assertIn("Treasure chest (DC 17): basic roll = {}".format(chest_roll), log)
            self.assertEqual("Chest trap (DC 19)" in log, trap_roll is not None)
            self.assertNotIn("Treasure chest (DC", guide)

    def test_container_overrides_validate_and_leave_other_contents_unchanged(self):
        dungeon = generate_dungeon(GenerationOptions(seed=42))
        def original_contents(keys):
            return tuple(replace(key, areas=tuple(
                replace(area, container=None, chest_trap=None, chest_locked=None, debug=()) for area in key.areas
            )) for key in keys)
        first = generate_encounters(dungeon, rules=self.rules, treasure_chest_dc=0, chest_trap_dc=0)
        for chest_dc, trap_dc in ((0, 34), (34, 0)):
            keys = generate_encounters(dungeon, rules=self.rules,
                                       treasure_chest_dc=chest_dc, chest_trap_dc=trap_dc)
            self.assertEqual(original_contents(first), original_contents(keys))
            self.assertTrue(any(area.container for key in keys for area in key.areas))
            for key in keys:
                for area in key.areas:
                    if area.container:
                        self.assertEqual(area.container == "chest", chest_dc == 0)
                        self.assertIsNone(area.chest_trap)
        for key in first:
            for area in key.areas:
                if area.container:
                    self.assertEqual(area.container, "chest")
                    self.assertIsNotNone(area.chest_trap)
        for name in ("treasure_chest_dc", "chest_trap_dc", "chest_lock_dc"):
            for invalid in (-1, 35, True, 2.5):
                with self.assertRaisesRegex(ValueError, name):
                    generate_encounters(dungeon, rules=self.rules, **{name: invalid})

    def test_chest_lock_threshold_is_inclusive_independent_and_only_in_log(self):
        dungeon = self.chamber()
        for trap_roll in (18, 19):
            for lock_roll in (16, 17):
                with self.subTest(trap_roll=trap_roll, lock_roll=lock_roll), \
                        patch("dungeon_encounters.basic_roll",
                              side_effect=[0, 0, 17, trap_roll, lock_roll]), \
                        patch("dungeon_encounters.treasure",
                              return_value=("Lair cache in this chamber.", "Coins: 2 cp.")):
                    keys = generate_encounters(dungeon, rules=self.rules)
                area = keys[0].areas[0]
                self.assertEqual(area.chest_locked, lock_roll >= 17)
                self.assertEqual(area.chest_trap is not None, trap_roll >= 19)
                guide = encounter_document(dungeon, keys, 11)
                label = "Locked chest" if lock_roll >= 17 else "Unlocked chest"
                self.assertIn("- {}.".format(label), guide)
                self.assertIn("Coins: 2 cp.", guide)
                self.assertNotIn("cache", guide)
                self.assertNotIn("in this chamber", guide)
                self.assertNotIn("Chest lock (DC", guide)
                log = encounter_log(dungeon, keys, 11)
                self.assertIn("Chest lock (DC 17): basic roll = {}".format(lock_roll), log)
                self.assertIn("Treasure result: Lair cache in this chamber.", log)

    def test_lock_override_preserves_containers_loot_and_traps(self):
        dungeon = generate_dungeon(GenerationOptions(seed=42))
        locked = generate_encounters(dungeon, rules=self.rules, chest_lock_dc=0)
        unlocked = generate_encounters(dungeon, rules=self.rules, chest_lock_dc=34)
        self.assertTrue(any(area.container == "chest" for key in locked for area in key.areas))
        for first, second in zip(locked, unlocked):
            for a, b in zip(first.areas, second.areas):
                self.assertEqual(replace(a, chest_locked=None, debug=()),
                                 replace(b, chest_locked=None, debug=()))
                if a.container == "chest":
                    self.assertIs(a.chest_locked, True)
                    self.assertIs(b.chest_locked, False)
                else:
                    self.assertIsNone(a.chest_locked)
                    self.assertIsNone(b.chest_locked)
                    self.assertFalse(any("Chest lock (" in line for line in a.debug + b.debug))

    def test_chest_trap_triggers_on_opening_not_a_floor_mechanism(self):
        for kind in (3, 4):
            rng = Mock()
            rng.choice.side_effect = [kind, "sleep"]
            rng.randint.return_value = 2
            description = trap_description(rng, chest=True)
            self.assertIn("opening the chest", description)
            self.assertIn("CON / PSN-SLEEP", description)
            self.assertIn("after 2 rounds, lasting 2 hours", description)
            self.assertNotIn("pressure plate", description)

    def test_monster_threshold_is_inclusive_and_validated(self):
        for threshold, presence, expected in ((11, 10, False), (11, 11, True),
                                               (0, 0, True), (33, 32, False),
                                               (33, 33, True)):
            rolls = [presence, 0, 0] if expected else [presence, 0]
            with patch("dungeon_encounters.basic_roll", side_effect=rolls), \
                    patch("dungeon_encounters.treasure", return_value=("None.",)):
                area = generate_encounters(self.chamber(), threshold, self.rules)[0].areas[0]
            self.assertEqual(area.monster is not None, expected)
            self.assertEqual(area.table_roll, 0 if expected else None)
        for invalid in (-1, 34, True, 2.5):
            with self.assertRaisesRegex(ValueError, "0 through 33"):
                generate_encounters(self.chamber(), invalid, self.rules)

    def test_treasure_uses_monster_level_and_rolls_coins_per_individual(self):
        rng = Mock()
        rng.randint.return_value = 1
        monsters = MonsterEncounter("Three level-one goblins", (1, 1, 1))
        debug = []
        with patch("dungeon_encounters.basic_roll", side_effect=[21, 20, 24]):
            loot = treasure(self.rules, rng, 9, monsters, debug)
        self.assertIn("Coins: 6 cp", loot[1])
        self.assertIn("1 pieces, worth 1 cp", loot[2])
        self.assertIn("Gems/jewelry presence (DC 23, modifier +3): basic roll = 20", debug)
        self.assertNotIn("check", loot[2])
        self.assertIn("Magic: none", loot[3])
        with patch("dungeon_encounters.basic_roll", return_value=20):
            self.assertIn("None", treasure(self.rules, rng, 1, monsters)[0])

    def test_empty_cache_and_magic_threshold_bonus(self):
        rng = Mock()
        rng.randint.return_value = 1
        debug = []
        with patch("dungeon_encounters.basic_roll", side_effect=[21, 0, 23]), \
                patch("dungeon_encounters.magic_item", return_value="Magic Shield") as item:
            loot = treasure(self.rules, rng, 6, None, debug)
        self.assertIn("Abandoned chamber cache", loot[0])
        self.assertIn("Coins: 1 gp", loot[1])
        self.assertIn("Magic presence (DC 25, modifier +2): basic roll = 23", debug)
        item.assert_called_once_with(self.rules, rng, 6, debug)
        with patch("dungeon_encounters.basic_roll", side_effect=[21, 0, 0]), \
                patch("dungeon_encounters.magic_item", return_value="Magic Shield"):
            deep = treasure(self.rules, rng, 30, None)
        self.assertIn("Coins: 4 pp", deep[1])

    def test_dragon_hoard_guarantees_and_multipliers(self):
        rng = Mock()
        rng.randint.return_value = 1
        with patch("dungeon_encounters.basic_roll", side_effect=[0, 22, 0]), \
                patch("dungeon_encounters.magic_item", return_value="Magic Shield") as item:
            loot = treasure(self.rules, rng, 7, MonsterEncounter("Young Horntail", (8,), True))
        self.assertEqual("Dragon hoard.", loot[0])
        self.assertIn("Coins: 400 gp", loot[1])
        self.assertIn("2 pieces, worth 4 gp, 4 gp", loot[2])
        self.assertIn("Magic: 2 items", loot[3])
        self.assertEqual(item.call_count, 2)
        item.assert_called_with(self.rules, rng, 10, None)

    def test_magic_category_subtype_bonus_and_charges(self):
        rng = Mock()
        rng.randint.return_value = 1
        cases = (
            (0, "Mace", "+2 to hit and attack power"),
            (9, "Plate", "+2 toughness"),
            (11, "Magic Shield", "-2 to hit"),
            (12, "Cloak of Invisibility", "power +2"),
            (14, "Invisibility", "single use"),
            (17, "Invisibility", "power +2"),
            (20, "Magic Missile", "2 missiles per charge"),
            (22, "Magic Missile", "+2 to hit and AP as a quarterstaff"),
            (24, "Magic Bracers", "+2 toughness"),
            (29, "Invisibility", "power +2"),
        )
        for roll, subtype, effect in cases:
            debug = []
            with patch("dungeon_encounters.basic_roll", side_effect=[roll, 27]):
                item = magic_item(self.rules, rng, 1, debug)
            self.assertIn(subtype, item)
            self.assertIn(effect, item)
            self.assertNotRegex(item, r"\broll\b")
            self.assertIn("Magic item category: basic roll = {}".format(roll), debug)
            self.assertIn("Magic item power at table level 1: basic roll = 27", debug)
            if roll in (20, 22):
                self.assertIn("2 charges", item)
                self.assertIn("Magic item charges: 2d12 = 2", debug)
        for level, power_roll, expected in ((1, 26, 1), (1, 27, 2), (3, 33, 3),
                                             (10, 30, 5), (20, 30, 5)):
            with patch("dungeon_encounters.basic_roll", side_effect=[11, power_roll]):
                self.assertIn("power +{}".format(expected), magic_item(self.rules, rng, level))

    def test_traps_use_saves_poison_timing_and_falling_attack_power(self):
        rng = Mock()
        rng.randint.return_value = 2
        pit = trap_description(rng, pit=True)
        self.assertIn("fall 20 feet, AP 20", pit)
        self.assertIn("ST 20 (DEX / FALL)", pit)
        for kind in range(1, 5):
            for poison in ("sleep", "paralysis", "deadly"):
                rng.randrange.return_value = kind
                rng.choice.return_value = poison
                description = trap_description(rng)
                self.assertIn("DC 20 (WIS)", description)
                self.assertIn("ST ", description)
                if kind >= 3:
                    self.assertIn("CON / PSN-" + poison.upper(), description)
                    self.assertIn("after 2 rounds", description)
                    self.assertIn("death 2 rounds later" if poison == "deadly" else "lasting 2 hours",
                                  description)

    def test_room_footprints_labels_hidden_features_and_reproducibility(self):
        dungeon = generate_dungeon(GenerationOptions(
            seed=42, levels=3, traps=2, pits=2, secret_doors=2, concealed_doors=2,
        ))
        contents = generate_encounters(dungeon, rules=self.rules)
        self.assertEqual(contents, generate_encounters(dungeon, rules=self.rules))
        self.assertNotEqual(contents, generate_encounters(replace(dungeon, seed=43), rules=self.rules))
        for level, key in zip(dungeon.levels, contents):
            self.assertEqual(len(key.areas), len(level.room_areas))
            self.assertEqual([len(cells) for cells in level.room_cells], list(level.room_areas))
            self.assertEqual([area.number for area in key.areas], list(range(1, len(key.areas) + 1)))
            positions = [(area.cell[1], area.cell[0]) for area in key.areas]
            self.assertEqual(positions, sorted(positions))
            for area in key.areas:
                self.assertEqual(sum(area.cell in cells for cells in level.room_cells), 1)
                self.assertIn(level.grid.tile(*area.cell), " .TP")
            self.assertEqual(len(key.traps), 4)
            self.assertEqual(Counter((kind, dc) for _, kind, dc in key.doors),
                             Counter({("Secret", 20): 2, ("Concealed", 17): 2}))
            root = xml(level.grid, encounter_labels=key.labels, player_view=True)
            labels = root.findall("s:g[@id='encounters']/s:g", NS)
            self.assertEqual(len(labels), len(key.areas))
            for label, area in zip(labels, key.areas):
                self.assertEqual(label.attrib["data-area"], str(area.number))
                self.assertEqual(label.attrib["data-column"], str(area.cell[0] + 1))
                self.assertEqual(label.attrib["data-row"], str(area.cell[1] + 1))
                self.assertEqual(label.find("s:text", NS).text, str(area.number))
            self.assertFalse(root.findall("s:g[@id='features']/s:g[@data-tile='T']", NS))
        document = encounter_document(dungeon, contents, 11)
        self.assertEqual(len(re.findall(r"^### \d+$", document, re.MULTILINE)),
                         sum(len(key.areas) for key in contents))
        self.assertIn("## Level 3", document)
        self.assertNotIn("TM ONLY", document)
        for level in contents:
            for cell, kind, dc in level.doors:
                self.assertIn("{} door at column {}, row {}: DC {} (WIS)".format(
                    kind, cell[0] + 1, cell[1] + 1, dc), document)

    def test_area_numbers_follow_label_rows_then_columns_not_generation_order(self):
        dungeon = GeneratedDungeon(
            DungeonMap(("#########", "#       #", "#       #", "#       #", "#########")),
            42, (1, 1, 1, 1), (),
            room_cells=(((6, 3),), ((6, 1),), ((2, 3),), ((2, 1),)),
        )
        key = generate_encounters(dungeon, rules=self.rules)[0]
        self.assertEqual([(area.number, area.cell) for area in key.areas],
                         [(1, (2, 1)), (2, (6, 1)), (3, (2, 3)), (4, (6, 3))])
        self.assertEqual(tuple(key.labels.values()), ("1", "2", "3", "4"))

    def test_markdown_is_playable_description_and_debug_log_retains_rolls(self):
        dungeon = self.chamber()
        with patch("dungeon_encounters.basic_roll", return_value=33):
            keys = generate_encounters(dungeon, rules=self.rules)
        markdown = encounter_document(dungeon, keys, 11)
        log = encounter_log(dungeon, keys, 11)
        for text in ("Monster presence", "table roll", "basic roll", "treasure check",
                     "Map label:", "Seed:", "Rules and generator rulings", "Encounter table:"):
            self.assertNotIn(text, markdown)
        area = markdown.split("### 1\n", 1)[1].split("### Explicit map traps", 1)[0]
        self.assertNotIn("column", area)
        self.assertNotIn("row", area)
        self.assertIn("Unicorn", area)
        self.assertIn("Coins:", area)
        self.assertIn("Magic Ring", area)
        self.assertIn("power +", area)
        self.assertIn("**Trap:**", area)
        for text in ("Seed: 42", "Level 1", "Area 1 (column 3, row 3)",
                     "Monster presence roll: 33 vs DC 11", "Monster table roll: 33",
                     "Treasure presence (DC 21): basic roll = 33", "Creature 1 coins",
                     "Gem count", "Gem 1 value", "Magic presence", "Magic item count",
                     "Magic item category: basic roll = 33", "Magic item subtype",
                     "Magic item power at table level 3: basic roll = 33"):
            self.assertIn(text, log)

    def test_debug_capture_does_not_change_treasure_or_random_state(self):
        for seed in range(10):
            plain_rng = random.Random(seed)
            debug_rng = random.Random(seed)
            plain = treasure(self.rules, plain_rng, 7, None)
            debug = []
            traced = treasure(self.rules, debug_rng, 7, None, debug)
            self.assertEqual(plain, traced)
            self.assertEqual(plain_rng.getstate(), debug_rng.getstate())
            self.assertTrue(debug)

    def test_markdown_omits_absent_contents_and_marks_only_empty_areas(self):
        dungeon = self.chamber()
        key = generate_encounters(dungeon, rules=self.rules)[0]
        for mask in range(8):
            with self.subTest(monster=bool(mask & 1), treasure=bool(mask & 2), trap=bool(mask & 4)):
                area = replace(
                    key.areas[0],
                    monster=MonsterEncounter("1 Goblin (level 1)", (1,)) if mask & 1 else None,
                    treasure=("Abandoned chamber cache.", "Coins: 2 cp.",
                              "Gems/jewelry: none.", "Magic: none.") if mask & 2 else ("None.",),
                    trap="Scything blade: ST 20 (DEX / BLADE) avoids it." if mask & 4 else "None.",
                    container=None, chest_trap=None, chest_locked=None,
                )
                contents = (replace(key, areas=(area,)),)
                markdown = encounter_document(dungeon, contents, 11)
                self.assertNotIn("Area", markdown)
                self.assertNotIn("TM ONLY", markdown)
                self.assertEqual("**Treasure:** None." in markdown, bool(mask & 1) and not bool(mask & 2))
                self.assertNotIn("Gems/jewelry: none", markdown)
                self.assertNotIn("Magic: none", markdown)
                self.assertNotIn("No monster", markdown)
                self.assertNotIn("### Explicit map traps", markdown)
                self.assertNotIn("### Secret and concealed doors", markdown)
                self.assertEqual("**Encounter:**" in markdown, bool(mask & 1))
                self.assertEqual("**Treasure:**" in markdown, bool(mask & 3))
                self.assertEqual("**Trap:**" in markdown, bool(mask & 4))
                self.assertEqual("Empty" in markdown, mask == 0)
                if mask == 0:
                    self.assertEqual(markdown.split("### 1\n", 1)[1].strip(), "Empty")
                    log = encounter_log(dungeon, contents, 11)
                    self.assertIn("Encounter result: No monster", log)
                    self.assertIn("Treasure result: None.", log)

    def test_random_chamber_trap_without_explicit_feature_and_label_fallback(self):
        dungeon = self.chamber()
        with patch("dungeon_encounters.basic_roll", side_effect=[0, 23]), \
                patch("dungeon_encounters.treasure", return_value=("None.",)):
            key = generate_encounters(dungeon, rules=self.rules)[0]
        self.assertNotEqual(key.areas[0].trap, "None.")
        self.assertEqual(dungeon.grid.tile(*key.areas[0].cell), " ")
        occupied = replace(dungeon, grid=DungeonMap(("#####", "#TTT#", "#TTT#", "#TTT#", "#####")))
        root = xml(occupied.grid, encounter_labels=generate_encounters(
            occupied, rules=self.rules)[0].labels)
        text = root.find("s:g[@id='encounters']/s:g/s:text", NS)
        self.assertEqual(text.attrib["y"], "0.14")

    def test_incomplete_rules_and_level_keys_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "rules.md"
            source.write_text("## Indoor Adventuring\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing section boundary"):
                EncounterRules(source)
            source.write_text("## Indoor Adventuring\n## Outdoor Adventuring\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing table"):
                EncounterRules(source)
        with self.assertRaisesRegex(ValueError, "every dungeon level"):
            encounter_document(self.chamber(), (), 11)
        with self.assertRaisesRegex(ValueError, "every dungeon level"):
            encounter_log(self.chamber(), (), 11)


class CommandLineTests(unittest.TestCase):
    def run_cli(self, script, *args):
        if script == "generate_dungeon_map.py":
            args = ("--puzzle-probability", 0) + args
        return subprocess.run(
            [sys.executable, str(HERE / script)] + [str(arg) for arg in args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        )

    def test_ascii_command_output_and_input_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "map.txt"
            source.write_text("###\n#.#\n###\n", encoding="ascii")
            result = self.run_cli("ascii_map_to_svg.py", source, "--feet-per-square", 5,
                                  "--corner-radius", 0.5, "--roughness", 0)
            self.assertEqual(result.returncode, 0, result.stderr)
            root = ET.parse(str(source.with_suffix(".svg"))).getroot()
            self.assertEqual(root.attrib["width"], "0.31in")
            for line in walls(root):
                for x, y in endpoints(line):
                    self.assertAlmostEqual(math.hypot(x - 1.5, y - 1.5), 0.5, places=10)
            result = self.run_cli("ascii_map_to_svg.py", source, "--output", source)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must not overwrite", result.stderr)
            self.assertEqual(source.read_text(), "###\n#.#\n###\n")
            source.write_text("#?\n", encoding="ascii")
            result = self.run_cli("ascii_map_to_svg.py", source)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("row 1, column 2", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_generator_roundtrip_and_distinct_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.svg"
            rerendered = Path(directory) / "rerendered.svg"
            result = self.run_cli(
                "generate_dungeon_map.py", "--output", output,
                "--seed", 42, "--traps", 3, "--secret-doors", 2, "--meandering", 0.8,
                "--corner-radius", 0.5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Seed: 42;", result.stdout)
            source = output.with_suffix(".txt")
            grid = parse_ascii(source.read_text(encoding="ascii"))
            self.assertTrue(is_connected(grid))
            result = self.run_cli(
                "ascii_map_to_svg.py", source, "--output", rerendered, "--seed", 42,
                "--corner-radius", 0.5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), rerendered.read_bytes())
            original = output.read_bytes()
            result = self.run_cli(
                "generate_dungeon_map.py", "--output", output, "--ascii-output", output
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be different", result.stderr)
            self.assertEqual(original, output.read_bytes())

    def test_generator_errors_do_not_write_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "invalid.svg"
            for args in (("--generate-encounters", "yes"), ("--generate-encounters", "true"),
                         ("--generate-encounters", "false"), ("--encounter-chance", -1),
                         ("--encounter-chance", 34), ("--encounter-chance", "1.5"),
                         ("--treasure-chest-dc", -1), ("--treasure-chest-dc", 35),
                         ("--treasure-chest-dc", "1.5"), ("--chest-trap-dc", -1),
                         ("--chest-trap-dc", 35), ("--chest-trap-dc", "nan"),
                         ("--chest-lock-dc", -1), ("--chest-lock-dc", 35),
                         ("--chest-lock-dc", "1.5"),
                         ("--width", 2), ("--roughness", "nan"),
                         ("--meandering", "nan"), ("--meandering", "1.1"),
                         ("--corner-radius", "0.6"), ("--corner-radius", "nan"),
                         ("--levels", 0), ("--levels", "1.5"), ("--stair-length", 0),
                         ("--ramp-probability", 101), ("--ramp-probability", "nan"),
                         ("--levels", 2, "--stairs-down", 0),
                         ("--levels", 2, "--roughness", "nan"),
                         ("--levels", 3, "--width", 7, "--height", 7, "--stairs-down", 20),
                         ("--width", 7, "--height", 7, "--traps", 50)):
                result = self.run_cli("generate_dungeon_map.py", "--output", output, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(output.exists())
                self.assertFalse(output.with_suffix(".txt").exists())
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_encounters_opt_in_persistence_and_path_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "stocked.svg"
            markdown = Path(directory) / "stocked-encounters.md"
            log_path = markdown.with_suffix(".log")
            result = self.run_cli("generate_dungeon_map.py", "--output", output, "--seed", 42)
            self.assertEqual(result.returncode, 0, result.stderr)
            original_svg = output.read_bytes()
            original_ascii = output.with_suffix(".txt").read_bytes()
            self.assertFalse(markdown.exists())
            self.assertFalse(log_path.exists())
            self.assertNotIn('id="encounters"', output.read_text())
            result = self.run_cli("generate_dungeon_map.py", "--output", output,
                                  "--seed", 42, "--generate-encounters")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(original_ascii, output.with_suffix(".txt").read_bytes())
            old_root = ET.fromstring(original_svg)
            new_root = ET.parse(str(output)).getroot()
            for group in ("walls", "features"):
                self.assertEqual(ET.tostring(old_root.find("s:g[@id='{}']".format(group), NS)),
                                 ET.tostring(new_root.find("s:g[@id='{}']".format(group), NS)))
            self.assertTrue(markdown.exists())
            guide = markdown.read_bytes()
            debug_log = log_path.read_bytes()
            self.assertIn(b"Monster presence roll:", debug_log)
            self.assertIn(b"Treasure chest (DC 17):", debug_log)
            self.assertIn(b"Chest lock (DC 17):", debug_log)
            self.assertNotIn(b"Monster presence roll:", guide)
            result = self.run_cli("generate_dungeon_map.py", "--output", output,
                                  "--seed", 42, "--generate-encounters")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(guide, markdown.read_bytes())
            self.assertEqual(debug_log, log_path.read_bytes())
            for collision in (markdown, log_path):
                result = self.run_cli("generate_dungeon_map.py", "--output", output,
                                      "--ascii-output", collision, "--generate-encounters")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("must be different", result.stderr)
                self.assertEqual(guide, markdown.read_bytes())
                self.assertEqual(debug_log, log_path.read_bytes())

    def test_container_cli_overrides_reach_markdown_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dungeon.svg"
            for chest_dc, trap_dc, lock_dc in ((0, 0, 0), (0, 34, 34), (34, 0, 0)):
                result = self.run_cli(
                    "generate_dungeon_map.py", "--output", output, "--seed", 42,
                    "--generate-encounters", "--treasure-chest-dc", chest_dc,
                    "--chest-trap-dc", trap_dc,
                    "--chest-lock-dc", lock_dc,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                guide = (Path(directory) / "dungeon-encounters.md").read_text(encoding="utf-8")
                log = (Path(directory) / "dungeon-encounters.log").read_text(encoding="utf-8")
                self.assertIn("Treasure chest (DC {}):".format(chest_dc), log)
                self.assertNotIn("Treasure chest (DC", guide)
                self.assertNotIn("Nearby lair", guide)
                self.assertNotIn("miles away", guide)
                self.assertNotIn("Lair cache", guide)
                self.assertNotIn("Abandoned chamber cache", guide)
                self.assertNotIn("Dragon hoard.", guide)
                self.assertEqual("**Chest trap:**" in guide, chest_dc == 0 and trap_dc == 0)
                if chest_dc == 34:
                    self.assertTrue("- Bag." in guide or "- Pack." in guide)
                    self.assertNotIn("chest.", guide)
                    self.assertNotIn("Chest trap (DC", log)
                    self.assertNotIn("Chest lock (DC", log)
                else:
                    self.assertIn("Chest trap (DC {}):".format(trap_dc), log)
                    self.assertIn("Chest lock (DC {}):".format(lock_dc), log)
                    self.assertIn("- {} chest.".format("Locked" if lock_dc == 0 else "Unlocked"), guide)

    def test_encounter_cli_keys_every_level_including_deeper_than_nine(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dungeon.svg"
            result = self.run_cli(
                "generate_dungeon_map.py", "--output", output, "--seed", 42,
                "--levels", 10, "--generate-encounters", "--encounter-chance", 0,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            guide = (Path(directory) / "dungeon-encounters.md").read_text(encoding="utf-8")
            debug_log = (Path(directory) / "dungeon-encounters.log").read_text(encoding="utf-8")
            self.assertNotIn("**Encounter:** No monster", guide)
            for index in range(1, 11):
                section = guide.split("## Level {}\n".format(index), 1)[1].split("\n## Level ", 1)[0]
                root = ET.parse(str(Path(directory) / "dungeon-level-{}.svg".format(index))).getroot()
                labels = root.findall("s:g[@id='encounters']/s:g", NS)
                self.assertGreater(len(labels), 0)
                self.assertEqual(len(re.findall(r"^### \d+$", section, re.MULTILINE)), len(labels))
                band = "1-3" if index <= 3 else "4-6" if index <= 6 else "7-9"
                log_section = debug_log.split("\nLevel {}\n".format(index), 1)[1].split("\nLevel ", 1)[0]
                self.assertIn("Encounter table: levels " + band, log_section)
                self.assertEqual(log_section.count("Monster presence roll:"), len(labels))
                self.assertEqual([label.attrib["data-area"] for label in labels],
                                 [str(number) for number in range(1, len(labels) + 1)])
                positions = [(int(label.attrib["data-row"]), int(label.attrib["data-column"]))
                             for label in labels]
                self.assertEqual(positions, sorted(positions))

    def test_multi_level_files_and_ascii_svg_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dungeon.svg"
            source = Path(directory) / "editable.txt"
            result = self.run_cli(
                "generate_dungeon_map.py", "--output", output, "--ascii-output", source,
                "--levels", 3, "--stair-length", 4, "--stairs-down", 2,
                "--ramp-probability", 100, "--seed", 42, "--traps", 2, "--player-view",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Level 3: 120 feet below the surface", result.stdout)
            self.assertFalse(output.exists())
            self.assertFalse(source.exists())
            previous = None
            for index in range(1, 4):
                text_path = Path(directory) / "editable-level-{}.txt".format(index)
                svg_path = Path(directory) / "dungeon-level-{}.svg".format(index)
                grid = parse_ascii(text_path.read_text(encoding="ascii"))
                self.assertTrue(is_connected(grid))
                counts = Counter(grid.to_ascii())
                self.assertEqual(counts["T"], 2)
                self.assertEqual(counts["R"], 8 if index < 3 else 0)
                if previous:
                    self.assertEqual(
                        {(x, y) for y, row in enumerate(previous.rows)
                         for x, tile in enumerate(row) if tile == "R"},
                        {(x, y) for y, row in enumerate(grid.rows)
                         for x, tile in enumerate(row) if tile == "I"},
                    )
                previous = grid
                rerendered = Path(directory) / "rerendered.svg"
                converted = self.run_cli(
                    "ascii_map_to_svg.py", text_path, "--output", rerendered,
                    "--seed", 42, "--player-view",
                )
                self.assertEqual(converted.returncode, 0, converted.stderr)
                self.assertEqual(svg_path.read_bytes(), rerendered.read_bytes())


if __name__ == "__main__":
    unittest.main()
