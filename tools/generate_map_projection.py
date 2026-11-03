#!/usr/bin/env python3
# Requires Python 3.8 or later.
"""Generate the equilateral chamfered cube net using only the Python standard library.

Run from any directory:
    python tools/generate_map_projection.py
    python tools/generate_map_projection.py --labels
    python tools/generate_map_projection.py --labels --check

Outputs default to doc/equilateral-chamfered-cube.{svg,json}, relative to this
script's repository. --output-dir selects another directory. --check validates
the geometry and checks that both existing exports are exactly reproducible.

Construction, with unit edges:
    s = 1/2, u = s + 1/sqrt(3), t = s + 2/sqrt(3).
    Eight vertices are (+/-u, +/-u, +/-u).
    Twenty-four are the signed permutations of (t, s, s).
    Squares lie on signed coordinate = t; hexagons on two signed coordinates
    summing to 2u. Their angles are A = acos(-1/3), B = (360 - A)/2.

The explicit hinge tree below is unfolded once, without layout search,
optimization, or iterative geometry fitting. All coordinates are computed from
the exact radical construction, not the rounded angles in the specification.

The net is viewed from the outside, with clockwise sectors running right to left.
Top attachments, left to right:    --HS--HS--HS
Bottom attachments, left to right: --SH--SH--SH
Here S = square, H = hexagon, - = an unattached strip edge. Bottom pairs are
reversed locally so squares attach to opposite edges of strip faces 2, 4, 6.
A literal reversal of the entire top sequence would put squares on edges
reserved for hexagons. The last bottom hexagon/strip junction wraps around the
cut ends of the strip when folded. Three hexagons meet at a common SOLID vertex,
not necessarily at one point of the paper: their angle deficit is positive.

JSON includes both the 3D solid and 2D net, ordered face boundaries, every edge,
fold hinges, and paired cut seams. Coordinates are in edge-length units, with
y up in the net; the SVG reverses y and uses 80 SVG units per edge. The SVG is
plain geometry by default: closed, unfilled face polygons with black outlines and
no vertex markers or labels. --labels adds centered, light-gray Greek sector
letters with a font size one third of a square panel's side length, with their
spelled-out names in smaller text below.
Face IDs match the JSON; vertex correspondence remains
in the JSON. JSON coordinates are rounded to 12 decimal places for reproducibility
across Python versions. Equal
cut-edge labels in the JSON are glued together, matching endpoints by their
solid_vertex IDs. No glue tabs are added.
"""

import argparse
from collections import Counter
from itertools import combinations, product
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET


TOLERANCE = 1e-9
ACUTE_ANGLE = math.degrees(math.acos(-1.0 / 3.0))
OBTUSE_ANGLE = (360.0 - ACUTE_ANGLE) / 2.0
OUTPUT_STEM = "equilateral-chamfered-cube"

# North is (+1, -1, -1); eta's opposite vertex (+1, +1, -1)
# sets the prime meridian. Equatorial labels run clockwise viewed from north.
SECTOR_LABELS = {
    "Hyz+-": "\u03b1", "Hxz--": "\u03b2", "Hxy--": "\u03b3",
    "Hyz-+": "\u03b4", "Hxz++": "\u03b5", "Hxy++": "\u03b6",
    "Hxz+-": "\u03b7", "Hyz--": "\u03b8", "Hxy+-": "\u03b9",
    "Hxy-+": "\u03ba", "Hxz-+": "\u03bb", "Hyz++": "\u03bc",
    "Sz-": "\u03bd", "Sy-": "\u03be", "Sx+": "\u03bf",
    "Sx-": "\u03c0", "Sz+": "\u03c1", "Sy+": "\u03c3",
}
SECTOR_NAMES = {
    "\u03b1": "Alpha", "\u03b2": "Beta", "\u03b3": "Gamma",
    "\u03b4": "Delta", "\u03b5": "Epsilon", "\u03b6": "Zeta",
    "\u03b7": "Eta", "\u03b8": "Theta", "\u03b9": "Iota",
    "\u03ba": "Kappa", "\u03bb": "Lambda", "\u03bc": "Mu",
    "\u03bd": "Nu", "\u03be": "Xi", "\u03bf": "Omicron",
    "\u03c0": "Pi", "\u03c1": "Rho", "\u03c3": "Sigma",
}


def require(condition, message):
    """Reject a failed geometry invariant with its diagnostic."""
    if not condition:
        raise ValueError(message)


def subtract(left, right):
    """Subtract corresponding vector coordinates."""
    return tuple(
        left_component - right_component
        for left_component, right_component in zip(left, right)
    )


def dot(left, right):
    """Compute a vector dot product in coordinate order."""
    return sum(
        left_component * right_component
        for left_component, right_component in zip(left, right)
    )


def unit(vector):
    """Normalize a nonzero vector to unit length."""
    length = math.sqrt(dot(vector, vector))
    return tuple(component / length for component in vector)


def cross(left, right):
    """Compute the three-dimensional cross product."""
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def center(points):
    """Average the coordinates of a collection of points."""
    return tuple(sum(axis) / len(points) for axis in zip(*points))


def boundary(items):
    """Iterate consecutive boundary pairs, including the closing edge."""
    return zip(items, items[1:] + items[:1])


def edge_key(first_id, second_id):
    """Return an order-independent pair of endpoint identifiers."""
    return tuple(sorted((first_id, second_id)))


def angle(previous, vertex, following):
    """Measure an interior angle in degrees, clamping rounding error."""
    cosine = dot(
        unit(subtract(previous, vertex)), unit(subtract(following, vertex))
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def build_solid_vertices():
    """Construct the radical-coordinate vertices in stable identifier order."""
    small_offset = 0.5
    corner_offset = small_offset + 1.0 / math.sqrt(3.0)
    large_offset = small_offset + 2.0 / math.sqrt(3.0)
    points = [
        tuple(coordinate_sign * corner_offset for coordinate_sign in signs)
        for signs in product((-1, 1), repeat=3)
    ]
    for axis_index in range(3):
        for signs in product((-1, 1), repeat=3):
            points.append(tuple(
                coordinate_sign * (
                    large_offset if coordinate_index == axis_index
                    else small_offset
                )
                for coordinate_index, coordinate_sign in enumerate(signs)
            ))
    vertices = {
        f"V{index + 1:02}": point for index, point in enumerate(points)
    }
    return vertices, large_offset, corner_offset


def build_solid():
    """Build ordered solid faces and their shared edges from exact vertices."""
    vertices, large_offset, corner_offset = build_solid_vertices()
    faces = {}
    for axis_count, prefix, offset in (
        (1, "S", large_offset), (2, "H", 2.0 * corner_offset)
    ):
        for axes in combinations(range(3), axis_count):
            for signs in product((-1, 1), repeat=axis_count):
                normal = tuple(
                    signs[axes.index(axis_index)] if axis_index in axes else 0
                    for axis_index in range(3)
                )
                name = prefix + "".join(
                    "xyz"[axis_index] for axis_index in axes
                )
                name += "".join(
                    "+" if coordinate_sign > 0 else "-"
                    for coordinate_sign in signs
                )
                ids = [
                    identifier for identifier, point in vertices.items()
                    if abs(dot(point, normal) - offset) < TOLERANCE
                ]
                origin = center([vertices[identifier] for identifier in ids])
                axis_x = unit(subtract(vertices[ids[0]], origin))
                axis_y = cross(unit(normal), axis_x)
                ids.sort(key=lambda identifier: math.atan2(
                    dot(subtract(vertices[identifier], origin), axis_y),
                    dot(subtract(vertices[identifier], origin), axis_x),
                ))
                faces[name] = {
                    "id": name,
                    "kind": "square" if axis_count == 1 else "hexagon",
                    "vertices": ids,
                    "normal": unit(normal),
                }
    edge_faces = {}
    for identifier, face in faces.items():
        for first_id, second_id in boundary(face["vertices"]):
            edge_faces.setdefault(
                edge_key(first_id, second_id), []
            ).append(identifier)
    edges = {
        key: {
            "id": f"E{index + 1:02}", "vertices": key, "faces": edge_faces[key]
        }
        for index, key in enumerate(sorted(edge_faces))
    }
    return vertices, faces, edges


def initialize_net(vertices, faces, strip):
    """Place the first strip face and establish its solid-to-net mapping."""
    root_three = math.sqrt(3.0)
    small_offset, corner_offset, large_offset = (
        0.5, 0.5 + 1.0 / root_three, 0.5 + 2.0 / root_three
    )
    horizontal_step, vertical_step, horizontal_span = (
        math.sqrt(2.0 / 3.0), 1.0 / root_three, 2.0 * math.sqrt(2.0) / 3.0
    )
    root_solid = [
        (large_offset, small_offset, small_offset),
        (large_offset, small_offset, -small_offset),
        (corner_offset, corner_offset, -corner_offset),
        (small_offset, large_offset, -small_offset),
        (small_offset, large_offset, small_offset),
        (corner_offset, corner_offset, corner_offset),
    ]
    root_flat = [
        (0.0, 0.5),
        (horizontal_step, 0.5 + vertical_step),
        (horizontal_step + horizontal_span, 0.5 + vertical_step - 1.0 / 3.0),
        (horizontal_step + horizontal_span, -0.5 + vertical_step - 1.0 / 3.0),
        (horizontal_span, -5.0 / 6.0),
        (0.0, -0.5),
    ]
    point_ids = {point: identifier for identifier, point in vertices.items()}
    net_vertices, net_faces, face_maps = {}, {}, {}

    # Reflect the seed face so its outward winding is preserved in the net.
    root_map = {
        point_ids[solid_point]: add_net_vertex(
            net_vertices, point_ids[solid_point],
            (-flat_point[0], flat_point[1])
        )
        for solid_point, flat_point in zip(root_solid, root_flat)
    }
    face_maps[strip[0]] = root_map
    net_faces[strip[0]] = {
        "id": strip[0], "kind": "hexagon", "placement": "strip",
        "vertices": [
            root_map[identifier] for identifier in faces[strip[0]]["vertices"]
        ],
        "parent": None, "hinge": None,
    }

    return net_vertices, net_faces, face_maps


def add_net_vertex(net_vertices, solid_id, point):
    """Append a net vertex with its ID and solid correspondence."""
    identifier = f"N{len(net_vertices) + 1:02}"
    net_vertices[identifier] = {
        "id": identifier, "position": point, "solid_vertex": solid_id
    }
    return identifier


def attach_net_face(vertices, faces, edges, net_vertices, net_faces, face_maps,
                    parent_id, child_id, placement):
    """Unfold one child across its parent, reusing hinge vertices."""
    require(child_id not in net_faces, f"Repeated face: {child_id}")
    shared = sorted(
        set(faces[parent_id]["vertices"]) & set(faces[child_id]["vertices"])
    )
    require(
        len(shared) == 2,
        f"Faces do not share an edge: {parent_id}, {child_id}"
    )
    first_id, second_id = shared
    solid_start, solid_end = vertices[first_id], vertices[second_id]
    flat_start = net_vertices[face_maps[parent_id][first_id]]["position"]
    flat_end = net_vertices[face_maps[parent_id][second_id]]["position"]
    axis_3d = unit(subtract(solid_end, solid_start))
    child_center = center([
        vertices[identifier] for identifier in faces[child_id]["vertices"]
    ])
    toward_center = subtract(child_center, solid_start)
    inward_3d = unit(tuple(
        component - dot(toward_center, axis_3d) * axis_component
        for component, axis_component in zip(toward_center, axis_3d)
    ))
    axis_2d = unit(subtract(flat_end, flat_start))
    perpendicular = (-axis_2d[1], axis_2d[0])
    parent_center = center([
        net_vertices[identifier]["position"]
        for identifier in net_faces[parent_id]["vertices"]
    ])
    side_sign = -math.copysign(
        1.0, dot(subtract(parent_center, flat_start), perpendicular)
    )
    child_map = {}
    for solid_id in faces[child_id]["vertices"]:
        if solid_id in shared:
            child_map[solid_id] = face_maps[parent_id][solid_id]
        else:
            relative = subtract(vertices[solid_id], solid_start)
            along, across = dot(relative, axis_3d), dot(relative, inward_3d)
            point = tuple(
                start_component + along * axis_component
                + side_sign * across * perpendicular_component
                for start_component, axis_component, perpendicular_component
                in zip(flat_start, axis_2d, perpendicular)
            )
            child_map[solid_id] = add_net_vertex(net_vertices, solid_id, point)
    face_maps[child_id] = child_map
    net_faces[child_id] = {
        "id": child_id, "kind": faces[child_id]["kind"],
        "placement": placement,
        "vertices": [
            child_map[identifier]
            for identifier in faces[child_id]["vertices"]
        ],
        "parent": parent_id, "hinge": edges[edge_key(*shared)]["id"],
    }


def build_net_edges(net_vertices, net_faces, edges):
    """Collect net edge incidences and pair copies of cut solid edges."""
    net_edges = {}
    for identifier, face in net_faces.items():
        for first_id, second_id in boundary(face["vertices"]):
            key = edge_key(first_id, second_id)
            if key not in net_edges:
                solid_key = edge_key(
                    net_vertices[first_id]["solid_vertex"],
                    net_vertices[second_id]["solid_vertex"]
                )
                net_edges[key] = {
                    "id": f"NE{len(net_edges) + 1:02}", "vertices": key,
                    "solid_edge": edges[solid_key]["id"], "faces": [],
                }
            net_edges[key]["faces"].append(identifier)
    copies = {}
    for edge in net_edges.values():
        edge["kind"] = "fold" if len(edge["faces"]) == 2 else "cut"
        copies.setdefault(edge["solid_edge"], []).append(edge)
    for pair in copies.values():
        for edge in pair:
            edge["mate"] = next(
                (other["id"] for other in pair if other is not edge), None
            )
    return net_edges


def build_net(vertices, faces, edges):
    """Unfold the fixed strip and attachments, then identify folds and cuts."""
    strip = ["Hxy++", "Hyz+-", "Hxz--", "Hxy--", "Hyz-+", "Hxz++"]
    attachments = [
        ("Hxy++", ["Sx+", "Hxz+-"], ["Hyz++", "Sy+"]),
        ("Hxz--", ["Sz-", "Hyz--"], ["Hxy-+", "Sx-"]),
        ("Hyz-+", ["Sy-", "Hxy+-"], ["Hxz-+", "Sz+"]),
    ]
    net_vertices, net_faces, face_maps = initialize_net(vertices, faces, strip)
    for index in range(1, len(strip)):
        attach_net_face(
            vertices, faces, edges, net_vertices, net_faces, face_maps,
            strip[index - 1], strip[index], "strip"
        )
    for parent_id, top, bottom in attachments:
        for child_id in top:
            attach_net_face(
                vertices, faces, edges, net_vertices, net_faces, face_maps,
                parent_id, child_id, "top"
            )
        for child_id in bottom:
            attach_net_face(
                vertices, faces, edges, net_vertices, net_faces, face_maps,
                parent_id, child_id, "bottom"
            )
    net_edges = build_net_edges(net_vertices, net_faces, edges)
    return net_vertices, net_faces, net_edges, list(reversed(strip))


def interiors_overlap(first, second):
    """Test convex polygon interior overlap, allowing touching boundaries."""
    # Separating-axis theorem for the convex faces; touching edges are allowed.
    for polygon in (first, second):
        for start, end in boundary(polygon):
            direction = subtract(end, start)
            axis = unit((-direction[1], direction[0]))
            left = [dot(point, axis) for point in first]
            right = [dot(point, axis) for point in second]
            if (min(max(left), max(right)) - max(min(left), min(right))
                    <= TOLERANCE):
                return False
    return True


def validate_face_angles(
    identifier, face, solid_polygon, flat_polygon, incidences,
    expected_vertex_count, max_length_error, max_angle_error,
):
    """Check angles, side lengths, planarity, and acute-vertex positions."""
    acute_indices = []
    for index, vertex_id in enumerate(face["vertices"]):
        incidences[vertex_id].append(identifier)
        expected_angle = 90.0
        if expected_vertex_count == 6:
            is_corner = int(vertex_id[1:]) <= 8
            expected_angle = ACUTE_ANGLE if is_corner else OBTUSE_ANGLE
            if is_corner:
                acute_indices.append(index)
        for polygon in (solid_polygon, flat_polygon):
            angle_degrees = angle(
                polygon[index - 1], polygon[index],
                polygon[(index + 1) % expected_vertex_count]
            )
            max_angle_error = max(
                max_angle_error, abs(angle_degrees - expected_angle)
            )
            max_length_error = max(
                max_length_error,
                abs(math.dist(polygon[index - 1], polygon[index]) - 1.0)
            )
        require(
            abs(dot(
                subtract(solid_polygon[index], solid_polygon[0]),
                face["normal"]
            )) < TOLERANCE,
            f"Nonplanar face: {identifier}"
        )
    return acute_indices, max_length_error, max_angle_error


def validate_hexagon_edges(identifier, face, faces, edges, acute_indices):
    """Require opposite acute corners and square-adjacent hexagon edges."""
    require(
        len(acute_indices) == 2 and acute_indices[1] - acute_indices[0] == 3,
        f"Acute vertices must be opposite: {identifier}"
    )
    square_edges = []
    for index, (first_id, second_id) in enumerate(boundary(face["vertices"])):
        adjacent = edges[edge_key(first_id, second_id)]["faces"]
        if any(faces[other_id]["kind"] == "square" for other_id in adjacent):
            square_edges.append(index)
            require(
                index not in acute_indices
                and (index + 1) % 6 not in acute_indices,
                f"Square at an acute vertex: {identifier}"
            )
    require(len(square_edges) == 2 and square_edges[1] - square_edges[0] == 3,
            f"Square edges must be opposite: {identifier}")


def validate_faces(vertices, faces, edges, net_vertices, net_faces):
    """Validate unfolded faces, accumulating geometry errors and incidences."""
    max_length_error, max_angle_error, max_distance_error = 0.0, 0.0, 0.0
    incidences = {identifier: [] for identifier in vertices}
    polygons = {}
    for identifier, face in faces.items():
        solid_polygon = [vertices[vertex_id] for vertex_id in face["vertices"]]
        net_face = net_faces[identifier]
        flat_polygon = [
            net_vertices[vertex_id]["position"]
            for vertex_id in net_face["vertices"]
        ]
        require(sum(
            first[0] * second[1] - second[0] * first[1]
            for first, second in boundary(flat_polygon)
        ) > 0.0, f"Net face must be viewed from outside: {identifier}")
        polygons[identifier] = flat_polygon
        require([
            net_vertices[vertex_id]["solid_vertex"]
            for vertex_id in net_face["vertices"]
        ] == face["vertices"], f"Vertex correspondence: {identifier}")
        expected_vertex_count = 6 if face["kind"] == "hexagon" else 4
        require(
            len(solid_polygon) == expected_vertex_count,
            f"Polygon size: {identifier}"
        )
        (acute_indices, max_length_error,
         max_angle_error) = validate_face_angles(
            identifier, face, solid_polygon, flat_polygon, incidences,
            expected_vertex_count, max_length_error, max_angle_error
        )
        if expected_vertex_count == 6:
            validate_hexagon_edges(
                identifier, face, faces, edges, acute_indices
            )
        for first_index, second_index in combinations(
            range(expected_vertex_count), 2
        ):
            max_distance_error = max(max_distance_error, abs(
                math.dist(
                    solid_polygon[first_index], solid_polygon[second_index]
                )
                - math.dist(
                    flat_polygon[first_index], flat_polygon[second_index]
                )
            ))
    return (
        incidences, polygons, max_length_error,
        max_angle_error, max_distance_error
    )


def validate_solid_incidences(faces, edges, incidences):
    """Check the solid's vertex face types and manifold edge incidences."""
    for vertex_id, incident_faces in incidences.items():
        expected = (
            {"hexagon": 3} if int(vertex_id[1:]) <= 8
            else {"hexagon": 2, "square": 1}
        )
        require(
            Counter(
                faces[identifier]["kind"] for identifier in incident_faces
            ) == expected,
            f"Vertex incidence: {vertex_id}"
        )
    for edge in edges.values():
        require(len(edge["faces"]) == 2, f"Nonmanifold edge: {edge['id']}")


def validate_seams(edges, net_vertices, net_edges):
    """Check fold counts and paired cut endpoints against the closed solid."""
    copies = {}
    net_edge_ids = {edge["id"]: edge for edge in net_edges.values()}
    fold_count = 0
    for edge in net_edges.values():
        copies.setdefault(edge["solid_edge"], []).append(edge)
        if edge["kind"] == "fold":
            fold_count += 1
            require(
                len(edge["faces"]) == 2 and edge["mate"] is None,
                "Invalid fold"
            )
        else:
            require(
                len(edge["faces"]) == 1 and edge["mate"] in net_edge_ids,
                "Unpaired cut"
            )
            mate = net_edge_ids[edge["mate"]]
            require(
                mate["mate"] == edge["id"]
                and mate["solid_edge"] == edge["solid_edge"],
                "Cut seam mismatch"
            )
    require(fold_count == 17, "The 18-face tree must have 17 hinges")
    for edge in edges.values():
        pair = copies[edge["id"]]
        require(len(pair) in (1, 2), "Wrong number of edge copies")
        require(
            sorted(
                identifier for copy in pair for identifier in copy["faces"]
            ) == sorted(edge["faces"]),
            "Folded edge incidence does not close"
        )
        for copy in pair:
            require(
                edge_key(*(
                    net_vertices[identifier]["solid_vertex"]
                    for identifier in copy["vertices"]
                )) == edge["vertices"],
                "Folded endpoints do not close"
            )


def validate_hinge_tree(net_faces, net_edges):
    """Ensure face insertion order forms a connected, acyclic hinge tree."""
    visited = set()
    for identifier, face in net_faces.items():
        require(
            face["parent"] in visited
            or (not visited and face["parent"] is None),
            "Disconnected or cyclic hinge tree"
        )
        if face["parent"] is not None:
            require(any(
                edge["kind"] == "fold" and edge["solid_edge"] == face["hinge"]
                and set(edge["faces"]) == {identifier, face["parent"]}
                for edge in net_edges.values()
            ), "Parent hinge missing")
        visited.add(identifier)


def validate_strip(faces, net_vertices, net_edges, strip, polygons):
    """Check strip alignment and its alternating attachment pattern."""
    centers = [center(polygons[identifier]) for identifier in strip]
    require(
        max(point[1] for point in centers) - min(point[1] for point in centers)
        < TOLERANCE,
        "Strip centers are not horizontal"
    )
    require(
        all(
            first[0] < second[0] for first, second
            in zip(centers, centers[1:])
        ),
        "Strip must be ordered left to right"
    )
    for index, identifier in enumerate(strip):
        for side in ("top", "bottom"):
            center_y = centers[index][1]
            side_edges = [
                edge for edge in net_edges.values()
                if identifier in edge["faces"]
                and abs(
                    net_vertices[edge["vertices"][0]]["position"][0]
                    - net_vertices[edge["vertices"][1]]["position"][0]
                ) > TOLERANCE
                and (center([
                    net_vertices[vertex_id]["position"]
                    for vertex_id in edge["vertices"]
                ])[1] > center_y) == (side == "top")
            ]
            side_edges.sort(key=lambda edge: center([
                net_vertices[vertex_id]["position"]
                for vertex_id in edge["vertices"]
            ])[0])
            pattern = [
                next((
                    faces[other_id]["kind"] for other_id in edge["faces"]
                    if other_id != identifier
                ), "-")
                for edge in side_edges
            ]
            expected = (
                ["hexagon", "square"] if side == "top"
                else ["square", "hexagon"]
            )
            require(pattern == (expected if index % 2 == 1 else ["-", "-"]),
                    f"Incorrect {side} attachment pattern: {identifier}")


def validate(
    vertices, faces, edges, net_vertices, net_faces, net_edges, strip,
):
    """Validate topology, unfolded geometry, seams, and strip placement."""
    require(
        (len(vertices), len(edges), len(faces)) == (32, 48, 18), "Solid counts"
    )
    require(Counter(face["kind"] for face in faces.values()) == {
        "hexagon": 12, "square": 6,
    }, "Face types")
    require(
        set(faces) == set(net_faces),
        "Every solid face must appear exactly once"
    )
    require((len(net_vertices), len(net_edges)) == (62, 79), "Net counts")
    require(
        len(vertices) - len(edges) + len(faces) == 2,
        "Solid Euler characteristic"
    )
    require(
        len(net_vertices) - len(net_edges) + len(net_faces) == 1,
        "Net Euler characteristic"
    )
    (incidences, polygons, max_length_error,
     max_angle_error, max_distance_error) = validate_faces(
        vertices, faces, edges, net_vertices, net_faces
    )
    validate_solid_incidences(faces, edges, incidences)
    require(max_length_error < TOLERANCE, "Unequal side lengths")
    require(max_angle_error < TOLERANCE, "Incorrect interior angles")
    require(
        max_distance_error < TOLERANCE, "Unfolding changed a face's geometry"
    )
    for first_id, second_id in combinations(polygons, 2):
        require(not interiors_overlap(polygons[first_id], polygons[second_id]),
                f"Overlapping faces: {first_id}, {second_id}")
    validate_seams(edges, net_vertices, net_edges)
    validate_hinge_tree(net_faces, net_edges)
    validate_strip(faces, net_vertices, net_edges, strip, polygons)
    return {
        "solid_counts": {"vertices": 32, "edges": 48, "faces": 18},
        "net_counts": {
            "vertices": 62, "edges": 79, "faces": 18,
            "hinges": 17, "cut_pairs": 31
        },
        "edge_length_tolerance": TOLERANCE,
        "angle_tolerance_degrees": TOLERANCE,
        "face_distance_tolerance": TOLERANCE,
        "overlapping_face_pairs": 0,
        "folded_seams_match": True,
    }


def serialize_json(
    vertices, faces, edges, net_vertices, net_faces, net_edges, strip,
    validation,
):
    """Serialize geometry and validation with reproducible coordinates."""
    def canonicalize(value):
        """Recursively round floats and normalize signed zero for JSON."""
        if isinstance(value, float):
            rounded = round(value, 12)
            return rounded if rounded != 0.0 else 0.0
        if isinstance(value, dict):
            return {key: canonicalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [canonicalize(item) for item in value]
        return value

    data = {
        "schema_version": 1,
        "name": "Equilateral chamfered cube",
        "edge_length": 1,
        "construction": {
            "method": "Exact radical coordinates and a fixed hinge tree; no iterative layout.",
            "s": "1/2", "u": "1/2 + 1/sqrt(3)", "t": "1/2 + 2/sqrt(3)",
            "hexagon_angles_degrees": [
                ACUTE_ANGLE, OBTUSE_ANGLE, OBTUSE_ANGLE
            ] * 2,
            "square_angle_degrees": 90,
        },
        "solid": {
            "coordinate_system": "right-handed xyz, centered at the origin",
            "vertices": [
                {"id": identifier, "position": point}
                for identifier, point in vertices.items()
            ],
            "edges": list(edges.values()), "faces": list(faces.values()),
        },
        "net": {
            "coordinate_system": "xy, x right, y up; outside view; unit edge length",
            "coordinate_decimal_places": 12,
            "strip_left_to_right": strip,
            "top_left_to_right": "--HS--HS--HS",
            "bottom_left_to_right": "--SH--SH--SH",
            "pattern_key": {"S": "square", "H": "hexagon", "-": "unattached strip edge"},
            "bottom_order_note": "Pairs reverse locally, keeping squares opposite on strip faces 2, 4, 6.",
            "assembly": "Fold dashed edges; join equal solid_edge cut labels, matching solid_vertex endpoints.",
            "vertices": list(net_vertices.values()),
            "edges": list(net_edges.values()),
            "faces": list(net_faces.values()),
        },
        "validation": validation,
    }
    return json.dumps(canonicalize(data), indent=2, allow_nan=False) + "\n"


def validate_svg(svg, polygons, include_labels=False):
    """Verify ordered, unfilled face polygons and optional sector labels."""
    root = ET.fromstring(svg)
    namespace = "{http://www.w3.org/2000/svg}"
    require(
        root.tag == namespace + "svg"
        and len(root) == (2 if include_labels else 1),
        "SVG must contain faces and only the requested labels"
    )
    group = root[0]
    require(group.tag == namespace + "g" and group.attrib == {
        "id": "faces", "fill": "none", "stroke": "black", "stroke-width": "1",
    }, "SVG faces must have unfilled black outlines")
    require(
        Counter(len(points) for points in polygons.values()) == {6: 12, 4: 6},
        "SVG must contain 12 hexagons and 6 squares"
    )
    require(
        len(group) == 18
        and [polygon.get("id") for polygon in group] == list(polygons),
        "SVG face IDs or order do not match the net"
    )
    for polygon in group:
        identifier = polygon.get("id")
        require(
            polygon.tag == namespace + "polygon" and len(polygon) == 0
            and set(polygon.attrib) == {"id", "points"},
            f"SVG face must be a polygon: {identifier}"
        )
        expected_points = " ".join(
            f"{x:.6f},{y:.6f}" for x, y in polygons[identifier]
        )
        require(
            polygon.get("points") == expected_points,
            f"SVG face boundary mismatch: {identifier}"
        )
    if include_labels:
        labels = root[1]
        require(labels.tag == namespace + "g" and labels.attrib == {
            "id": "labels", "fill": "lightgray", "font-family": "sans-serif",
            "font-size": f"{80.0 / 3.0:.6f}", "text-anchor": "middle",
            "dominant-baseline": "central",
        }, "SVG labels must be centered, light gray, and one third of a square side")
        require(len(labels) == len(polygons), "SVG must label every face once")
        for label, (identifier, points) in zip(labels, polygons.items()):
            x, y = center(points)
            require(label.tag == namespace + "text" and len(label) == 1
                    and label.attrib == {
                        "x": f"{x:.6f}", "y": f"{y:.6f}",
                        "data-face": identifier,
                    } and label.text == SECTOR_LABELS[identifier],
                    f"SVG sector label mismatch: {identifier}")
            name_element = label[0]
            require(name_element.tag == namespace + "tspan"
                    and len(name_element) == 0
                    and name_element.attrib == {
                        "x": f"{x:.6f}", "y": f"{y + 80.0 / 4.0:.6f}",
                        "font-size": f"{80.0 / 8.0:.6f}",
                    } and name_element.text == SECTOR_NAMES[
                        SECTOR_LABELS[identifier]
                    ],
                    f"SVG sector name mismatch: {identifier}")


def serialize_svg(net_vertices, net_faces, include_labels=False):
    """Render black outlines with optional light-gray sector labels."""
    scale, margin = 80.0, 55.0
    points = [vertex["position"] for vertex in net_vertices.values()]
    min_x, max_x = (
        min(point[0] for point in points), max(point[0] for point in points)
    )
    min_y, max_y = (
        min(point[1] for point in points), max(point[1] for point in points)
    )
    width = (max_x - min_x) * scale + 2 * margin
    height = (max_y - min_y) * scale + 2 * margin

    def screen(point):
        """Map a net point to SVG coordinates with downward-positive y."""
        return (
            (point[0] - min_x) * scale + margin,
            (max_y - point[1]) * scale + margin
        )

    polygons = {
        identifier: [
            screen(net_vertices[vertex_id]["position"])
            for vertex_id in face["vertices"]
        ]
        for identifier, face in net_faces.items()
    }
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.6f}" height="{height:.6f}" '
        f'viewBox="0 0 {width:.6f} {height:.6f}">',
        '  <g id="faces" fill="none" stroke="black" stroke-width="1">',
    ]
    for identifier, points in polygons.items():
        serialized_points = " ".join(f"{x:.6f},{y:.6f}" for x, y in points)
        lines.append(
            f'    <polygon id="{identifier}" points="{serialized_points}"/>'
        )
    lines.append('  </g>')
    if include_labels:
        lines.append(
            '  <g id="labels" fill="lightgray" font-family="sans-serif" '
            f'font-size="{scale / 3.0:.6f}" text-anchor="middle" '
            'dominant-baseline="central">'
        )
        for identifier, points in polygons.items():
            x, y = center(points)
            lines.append(
                f'    <text x="{x:.6f}" y="{y:.6f}" data-face="{identifier}">'
                f'{SECTOR_LABELS[identifier]}'
                f'<tspan x="{x:.6f}" y="{y + scale / 4.0:.6f}" '
                f'font-size="{scale / 8.0:.6f}">'
                f'{SECTOR_NAMES[SECTOR_LABELS[identifier]]}</tspan></text>'
            )
        lines.append('  </g>')
    lines.append('</svg>')
    svg = "\n".join(lines) + "\n"
    validate_svg(svg, polygons, include_labels)
    return svg


def main():
    """Generate validated exports, or verify their exact existing bytes."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path(__file__).resolve().parents[1] / "doc"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Validate and compare existing exports without writing."
    )
    parser.add_argument(
        "--labels", action="store_true",
        help="Label panels with light-gray Greek sector letters and names."
    )
    args = parser.parse_args()
    vertices, faces, edges = build_solid()
    net_vertices, net_faces, net_edges, strip = build_net(
        vertices, faces, edges
    )
    validation = validate(
        vertices, faces, edges, net_vertices, net_faces, net_edges, strip
    )
    outputs = {
        "json": serialize_json(
            vertices, faces, edges, net_vertices, net_faces, net_edges,
            strip, validation
        ),
        "svg": serialize_svg(net_vertices, net_faces, args.labels),
    }
    data = json.loads(outputs["json"])
    # Check the rounded, exported geometry too, not just the in-memory model.
    validate(
        {
            vertex["id"]: vertex["position"]
            for vertex in data["solid"]["vertices"]
        },
        {face["id"]: face for face in data["solid"]["faces"]},
        {
            edge_key(*edge["vertices"]): {
                **edge, "vertices": tuple(edge["vertices"])
            }
            for edge in data["solid"]["edges"]
        },
        {vertex["id"]: vertex for vertex in data["net"]["vertices"]},
        {face["id"]: face for face in data["net"]["faces"]},
        {edge_key(*edge["vertices"]): edge for edge in data["net"]["edges"]},
        data["net"]["strip_left_to_right"],
    )
    if not args.check:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    for extension, content in outputs.items():
        output = args.output_dir / f"{OUTPUT_STEM}.{extension}"
        if args.check:
            require(
                output.is_file()
                and output.read_bytes() == content.encode("utf-8"),
                f"Missing or stale export: {output}"
            )
        else:
            output.write_bytes(content.encode("utf-8"))
        print(f"{'Checked' if args.check else 'Wrote'} {output}")
    print("Validated: 18 faces, 32 solid vertices, 48 solid edges, 17 hinges, 31 cut pairs; no overlaps.")


if __name__ == "__main__":
    main()
