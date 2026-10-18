# ASCII and procedural dungeon maps

This document describes the Python modules in the repository root. They use
Python 3.7+ and the standard library. The commands in `tools` have their own
[implementation documentation](tools/generate_dungeon_map.md).

```powershell
python ascii_map_to_svg.py map.txt --output map.svg
python generate_dungeon_map.py --width 60 --height 40 --seed 42 --puzzle-probability 0 --output dungeon.svg
```

The converter reads ASCII and writes SVG. The generator writes both formats.
Puzzles are enabled by default and imply encounter stocking. Use
`--puzzle-probability 0` or `--max-puzzles-per-level 0` to disable puzzles;
`--generate-encounters` enables stocking without puzzles.

## Module organization

| Module | Responsibility |
| --- | --- |
| `dungeon_geometry.py` | ASCII model, validation, connectivity, routing, terrain inference, and stair footprints |
| `dungeon_passages.py` | Sixteen-heading natural passage routing and floor footprints |
| `dungeon_render.py` | Wall geometry, feature symbols, encounter labels, and SVG serialization |
| `dungeon_map.py` | Room placement, passage networks, decoration, stairs, and linked levels |
| `dungeon_encounters.py` | Rulebook tables, encounter stocking, treasure, numbering, and TM documents |
| `dungeon_puzzles.py` | Catalog loading, puzzle placement, prerequisites, rewards, and runtime progression validation |
| `dungeon_games.py` | Strategy-game parsing and validation |
| `dungeon_cli.py` | Shared argument validators and rendering options |
| `generate_dungeon_map.py` | Generation arguments, output preparation, file writing, and reporting |
| `ascii_map_to_svg.py` | ASCII input and SVG output |

Keep `dungeon_puzzles.md` beside `dungeon_puzzles.py`: the module loads that
catalog at runtime. `EncounterRules` reads `TreasuresAndTrollsBasicMD.md`.
Its default `RULES_PATH` is the parent of the module's directory followed by
that filename. For these root modules, that points **one directory above the
repository**, not at the rulebook in the repository root. Python callers can
pass an explicit `EncounterRules` instance, as shown below. The command-line
stocking pipeline uses the default path.

## ASCII format

One character represents one square. Literal spaces are smooth floor,
including leading and trailing spaces; tabs are invalid. Short rows are
padded on the right with `#`. LF and CRLF are accepted, and a final newline
does not add a row. Outside the map is solid stone.

| Character | Meaning |
| --- | --- |
| `#` | Solid stone |
| `~` | Void, open for connectivity but without floor or boundary-wall drawing |
| space / `.` | Smooth worked floor / rough cavern floor |
| `\` / `/` | Diagonal walls dividing a square into triangles |
| `\|` / `_` / `L` | Floor with a left / bottom / both partition walls |
| `d` / `x` / `c` | Normal / secret / concealed door |
| `bb` | One normal-width door centered on the shared edge of two adjacent squares |
| `l` / `m` / `n` | Floor with a left / bottom / both edge doors |
| `T` | Trap, including covered pits |
| `C` | Chest |
| `E` / `e` | Straight stairs up / down |
| `R` / `r` | Ramp up / down |
| `S` / `s` / `Z` | Spiral stairs up / down / both |

For `\`, the neighbor pairs are north+east and south+west; for `/`, they
are north+west and south+east. Each pair must be two open neighbors
(spaces, periods, or voids) or two stone neighbors. At least one triangle
must be open. When both are open, the wall still separates them: movement
cannot cross it. Diagonal neighbors cannot be feature tiles.

`d`, `x`, and `c` require opposite floor/trap/chest neighbors and `#` on both
perpendicular sides. `|` and `L` require literal space on the left; `_`
and `L` require literal space below. The same respective adjacency rules
apply to `l`, `m`, and `n`, whose doors remain passable. Each `b` must have
exactly one cardinal `b` neighbor. An isolated `bb` pair draws a single
normal-width door, half in each square; `d` is centered within one square.

Straight runs of the same stair/ramp letter render as one full-length
symbol. Bent or branching clusters render individual symbols. Spiral
footprints are square, size 2, 3, or 4, with a literal-space landing in any
corner. The landing is one square for sizes 2 and 3 and 2x2 for size 4.
A 3x3 spiral's center must be literal space or `#`.

Authored maps are validated, not repaired. Generation calls
`clear_invalid_diagonals` after carving/decorating connections, converting
invalid diagonals to literal-space floor. Connectivity respects partitions,
the separate diagonal triangles, and explicitly blocked cells. A reachability
search starting on a two-sided diagonal begins in its north-facing triangle.

## Rendering and symbols

Smooth walls are straight. Rough walls have seeded edge jitter and rounded
convex and concave corners. Corner radius and jitter can be set independently.
Feature groups inherit rough terrain only when they border rough floor and
no smooth floor. Diagonals infer terrain from their open neighbors.

SVG output has transparent backgrounds, black wall lines, and editable
feature groups. Walls and features use separate `walls` and `features`
groups; numbered encounter labels use `encounters`. Void squares clip wall
and feature drawing, and edges adjoining void are not outlined.

Doors use rectangles; secret and concealed doors have large uppercase `S`/`C`
labels independent of their ASCII keys. Traps use an X and `T`; chests use
a lidded-box symbol. Trapped chests also show a `T` on generated TM maps.
Straight stairs use treads, ramps use tapering sides, and both
have arrows and tile labels. Runs determine orientation; single squares
infer it from surrounding passages. Spiral symbols show their direction.

| Rendering option | Default | Meaning |
| --- | --- | --- |
| `--feet-per-pixel` / `--feet-per-square` | `10` | Map feet per square |
| `--feet-per-inch` | `50` | Map feet per printed inch |
| `--line-width` | `0.01` | Printed stroke width in inches |
| `--seed` | Converter: `0`; generator: random | Seed for rendering and generation |
| `--roughness` | `0.12` | Wall deviation, `0` through `0.2` squares |
| `--rough-segments` | `6` | Segments per rough edge, `2` through `32` |
| `--corner-radius` | Automatic | Radius, `0` through `0.5` squares |
| `--player-view` | Off | Hide trap/chest markers and draw secret/concealed doors as walls |

Automatic corner radius is three times roughness, capped at 0.35 squares.
An explicit radius of zero disables rounding, not jitter; positive radius
with zero roughness gives clean rounded corners. Scale values must be finite
and positive. Printed width/height is the square count times
feet-per-square / feet-per-inch, plus one stroke width.

Player view changes only SVG visibility. ASCII, encounter keys, and debug
logs remain **TM-only**. Encounter numbers remain visible in player view.

## Procedural generation

### Rooms and passage networks

`GenerationOptions` controls the base layout. All rooms are placed before
passages. Worked rooms are rectangles; cavern rooms grow connected, irregular
footprints around multiple offset lobes. Room area is sampled around `room_size`,
with varied aspect ratio and dimensions of at least three squares.

Room positions are sampled inside a two-square border. Placement rejects
reserved inherited-stair geometry and the three-square buffer around placed
rooms. The room budget is
`(width - 4) * (height - 4) * density`. Placement stops when that budget is
met or after 80 consecutive unsuccessful room attempts; each sampled shape
gets up to 24 position attempts. The budget is a target, not an exact area.

In mixed terrain, a candidate near an existing room of the opposite terrain
is probabilistically retried, with the bias fading to zero over a distance
of roughly four typical room widths. This softly clusters natural cave
systems and worked rooms without forbidding either kind among the other.
Room types are still sampled using `rough_probability`; values zero and one
remain entirely worked and entirely natural, respectively.

Room pairs are ranked by closest footprint distance. In shuffled room order,
each room attempts one short connection to earlier rooms, or two with 25%
probability. Unconnected components are then joined, attempting short links
before allowing links over `corridor_length`. This option is a **soft
passage-length limit**, not a required length or average.

A link may join two room openings directly or branch once onto a passage
incident to the destination room. Physical-network validation rejects
duplicate room connections, unrelated room crossings, unplanned room
entrances, and unplanned corridor contacts or multiple rejoins.

Worked passages are orthogonal. A passage is rough only when both endpoint
rooms are rough. Natural routing uses 16 headings: cardinal, 1:1 diagonal,
and 2:1/1:2 steps and reflections. A smoothly interpolated random resistance
field and obstacle-aware target costs guide bounded backtracking. A soft
heading-alignment cost favors smooth bends without prohibiting sharp turns.
The route targets the exterior opening, and diagonal steps expand into
connected floor footprints. `meandering` controls resistance-field strength:
zero gives uniform costs; one gives the strongest variation.

### Stairs, decoration, and failure handling

Straight stairs and ramps are placed outside room footprints, reserving
their walls and approaches. Candidates are ranked by floor collisions and
distance to existing floor. Colliding passages are rerouted or reconnected;
stair approaches attach to a single existing floor contact. Layout repair
cannot discard rooms from a generated room network. Repair notes are retained
in `layout_notes`.

Worked corners are chamfered probabilistically; eligible natural corners
are chamfered automatically. Doors are placed at valid room entrances:
exact counts first, then probabilities for unspecified types. Floor features
avoid protected stair geometry and adjacent diagonals; traps may adjoin doors.
`traps + pits` produces that many explicit `T` tiles, preferring chamber
entrances; ASCII does not distinguish pits from other traps. Stocking can
add further chamber traps.

Layout placement/routing failures are retried up to 12 times per level.
Exhaustion raises an error with the placement problem and suggested option
changes. A disconnected completed grid raises an error rather than being
returned. These are runtime checks in the generator.

| Layout option | Default | Range or behavior |
| --- | --- | --- |
| `--width`, `--height` | `60`, `40` | Integers at least 7 |
| `--room-size` | `35` | Finite area target, at least 4 |
| `--density` | `0.3` | Room-budget fraction, greater than 0 and at most `0.4` |
| `--corridor-length` | `8` | Finite positive soft length limit |
| `--rough-probability` | `0.4` | Probability a room is rough |
| `--meandering` | `0.6` | Natural-route winding strength, `0` through `1` |
| `--door-probability` | `0.45` | Normal-door probability |
| `--secret-door-probability` | `0.1` | Secret-door probability |
| `--concealed-door-probability` | `0.05` | Concealed-door probability |
| `--doors`, `--secret-doors`, `--concealed-doors` | Unspecified | Exact nonnegative counts overriding that type's probability |
| `--traps`, `--pits` | `0` | Exact nonnegative floor-feature counts |
| `--chamfer-probability` | `0` | Worked-corner probability |

Probabilities are finite values from zero through one. The three door
probabilities must sum to at most one, including when counts are specified.
Exact feature counts apply during base-layout decoration; puzzle placement
subsequently changes geometry and may remove random contents in puzzle rooms.

### Linked dungeon levels

`--levels` defaults to 1 and must be positive. For multiple levels, the first
level has a surface up staircase. Each non-final level gets `--stairs-down`
passages, or a random 1-3 when unspecified, plus `--ramps-down`.
Each sampled down staircase becomes a ramp with `--ramp-probability`
percent chance (0-100, default 0). `--stair-length` defaults to 3 and must fit
the map and its approaches.

Descending footprints are inherited at the same coordinates, with matching
up symbols, on the next level. Base generation gives the final level no new
down passages. Multi-level `stairs_up` accepts 0 or 1 and `ramps_up` must be
zero; incoming up links are determined by the level above. Single-level
explicit stairs/ramps use one-square footprints and default to zero.

Multi-level depth is `level_number * stair_length * 10` feet; a single level
has depth zero. Rendering scale does not alter that depth. A level transform
runs before descending links are inherited, allowing puzzle-adjusted links
and sufficient lower-level width.

### Random puzzles and progression gates

`--puzzle-probability` defaults to `0.35`; each of
`--max-puzzles-per-level` slots (default 2, range 0-50) rolls independently.
Successful slots select uniformly from unused, depth-eligible definitions.
The catalog contains 50 puzzles, used at most once per adventure. The
`Dungeon levels` fields constrain strategy-game eligibility. Exhaustion or
insufficient eligible definitions reduces the count without repeating puzzles.

Each level is stocked before its puzzles are attached and before the next
level is generated. Placement reserves the first room from reuse to leave
an accessible source encounter for prerequisites.

Stair puzzles are catalog numbers **3, 8, 13, 15, 26, 30, and 39**. Placement
first seeks an unused existing room with a complete clear 5x5 floor region.
It puts a 2x2 down spiral **inside that room**, with clear surrounding floor
and a separate label cell. Straight down stairs/ramps are removed when these
spirals are placed. The staircase leads to the next level, including beyond
the mapped dungeon when placed on the final level. Its seal is described at
both ends when the lower level is mapped. It has no separate reward room or
passage gate.

Other passage puzzles first seek an existing edge room for an outward
six-square passage to an isolated 5x5 reward room. A normal `D` tile gates
the branch. Local puzzles reuse available rooms without an onward gate.
Definitions that cannot use existing rooms are placed in an added wing off
an ungated common corridor. A wing can increase width, and stair-puzzle wings
increase height to at least nine when needed.

Puzzle rooms are accessible without solving another puzzle. Same-level
reward branches are independent, nonoverlapping, stair-free, and limited by
runtime validation to at most ten passage squares. Each contains a guardian
and at least 100 sp in value or magic. Hoards are ranked by permanent magic
count, consumable magic count, then money/gem value. Hoards and their encounters
are moved or exchanged, not duplicated; floor traps stay in place. The primary
gate protects the level's best hoard, and a final-level primary gate protects
the dungeon's best hoard.

Every puzzle also gets an explicit solved-only prize from a separate seeded
stream: 40% jewelry (d3 pieces), 40% gems (d6), or 20% one magic item.
Values use dungeon-depth tables capped at level 10. Generated prizes and
placement notes give the concrete rewards and geography for the TM.
Random monsters and chamber traps are cleared from puzzle encounter records.

Required items are physical loot, with source and destination references.
Selection prefers earlier puzzle rewards that cannot be permanently sealed,
listing items with those encounters' solved-only prizes, not just in notes.
Otherwise it uses accessible encounter loot on the same or an earlier level,
outside protected branches and puzzle rooms. Runtime validation checks sources,
same-level accessibility, eligibility, unique puzzles, reward ranking, branch
geometry, and aligned links.

The catalog supplies setups, clues, solutions, hints, and consequence rules.
Strategy parsing/validation uses the standard library; the runtime does not
depend on a chess package or engine. Trap/access challenges allow unlimited
retries; treasure-only failure limits must not permanently lock required items
or progression. See [the catalog](dungeon_puzzles.md) for the actual rules.

### Encounters, treasure, and traps

Stocking keys retained chamber footprints. Labels are chosen near each room's
centroid on labelable floor, preferring non-trap squares; areas are numbered
top-to-bottom, then left-to-right, restarting per level. ASCII contains no
encounter numbers.

Generation basic rolls sum three independent integers from 0 through 11,
without symbol rerolls. A presence roll meeting `--encounter-chance` (default
11, range 0-33) generates a monster-table roll. Encounter bands are levels
1-3, 4-6, and 7-9, with the deepest band used below level 9.
Treasure uses creature levels and tables capped at 1-10. Empty chambers can
receive an abandoned cache; dragon hoards have their own multipliers.

Treasure container, trap, and lock generation uses separate seeded streams.
`--treasure-chest-dc` (17), `--chest-trap-dc` (19), and `--chest-lock-dc`
(17) are generation thresholds in 0-34, not player action DCs. Non-chest
treasure uses a bag or pack. Chest trapping and locking are independent.
Random chamber traps occur on a basic roll of at least 23 unless that room
already has an explicit `T`.

After puzzle placement and hoard relocation, stocked room traps are marked
`T`, preferring the room side of a door or open entrance. Chests are marked
`C` away from entrances and door squares, avoiding positions that would cut
off access through the chamber. Stair footprints, landings, and the clear
ring around room spirals are protected. The encounter key gives each
trap/chest's one-based column and row. A trapped chest keeps its `C` tile;
the generated TM SVG adds a small `T` to its chest symbol. ASCII alone does
not encode whether a chest is trapped.

Generated trap descriptions specify detection, disarming, avoidance saves,
and damage/poison consequences. Hidden doors are keyed at DC 20 WIS for
secret doors and DC 17 WIS for concealed doors. `RULINGS` in
`dungeon_encounters.py` records table interpretations and improvised effects;
the debug log includes those rulings and stocking results.

## Files and Python API

`--output` defaults to `dungeon.svg`. `--ascii-output` defaults to the SVG
path with `.txt`. Multiple levels append `-level-N` to both map stems.
Stocking writes `<SVG stem>-encounters.md` and `<SVG stem>-encounters.log`,
one document of each type for all levels. Paths are checked for collisions,
and SVG/key/log documents are prepared before writing. Output directories
must already exist. The converter refuses to overwrite its input.

```python
from pathlib import Path

from dungeon_encounters import EncounterRules, encounter_document
from dungeon_geometry import parse_ascii, validate_map
from dungeon_map import GenerationOptions, generate_dungeon
from dungeon_puzzles import generate_adventure
from dungeon_render import svg_document

options = GenerationOptions(seed=42)
dungeon = generate_dungeon(options)
for level in dungeon.levels:
    validate_map(level.grid)
    svg = svg_document(level.grid, seed=dungeon.seed)

rules = EncounterRules(Path("TreasuresAndTrollsBasicMD.md"))
adventure, keys = generate_adventure(options, rules=rules)
key = encounter_document(adventure, keys, encounter_chance=11)
```

`GeneratedDungeon.levels` returns all levels in order; `grid`, `room_areas`,
`corridor_lengths`, `stairways`, `room_cells`, `depth_feet`, and `layout_notes`
on the result describe its first level. `density` reports open area divided
by the entire grid, counts diagonals as half squares, and excludes stone
and void. It is distinct from the room-placement budget.

`generate_dungeon` accepts an optional `level_transform(level, depth)` callback.
`generate_adventure` returns `(dungeon, encounter_levels)` and performs runtime
progression validation before returning. Calling it with puzzles disabled
still stocks encounters; the CLI only stocks a puzzle-disabled map when
`--generate-encounters` is supplied.

For manual stocking with `generate_encounters`, call
`place_encounter_features(dungeon, keys)` on the unmarked dungeon after
stocking and any encounter relocation to obtain the marked dungeon and keys
with `trap_cell`/`chest_cell` coordinates.
Pass `trapped_chests=keys[index].trapped_chests` to `svg_document` to include
chest-trap indicators when rendering a stocked level.
