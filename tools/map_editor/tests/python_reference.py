"""Development-only bridge for comparing the browser port with Python."""

import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dungeon_geometry import TILES, parse_ascii, validate_map
from dungeon_render import svg_document


def canonical(element):
    def number(match):
        value = float(match.group())
        return format(round(value, 8), ".8g") if math.isfinite(value) else match.group()

    return [
        element.tag.rsplit("}", 1)[-1],
        {key: re.sub(r"-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?", number, value)
         for key, value in element.attrib.items()},
        element.text or "",
        [canonical(child) for child in element],
    ]


request = json.load(sys.stdin)
results = []
for item in request:
    try:
        grid = parse_ascii(item["ascii"])
        validate_map(grid)
    except ValueError as error:
        results.append({"valid": False, "error": str(error)})
        continue
    options = item.get("options", {})
    names = {
        "feetPerSquare": "feet_per_pixel", "feetPerInch": "feet_per_inch",
        "lineWidth": "line_width", "cornerRadius": "corner_radius",
        "roughness": "roughness", "roughSegments": "rough_segments",
        "seed": "seed", "playerView": "player_view",
    }
    python_options = {names[key]: value for key, value in options.items()}
    result = {"valid": True, "ascii": grid.to_ascii(), "tiles": "".join(sorted(TILES))}
    if "svg" in item:
        result["expected"] = canonical(ET.fromstring(svg_document(grid, **python_options)))
        result["actual"] = canonical(ET.fromstring(item["svg"]))
    results.append(result)
json.dump(results, sys.stdout)
