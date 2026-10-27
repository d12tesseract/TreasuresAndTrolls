import math
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import generate_map_projection as projection


NS = {"s": "http://www.w3.org/2000/svg"}
HERE = Path(__file__).resolve().parent


class MapProjectionLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vertices, cls.faces, cls.edges = projection.BuildSolid()
        cls.net_vertices, cls.net_faces, cls.net_edges, cls.strip = projection.BuildNet(
            cls.vertices, cls.faces, cls.edges
        )
        cls.sectors = {
            label: face for face, label in projection.g_SectorLabels.items()
        }

    def test_outside_view_orders_equatorial_sectors_right_to_left(self):
        labeled = ET.fromstring(projection.SerializeSvg(
            self.net_vertices, self.net_faces, True
        ))
        labels = labeled.find("s:g[@id='labels']", NS)
        equator = sorted(
            (label for label in labels
             if self.net_faces[label.get("data-face")]["placement"] == "strip"),
            key=lambda label: float(label.get("x")),
        )
        self.assertEqual(
            [label.text for label in equator],
            list("\u03b5\u03b4\u03b3\u03b2\u03b1\u03b6"),
        )
        self.assertEqual([label.get("data-face") for label in equator], self.strip)

    def test_net_preserves_outward_face_winding(self):
        for face, net_face in self.net_faces.items():
            with self.subTest(face=face):
                points = [self.net_vertices[vertex]["position"]
                          for vertex in net_face["vertices"]]
                area = sum(first[0] * second[1] - second[0] * first[1]
                           for first, second in projection.Boundary(points))
                self.assertGreater(area, 0)

    def test_hexagon_order_and_poles(self):
        north = (1, -1, -1)
        equator = [self.sectors[chr(code)] for code in range(0x3B1, 0x3B7)]
        for first, second in projection.Boundary(equator):
            self.assertAlmostEqual(projection.Dot(self.faces[first]["normal"], north), 0)
            self.assertLess(projection.Dot(projection.Cross(
                self.faces[first]["normal"], self.faces[second]["normal"]
            ), north), 0)
        for polar, neighbors in (
            ("\u03b7", "\u03b6\u03b1"), ("\u03b8", "\u03b2\u03b3"),
            ("\u03b9", "\u03b4\u03b5"), ("\u03ba", "\u03b1\u03b2"),
            ("\u03bb", "\u03b3\u03b4"), ("\u03bc", "\u03b5\u03b6"),
        ):
            for neighbor in neighbors:
                self.assertEqual(len(set(self.faces[self.sectors[polar]]["vertices"])
                                     & set(self.faces[self.sectors[neighbor]]["vertices"])), 2)
        for labels, direction in (("\u03b7\u03b8\u03b9", north),
                                  ("\u03ba\u03bb\u03bc", (-1, 1, 1))):
            common = set.intersection(*(
                set(self.faces[self.sectors[label]]["vertices"]) for label in labels
            ))
            self.assertEqual(len(common), 1)
            for actual, expected in zip(projection.Unit(self.vertices[common.pop()]),
                                        projection.Unit(direction)):
                self.assertAlmostEqual(actual, expected)

    def test_square_sectors_have_requested_hexagon_neighbors(self):
        self.assertEqual(set(projection.g_SectorLabels), set(self.faces))
        for square, neighbors in (
            ("\u03bd", "\u03b7\u03b8\u03b1\u03b2"),
            ("\u03be", "\u03b8\u03b9\u03b3\u03b4"),
            ("\u03bf", "\u03b9\u03b7\u03b5\u03b6"),
            ("\u03c0", "\u03ba\u03bb\u03b2\u03b3"),
            ("\u03c1", "\u03bb\u03bc\u03b4\u03b5"),
            ("\u03c3", "\u03bc\u03ba\u03b6\u03b1"),
        ):
            face = self.sectors[square]
            self.assertEqual(self.faces[face]["kind"], "square")
            adjacent = {
                other for edge in self.edges.values() if face in edge["faces"]
                for other in edge["faces"] if other != face
            }
            self.assertEqual(adjacent, {self.sectors[label] for label in neighbors})

    def test_labels_are_optional_centered_and_scaled_to_square_side(self):
        plain = ET.fromstring(projection.SerializeSvg(self.net_vertices, self.net_faces))
        labeled = ET.fromstring(projection.SerializeSvg(
            self.net_vertices, self.net_faces, True
        ))
        self.assertIsNone(plain.find("s:g[@id='labels']", NS))
        plain[0].tail = labeled[0].tail = None
        self.assertEqual(ET.tostring(plain[0]), ET.tostring(labeled[0]))
        group = labeled.find("s:g[@id='labels']", NS)
        self.assertEqual(group.get("fill"), "lightgray")
        self.assertEqual(group.get("text-anchor"), "middle")
        self.assertEqual(group.get("dominant-baseline"), "central")
        self.assertEqual(len(group), 18)
        self.assertEqual({text.text for text in group}, set(self.sectors))
        polygons = {polygon.get("id"): [
            tuple(map(float, point.split(","))) for point in polygon.get("points").split()
        ] for polygon in labeled[0]}
        square = polygons[self.sectors["\u03bd"]]
        self.assertAlmostEqual(float(group.get("font-size")),
                               math.dist(square[0], square[1]) / 3, places=5)
        for text in group:
            face = text.get("data-face")
            self.assertEqual(text.text, projection.g_SectorLabels[face])
            center = projection.Center(polygons[face])
            self.assertAlmostEqual(float(text.get("x")), center[0], places=5)
            self.assertAlmostEqual(float(text.get("y")), center[1], places=5)

    def test_cli_generates_and_checks_both_label_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [
                sys.executable, str(HERE / "generate_map_projection.py"),
                "--output-dir", directory,
            ]
            json_path = Path(directory) / (projection.g_szStem + ".json")
            original_json = None
            for options in ([], ["--labels"]):
                for check in ([], ["--check"]):
                    result = subprocess.run(
                        command + options + check, capture_output=True, text=True
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                if original_json is None:
                    original_json = json_path.read_bytes()
                else:
                    self.assertEqual(json_path.read_bytes(), original_json)
            result = subprocess.run(command + ["--check"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing or stale export", result.stderr)

    def test_sector_names_are_spelled_out_smaller_and_below_letters(self):
        labeled = ET.fromstring(projection.SerializeSvg(
            self.net_vertices, self.net_faces, True
        ))
        group = labeled.find("s:g[@id='labels']", NS)
        expected = dict(zip(
            "\u03b1\u03b2\u03b3\u03b4\u03b5\u03b6\u03b7\u03b8\u03b9"
            "\u03ba\u03bb\u03bc\u03bd\u03be\u03bf\u03c0\u03c1\u03c3",
            ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta",
             "Eta", "Theta", "Iota", "Kappa", "Lambda", "Mu",
             "Nu", "Xi", "Omicron", "Pi", "Rho", "Sigma"),
        ))
        for label in group:
            with self.subTest(sector=label.text):
                names = label.findall("s:tspan", NS)
                self.assertEqual(len(names), 1)
                name = names[0]
                self.assertEqual(name.text, expected[label.text])
                self.assertEqual(name.get("x"), label.get("x"))
                self.assertGreater(float(name.get("y")), float(label.get("y")))
                self.assertGreater(float(name.get("font-size")), 0)
                self.assertLess(float(name.get("font-size")),
                                float(group.get("font-size")))


if __name__ == "__main__":
    unittest.main()
