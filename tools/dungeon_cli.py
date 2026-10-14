"""Shared argument validation and rendering options for dungeon commands."""

import argparse
import math
from typing import Dict


def positive_number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return number


def probability(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("must be between zero and one")
    return number


def nonnegative_integer(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def add_render_arguments(parser: argparse.ArgumentParser, seed_default=0) -> None:
    parser.add_argument("--feet-per-pixel", "--feet-per-square", type=positive_number, default=10,
                        help="map feet per ASCII square (default: 10)")
    parser.add_argument("--feet-per-inch", type=positive_number, default=50,
                        help="map feet per printed SVG inch (default: 50)")
    parser.add_argument("--line-width", type=positive_number, default=0.01,
                        help="stroke width in inches (default: 0.01)")
    parser.add_argument("--seed", type=int, default=seed_default,
                        help="random seed (ASCII default: 0; generated maps: random)")
    parser.add_argument("--roughness", type=float, default=0.12,
                        help="rough-wall deviation, 0 to 0.2 squares (default: 0.12)")
    parser.add_argument("--rough-segments", type=int, default=6,
                        help="segments per rough tile edge, 2 to 32 (default: 6)")
    parser.add_argument("--corner-radius", type=float,
                        help="rough corner radius, 0 to 0.5 squares (default: automatic, up to 0.35)")
    parser.add_argument("--player-view", action="store_true",
                        help="hide traps/pits and show secret/concealed doors as walls")


def render_options(args: argparse.Namespace) -> Dict:
    return {
        name: getattr(args, name) for name in (
            "feet_per_pixel", "feet_per_inch", "line_width", "seed",
            "roughness", "rough_segments", "player_view", "corner_radius",
        )
    }
