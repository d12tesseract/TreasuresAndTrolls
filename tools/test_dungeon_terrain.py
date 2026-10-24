import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import math
import random
import re
from collections import Counter
from pathlib import Path

from dungeon_encounters import generate_encounters
from dungeon_geometry import (
    DOORS, STRAIGHT, STAIR_OPPOSITES, DungeonMap, Stairway, _stair_runs, parse_ascii,
    reachable_cells, validate_map, _tile_components,
)
from dungeon_map import GenerationOptions, generate_dungeon
from dungeon_render import (
    _bounded_walk, _rough_wall_chains, _wall_curve, _wall_edges, _wall_walk, svg_document,
)


NS = {"s": "http://www.w3.org/2000/svg"}


def cubic_segments(path):
    coordinates = list(map(float, re.findall(r"-?\d+(?:\.\d*)?(?:e[+-]?\d+)?", path)))
    start = tuple(coordinates[:2])
    for index in range(2, len(coordinates), 6):
        first, second, end = [tuple(coordinates[offset:offset + 2])
                              for offset in (index, index + 2, index + 4)]
        yield start, first, second, end
        start = end


def curve_point(segment, t):
    return tuple(sum(point[axis] * weight for point, weight in zip(segment, (
        (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3,
    ))) for axis in (0, 1))


def boundary_distance(point, edges):
    distances = []
    for edge in edges:
        delta = tuple(edge.end[axis] - edge.start[axis] for axis in (0, 1))
        t = max(0, min(1, sum((point[axis] - edge.start[axis]) * delta[axis]
                             for axis in (0, 1)) / sum(value ** 2 for value in delta)))
        distances.append(math.hypot(*(point[axis] - edge.start[axis] - t * delta[axis]
                                      for axis in (0, 1))))
    return min(distances)


class TerrainContractTests(unittest.TestCase):
    def test_straight_stair_approaches_keep_the_full_width_in_every_direction(self):
        for width in (1, 2, 3, 4):
            for tile in STRAIGHT:
                with self.subTest(width=width, tile=tile):
                    horizontal = tile in "FfHhPpRr"
                    cells = tuple((x, y) for x in range(6, 6 + (3 if horizontal else width))
                                  for y in range(6, 6 + (width if horizontal else 3)))
                    stairs = Stairway(cells, tile, horizontal)
                    self.assertEqual(stairs.width, width)
                    self.assertEqual(len(stairs.entrance_cells), width)
                    self.assertEqual(len(stairs.approach_cells),
                                     width * (1 + max(1, width // 2)))
                    self.assertFalse(stairs.walls.intersection(stairs.approach_cells))
                    self.assertTrue(set(stairs.approach_cells) <= stairs.clearance)
                    opposite = stairs.landing_spans[
                        0 if stairs.entrance == stairs.landings[1] else 1
                    ]
                    self.assertTrue(set(opposite) <= stairs.walls)

    def test_generated_stairs_and_ramps_match_passage_width_and_linked_footprints(self):
        for width, levels, ramp_probability in ((1, 2, 0), (2, 1, 0), (2, 2, 0),
                                                 (2, 2, 100), (3, 2, 0)):
            with self.subTest(width=width, levels=levels, ramps=ramp_probability):
                dungeon = generate_dungeon(GenerationOptions(
                    width=40, height=30, room_size=35, density=0.2, seed=42,
                    passage_width=width, levels=levels, stairs_down=1,
                    ramps_up=1 if levels == 1 else 0, ramp_probability=ramp_probability,
                ))
                for level in dungeon.levels:
                    validate_map(level.grid)
                    for stairs in level.stairways:
                        self.assertEqual(stairs.width, width)
                        axis = 0 if stairs.horizontal else 1
                        length = max(p[axis] for p in stairs.cells) - min(
                            p[axis] for p in stairs.cells
                        ) + 1
                        self.assertEqual(length, 3 if levels > 1 else 1)
                        self.assertTrue(all(level.grid.tile(*p) in " ."
                                            for p in stairs.approach_cells))
                        self.assertTrue(all(level.grid.tile(*p) == "#"
                                            for p in stairs.walls))
                if levels > 1:
                    down = next(p for p in dungeon.stairways if p.tile in "efghopqr")
                    up = next(p for p in dungeon.levels[1].stairways
                              if p.tile == STAIR_OPPOSITES[down.tile])
                    self.assertEqual(down.cells, up.cells)

    def test_annotations_roundtrip_without_changing_terrain_or_blank_rows(self):
        text = "####\r\n# T#\r\n####\r\n\r\n1,1: 12\r\n0,0: Stone: <&> \u00e9\r\n"
        grid = parse_ascii(text)
        self.assertEqual(grid.rows, ("####", "# T#", "####"))
        self.assertEqual(grid.labels, {(1, 1): "12", (0, 0): "Stone: <&> \u00e9"})
        self.assertEqual(parse_ascii(grid.to_ascii()), grid)
        self.assertIn("\n\n1,1: 12\n0,0: Stone:", grid.to_ascii())
        self.assertEqual(parse_ascii(" \n\n").rows, (" ", "#"))

    def test_invalid_annotations_fail_explicitly(self):
        for suffix in ("0,0: ", "0,0: first\n0,0: second", "3,0: outside",
                       "-1,0: outside", "0.5,0: fractional", "0,0: a\nbad entry",
                       "0,0: a\n\n1,0: b", "0,0: bad\x00text"):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                parse_ascii("###\n\n" + suffix + "\n")
        for text in ("###\n0,0: missing blank\n", "###\n\n\n0,0: extra blank\n"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "exactly one blank"):
                parse_ascii(text)

    def test_annotations_render_on_stone_void_and_features_and_escape_text(self):
        grid = parse_ascii("####\n#TC~\n####\n\n0,0: Rock <&>\n1,1: 1\n2,1: 2\n3,1: Void\n")
        for player_view in (False, True):
            root = ET.fromstring(svg_document(grid, player_view=player_view))
            groups = root.findall("s:g[@id='encounters']/s:g", NS)
            self.assertEqual([group.attrib["data-area"] for group in groups], list(grid.labels.values()))
            self.assertEqual([group.attrib["transform"] for group in groups],
                             ["translate(0 0)", "translate(1 1)", "translate(2 1)", "translate(3 1)"])
            self.assertEqual(groups[0].find("s:text", NS).text, "Rock <&>")
            self.assertEqual(groups[1].find("s:text", NS).attrib["font-size"], "0.22")
            self.assertEqual(groups[2].find("s:text", NS).attrib["y"], "0.14")
        with self.assertRaisesRegex(ValueError, "inside the map"):
            svg_document(grid, encounter_labels={(4, 0): "outside"})

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
        for text in ("# b #", "bb\nb#", "dd\nd#"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                svg_document(parse_ascii(text))
        for tile in "DX":
            with self.assertRaises(ValueError):
                parse_ascii(tile)

    def test_door_lines_are_contiguous_and_centered_doors_follow_the_tile_axis(self):
        for tile in "dxcb":
            for horizontal in (True, False):
                rows = ("#######", "#     #", "##{}##".format(tile * 3), "#     #", "#######")
                if not horizontal:
                    rows = tuple("".join(row) for row in zip(*rows))
                grid = DungeonMap(rows)
                root = ET.fromstring(svg_document(grid))
                groups = root.findall(".//s:g[@data-tile='{}']".format(tile), NS)
                self.assertEqual(len(groups), 1)
                group = groups[0]
                if tile == "b":
                    drawing = group.find("s:g", NS)
                    self.assertEqual("rotate(90)" in drawing.attrib["transform"], not horizontal)
                    self.assertEqual(float(drawing.find("s:rect", NS).attrib["width"]), 1.7)
                else:
                    self.assertEqual("rotate(90" in group.attrib["transform"], not horizontal)
                    self.assertEqual(float(group.find("s:rect", NS).attrib["width"]), 2.7)
                player = ET.fromstring(svg_document(grid, player_view=True))
                self.assertEqual(player.find(".//s:g[@data-tile='{}']".format(tile), NS) is None,
                                 tile in "xc")
                if tile in "xc":
                    walls = player.findall(".//s:g[@id='walls']/s:line", NS)
                    last = walls[-1].attrib
                    self.assertEqual(
                        tuple(float(last[name]) for name in ("x1", "y1", "x2", "y2")),
                        (2, 2.5, 5, 2.5) if horizontal else (2.5, 2, 2.5, 5),
                    )

    def test_centered_doors_have_half_square_wall_connections_to_adjacent_terrain(self):
        for length in (2, 3, 4):
            for terrain in ("#", " ", ".", "|", "~"):
                for horizontal in (True, False):
                    row = terrain + "b" * length + terrain
                    grid = DungeonMap((row,) if horizontal else tuple(row))
                    for player_view in (False, True):
                        root = ET.fromstring(svg_document(grid, player_view=player_view))
                        groups = root.findall(".//s:g[@data-tile='b']", NS)
                        self.assertEqual(len(groups), 1)
                        connectors = groups[0].findall("s:line", NS)
                        coordinates = [
                            tuple(float(line.attrib[name]) for name in ("x1", "y1", "x2", "y2"))
                            for line in connectors
                        ]
                        self.assertEqual(coordinates, [
                            (0, 0.5, 0.5, 0.5), (length - 0.5, 0.5, length, 0.5),
                        ] if horizontal else [
                            (0.5, 0, 0.5, 0.5), (0.5, length - 0.5, 0.5, length),
                        ])
                        self.assertTrue(all(line.attrib["data-texture"] == "smooth"
                                            for line in connectors))
                        self.assertEqual(
                            float(groups[0].find("s:g/s:rect", NS).attrib["width"]),
                            length - 1.3,
                        )

    def test_door_lines_need_no_surrounding_floor_or_stone_ends(self):
        for tile in "dxc":
            for text in ("##{}##", " {} ", "{}"):
                for horizontal in (True, False):
                    rows = (text.format(tile * 3),)
                    if not horizontal:
                        rows = tuple("".join(row) for row in zip(*rows))
                    grid = DungeonMap(rows)
                    root = ET.fromstring(svg_document(grid))
                    groups = root.findall(".//s:g[@data-tile='{}']".format(tile), NS)
                    self.assertEqual(len(groups), 1)
                    group = groups[0]
                    self.assertEqual("rotate(90" in group.attrib["transform"], not horizontal)
                    self.assertEqual(float(group.find("s:rect", NS).attrib["width"]), 2.7)
                    jamb = group.findall("s:line", NS)[-1]
                    self.assertEqual(float(jamb.attrib["x2"]), 3)
                    self.assertEqual(float(jamb.attrib["y2"]), 0.5)
                    player = ET.fromstring(svg_document(grid, player_view=True))
                    self.assertEqual(len(player.findall(".//s:g[@data-tile='{}']".format(tile), NS)),
                                     1 if tile == "d" else 0)
            validate_map(parse_ascii("#{}#".format(tile)))

    def test_directional_stair_and_ramp_rectangles_have_full_width_length_and_elevation(self):
        for tile in STRAIGHT:
            with self.subTest(tile=tile):
                grid = DungeonMap((tile * 4, tile * 4))
                run = _stair_runs(grid)[(0, 0)]
                self.assertEqual(len(run.cells), 8)
                root = ET.fromstring(svg_document(grid, feet_per_pixel=5))
                groups = root.findall(".//s:g[@data-tile='{}']".format(tile), NS)
                self.assertEqual(len(groups), 1)
                group = groups[0]
                horizontal = tile in "FfHhPpRr"
                texts = [text.text for text in group.findall(".//s:text", NS)]
                self.assertEqual(texts, [] if tile in "EeFfGgHh" else
                                 ["ramp " + ("up" if tile.isupper() else "down")])
                length, width = (4, 2) if horizontal else (2, 4)
                self.assertEqual(group.attrib["data-length"], str(length))
                self.assertEqual(group.attrib["data-width"], str(width))
                self.assertEqual(float(group.attrib["data-elevation"]),
                                 length * 5 * (1 if tile.isupper() else -1))
                self.assertEqual(group.attrib["data-direction"], "up" if tile.isupper() else "down")
                facing = ("north" if tile in "EeOo" else "east" if tile in "FfPp"
                          else "south" if tile in "GgQq" else "west")
                self.assertEqual(group.attrib["data-facing"], facing)
                drawing = group.find("s:g/s:g", NS)
                transform = {
                    "north": "rotate(0)", "east": "translate(4 0) rotate(90)",
                    "south": "translate(4 2) rotate(180)", "west": "translate(0 2) rotate(270)",
                }[facing]
                self.assertEqual(drawing.attrib["transform"], transform)
                lines = drawing.findall("s:line", NS)
                self.assertEqual(len(lines), 5 * length + 3 if tile in "EeFfGgHh" else 5)
                self.assertEqual(len(group.findall("s:clipPath/s:rect", NS)), 8)
                self.assertEqual(float(lines[-3].attrib["x1"]), width / 2)
                self.assertEqual(float(lines[-3].attrib["y2"]), 0.18)
        irregular = ET.fromstring(svg_document(parse_ascii("FFF\nF##\nFFF")))
        self.assertEqual(len(irregular.findall(".//s:g[@data-tile='F']", NS)), 1)
        self.assertEqual(len(irregular.findall(".//s:clipPath/s:rect", NS)), 7)
        separate = ET.fromstring(svg_document(parse_ascii("F#F")))
        self.assertEqual(len(separate.findall(".//s:g[@data-tile='F']", NS)), 2)

    def test_partitions_form_enclosed_smooth_rooms_inside_caverns(self):
        grid = parse_ascii(".......\n.____..\n.|..|..\n.|..|..\n.L__L..\n.......")
        validate_map(grid)
        self.assertNotIn((0, 0), reachable_cells(grid, (2, 2)))
        self.assertIn((3, 3), reachable_cells(grid, (2, 2)))
        boundary = parse_ascii("#####\n#.|.#\n#_L.#\n#####")
        root = ET.fromstring(svg_document(boundary, corner_radius=0))
        walls = root.findall(".//s:g[@id='walls']/s:line", NS)
        smooth = [wall.attrib for wall in walls if wall.attrib["data-texture"] == "smooth"]
        self.assertTrue(any(wall["x1"] == "2" and wall["y1"] == "1" and wall["y2"] == "1"
                            for wall in smooth))
        self.assertTrue(any(wall["x1"] == "1" and wall["y1"] == "3" and wall["y2"] == "3"
                            for wall in smooth))
        for text in ("|", "_", "L", "#L~", "#L#\n|\\|\n#_#"):
            validate_map(parse_ascii(text))

    def test_down_stairs_taper_to_half_width_along_the_arrow_but_up_stairs_stay_uniform(self):
        for tile in "EeFfGgHh":
            for length in (1, 3, 19):
                for width in (1, 3):
                    with self.subTest(tile=tile, length=length, width=width):
                        horizontal = tile in "FfHh"
                        grid = DungeonMap((tile * (length if horizontal else width),) *
                                          (width if horizontal else length))
                        root = ET.fromstring(svg_document(grid))
                        drawing = root.find(".//s:g[@data-tile='{}']/s:g/s:g".format(tile), NS)
                        lines = drawing.findall("s:line", NS)
                        count = 5 * length
                        self.assertEqual(len(lines), count + 3)
                        treads = list(reversed(lines[:count]))
                        widths = [float(line.attrib["x2"]) - float(line.attrib["x1"])
                                  for line in treads]
                        for index, actual in enumerate(widths):
                            expected = (width - 0.3) * (
                                1 - index / (2 * (count - 1)) if tile.islower() else 1
                            )
                            self.assertAlmostEqual(actual, expected)
                            if tile.islower() and index:
                                self.assertLess(actual, widths[index - 1])
                            self.assertAlmostEqual(
                                float(treads[index].attrib["x1"]) + float(treads[index].attrib["x2"]),
                                width,
                            )
                        self.assertAlmostEqual(widths[-1] / widths[0], 0.5 if tile.islower() else 1)
                        arrow = tuple(float(lines[count].attrib[name])
                                      for name in ("x1", "y1", "x2", "y2"))
                        for actual, expected in zip(arrow, (width / 2, length - 0.18, width / 2, 0.18)):
                            self.assertAlmostEqual(actual, expected)

    def test_ramp_arrows_have_fitting_up_down_annotations_on_both_views_and_all_axes(self):
        for tile in "OoPpQqRr":
            for length in (1, 4):
                for width in (1, 3):
                    horizontal = tile in "PpRr"
                    grid = DungeonMap((tile * (length if horizontal else width),) *
                                      (width if horizontal else length))
                    for player_view in (False, True):
                        with self.subTest(tile=tile, length=length, width=width, player_view=player_view):
                            root = ET.fromstring(svg_document(grid, player_view=player_view))
                            drawing = root.find(".//s:g[@data-tile='{}']/s:g/s:g".format(tile), NS)
                            self.assertEqual(len(drawing.findall("s:line", NS)), 5)
                            annotation = drawing.find("s:g", NS)
                            text = annotation.find("s:text", NS)
                            self.assertEqual(text.text, "ramp " + ("up" if tile.isupper() else "down"))
                            size = float(text.attrib["font-size"])
                            self.assertGreater(size, 0)
                            self.assertLessEqual(size, 0.22)
                            self.assertLessEqual(size * len(text.text) * 0.6, length - 0.4 + 1e-9)
                            self.assertTrue(annotation.attrib["transform"].endswith(
                                "rotate(90)" if tile in "QqRr" else "rotate(-90)"
                            ))
                            self.assertIsNone(drawing.find("s:text", NS))
                            self.assertEqual(len(drawing.findall(".//s:text", NS)), 1)

    def test_generated_stairs_keep_directional_labels_and_opposite_linked_approaches(self):
        dungeon = generate_dungeon(GenerationOptions(
            seed=42, width=30, height=24, levels=2, stair_length=4, stairs_down=1, ramps_down=1,
        ))
        for level in dungeon.levels:
            parsed_runs = _stair_runs(level.grid)
            for run in level.stairways:
                self.assertTrue(all(level.grid.tile(*cell) == run.tile for cell in run.cells))
                self.assertEqual(parsed_runs[run.cells[0]].horizontal, run.horizontal)
                self.assertEqual(parsed_runs[run.cells[0]].entrance, run.entrance)
        for down in dungeon.levels[0].stairways:
            if not down.tile.islower():
                continue
            up = next(run for run in dungeon.levels[1].stairways if run.cells == down.cells)
            self.assertEqual(up.tile, STAIR_OPPOSITES[down.tile])
            self.assertEqual(up.entrance, down.closed_end)

    def test_ascii_converter_exports_512_square_maps_with_the_new_geometry(self):
        rows = [list("#" * 512) for _ in range(512)]
        for y in (509, 510):
            rows[y][507:511] = "FFFF"
        for y, cells in ((1, "   "), (2, "xxx"), (3, "   ")):
            rows[y][2:5] = cells
        rows[5][2:4] = "bb"
        rows[6][2] = "L"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "maximum.txt"
            source.write_text("\n".join("".join(row) for row in rows) + "\n", encoding="utf-8")
            original = source.read_bytes()
            for player_view in (False, True):
                output = source.with_name("player.svg" if player_view else "map.svg")
                command = [sys.executable, str(Path(__file__).with_name("ascii_map_to_svg.py")),
                           str(source), "--output", str(output), "--feet-per-square", "5"]
                if player_view:
                    command.append("--player-view")
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                root = ET.parse(output).getroot()
                self.assertEqual(root.attrib["viewBox"], "-0.05 -0.05 512.1 512.1")
                stairs = root.find(".//s:g[@data-tile='F']", NS)
                self.assertEqual(stairs.attrib["data-length"], "4")
                self.assertEqual(stairs.attrib["data-width"], "2")
                self.assertEqual(stairs.attrib["data-elevation"], "20")
                self.assertEqual(len(root.findall(".//s:g[@data-tile='x']", NS)),
                                 0 if player_view else 1)
                centered = root.find(".//s:g[@data-tile='b']/s:g", NS)
                self.assertEqual(centered.attrib["transform"], "translate(0.5 0.5)")
            self.assertEqual(source.read_bytes(), original)

    def test_spiral_arrows_use_three_quarter_radius_and_down_treads_taper_clockwise(self):
        for size in (2, 3, 4):
            for tile in "SsZ":
                for corner in ("NW", "NE", "SW", "SE"):
                    for center_tile in (" ", "#") if size == 3 else ("#",):
                        with self.subTest(size=size, tile=tile, corner=corner, center=center_tile):
                            rows = [list("#" * 8) for _ in range(8)]
                            run = Stairway.spiral_at(2, 2, size, tile, corner)
                            run.paint(rows)
                            if size == 3:
                                rows[3][3] = center_tile
                            grid = DungeonMap(tuple("".join(row) for row in rows))
                            root = ET.fromstring(svg_document(grid))
                            drawing = root.find(".//s:g[@data-spiral='true']/s:g", NS)
                            arrows = drawing.findall("s:path[@data-direction]", NS)
                            self.assertEqual([arrow.attrib["data-direction"] for arrow in arrows],
                                             ["up", "down"] if tile == "Z" else
                                             ["down" if tile == "s" else "up"])
                            radius = size / 2
                            for arrow in arrows:
                                coordinates = list(map(float, re.findall(
                                    r"-?\d+(?:\.\d*)?(?:e[+-]?\d+)?", arrow.attrib["d"])))
                                for value in coordinates[2:4]:
                                    self.assertAlmostEqual(value, radius * 0.75)
                                self.assertEqual(coordinates[6],
                                                 int(arrow.attrib["data-direction"] == "down"))
                            lines = drawing.findall("s:line", NS)[:-2 * len(arrows)]
                            full_width = radius - (0.5 if size == 3 else 0.12)
                            previous = None
                            for index, line in enumerate(lines):
                                x1, y1, x2, y2 = (float(line.attrib[name])
                                                  for name in ("x1", "y1", "x2", "y2"))
                                width = math.hypot(x2 - x1, y2 - y1)
                                factor = 1 - index / (2 * (len(lines) - 1)) if tile == "s" else 1
                                self.assertAlmostEqual(width, full_width * factor)
                                if previous is not None and tile == "s":
                                    self.assertLess(width, previous[0])
                                    self.assertGreater(previous[1] * (y2 - y1) -
                                                       previous[2] * (x2 - x1), 0)
                                previous = (width, x2 - x1, y2 - y1)
                            if tile == "s":
                                self.assertAlmostEqual(width, full_width / 2)
                                landing_x = sum(x + 0.5 for x, y in run.landing_cells) / len(run.landing_cells)
                                landing_y = sum(y + 0.5 for x, y in run.landing_cells) / len(run.landing_cells)
                                first_angle = math.atan2(landing_y - 2 - radius,
                                                         landing_x - 2 - radius) + math.pi / 4
                                for line, angle in ((lines[0], first_angle),
                                                    (lines[-1], first_angle + 3 * math.pi / 2)):
                                    dx = float(line.attrib["x2"]) - float(line.attrib["x1"])
                                    dy = float(line.attrib["y2"]) - float(line.attrib["y1"])
                                    self.assertAlmostEqual(dx / math.hypot(dx, dy), math.cos(angle))
                                    self.assertAlmostEqual(dy / math.hypot(dx, dy), math.sin(angle))

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
            self.assertEqual(Counter(
                tile for tile, _ in _tile_components(dungeon.grid, DOORS)
            ), {"d": 3, "x": 2, "c": 2})
            self.assertFalse(set("DX") & set(counts))
            validate_map(dungeon.grid)
            key = generate_encounters(dungeon)[0]
            self.assertEqual(Counter(item[1] for item in key.doors),
                             {"Secret": 2, "Concealed": 2})

    def test_cavern_walk_offsets_obey_half_square_and_45_degree_bounds_and_close_exactly(self):
        for closed in (False, True):
            for spacing in (0.25, math.sqrt(2) / 4):
                distances = [index * spacing for index in range(81)]
                limits = [0.5] * len(distances)
                limits[20] = limits[60] = 0.1
                for seed in range(12):
                    offsets = _bounded_walk(distances, limits, closed, random.Random(seed).random)
                    self.assertAlmostEqual(offsets[-1], offsets[0])
                    if not closed:
                        self.assertEqual(offsets[0], 0)
                    for index, offset in enumerate(offsets):
                        self.assertLessEqual(abs(offset), limits[index] + 1e-12)
                        if index:
                            self.assertLessEqual(abs(offset - offsets[index - 1]), spacing + 1e-12)
        offsets = _bounded_walk([index / 4 for index in range(41)], [0.5] * 41, False, lambda: 1)
        self.assertEqual(max(offsets), 0.5)
        self.assertEqual(offsets[-1], 0)

    def test_cavern_walk_carries_between_squares_and_curves_preserve_straight_edge_slope(self):
        for diagonal in (False, True):
            vertices = [(2 + step if diagonal else 2, 1 + step) for step in range(7)]
            tangent = (1 / math.sqrt(2), 1 / math.sqrt(2)) if diagonal else (0, 1)
            normal = (-tangent[1], tangent[0])
            for random_value in (0, 1):
                points = _wall_walk(vertices, 10, 10, 0.5, 4, 0.5, lambda: random_value)
                self.assertEqual(len(points), 25)
                self.assertEqual(points[0], vertices[0])
                self.assertEqual(points[-1], vertices[-1])
                offsets = [sum((point[axis] - vertices[0][axis]) * normal[axis]
                               for axis in (0, 1)) for point in points]
                self.assertAlmostEqual(max(map(abs, offsets)), 0.5)
                self.assertGreater(abs(offsets[8]), 0.4, "integer square boundaries must not reset the walk")
                for segment in cubic_segments(_wall_curve(points, False)):
                    previous = curve_point(segment, 0)
                    for step in range(1, 11):
                        following = curve_point(segment, step / 10)
                        delta = tuple(following[axis] - previous[axis] for axis in (0, 1))
                        forward = sum(delta[axis] * tangent[axis] for axis in (0, 1))
                        sideways = sum(delta[axis] * normal[axis] for axis in (0, 1))
                        self.assertGreaterEqual(forward, -1e-9)
                        self.assertLessEqual(abs(sideways), forward + 1e-9)
                        previous = following

    def test_cavern_turns_use_corner_bisectors_and_skip_crowded_inside_samples(self):
        vertices = [(1, 1), (2, 1), (2, 2)]
        inside = _wall_walk(vertices, 5, 5, 0.5, 4, 0.5, lambda: 1)
        outside = _wall_walk(vertices, 5, 5, 0.5, 4, 0.5, lambda: 0)
        self.assertEqual(len(inside), 7)
        self.assertEqual(len(outside), 9)
        for points, sign in ((inside, 1), (outside, -1)):
            corner = next(point for point in points if
                          abs((point[0] - 2) + (point[1] - 1)) < 1e-9 and
                          sign * (point[1] - 1) > 0)
            self.assertLessEqual(math.hypot(corner[0] - 2, corner[1] - 1), 0.5 + 1e-9)
        values = iter((0, 1, 1, 1, 0, 0, 1, 0))
        crossing = _wall_walk(vertices, 5, 5, 0.5, 4, 0.5, lambda: next(values))
        self.assertTrue(all(math.isfinite(value) for point in crossing for value in point))

    def test_cavern_paths_are_continuous_bounded_curves_with_exact_smooth_joins(self):
        maps = (
            "##########\n#........#\n#...##...#\n#........#\n##########",
            "########\n#  ....#\n#  ....#\n########",
            "#######\n###...#\n##/...#\n#.....#\n#######",
            ".#.\n#.#\n.#.",
            "#####\n#..~#\n#...#\n#####",
        )
        for text in maps:
            grid = parse_ascii(text)
            edges = _wall_edges(grid)
            rough = [edge for edge in edges if edge.rough]
            chains = _rough_wall_chains(edges)
            self.assertEqual(sum(len(chain) - 1 for chain in chains), len(rough))
            for seed in range(8):
                document = svg_document(grid, seed=seed)
                self.assertEqual(document, svg_document(grid, seed=seed))
                root = ET.fromstring(document)
                walls = root.find("s:g[@id='walls']", NS)
                self.assertTrue(all(line.attrib["data-texture"] == "smooth"
                                    for line in walls.findall("s:line", NS)))
                paths = walls.findall("s:path", NS)
                self.assertEqual(len(paths), len(chains))
                for path, chain in zip(paths, chains):
                    data = path.attrib["d"]
                    self.assertIn(" C ", data)
                    self.assertNotRegex(data, r"[LQHVA]")
                    segments = list(cubic_segments(data))
                    closed = chain[0] == chain[-1]
                    self.assertEqual(data.endswith(" Z"), closed)
                    if not closed:
                        self.assertEqual(segments[0][0], chain[0])
                        self.assertEqual(segments[-1][-1], chain[-1])
                    else:
                        self.assertEqual(segments[0][0], segments[-1][-1])
                    joins = list(zip(segments, segments[1:]))
                    if closed:
                        joins.append((segments[-1], segments[0]))
                    for first, second in joins:
                        for axis in (0, 1):
                            self.assertAlmostEqual(first[3][axis] - first[2][axis],
                                                   second[1][axis] - second[0][axis])
                    for segment in segments:
                        for step in range(9):
                            point = curve_point(segment, step / 8)
                            self.assertTrue(0 <= point[0] <= grid.width)
                            self.assertTrue(0 <= point[1] <= grid.height)
                            self.assertLessEqual(boundary_distance(point, rough), 0.5 + 1e-9)
        mixed = parse_ascii(maps[1])
        root = ET.fromstring(svg_document(mixed))
        smooth = root.findall("s:g[@id='walls']/s:line", NS)
        expected = [edge for edge in _wall_edges(mixed) if not edge.rough]
        self.assertEqual([tuple(float(line.attrib[name]) for name in ("x1", "y1", "x2", "y2"))
                          for line in smooth], [edge.start + edge.end for edge in expected])


if __name__ == "__main__":
    unittest.main()
