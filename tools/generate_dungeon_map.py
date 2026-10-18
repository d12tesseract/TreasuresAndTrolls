#!/usr/bin/env python3
"""Generate a connected dungeon as editable ASCII and SVG, using a shared renderer."""

import argparse
from pathlib import Path

from dungeon_encounters import (
    encounter_document, encounter_log, generate_encounters, place_encounter_features,
)
from dungeon_puzzles import PUZZLE_COUNT, generate_adventure
from dungeon_cli import (
    add_render_arguments,
    nonnegative_integer,
    positive_number,
    probability,
    render_options,
)
from dungeon_map import GenerationOptions, generate_dungeon
from dungeon_render import svg_document


def _add_layout_arguments(parser: argparse.ArgumentParser) -> None:
    """Register output paths, level geometry, terrain, and explicit feature counts."""
    parser.add_argument("--output", type=Path, default=Path("dungeon.svg"),
                        help="SVG destination (default: dungeon.svg)")
    parser.add_argument("--ascii-output", type=Path,
                        help="ASCII destination (default: SVG stem.txt; always includes hidden features)")
    parser.add_argument("--width", type=int, default=60, help="width in squares, at least 7 (default: 60)")
    parser.add_argument("--height", type=int, default=40, help="height in squares, at least 7 (default: 40)")
    parser.add_argument("--levels", type=int, default=1,
                        help="number of linked dungeon levels (default: 1)")
    parser.add_argument("--stair-length", type=int, default=3,
                        help="multi-level stair/ramp length in squares (default: 3)")
    parser.add_argument("--ramp-probability", type=float, default=0,
                        help="percentage chance each multi-level down stairway is a ramp, 0-100 (default: 0)")
    parser.add_argument("--room-size", type=positive_number, default=35,
                        help="target average room floor area in squares (default: 35)")
    parser.add_argument("--corridor-length", type=positive_number, default=8,
                        help="soft passage-length limit; exceed only to connect rooms/components (default: 8)")
    parser.add_argument("--meandering", type=probability, default=0.6,
                        help="natural passage winding strength, 0 direct, 1 strongest bends (default: 0.6)")
    parser.add_argument("--density", type=probability, default=0.3,
                        help="room-area target inside the two-square border, greater than 0 and at most 0.4 (default: 0.3)")
    parser.add_argument("--rough-probability", type=probability, default=0.4,
                        help="probability of a rough cavern rather than a worked room (default: 0.4)")
    parser.add_argument("--door-probability", type=probability, default=0.45,
                        help="normal door probability at eligible entrances (default: 0.45)")
    parser.add_argument("--secret-door-probability", type=probability, default=0.1,
                        help="secret door probability at eligible entrances (default: 0.1)")
    parser.add_argument("--concealed-door-probability", type=probability, default=0.05,
                        help="concealed door probability at eligible entrances (default: 0.05)")
    for name in ("doors", "secret-doors", "concealed-doors"):
        parser.add_argument("--" + name, type=nonnegative_integer,
                            help="exact {} count; overrides its probability".format(name.replace("-", " ")))
    parser.add_argument("--stairs-down", type=nonnegative_integer,
                        help="down passages per connection (default: 0 for one level, "
                             "random 1-3 for multiple levels; may become ramps)")
    for name in ("traps", "pits", "stairs-up", "ramps-down", "ramps-up"):
        parser.add_argument("--" + name, type=nonnegative_integer, default=0,
                            help="exact {} count (default: 0)".format(name.replace("-", " ")))
    parser.add_argument("--chamfer-probability", type=probability, default=0,
                        help="worked-corner chamfer probability; natural corners always chamfer (default: 0)")


def _add_encounter_arguments(parser: argparse.ArgumentParser) -> None:
    """Register puzzle placement, encounter stocking, and treasure thresholds."""
    parser.add_argument("--generate-encounters", action="store_true",
                        help="write encounters even when puzzles are disabled (puzzles imply encounters)")
    parser.add_argument("--puzzle-probability", type=probability, default=0.35,
                        help="independent probability for each puzzle slot per level; 0 disables (default: 0.35)")
    parser.add_argument("--max-puzzles-per-level", type=nonnegative_integer, default=2,
                        help="puzzle slots per level, 0-{}; each rolls independently (default: 2)".format(PUZZLE_COUNT))
    parser.add_argument("--encounter-chance", type=int, default=11,
                        help="minimum basic roll for a monster, 0-33 inclusive (default: 11)")
    parser.add_argument("--treasure-chest-dc", type=int, default=17,
                        help="generation DC for a chest rather than bag/pack, 0-34 (default: 17)")
    parser.add_argument("--chest-trap-dc", type=int, default=19,
                        help="generation DC for trapping a treasure chest, 0-34 (default: 19)")
    parser.add_argument("--chest-lock-dc", type=int, default=17,
                        help="generation DC for locking a treasure chest, 0-34 (default: 17)")


def _parse_arguments():
    """Parse command options and reject invalid thresholds or output collisions."""
    parser = argparse.ArgumentParser(description=__doc__)
    _add_layout_arguments(parser)
    _add_encounter_arguments(parser)
    add_render_arguments(parser, seed_default=None)
    args = parser.parse_args()
    if args.max_puzzles_per_level > PUZZLE_COUNT:
        parser.error("--max-puzzles-per-level must be from 0 through {}".format(PUZZLE_COUNT))
    for name, maximum in (("encounter_chance", 33), ("treasure_chest_dc", 34),
                          ("chest_trap_dc", 34), ("chest_lock_dc", 34)):
        if not 0 <= getattr(args, name) <= maximum:
            parser.error("--{} must be an integer from 0 through {}".format(name.replace("_", "-"), maximum))
    ascii_output = args.ascii_output or args.output.with_suffix(".txt")
    if ascii_output.resolve() == args.output.resolve():
        parser.error("ASCII and SVG output paths must be different")
    return parser, args, ascii_output


def _generate_from_arguments(args):
    """Build generation options and generate either an adventure or bare maps."""
    options = GenerationOptions(**{
        name: getattr(args, name) for name in GenerationOptions.__dataclass_fields__
    })
    encounter_options = {
        name: getattr(args, name) for name in (
            "encounter_chance", "treasure_chest_dc", "chest_trap_dc", "chest_lock_dc",
        )
    }
    encounters = None
    if args.puzzle_probability > 0 and args.max_puzzles_per_level > 0:
        result, encounters = generate_adventure(
            options, puzzle_probability=args.puzzle_probability,
            max_puzzles_per_level=args.max_puzzles_per_level,
            **encounter_options,
        )
    else:
        result = generate_dungeon(options)
        if args.generate_encounters:
            result, encounters = place_encounter_features(
                result, generate_encounters(result, **encounter_options),
            )
    return options, result, encounters, encounter_options


def _map_destinations(args, options, result, ascii_output):
    """Resolve each level's ASCII and SVG paths, suffixing multi-level outputs."""
    destinations = []
    for index, level in enumerate(result.levels, 1):
        text_path, svg_path = ascii_output, args.output
        if options.levels > 1:
            text_path, svg_path = (
                path.with_name("{}-level-{}{}".format(path.stem, index, path.suffix))
                for path in (text_path, svg_path)
            )
        destinations.append((level, text_path, svg_path))
    return destinations


def _prepare_outputs(args, options, result, encounters, encounter_options, ascii_output):
    """Prepare all documents and validate distinct paths before writing any file."""
    rendering = render_options(args)
    rendering["seed"] = result.seed
    destinations = _map_destinations(args, options, result, ascii_output)
    paths = [path.resolve() for _, text_path, svg_path in destinations
             for path in (text_path, svg_path)]
    encounter_files = []
    if encounters is not None:
        encounter_path = args.output.with_name(args.output.stem + "-encounters.md")
        log_path = encounter_path.with_suffix(".log")
        paths.extend((encounter_path.resolve(), log_path.resolve()))
        encounter_files = [
            (encounter_path, encounter_document(result, encounters, args.encounter_chance)),
            (log_path, encounter_log(result, encounters, args.encounter_chance)),
        ]
    if len(paths) != len(set(paths)):
        raise ValueError("all ASCII, SVG, encounter and log output paths must be different")
    documents = [
        svg_document(level.grid, encounter_labels=encounters[index].labels if encounters else None,
                     trapped_chests=encounters[index].trapped_chests if encounters else None,
                     **rendering)
        for index, (level, _, _) in enumerate(destinations)
    ]
    return destinations, documents, encounter_files


def _save_outputs(destinations, documents, encounter_files):
    """Write the prevalidated ASCII, SVG, encounter-key, and debug-log documents."""
    for (level, text_path, svg_path), document in zip(destinations, documents):
        text_path.write_text(level.grid.to_ascii(), encoding="ascii")
        svg_path.write_text(document, encoding="utf-8")
    for path, document in encounter_files:
        path.write_text(document, encoding="utf-8")


def _report_outputs(options, result, destinations, encounter_files):
    """Print level statistics, layout notes, and the generated artifact paths."""
    for index, (level, text_path, svg_path) in enumerate(destinations, 1):
        if options.levels > 1:
            print("Level {}: {} feet below the surface".format(index, level.depth_feet))
        print("Seed: {}; rooms: {}; open area: {:.1%}; room area: {:.1%} (room target: {:.1%})".format(
            result.seed, len(level.room_areas), level.density,
            sum(level.room_areas) / ((level.grid.width - 4) * (level.grid.height - 4)), options.density
        ))
        for note in level.layout_notes:
            print(note)
        print("ASCII: {}\nSVG: {}".format(text_path, svg_path))
    if encounter_files:
        print("Encounters (TM only): {}".format(encounter_files[0][0]))
        print("Encounter debug log (TM only): {}".format(encounter_files[1][0]))


def main() -> None:
    """Generate command-line dungeon artifacts and report actionable input errors."""
    parser, args, ascii_output = _parse_arguments()
    try:
        options, result, encounters, encounter_options = _generate_from_arguments(args)
        destinations, documents, encounter_files = _prepare_outputs(
            args, options, result, encounters, encounter_options, ascii_output,
        )
        _save_outputs(destinations, documents, encounter_files)
    except (OSError, ValueError) as error:
        parser.exit(1, "error: {}\n".format(error))
    _report_outputs(options, result, destinations, encounter_files)


if __name__ == "__main__":
    main()
