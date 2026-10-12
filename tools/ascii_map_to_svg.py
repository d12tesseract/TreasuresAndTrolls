#!/usr/bin/env python3
"""Convert an ASCII dungeon map into editable SVG walls and feature symbols."""

import argparse
from pathlib import Path

from dungeon_map import add_render_arguments, parse_ascii, render_options, svg_document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="ASCII map text file (spaces are floor)")
    parser.add_argument("--output", type=Path, help="SVG destination (default: input stem.svg)")
    add_render_arguments(parser)
    args = parser.parse_args()
    output = args.output or args.input.with_suffix(".svg")
    if output.resolve() == args.input.resolve():
        parser.error("output must not overwrite the input map")
    try:
        grid = parse_ascii(args.input.read_text(encoding="ascii"))
        document = svg_document(grid, **render_options(args))
        output.write_text(document, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(1, "error: {}\n".format(error))


if __name__ == "__main__":
    main()
