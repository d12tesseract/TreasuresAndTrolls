"""Shared argument validation and rendering options for dungeon commands."""

import argparse
import math
from typing import Dict


def positive_number(value: str) -> float:
    """Parse a finite, strictly positive command-line number."""
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return number


def probability(value: str) -> float:
    """Parse a finite probability in the inclusive range zero through one."""
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("must be between zero and one")
    return number


def nonnegative_integer(value: str) -> int:
    """Parse a command-line integer that is zero or greater."""
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def add_render_arguments(parser: argparse.ArgumentParser, seed_default=0) -> None:
    """Register the scale, wall appearance, seed, and player-view options."""
    parser.add_argument("--feet-per-pixel", "--feet-per-square", type=positive_number, default=10,
                        help="map feet per ASCII square (default: 10)")
    parser.add_argument("--feet-per-inch", type=positive_number, default=50,
                        help="map feet per printed SVG inch (default: 50)")
    parser.add_argument("--line-width", type=positive_number, default=0.01,
                        help="stroke width in inches (default: 0.01)")
    parser.add_argument("--seed", type=int, default=seed_default,
                        help="random seed (ASCII default: 0; generated maps: random)")
    parser.add_argument("--roughness", type=float, default=0.5,
                        help="cavern-wall walk bound, 0 to 0.5 squares (default: 0.5)")
    parser.add_argument("--rough-segments", type=int, default=4,
                        help="walk intervals per cavern edge, 2 to 32 (default: 4)")
    parser.add_argument("--corner-radius", type=float,
                        help="corner-bisector walk bound, 0 to 0.5 squares (default: roughness)")
    parser.add_argument("--player-view", action="store_true",
                        help="hide traps/pits and show secret/concealed doors as walls")


def render_options(args: argparse.Namespace) -> Dict:
    """Select the shared SVG renderer's keyword arguments from parsed options."""
    return {
        name: getattr(args, name) for name in (
            "feet_per_pixel", "feet_per_inch", "line_width", "seed",
            "roughness", "rough_segments", "player_view", "corner_radius",
        )
    }
