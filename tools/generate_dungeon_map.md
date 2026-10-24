# ASCII and procedural dungeon maps

This document describes the Python modules in `tools` and the standalone
browser map editor. The Python commands use Python 3.7+ and the standard
library; the browser editor needs neither Python nor a server.

```powershell
python tools\ascii_map_to_svg.py map.txt --output map.svg
python tools\generate_dungeon_map.py --width 60 --height 40 --seed 42 --puzzle-probability 0 --output dungeon.svg
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
Its default `RULES_PATH` points to that file in the repository root. Python
callers can also pass an explicit `EncounterRules` instance.

## Offline browser editor

Open [map_editor.html](map_editor/map_editor.html) directly in a modern browser.
JavaScript and CSS are embedded in this one HTML file, which can be copied
and used on its own. There is no installation,
build step, server, CDN, or network dependency. This is **only a map editor**:
it does not generate procedural maps, puzzles, encounters, or treasure.

Select a terrain type, choose a 1x1, 2x2, 3x3, or 5x5 square brush, and click
or drag to paint. The graphical canvas is a simplified live preview; exported
SVG adds full wall roughness, rounding, and feature drawings. One stroke is
one undo operation. Undo/redo buttons and Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, and
Ctrl+Y are available outside text fields.
The 2x2 brush extends right and down from the cursor square; the 3x3 and 5x5
brushes are centered on it. Brushes clip at the map edges.

- **Load ASCII / Save ASCII:** preserve terrain cells, including literal spaces, and labels.
  Loading or creating a map asks before discarding unsaved terrain changes.
  Saving downloads a file; the browser does not overwrite the original file.
- **Resize map:** preserves the top-left corner and adds stone on the
  right/bottom when expanding. Shrinking asks before cropping non-stone cells or labels.
  Undo restores cropped cells and the previous dimensions.
- **Move contents:** drag all terrain and labels by whole squares within the current
  map, filling vacated cells with stone. This moves the map data, not the
  viewport. A move that would lose any non-stone cell or label is blocked: expand the
  map first. A move is undoable; ordinary scrolling remains separate.
- **Feet per square:** defaults to 5 and controls physical SVG size, not
  pixel zoom. Export uses 50 feet per inch. ASCII contains no scale metadata;
  loading retains the current scale. Use the same scale options in Python
  when comparing printed SVG dimensions.
- **Zoom:** use the minus/plus buttons or percentage selector to zoom the
  preview from 25% to 400%. Painting, moving, and label editing follow the
  zoomed grid. Zoom does not change map data, undo history, or SVG scale.
- **Export SVG:** runs the complete renderer directly in JavaScript, without
  invoking Python. Player SVG hides traps/chests and disguises secret and
  concealed doors as walls.
- **Display labels:** enabled by default; controls labels in the preview and SVG,
  without removing them from ASCII. Right-click any square, including stone,
  to edit its label. Save an empty label or choose Remove label to delete it.
  Label changes support undo/redo.

A single `b` is allowed while building a centered door. Add its adjacent `b`
to complete the door. Spiral stairs can likewise be painted one cell at a
time using `S`, `s`, or `Z`; their landings must be literal spaces. Incomplete
structures show coordinate-specific validation errors and may be loaded/saved
as **ASCII drafts**, but SVG export is blocked until they are complete.
Impossible structures and other invalid geometry (for example a bent door
line or a malformed diagonal) are rejected atomically without changing
the map. An unfinished structure does not hide other invalid inputs.

Finished ASCII maps use the exact same terrain keys, geometry, and symbols
in JavaScript and Python. The renderers share the same seeded wall-walk random
number generator and produce matching cavern curves for matching options.
SVG serialization is not byte-identical.
Old `D/X/C` door maps are not automatically migrated: `C` now means chest and
`d` is a single-square door, so guessing old meanings would change maps.

Maps support 512 x 512 squares (262,144 cells); files may contain up to 16 MiB
including labels. Void squares are deep violet in the editor preview only.
The canvas supports view zoom and ordinary scrolling, not drag-to-pan. Exported
ASCII/SVG contains no editor grid or selection overlays. The editor can edit
encounter numbers and other map labels, but not encounter contents or trapped-chest metadata.

### Development checks

Only development checks need Node.js 22+ and Python. No npm packages are used.
From the repository root:

```powershell
node --test tools\map_editor\tests\editor.test.cjs
node --test tools\map_editor\tests\browser.test.cjs
python -m unittest discover -s tools -p test_dungeon_terrain.py -q
```

The HTML's content-security policy uses hashes for its embedded scripts and
stylesheet. Update the corresponding SHA-256 hashes when editing those blocks;
the model/renderer check verifies them.

The browser check uses installed Microsoft Edge on Windows, or an explicit
`BROWSER` environment variable pointing to a Chromium-based browser. It opens
an isolated copy of `map_editor.html` through `file://`, disables page networking, exercises real pointer
input/import/downloads, and removes its temporary browser profile afterward.
The model/renderer check compares finished-map validation and normalized SVG
geometry with Python using shared fixtures. Python is a test reference only,
never an editor runtime dependency.

## ASCII format

One character represents one square. Literal spaces are smooth floor,
including leading and trailing spaces; tabs are invalid. Short rows are
padded on the right with `#`. LF and CRLF are accepted, and a final newline
does not add a row. Outside the map is solid stone.

Optional labels follow the terrain after **exactly one empty line**, one per
square, using zero-based `x,y: text` coordinates (`0,0` is the top-left).
For example:

```text
#####
#   #
#####

2,1: 12
0,0: Secret entrance
```

Labels may be placed on any in-bounds square, including stone or void. Text
may contain colons, spaces, and UTF-8 characters; surrounding whitespace is
trimmed. Empty labels, duplicate locations, malformed annotations, control
characters, and out-of-bounds coordinates are rejected. Files without labels
retain the original terrain-only format. Labels use the generator's encounter
label styling and remain visible in player SVGs unless hidden in the editor.

| Character | Meaning |
| --- | --- |
| `#` | Solid stone |
| `~` | Void, open for connectivity but without floor or boundary-wall drawing |
| space / `.` | Smooth worked floor / rough cavern floor |
| `\` / `/` | Diagonal walls dividing a square into triangles |
| `\|` / `_` / `L` | Floor with a left / bottom / both partition walls |
| `d` / `x` / `c` | Normal / secret / concealed door |
| `b` | Centered door line; at least two adjacent cells along its horizontal or vertical axis |
| `C` | Chest |
| `l` / `m` / `n` | Floor with a left / bottom / both edge doors |
| `T` | Trap, including covered pits |
| `E` / `e`, `F` / `f`, `G` / `g`, `H` / `h` | Stairs up / down toward north, east, south, west respectively |
| `O` / `o`, `P` / `p`, `Q` / `q`, `R` / `r` | Ramps up / down toward north, east, south, west respectively |
| `S` / `s` / `Z` | Spiral stairs up / down / both |

For `\`, the neighbor pairs are north+east and south+west; for `/`, they
are north+west and south+east. Each pair must be two open neighbors
(spaces, periods, voids, or wall-partition floor) or two stone neighbors. At least one triangle
must be open. When both are open, the wall still separates them: movement
cannot cross it. Diagonal neighbors cannot be feature tiles.

`d`, `x`, and `c` form contiguous doorways when identical cells touch in a
straight line, without requiring floor beside the line or stone at its ends.
For example, `##ddd##` renders as one horizontal doorway three squares wide;
`##xxx##` and `##ccc##` behave the same way for secret and concealed doors.
Door cells can be painted individually through solid stone. Single-cell doors
infer orientation from neighboring passages and default to horizontal when
ambiguous; adding adjacent identical doors determines the line's axis.
Secret/concealed spans become single unbroken walls in player SVGs.
Wall partitions (`|`, `_`, `L`) may touch any terrain and always count as
smooth floor, including where they meet cavern stone. Edge doors (`l`, `m`, `n`)
still require literal space to the left, below, or both, respectively.
Centered `b` door lines follow the axis of their cells: horizontal cells draw
a horizontal doorway and vertical cells a vertical doorway. Two cells draw one
normal-width door centered between them; longer lines extend that same symbol.
Half-square smooth wall sections connect both ends of the centered doorway to
the terrain at the outer edges of its `b` cells.

Cardinally connected cells with the same stair/ramp letter render as one symbol
spanning the group's full length and width. Irregular groups are clipped to their
painted cells. Uppercase means up and lowercase means down along the explicitly
specified compass direction, regardless of nearby passages. Elevation change is
the directional length times feet per square; for example, a 4-by-2 block of `F`
at 5 feet per square is 20 feet long, 10 feet wide, and ascends 20 feet eastward.
SVG groups record square length/width, facing, up/down direction, and signed
elevation in feet. Existing `E/e` and `R/r` maps now explicitly mean north stairs
and west ramps rather than inferring direction. Spiral
footprints are square, size 3 or any positive even size, with a literal-space landing in any
corner. The landing is one square for size 3 and half the side length for even
sizes: 2x2 for size 4, 3x3 for size 6, and so on.
A 3x3 spiral's center must be literal space or `#`.

Authored maps are validated, not repaired. Generation calls
`clear_invalid_diagonals` after carving/decorating connections, converting
invalid diagonals to literal-space floor. Connectivity respects partitions,
the separate diagonal triangles, and explicitly blocked cells. A reachability
search starting on a two-sided diagonal begins in its north-facing triangle.

## Rendering and symbols

Smooth walls remain straight and grid-aligned. Natural cavern boundaries are
traced into continuous paths, not rendered as separate square-edge segments.
The default random walk samples each edge at its start, quarter, midpoint,
three-quarter, and endpoint, carrying its displacement across square borders.
It can wander half a square to either side of the nominal boundary, including
into stone. Each step changes lateral offset by at most its forward distance,
limiting the walk to 45 degrees relative to a straight or diagonal edge.
Smooth-wall joins stay exactly on the original grid; closed cavern boundaries
close seamlessly without a forced grid anchor.

At turns, displacement follows the corner bisector (a 45-degree ray for a
right-angle corner). Crowded quarter-edge samples are removed on inside turns;
outside turns retain the bisector sample to make a wider bend. Signed offsets
allow the walk to cross the nominal boundary through a turn. The resulting
points control a continuous B-spline rendered as cubic SVG Bezier curves.
The convex-hull curve fit avoids the overshoot of unconstrained interpolation.
Wall coordinates remain within the map and void clipping is unchanged.
Feature groups inherit rough terrain only when they border rough floor and
no smooth floor. Diagonals infer terrain from their open neighbors.

SVG output has transparent backgrounds, black wall lines, and editable
feature groups. Walls and features use separate `walls` and `features`
groups; numbered encounter labels use `encounters`. Void squares clip wall
and feature drawing, and edges adjoining void are not outlined.

Doors use rectangles; secret and concealed doors include uppercase `S`/`C`.
Chests use a lidded rectangle with a clasp. Traps use an X and `T`.
Straight stairs going up use equal-width treads. Stairs going down narrow
progressively along the arrow's direction: the bottom tread is exactly half
the width of the top tread, regardless of the stairway's length or width.
Ramps use side rails, with "ramp up" or "ramp down" beside the center-line
arrow. These annotations follow the ramp's axis and remain upright for east/west
ramps; short ramps fit the words horizontally without reducing their font size.

All SVG text uses the same font size: 90% of a map square, including encounter
numbers, secret/concealed-door markers, trap letters, and ramp annotations.
Long map labels are fitted horizontally rather than reduced in height.
Both stairs and ramps retain directional arrows, but their ASCII tile letters
are not drawn on SVGs. The input letters still determine orientation even for
single squares; editor preview letters and custom map labels are unchanged.
Spiral direction arrows follow arcs at three-quarters of the outer stairway
radius. Down-only spirals narrow their radial treads progressively clockwise
from the landing, with the final tread half the width of the first. Up-only
spirals retain equal-width treads. Bidirectional spirals retain uniform treads
and show separate up/down arrow arcs at the same three-quarter radius.

| Rendering option | Default | Meaning |
| --- | --- | --- |
| `--feet-per-pixel` / `--feet-per-square` | `5` | Map feet per square |
| `--feet-per-inch` | `50` | Map feet per printed inch |
| `--line-width` | `0.01` | Printed stroke width in inches |
| `--seed` | Converter: `0`; generator: random | Seed for rendering and generation |
| `--roughness` | `0.5` | Maximum wall-walk displacement, `0` through `0.5` squares |
| `--max-wall-deviation` | `0.5` | Hard limit on the complete cavern-wall SVG path's distance from its original square edges, `0` through `0.5` squares (0-50%) |
| `--rough-segments` | `4` | Walk intervals per edge, `2` through `32`; four gives five sample points |
| `--corner-radius` | Roughness | Maximum corner-bisector displacement, `0` through `0.5` squares |
| `--player-view` | Off | Hide traps and draw secret/concealed doors as walls |

`--corner-radius` is retained as the bound on corner-bisector displacement,
rather than the radius of the former circular corner approximation. Zero pins
the corner's walk sample to the nominal vertex; cubic fitting still smooths
the turn. Zero roughness disables random displacement, not curved fitting.
`--max-wall-deviation` caps both displacement and curved fitting, including
corners. Its default and maximum are `0.5` (50%, or half a square). For example,
`--max-wall-deviation 0.25` keeps the entire wall path within a quarter square of
the original edges; `--max-wall-deviation 0` draws the same straight wall geometry
as smooth stone. This bounds the path itself, not the outer edge of its stroke.
The offline editor exposes the same setting as **Cavern wall deviation (%)**
for SVG export, using whole percentages (`0` through `50`, default `50`).
Python's `svg_document(max_wall_deviation=...)` and the editor's
`renderSvg(..., { maxWallDeviation: ... })` APIs use the same square fractions
as the CLI (`0` through `0.5`, default `0.5`).
Scale values must be finite and positive. Printed width/height is the square count times
feet-per-square / feet-per-inch, plus one stroke width.

Player view hides traps and chests and changes hidden-door visibility only in
SVG. ASCII, encounter keys, and debug
logs remain **TM-only**. Encounter numbers remain visible in player view.

## Procedural generation

### Rooms and passage networks

`GenerationOptions` controls the base layout. All rooms are placed before
passages. Worked rooms are rectangles; cavern rooms grow connected, irregular
footprints around multiple offset lobes. Room area is sampled around `room_size`,
with varied aspect ratio and dimensions of at least three squares.

Room positions are sampled inside a two-square border. Placement rejects
reserved inherited-stair geometry and a three-square buffer around placed
rooms, enlarged to `passage_width + 1` for wider passages. The room budget is
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

`--passage-width` sets the passage floor width in squares (default 2).
Routing reserves clearance for the full footprint, including bends, and
doorways span the passage rather than leaving an open gap alongside a door.
Exact door counts count whole doorways, not the individual tiles in each span.
Generated stairs, ramps, and their protected approaches use the same passage width.
At the default 5 feet per square, passages are 10 feet wide. The default
120-by-80 map and 140-square room target preserve the physical map dimensions
and typical room area of the former 60-by-40, 35-square layout at 10 feet per square.

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
avoid protected stair geometry and adjacent doors/diagonals.
`traps + pits` produces that many `T` tiles; ASCII does not distinguish them.

Layout placement/routing failures are retried up to 12 times per level.
Exhaustion raises an error with the placement problem and suggested option
changes. A disconnected completed grid raises an error rather than being
returned. These are runtime checks in the generator.

| Layout option | Default | Range or behavior |
| --- | --- | --- |
| `--width`, `--height` | `120`, `80` | Integers at least 7 |
| `--room-size` | `140` | Finite area target, at least 4 |
| `--passage-width` | `2` | Positive integer fitting inside the stone border |
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
the map and its approaches. Stairs and ramps are `passage_width` squares wide,
including their landings and protected approaches.

Descending footprints are inherited at the same coordinates, with matching
up symbols, on the next level. Base generation gives the final level no new
down passages. Multi-level `stairs_up` accepts 0 or 1 and `ramps_up` must be
zero; incoming up links are determined by the level above. Single-level
explicit stairs/ramps are one square long, retain the selected passage width,
and default to zero.

Multi-level depth is `level_number * stair_length * 10` feet; a single level
has depth zero. Rendering scale does not alter that depth. A level transform
runs before descending links are inherited, allowing puzzle-adjusted links
and sufficient lower-level width and height.

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
first seeks an unused existing room with enough clear floor for the spiral and
a surrounding floor ring. Spiral side length is twice `passage_width`: the
default width 2 produces a 4x4 down spiral with a 2x2 landing; width 1 retains
the 2x2 spiral. It puts the spiral **inside that room**, with clear surrounding floor
and a separate label cell. Straight down stairs/ramps are removed when these
spirals are placed. The staircase leads to the next level, including beyond
the mapped dungeon when placed on the final level. Its seal is described at
both ends when the lower level is mapped. It has no separate reward room or
passage gate.

Other passage puzzles first seek an existing edge room for an outward
six-square passage to an isolated 5x5 reward room. A normal `d` tile gates
the branch. Local puzzles reuse available rooms without an onward gate.
Definitions that cannot use existing rooms are placed in an added wing off
an ungated common corridor. A wing can increase width, and stair-puzzle wings
increase height as needed to fit the full-width spiral and its surrounding floor.

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
top-to-bottom, then left-to-right, restarting per level. When encounters are
generated, every level's ASCII file includes its numbered labels after the
terrain. The converter and editor preserve these positions when rendering SVG.

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
