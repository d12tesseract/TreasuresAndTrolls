#!/usr/bin/env python3
"""Convert white bitmap regions into individually editable SVG wall lines.

Requires Pillow: python -m pip install Pillow

Example:
    python pixelmap_bmp_to_svg.py map.bmp --output map.svg
"""

import argparse
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image

WHITE = (255, 255, 255)
RED = (255, 0, 0)
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def svg_document(
    image: Image.Image,
    feet_per_pixel: float = 10,
    feet_per_inch: float = 50,
    line_width: float = 0.01,
) -> str:
    """Outline white pixels, excluding shared white/red and white/white edges.

    Other colors are non-empty space. Image borders are outlined. Coordinates
    are in pixel units, with a half-stroke margin to prevent border clipping.
    """
    for name, value in (
        ("feet_per_pixel", feet_per_pixel),
        ("feet_per_inch", feet_per_inch),
        ("line_width", line_width),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and greater than zero")

    inches_per_pixel = feet_per_pixel / feet_per_inch
    if not math.isfinite(inches_per_pixel) or inches_per_pixel <= 0:
        raise ValueError("map scale is outside the supported numeric range")
    stroke = line_width / inches_per_pixel
    width, height = image.size
    physical_width = width * inches_per_pixel + line_width
    physical_height = height * inches_per_pixel + line_width
    if not all(
        math.isfinite(value) and value > 0
        for value in (stroke, physical_width, physical_height)
    ):
        raise ValueError("SVG dimensions are outside the supported numeric range")

    root = ET.Element(
        "svg",
        {
            "xmlns": SVG_NAMESPACE,
            "width": f"{physical_width:.12g}in",
            "height": f"{physical_height:.12g}in",
            "viewBox": (
                f"{-stroke / 2:.12g} {-stroke / 2:.12g} "
                f"{width + stroke:.12g} {height + stroke:.12g}"
            ),
        },
    )
    rgb = image.convert("RGB")
    pixels = rgb.load()
    for y in range(height):
        for x in range(width):
            if pixels[x, y] != WHITE:
                continue
            edges = (
                (x, y - 1, x, y, x + 1, y),
                (x, y + 1, x, y + 1, x + 1, y + 1),
                (x - 1, y, x, y, x, y + 1),
                (x + 1, y, x + 1, y, x + 1, y + 1),
            )
            for neighbor_x, neighbor_y, x1, y1, x2, y2 in edges:
                if (
                    0 <= neighbor_x < width
                    and 0 <= neighbor_y < height
                    and pixels[neighbor_x, neighbor_y] in (WHITE, RED)
                ):
                    continue
                ET.SubElement(
                    root,
                    "line",
                    {
                        "x1": str(x1),
                        "y1": str(y1),
                        "x2": str(x2),
                        "y2": str(y2),
                        "stroke": "black",
                        "stroke-width": f"{stroke:.12g}",
                        "stroke-linecap": "butt",
                    },
                )

    root.text = "\n  " if len(root) else "\n"
    for line in root:
        line.tail = "\n  "
    if len(root):
        root[-1].tail = "\n"
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    ) + "\n"


def positive_number(value: str) -> float:
    """Parse a finite, positive numeric command-line argument."""
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite value greater than zero")
    return number


def main() -> None:
    """Read a BMP and write an SVG at the requested physical scale."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="input bitmap (.bmp)")
    parser.add_argument(
        "--output", type=Path, help="output SVG (default: input name with .svg)"
    )
    parser.add_argument(
        "--feet-per-pixel", type=positive_number, default=10,
        help="map feet per bitmap pixel (default: 10)",
    )
    parser.add_argument(
        "--feet-per-inch", type=positive_number, default=50,
        help="map feet per printed SVG inch (default: 50)",
    )
    parser.add_argument(
        "--line-width", type=positive_number, default=0.01,
        help="stroke width in inches (default: 0.01)",
    )
    args = parser.parse_args()
    output = args.output or args.input.with_suffix(".svg")
    if output.resolve() == args.input.resolve():
        parser.error("output must not overwrite the input bitmap")

    try:
        with Image.open(args.input) as image:
            if image.format != "BMP":
                raise ValueError("input must be a BMP image")
            document = svg_document(
                image, args.feet_per_pixel, args.feet_per_inch, args.line_width
            )
        output.write_text(document, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
