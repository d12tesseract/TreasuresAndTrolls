# ASCII and procedural dungeon maps

Requires **Python 3.7+**, with no third-party packages.

The generator now includes random puzzles and encounter stocking by default.
Use `--puzzle-probability 0` for the original puzzle-free layout behavior;
add `--generate-encounters` if you still want ordinary encounter stocking.
See [Random puzzles and progression gates](#random-puzzles-and-progression-gates)
for probability controls, expanded map dimensions, and TM item references.

```powershell
python ascii_map_to_svg.py map.txt --output map.svg
python generate_dungeon_map.py --width 60 --height 40 --seed 42 --output dungeon.svg
```

The generator writes `dungeon.txt` as well as `dungeon.svg`. The ASCII converter
and generator share geometry, rendering, and command-line options.

## Module organization

`tools` is the canonical implementation. The commands and map/encounter
imports in `campaigns/ur` are compatibility entry points, not separate copies.
Keep the shared Python modules and puzzle catalog together.

| Module | Responsibility |
| --- | --- |
| `dungeon_geometry.py` | ASCII model, validation and diagonal cleanup, connectivity and routing, terrain inference, and stair geometry |
| `dungeon_passages.py` | Sixteen-heading cavern centerlines, bounded backtracking, and diagonal floor footprints |
| `dungeon_render.py` | Wall geometry, rough edges, feature symbols, and SVG serialization |
| `dungeon_map.py` | Seeded room/corridor generation, stair placement, and linked levels |
| `dungeon_encounters.py` | Rules-based stocking, treasure ranking, chamber numbering, and encounter documents |
| `dungeon_puzzles.py` | Catalog loading, puzzle branches, reward placement, and progression validation |
| `dungeon_games.py` | Deterministic strategy-game rules and validation |
| `dungeon_cli.py` | Shared command-line value validators and rendering options |

The two command scripts handle argument parsing and file output. Existing
imports such as `from dungeon_map import DungeonMap, svg_document` remain
supported; new rendering-only callers can import the geometry and rendering
modules directly. `dungeon_puzzles.treasure_value` and
`dungeon_puzzles.reachable_cells` remain available as compatibility imports,
but their implementations belong to encounters and geometry respectively.

Behavior-preserving optimizations retain random-call and output ordering;
the new cavern algorithm intentionally changes maps containing natural terrain.
Room placement maintains a local exclusion set. Stair selection translates two
footprint templates per stair type instead of constructing a `Stairway` and
its wall/clearance sets at every candidate square; only tested finalists become
objects. Puzzle placement reuses per-operation treasure rankings, item-source
sets, and location indexes. These are local to an operation, not persistent
caches. Encounter stocking depends on geometry rather than importing the
generator at runtime, and shares currency values between hoard generation
and treasure ranking. Compatibility exports in `dungeon_map` remain available.

## ASCII format

Each character occupies one map square. **Spaces are floor**, including leading
and trailing spaces. Do not trim them or use tabs. Short rows, including empty
rows, are padded on the right with `#` to the longest row's width. LF and CRLF
line endings are accepted; one final newline does not create another row.
Outside the map is solid stone. Unknown characters and invalid arrangements
produce errors with one-based row and column numbers.

| Character | Meaning |
|---|---|
| `#` | Solid stone |
| `~` | Void: neither floor nor stone; no boundary walls and no blocked connections |
| space | Open floor with smooth worked walls |
| `.` | Open floor with rough cavern/hewn walls |
| `\` | Diagonal from top left to bottom right |
| `/` | Diagonal from bottom left to top right |
| `\|` | Smooth floor with a wall on its left |
| `_` | Smooth floor with a wall on its bottom |
| `L` | Smooth floor with walls on its left and bottom |
| `D` | Normal door |
| `X` | Secret door |
| `C` | Concealed door |
| `d` | One half of an isolated horizontal/vertical `dd` door pair; door lies on the shared edge |
| `l` / `m` / `n` | Floor with a left / bottom / both left and bottom wall door |
| `T` | Trap, including covered pits |
| `E` / `e` | Stairs up / down |
| `R` / `r` | Ramp up / down |
| `S` / `s` / `Z` | Spiral stairs up / down / both |

For example, this map joins a worked room to a cavern through a door:

```text
#############
#   #####...#
#   D.......#
#   #####...#
#############
```

### Diagonals, partitions, and doors

Diagonals divide a square into two separate triangles. For `\`, the neighbor
pairs are north+east and south+west; for `/`, north+west and south+east.
Each pair must contain two spaces/periods/voids (open) or two `#` (solid).
Either or both triangles may be open, but not both solid. When both are open,
the wall still separates them: connectivity cannot cross the diagonal.
Feature tiles are not allowed in these four positions. Two period neighbors give the diagonal rough cavern texture;
mixed or space neighbors give it smooth texture. The diagonal itself is the exposed wall of the solid
triangle; no extra square-edge walls are drawn across the open triangle.

Generated connections that invalidate a diagonal, for example by opening only
one edge of a solid triangle, replace it with a literal empty-space floor square. This cleanup
also runs after puzzle wings are joined. Authored ASCII maps remain strict:
the converter reports invalid diagonals instead of silently rewriting them.

`|` and `L` require a literal space to their left. `_` and `L` require a literal
space below. Their partitions are rendered once, even though both sides are
floor. These tiles are available in authored maps but are not generated.

`D`, `X`, and `C` require either north+south or east+west neighbors that are
literal spaces or periods, with `#` on the perpendicular sides. The two open
neighbors may have different terrain. Junction doors and doors directly
adjacent to other feature tiles are rejected. Doors span the passage width.

An isolated `dd` pair needs exactly two adjacent `d` squares, horizontally or
vertically, with no branching or additional adjacent `d`. Its rectangle is
centered on the shared square edge, rather than either square center.
`l`/`n` require literal floor space to the left, and `m`/`n` require literal
floor space below. Their edge door symbols include wall stubs on each side
of the doorway; they remain passable for connectivity.

Void does not acquire a floor outline or stone boundary. An edge adjoining
`~` is never drawn, and a connection through an in-bounds void stays open.
Wall strokes and feature symbols are clipped out of void squares, including
rough-wall jitter, without trimming the outer map's half-stroke margin.
Void squares do not count toward generated floor density.

Feature tiles replace the floor character. A touching group of feature tiles
inherits rough wall texture only when it borders rough floor and no smooth
floor. Otherwise it is smooth, including isolated groups with no terrain to
infer from. Diagonals infer their terrain from their open neighbors as above;
partition tiles remain smooth.

## Rendering and symbols

Walls around spaces are straight. Rough walls subdivide each exposed tile edge
and offset interior points to either side of its baseline, tapering the offsets
toward shared endpoints. Both inward and outward rough corners are rounded:
the adjoining edges are shortened and joined by a sampled circular arc rather
than meeting at the sharp grid corner. Set `--corner-radius` from **0 to 0.5
map squares** to control rounding independently of wall jitter. At `0.5`, the
diameter spans a whole square: an isolated rough square becomes a roughly
circular outline, while edges shared with open floor remain open. Inward
corners and stone islands use the same radius. Rounded arcs retain seeded
radial jitter controlled by `--roughness`, including at the maximum radius.
This jitter tapers to zero at shared endpoints and stays within each corner's
square so the outline remains connected and cannot cross neighboring arcs.
Near the maximum, jitter on the shrinking straight pieces fades to avoid
spikes, but jitter on the arcs remains.

Omitting `--corner-radius` keeps the automatic radius rule: three times
`--roughness`, capped at 0.35 squares. With that default, zero roughness disables
both jitter and rounding. An explicit positive radius still rounds corners
when roughness is zero, producing clean circular curves; an explicit radius
of zero disables rounding without disabling jitter. Smooth worked walls and
their diagonal corners are unaffected. Natural diagonal wall faces use rough
texture too; their chamfer vertices remain shared endpoints rather than being
treated as right-angle rounding arcs.
The small segments approximate circular arcs while remaining individually
editable; increase `--rough-segments` for finer curves.
The outline remains connected. At a normal
rough/smooth boundary join, a short connector perpendicular to the smooth wall
links it to the offset rough wall. Four-way corner contacts retain their shared
grid vertex. Rough geometry is clamped at map borders to keep the physical
extent unchanged. Shared open edges are never outlined.

Every wall piece is a separate SVG `<line>`, not a merged outline. Wall lines
live in the `walls` group; independently editable feature symbols live in the
`features` group. SVGs have black outlines, a transparent background, and no
filled rock or grid overlay.

Normal doors use a rectangle across the passage; secret and concealed doors
add `X`/`C` labels. Traps, including covered pits, use an X and `T`.
Stairs use treads, ramps use tapering sides, and both use arrows plus
their ASCII letter. In east-west passages their drawing rotates to match;
in north-south passages and ambiguous room locations it uses a north-south
axis. Down arrows point north (east when rotated), up arrows point the other
way. The labels make elevation direction explicit.

A straight, contiguous run of the same stair/ramp letter, such as `eee`,
represents one passage spanning that many squares. The renderer draws one
full-length symbol, aligned to the run even in an open room. A single letter
uses the original one-square symbol and passage-based orientation; bent or
branching letter clusters retain individual symbols. This notation survives
ASCII editing and conversion back to SVG without a separate metadata file.
The multi-level generator aligns these runs between adjacent floors.

Spiral stairs use a square 2×2, 3×3, or 4×4 footprint of the same `S`, `s`,
or `Z` character. One corner is a **literal space** landing: 1×1 for 2×2 and
3×3 footprints, or 2×2 for 4×4. Any corner is allowed. A 3×3 center must be
literal space or `#`. Examples (up, down, and both):

```text
 S
SS
```

```text
 ss
s#s
sss
```

```text
  ZZ
  ZZ
ZZZZ
ZZZZ
```

The circular outline's diameter equals the footprint width. Radial treads
and curved arrows indicate counterclockwise ascent (`S`), clockwise descent
(`s`), or both (`Z`); the corner landing remains clear.
Both winding arrows remain visible for every landing corner; `Z` uses separate
concentric ascent and descent arrows.
A 3×3 center is outlined as a circle one square in diameter: a complete
circle for solid stone (`#`), or a circle with a quarter-circle opening
facing the landing for literal space. Treads meet this circular boundary
instead of a square central wall.
For placement APIs, `Stairway.spiral_at(left, top, size=3, tile="s",
landing_corner="NW")` returns the glyph cells separately from `landing_cells`.
`clearance` includes the full square footprint; `paint(rows)` writes glyphs
and literal-floor landing while preserving a 3×3 center. Linked levels retain
the footprint and landing, replacing `s` with `S` on the level below.

| Option (both programs) | Default | Meaning |
|---|---|---|
| `--feet-per-pixel` / `--feet-per-square` | `10` | Feet represented by one ASCII square |
| `--feet-per-inch` | `50` | Map feet per printed SVG inch |
| `--line-width` | `0.01` | Stroke width in printed inches |
| `--seed` | ASCII: `0`; generator: random | Reproducible rough geometry and generated layouts |
| `--roughness` | `0.12` | Maximum wall jitter in squares, from `0` to `0.2`; also sets the automatic corner radius |
| `--corner-radius` | automatic | Rough corner radius in map squares, `0` to `0.5`; maximum diameter is one square |
| `--rough-segments` | `6` | Line pieces per rough tile edge, from `2` to `32`; corner arcs use at least 6 pieces |
| `--player-view` | off | Hide `T` and draw `X`/`C` as ordinary wall segments |

Scale values must be finite and positive. The SVG dimensions are the map
dimensions times feet-per-square / feet-per-inch, plus one line width for
the half-stroke margin on each side. A 60 by 40 map at the defaults is
12.01 by 8.01 inches. Scaling does not change generation or the number of squares.

Player view affects **only the SVG**. Generated ASCII always retains all secret
doors, concealed doors, and traps; do not distribute that file to players.
When encounter generation is enabled, the Markdown encounter key and debug log
are also **TM-only**, even with `--player-view`. Chamber numbers remain visible in
player-view SVGs without revealing their contents.

```powershell
python ascii_map_to_svg.py dungeon.txt --seed 42 --player-view --output players.svg
python ascii_map_to_svg.py dungeon.txt --feet-per-square 5 --feet-per-inch 25 --line-width 0.008
python ascii_map_to_svg.py dungeon.txt --corner-radius 0.5 --output rounded.svg
python generate_dungeon_map.py --rough-probability 1 --corner-radius 0.5 --output rounded-caverns.svg
```

## Procedural generation

The generator places **all rooms before routing any passages**. Rectangular
worked rooms and irregular connected caverns have randomized sizes and types.
Each position is sampled uniformly across translations where its footprint
fits inside the map's **two-square room border**. Overlaps, a **three-square
rock buffer between room footprints**, including their corners, and reserved
stair clearances are rejected; passages do not influence placement. Rooms that
cannot fit after bounded placement attempts are discarded, even below the
requested density.
Borders, room sizes, and collision rejection constrain the accepted layouts:
this is not exact uniform sampling of every possible packed configuration.
There is no regular grid or forced even spacing, so random clustering remains
possible.

Rooms are processed in seeded random order. Each room attempts **one initial
connection with 75% probability, or two with 25% probability**, to earlier rooms;
the first room has no earlier neighbor. Candidate selection randomizes the
nearest few neighbors before trying farther alternatives. These counts are
best-effort, not final degree limits: later rooms can connect back to an earlier
room, and component bridges can add necessary connections.

Initial connections must fit within `--corridor-length`. The generator tries
all feasible short component bridges before allowing a longer passage, and
only allows a long link between disconnected components. After each long link,
short alternatives are reconsidered. Unordered room pairs are unique: reverse-order requests
cannot add a second direct passage, but indirect alternative routes through
other rooms are allowed.

Passages use explicit boundary openings and cannot cross unrelated rooms or
existing passages. They leave **at least one solid rock square**, including
diagonally: separate passages cannot touch at their corners or graze room
corners. The only exceptions are the local footprint of an intended room opening
or junction. A connection may instead
deliberately attach to an existing passage at a registered three- or four-way
junction. The full floor footprint is checked, including diagonal fillers;
incidental intersections and repeated contacts are rejected. Unroutable links
try alternative openings or neighbors, and disconnected layouts are retried
within a bounded budget rather than returned with unsafe fallback passages.
These rules also apply to stair access and repairs, but not to the separately
generated puzzle wings.

Worked corridors remain orthogonal and detour around obstacles. Corridors are
rough when both endpoint rooms are rough, otherwise smooth.
Natural passages choose among **16 compass headings**, represented
on the grid by cardinal, 1:1 diagonal, and 2:1/1:2 steps and their reflections.
Their target is the **exterior square immediately in front of the destination
room's opening**, not its center. The final connection through that opening
is preserved.

Natural passages follow a **smoothly varying random resistance field**:
neighboring squares have similar routing costs, encouraging broad, irregular
bends through lower-resistance regions instead of independent random turns.
Obstacle-aware distances from the destination guide a bounded search through
that field. All **16 headings** remain available: passages may move temporarily
away from the target, double back, turn more than 90 degrees, or detour even
within three squares of the destination. A soft preference for continuing the
current heading smooths bends without prohibiting sharp turns.

The route must still stay inside the map, avoid blocked terrain, and avoid
crossing or tangling with its earlier footprint. Backtracking compensates for
blocked or tangled choices; if no route is found within the search budget,
the generator retries the layout rather than carving a self-crossing fallback.
The exterior target square and final connection through the opening are
preserved.

`--meandering` controls **winding strength**: `0` uses uniform routing costs
for direct routes, `1` gives the strongest preference for winding low-resistance
routes, and the default is `0.6`. It is no longer a per-step heading-change
probability. Obstacles and narrow spaces can limit available bends; even at
`0`, a passage can detour when a direct route is blocked.
Diagonal steps fill their adjoining half-squares so the passage is physically
connected. **Natural rooms and passages always chamfer eligible corners**,
including at `--chamfer-probability 0` and `--meandering 0`; that chamfer option
controls only worked-room corners. Protected stair approaches and features
are not chamfered. Stair-collision repair still routes around protected
footprints before final chamfering. Every generated walkable square remains
connected, treating doors and covered pits as passable.

| Option | Default | Meaning |
|---|---|---|
| `--width`, `--height` | `60`, `40` | Base map dimensions in squares, each at least 7; puzzle wings can increase width |
| `--levels` | `1` | Positive number of levels; 1 generates a single floor without automatic stairs |
| `--stair-length` | `3` | Positive integer length of each multi-level stairway or ramp, in squares |
| `--ramp-probability` | `0` | **Percentage, 0-100**, that a multi-level down stairway becomes a ramp |
| `--room-size` | `35` | Target average room floor area in squares, at least 4 |
| `--corridor-length` | `8` | Positive soft length limit; longer passages are allowed only when short links cannot connect the room network |
| `--meandering` | `0.6` | Natural-passage winding strength; `0` is direct, `1` gives the strongest bends |
| `--density` | `0.3` | Room-footprint target within the two-square room border, excluding passages; greater than 0 and at most 0.4 |
| `--rough-probability` | `0.4` | Probability each room is a cavern |
| `--door-probability` | `0.45` | Normal door probability at an eligible room entrance |
| `--secret-door-probability` | `0.1` | Secret door probability at an eligible entrance |
| `--concealed-door-probability` | `0.05` | Concealed door probability at an eligible entrance |
| `--doors`, `--secret-doors`, `--concealed-doors` | unset | Exact counts, overriding their respective probabilities |
| `--traps`, `--pits` | `0` | Exact trap / covered pit counts; both emit `T`, so the total marker count is their sum |
| `--stairs-down` | single: `0`; multi: random `1-3` | Exact one-square down stairs in single-level mode; passages per connection in multi-level mode, subject to ramp replacement |
| `--stairs-up` | `0` | Exact one-square up stairs in single-level mode; automatic in multi-level mode |
| `--ramps-down`, `--ramps-up` | `0` | Exact one-square ramps in single-level mode; multi-level down ramps are additional guaranteed passages, up ramps are automatic |
| `--chamfer-probability` | `0` | Probability of converting an eligible smooth room corner to a diagonal |
| `--generate-encounters` | off | Force ordinary encounter stocking when puzzles are disabled; enabled puzzles already imply stocking and TM output |
| `--puzzle-probability` | `0.35` | Independent probability, 0-1, for each puzzle slot per level; 0 disables puzzles |
| `--max-puzzles-per-level` | `2` | Number of independent puzzle slots, integer 0-50; 0 disables puzzles |
| `--encounter-chance` | `11` | Minimum basic roll for a monster in each chamber, integer 0-33 inclusive |
| `--treasure-chest-dc` | `17` | Generation threshold for treasure in a chest; otherwise a bag/pack. Integer 0-34: 0 always, 34 never |
| `--chest-trap-dc` | `19` | Generation threshold for a treasure chest to be trapped. Integer 0-34: 0 always, 34 never |
| `--chest-lock-dc` | `17` | Independent generation threshold for a chest to be locked. Integer 0-34: 0 always locked, 34 always unlocked |
| `--output` | `dungeon.svg` | SVG destination |
| `--ascii-output` | SVG filename with `.txt` extension | Editable ASCII destination |

Probabilities are between 0 and 1, **except `--ramp-probability`, which is a
percentage between 0 and 100**. The three door probabilities must sum to at
most 1; the remainder leaves entrances open. Only isolated, one-square-wide
entrances with valid stone sidewalls are eligible for doors; other entrances
remain open. Specifying an exact door count reserves that many valid entrances
first and disables that category's probability. Its unused probability becomes
open-entrance probability, not an increased chance for other door types.
Exact zero therefore suppresses a door type completely.

Room area, density, and corridor length are **soft targets**, since map bounds,
room spacing, and obstacle-free routing constrain them. Room dimensions vary,
are at least 3 by 3 before cavern shaping, and are capped to fit the map.
The program reports both room-footprint area and achieved total open area,
counting diagonal squares as half a square in the latter. Density controls only
the **room-footprint budget**, calculated as
`(width - 4) * (height - 4) * density`; passages add extra walkable area. High densities
or small maps may fall short; adding the last room can overshoot. Room count
varies with sampled room sizes and available packing space, not corridor area.
Lower density generally produces fewer chambers distributed across the same
map area, increasing average chamber spacing and passage length rather than
confining the dungeon to a small cluster. Individual random layouts can still
cluster by chance; very small budgets may allow only one chamber.

Reported corridor lengths count newly carved squares outside room footprints,
not center-to-center distances. The soft limit is checked against the actual
carved footprint, including cavern winding and diagonal fillers. An over-limit
route is rejected in favor of another room wherever a short connection works;
long passages are reserved for otherwise disconnected rooms or subnetworks.
Shared floor is counted only
once. `GeneratedDungeon.density` remains the achieved total walkable fraction,
not the room-only input target.

Room-first generation changes layouts for previously used seeds. The revised
algorithm remains reproducible for the same seed and options.

Base feature counts are **exact**, with no overlap. Puzzle gates add their own
`D` tiles beyond the requested door counts; progression puzzles replace all
down passages with independently gated stairways (at most one per puzzle),
as described below. Other features cannot replace the
literal neighbors required by doors or diagonals. Placement retries up to
12 layouts before reporting an error rather than silently reducing counts.
The same seed and options reproduce the layout, features, and SVG geometry.
Save the reported seed; ASCII stores the map but does not embed rendering options.

Generated stairs and ramps are **corridor-only**, never features inside rooms.
Their sides, corners, and closed end have a full one-square `#` buffer. The
only touching non-stone squares are other squares in the same stair/ramp run
and its one entry corridor. That entry has a protected two-square approach,
not a room, doorway, trap, or junction immediately beside the stairs. These
rules apply to optional single-level stairs/ramps as well as linked levels;
hand-authored ASCII maps remain supported without imposing generation rules.
Puzzle spirals are the exception: their 3x3 footprint must fit inside a complete
5x5 or larger floor area, with a clear one-square floor ring separating the
stairwell from walls and doorways. A chamber's bounding box alone is not enough.

The generator resolves stairway collisions in this order:

1. Place new stairways in another clear area of stone outside rooms, allowing
   enough space for the **entire length**, buffer, and both levels' approaches.
   Route an entry corridor to the new position. Collision-free positions are
   preferred over positions intersecting existing corridors.
2. If corridors intersect the reserved stairwell, reroute their full paths
   around it within the soft length limit, preserving their room connections
   and rough/worked terrain type where possible; room openings may change.
   Reroutes and new access branches follow the same
   no-crossing and explicit-junction rules as room passages.
   Inherited stairs cannot move: rooms and passages avoid their reserved
   clearances from the start.
3. If no short detour exists, remove the intersecting link and reconnect any
   separated components, trying short links to other nearby rooms before long
   links. Unnecessary long replacement links are omitted. Shared cells still
   used by surviving rooms or corridors are retained. If a base room would be lost, a junction
   becomes invalid, or a required entrance cannot be connected, retry the layout
   and ultimately report an explicit error if all attempts fail.

Retained corridor repairs are reported in the CLI.
Room areas and corridor lengths describe the retained layout, including added
stair access corridors. Layouts containing stairs can differ from earlier
generator versions even with the same seed.

```powershell
python generate_dungeon_map.py --width 80 --height 50 --seed 2026 --density 0.35 --room-size 45 --corridor-length 10 --rough-probability 0.6 --secret-doors 4 --concealed-doors 2 --traps 8 --pits 3 --stairs-down 2 --stairs-up 1 --ramps-down 1 --chamfer-probability 0.4 --output adventure.svg
python generate_dungeon_map.py --seed 42 --rough-probability 1 --meandering 0.9 --output caverns.svg
```

### Linked dungeon levels

```powershell
python generate_dungeon_map.py --levels 4 --stair-length 3 --stairs-down 2 --ramp-probability 25 --seed 42 --output keep.svg
```

This writes `keep-level-1.txt` / `keep-level-1.svg` through
`keep-level-4.txt` / `keep-level-4.svg`. A custom `--ascii-output` gets the same
`-level-N` suffix before its extension. Single-level filenames are unchanged.
All levels are generated and rendered before any output is written, so invalid
options or impossible placements do not leave partial generated maps.

With more than one level:

- Level 1 has exactly one up **stairway** to the surface, never a surface ramp.
- Each non-final level has the requested `--stairs-down` passages, or a seeded
  random count of 1-3 if omitted. Each is independently replaced by a ramp with
  the given percentage chance. `--ramps-down` adds guaranteed ramps per
  connection. Progression puzzles explicitly replace these down passages
  with independent gated stairways, up to the smaller of the original exit
  count and the number of passage puzzles, and report the replacement. Without such a puzzle,
  counts are preserved; at least one passage per connection is required.
- Every descending passage is copied to the next level at **all the same
  coordinates**, with the same length and axis. `e` becomes `E`, and `r`
  becomes `R` (spiral `s` becomes `S`). Up passages are inherited, not randomly placed. `--stairs-up`
  may be omitted or set to 0/1; other values and nonzero `--ramps-up` are errors.
- The bottom level has **no down stairs or ramps**, regardless of the requested
  per-connection counts.
- Stairways and ramps occupy `--stair-length` consecutive squares in terminal
  stairwells, with **one accessible landing per floor**. The sides and far end
  are stone: a corridor ends at the stairway rather than continuing through it
  on the same floor. The matching passage on the adjacent level opens at the
  opposite end. This also applies to the surface stairway.
- Stairwells and their entry approaches stay outside rooms on both levels.
  Clearance is reserved for the next level's opposite-facing approach, even
  though that end is closed on the current level. Corridors are rerouted or
  removed using the collision rules above before doors, traps, and other
  features are placed. Added access corridors can raise the achieved density
  above its target.

Level spacing is `stair_length * 10` feet: with the default length 3, floors
are 30, 60, 90, ... feet below the surface. Stairs descend at 45 degrees at
the default 10-foot square scale. Ramps use the same footprint and elevation
change. As with the original generator, rendering scale options only change
drawing scale, not generation or reported depths.

With `--levels 1`, no surface or linked passages are automatically added;
the existing optional one-square stair/ramp feature counts still apply.
`--stair-length` and `--ramp-probability` have no generation effect in that mode.
Single-level stairs now follow the same corridor-only clearance rules instead
of appearing inside rooms. With puzzles disabled, generation without
stairs/ramps is unchanged.

### Random puzzles and progression gates

The 50 puzzles in [dungeon_puzzles.md](dungeon_puzzles.md) are the live catalog,
loaded by `dungeon_puzzles.py`; keep both files together. The encounter key
includes the selected puzzles' setup, clues, solutions, failure guidance, and
rewards rather than requiring the TM to consult a separate catalog.

Exactly **35 of the 50 catalog puzzles (70%)** have added consequences.
Treasure-only puzzles have finite failure limits and permanently unavailable
prizes after exhaustion. The Broken King's Shadow and Pilgrim's Three
Offerings now protect local treasure vaults, never generated progression gates.
Escape traps and dungeon-access puzzles keep unlimited retries, with progressive
penalties capped at the dungeon level plus two. These caps reduce risk but
do not prevent deaths or party wipes; saves and combat resolve normally.
Bookkeeping uses one party-wide failure count per puzzle. Repeated temporary
effects replace their magnitude and refresh their duration rather than stacking;
prop and board resets do not clear them. Combat injuries resolve normally.
The TM key includes shared consequence rules, the actual dungeon level used
for scaling, and each selected puzzle's specific triggers and limits.
Failure counts persist across rest and resets; clue searches, questions,
practice, and refused illegal moves do not spend attempts.

```powershell
python generate_dungeon_map.py --levels 3 --seed 42 --output adventure.svg
python generate_dungeon_map.py --levels 3 --puzzle-probability 0.7 --max-puzzles-per-level 2 --output puzzles.svg
python generate_dungeon_map.py --levels 3 --puzzle-probability 1 --max-puzzles-per-level 1 --output one-per-level.svg
python generate_dungeon_map.py --puzzle-probability 0 --generate-encounters --output encounters-only.svg
python generate_dungeon_map.py --puzzle-probability 0 --output unstocked.svg
```

Each level rolls once for each puzzle slot. With the defaults (two slots, each
at probability 0.35), the probabilities are **42.25% for no puzzles, 45.5% for
one, and 12.25% for two**. At probability 0.7 they become 9%, 42%, and 49%.
These percentages apply while enough unused puzzles are eligible at the
current depth. Probability 1 fills every eligible slot; zero slots or probability
zero disables puzzles. Selection is uniform without replacement from the unused,
depth-eligible catalog, so a puzzle appears **at most once in the entire dungeon**.
Exhausting that eligible pool leaves slots empty and is reported, rather than
repeating puzzles or placing a deep-level puzzle too early. A deeper level
can unlock entries that were ineligible above it.

#### Deterministic strategy games

Puzzles 31-40 add four normal-play Nim variations, two historical chess mates,
two Capture Go ladders, Wythoff's game, and Chomp. Their rules, exact starts,
boards, winning strategies, and fixed opponent policies are included directly
in the generated TM key. All give the party the first move and restore the
**identical position** after a loss while attempts remain. Treasure games have
finite attempts; access games remain retryable, with any stated capped penalty.
The playing tokens are not repeatable treasure. Random selection and
consequence combat are separate from deterministic board-game play:
no board move or board-game outcome uses chance.

The Nim variants use three or four gem/coin piles, or markers on 3-by-9 and
4-by-9 boards labeled 0-8. All starting nim-sums are nonzero. Removing the
last object wins; these are not misere variants. The key explains how to
restore xor zero after every guardian move.

Chess uses the published Immortal Game continuation (mate in **3**) and the
Evergreen Game's announced mate (mate in **4**), with FENs, diagrams, citations,
and complete branches for every legal Black defense along the supplied White
strategy. The Immortal puzzle has **no move deadline**: three moves is its
shortest solution, not a limit. Failed games animate progressively more black
pieces, from one pawn to all 14 starting black pieces; after 14 failures its
reliquary seals permanently. Piece combat stats scale by dungeon level and
piece type. The Evergreen puzzle retains its visible **four-White-move**
counter, unlimited retries, and a capped failure penalty. Mate on the final
allowed move or earlier succeeds. The regular tabletop Immortal puzzle
appears only on **Levels 1-3**; the giant spectral Evergreen puzzle only on
**Level 4+**.

The Go entries are explicitly **five-by-five Capture Go**, not full-board
territory-scoring problems: capture the marked White chain within **3** or
**5 Black moves**. The shorter ladder is restricted to Levels 1-3 and the
longer to Level 4+. Every legal White defense is covered: a defender either
extends the ladder or permits an immediate capture; the last extension is
doomed at the edge. Normal captures, no suicide, and positional superko apply.
The generator validates these ladders and the Nim/Wythoff/Chomp starts with
standard-library code in `dungeon_games.py`. Full chess legality and exact
minimum mate lengths are verified by the strategy regression tests.

Depth restrictions do not guarantee every new puzzle will appear in a given
dungeon. A single-level dungeon cannot select the longer chess/Go entries;
unused shallow-only entries also cannot be placed on deeper levels.

#### Escape-room codes and hidden evidence

Puzzles 41-50 add dungeon-themed cipher rooms: a fallen adventurer's gear,
an apprentice's study, a tomb painter's chamber, a monastery library, a
smuggler's cache, a mine survey station, a bellmaker's workshop, an observatory,
a field infirmary, and a cartographer's outpost.

Each has **2-4 genuine hidden clues and 2-4 hidden decoys**, with individual
**DC 17 or 20 WIS searches**, exact hiding places and discovered text, an
intact visible cipher key, and a complete solution. The key and its public
instructions are room fixtures, not additional hidden clues. Substitution,
letter shifts, reversal, coordinate and book lookups, binary lamps, signal
codes, ordering, letter extraction, and a serpentine reading route yield
numeric, letter, or symbol passwords.

The TM key labels genuine evidence and decoys separately, but the TM should
reveal only the object's text and observable identifying marks to players.
Every decoy can be excluded using a visible rule such as the wrong seal,
date, material, or orientation; no arbitrary guess about which clue the TM
prefers is necessary. All required evidence is inside the puzzle room.

Discovery rolls happen **during play**, not during dungeon generation:
basic roll + WIS modifier + applicable bonuses must meet the listed DC.
These are ordinary clue searches, with no class restriction or trap-specific
penalty. A failed search costs an exploration turn and may be retried;
precise inspection of the actual hiding place reveals its clue without a
roll. Failures never remove clues or permanently lock the solution.
Wrong-code responses and recovery hints are given separately for each puzzle.
Neither codes nor the genuine/decoy classifications are added to the SVG.

The study, library, mine, observatory, and cartographer puzzles use the existing
progression-gate geometry. The others protect local treasure or provide a
temporary escape-room challenge. All ten use the existing nonrepeating
selection pool and are eligible on any level; probability defaults are unchanged.

#### Generation and placement

Generation proceeds in order: generate Level 1, stock its encounters, select
and install its puzzles, finalize its exits, then generate Level 2 with those
inherited exits. The same process continues downward. Puzzle selection has
its own seeded random stream; stocked levels in puzzle mode also use seeded
per-level encounter streams. Seed replay reproduces layouts, loot, selections,
and required-item locations. Disabling puzzles preserves the original layout
and encounter-generation streams.

**Layout changes:** Same-level passage puzzles prefer reusing safe existing
edge rooms. A six-square gated passage connects the puzzle room to a new
5-by-5 guarded encounter room, with no stairs in that branch. When there are
not enough safe existing chambers, placement falls back to an independent
edge wing instead of erasing stocked rooms or allowing bypass corridors.
Expansion accommodates new chambers and inherited stairwells; the CLI and
debug log report expansions and actual stair replacements. Corridor and room
metadata, ASCII, SVG, and encounter labels describe the final layout.
Requested density and average room size remain soft targets.

Local puzzles (chests and temporary escape rooms) do not change the level's
stairs. Every puzzle room is reachable without
solving another puzzle; local challenges are not hidden behind progression gates.
The ogre's and wizard's reward keys open their respective progression gates,
rather than being unassigned keys. A same-level passage
puzzle has a **real `D` gate** at the exit of its chamber, with a corridor beyond
it. The TM key identifies the exact gate coordinate and all protected area
numbers. Treat it as impassable until solved, not as an ordinary pickable lock;
ASCII connectivity and SVG rendering represent the solved, passable state.
Puzzle contents and solutions never appear on the player SVG.

- Same-level passage puzzles guard their own separate encounter rooms, never
  a nested continuation or a down stairway. Selecting these puzzles alone
  leaves the original down exits intact.
- Catalog stair puzzles **3, 8, 13, 15, 26, 30, and 39** always contain a
  circular **3-by-3 spiral staircase inside their own chamber**, which is at
  least 5-by-5. The generator reuses a suitable existing encounter chamber:
  the puzzle's encounter label, the spiral's entire footprint, and its landing
  stay together in that room. No passage leads from the puzzle to a remote
  staircase. If no existing chamber fits safely, the added chamber contains
  both the puzzle and its stairs. They do not receive a separate guarded reward chamber.
  Previously generated down stairs and ramps are replaced **only when an
  actual stair puzzle is selected**, not merely because another passage
  puzzle was selected.
- On a non-final level, stair-puzzle footprints and landings match the up
  spirals on the level below. Each has a **linked seal at both ends** that
  opens only when its own puzzle is solved; the lower-level key includes
  the corresponding seal instructions. After release, travel is two-way.
  With multiple puzzle exits, solving any one permits descent, but returning
  through another stairway never bypasses its unsolved seal. Maps render the
  solved, passable state.
- On the final level, including a one-level dungeon, a selected stair puzzle
  explicitly leads to an **unmapped lower level**. It is not silently
  converted into a same-level reward gate or another puzzle type.
- Gates never form a serial chain. Opening one gate reveals only its own
  encounter area; other branches remain locked until their own puzzles are solved.
  Catalog shortcuts and emergency releases never bypass a branch's gate.

The first guarded encounter branch receives the level's highest-ranked treasure;
subsequent branches receive the next-highest-ranked hoards, each **together with its
guarding encounter, container, lock, and chest trap**.
Floor traps stay at their original locations. Loot is moved, not duplicated.
If the bottom level has a gated section, a final stocking pass exchanges hoards
as necessary to put the **entire dungeon's** highest-ranked generated treasure
in its first branch, not merely the best treasure originally rolled on that floor.
All levels then redistribute their best remaining hoards among their independent
guarded encounter branches. This pass does not
move map features or required puzzle items, so their keyed locations stay valid.
Ranking compares permanent/reusable magic-item count first (including wands
and staves), then potion/scroll count, then the combined coin and gem value
converted to copper pieces. Thus any permanent magic outranks any quantity of
consumables, and any magic outranks monetary treasure; money breaks remaining
ties. One of equally ranked best hoards is sufficient. Each guarded encounter branch receives at
least **100 sp of treasure value or magic**, topping up poor/empty rewards when
necessary (an empty reward becomes an unlocked chest). A branch without a
guarding encounter receives a guaranteed encounter from the normal depth-based
monster table, independently of the ordinary monster-presence threshold.
This moved encounter hoard and its minimum value are separate from the
puzzle's own prize; neither duplicates the other.

**Puzzle prizes:** Every selected puzzle has its own exact rolled prize,
stored separately in `EncounterArea.puzzle_reward` and rendered as a list
in the TM key. The roll gives **40%: 1d3 pieces of jewelry; 40%: 1d6 gems;
20%: one magic item**. Prices, powers, and depth-dependent results use the
existing wandering-monster treasure tables at the puzzle's dungeon level.
These concrete generated prizes replace illustrative catalog rewards rather
than adding a second copy of those rewards or of a guarded encounter hoard.

**Required items:** External puzzle items are physically stored in their
source encounter area's `EncounterArea.puzzle_items` and listed in that
area's **Treasure** list, not merely mentioned in a placement note. Placement
prefers the reward of an earlier, solvable puzzle, but excludes prizes that
can become permanently sealed after finite failures. Otherwise it uses
accessible non-puzzle encounter loot on the same or an earlier level.
Every prerequisite remains obtainable before its destination puzzle;
it is never placed in that puzzle's own room or behind its own gate.
Item placement does not depend on an ordinary treasure roll.

The TM key gives both directions: puzzle notes name each item's source
**Level/Area**, and the source Treasure entry names the physical item and its
destination **Level/Area and puzzle title**. Generated locations supersede
the catalog's illustrative studies, workshops, guardrooms, and other locations.
References are resolved after final chamber numbering, so an earlier area's
Treasure list includes items needed by later puzzles. Hoard redistribution
does not duplicate or relocate these required items.

Before writing output, the generator checks that solved maps are connected,
closed progression gates cannot be bypassed, reward branches do not overlap or
nest, protected encounter areas contain valuable guarded loot and no stairs,
stair puzzles have their in-room spiral and applicable lower-level seals,
every prerequisite is accessible before its puzzle, IDs are unique, and
adjacent stair footprints match. Impossible safe
wing connections produce an explicit error rather than an unkeyed or bypassable
puzzle; try a larger map, fewer crowded features, or another seed.

### Encounters, treasure, and traps

```powershell
python generate_dungeon_map.py --levels 10 --seed 42 --generate-encounters --encounter-chance 11 --output keep.svg
```

This adds numbered chamber labels to every level's SVG and writes one
`keep-encounters.md` covering all levels, plus a separate `keep-encounters.log`
for debugging. With a single level, it writes `keep.svg`, `keep.txt`,
`keep-encounters.md`, and `keep-encounters.log`. The Markdown and log filenames
are derived from the original `--output` stem, independently of `--ascii-output`. All output
paths must differ. Enabled puzzles imply stocking and these outputs even if
a particular level rolls no puzzles. With `--puzzle-probability 0`, include
`--generate-encounters` to retain stocking, or omit that flag for the original
unstocked output without numbers, a Markdown document, or a debug log. The
flag takes no `true`/`false` value.

Numbers restart at 1 on each level, in reading order: label rows from top to
bottom, and left to right within each row, starting at the upper left.
They identify the retained worked rooms and caverns, not corridors or stairways.
Labels use actual chamber footprints and
prefer plain floor near the chamber's center, avoiding feature symbols. A
fully trap-filled chamber uses a small label above its feature symbol instead.
The SVG `encounters` group contains editable labels with `data-area`,
`data-column`, and `data-row` attributes. Numbered Markdown entries use only
their area number, without row/column coordinates. Coordinates remain in the
debug log, SVG metadata, and the unnumbered trap/door keys, using one-based
(column, row), with the top-left square at (1, 1).

The Markdown contains encounter descriptions, treasure quantities and item
effects, and playable trap/door details (including detection DCs and saving
throws), not generation rolls or rule-table diagnostics. The `.log` records
the seed, rule-table rulings, per-level table bands, and per-area monster
presence/selection rolls, monster quantities, treasure checks, coin and gem
rolls, and magic-item category/subtype/power/charge rolls. It is generated from
the same stored results without rerolling. Numbered entry headings are just
the number (for example, `### 1`), without "Area". Absent monsters and traps
are omitted, as are empty gem/magic categories. Monsters without treasure
explicitly show **Treasure:** None. Otherwise absent treasure is omitted.
An entry with no monsters, treasure, traps, puzzle, or required puzzle items
contains only `Empty`.
Empty level-wide trap and door keys are omitted too.

The encounter Markdown is a secret document for the TM to read from as players
explore; it does not print a "TM only" notice. The debug log is also private
and is for debugging, not the adventure handout.

Stocking uses a separate random stream derived from the map seed. Enabling it
does not change layout, doors, explicit trap counts, stairways, wall texture,
or ASCII output. The same seed and options reproduce the entire key and log.
Reading-order numbering relabels existing contents without changing which
chamber receives those contents for a given seed. ASCII
does not store chamber identities or encounter contents; converting it with
`ascii_map_to_svg.py` does not restore encounter numbers. Regenerate with the
original options/seed, or retain the Python encounter metadata to rerender labels.

`dungeon_encounters.py` reads the encounter, money, gem, magic-item, and creature
level tables directly from the repository's `TreasuresAndTrollsBasicMD.md`,
resolved relative to the module (not the current working directory). Missing
or malformed required tables produce an error before output is written.
Monster selection uses the level 1-3, 4-6, or 7-9 column; **all dungeon levels
above 9 continue using 7-9**. Quantities such as `d4 + 1` are rolled separately.
Adventuring parties include a random count, alignment, and roster with race,
class, and level; they are not complete character sheets.

Every generation basic roll sums exactly three independent integers in 0-11.
**There are no symbol rerolls**, including treasure checks and magic-item
power. The user's no-rerolls rule overrides the power-table paragraph.
Monster presence succeeds on a roll **equal to or greater than**
`--encounter-chance`: 0 always gives a monster, while 33 requires three 11s.
The default is 11. This chamber-stocking threshold is separate from the rules'
periodic wandering-encounter check.

Each chamber checks for treasure, including unoccupied chambers. Treasure
requires DC 21, with coins rolled once per creature at its listed monster
level. Gems use basic + creature count >= 23, with d6 individual values; magic
uses DC 25, +2 per level above 5, then d3 items. Items receive a table-selected
type/subtype, power, and charges where applicable. Dragon hoards are guaranteed:
use dragon level + 2, multiply gold-converted coins by 10, double gems and
magic-item counts, and automatically pass the magic check. Magic still needs
detection and identification during play.

For dungeon encounters, **the numbered chamber is the monster's lair**:
treasure is in that chamber, not in another nearby location. Dragons also
remain in their chamber lairs; there is no wilderness-distance roll.
The existing treasure-presence check still determines whether there is loot.

For each area with treasure, a separate basic roll of **17+** stores all of
it in a chest; otherwise it is in a bag or pack. Only a chest receives a
trap check: **19+** makes it trapped. A separate **17+** lock check makes
the chest locked; a lower roll leaves it unlocked. Locking is independent
of trapping, so locked and unlocked chests can both be trapped.
Override these generation thresholds with `--treasure-chest-dc`,
`--chest-trap-dc`, and `--chest-lock-dc`. Each accepts integers 0-34:
0 guarantees success and 34 guarantees failure on the 0-33 basic roll.
There is no separate bag DC; bag/pack is the alternative when the chest
check fails. These DCs are **not player checks to find, open or disarm**
the container. The key simply labels treasure as **Locked chest**,
**Unlocked chest**, **Bag**, or **Pack**, followed by its contents; it does not
repeat that the cache is in this chamber. Generation rolls, including the
lock check, stay in the debug log, not the encounter text.

```powershell
python generate_dungeon_map.py --generate-encounters --seed 42 --treasure-chest-dc 17 --chest-trap-dc 19 --chest-lock-dc 17 --output keep.svg
```

Trapped chests have an opening-triggered poison needle or gas trap, with
saving throws and poison timing described under **Chest trap** in the key.
They are additional to chamber hazards and explicit T traps, do not add
ASCII symbols, and do not change exact feature counts. Container generation
uses its own seeded random stream, so changing the container DC overrides
does not change monsters, treasure quantities/items, or other map traps.
Lock generation has a separate stream too: changing `--chest-lock-dc`
does not change containers, chest traps, or any other generated contents.
The class-specific adjudication guidance below still applies; chest-trap
generation does not implement the previously documented class-rule changes.

Each chamber without an explicit T feature independently checks basic >= 23
for an improvised trap, regardless of monsters or treasure. These random traps
are keyed by chamber number in Markdown and **do not add ASCII T symbols** or
change exact `--traps` / `--pits` counts. Every existing T symbol, including
those in corridors, also receives a coordinate-keyed trap description.
Traps include pits, blades, falling masonry, poison needles, and poison gas.
Entries specify triggers, detection/disarming DCs, saving throws, attack power,
and relevant poison onset/duration. Resolve saves and wounds during play using
victim abilities and toughness; damage uses the rules' wound system, not hit
points. Player saving throws retain symbol rerolls.

Every secret and concealed door receives its own coordinate-keyed WIS check:
**secret DC 20 (Medium)** versus **concealed DC 17 (Easy)**. Roll basic + WIS
modifier + applicable level/class bonus and meet or exceed the DC; no symbol
rerolls apply to detection.

The debug log records the generator's rulings for source-table gaps:

- The misplaced second encounter row 16 is treated as 22; magic-item roll 12
  uses Misc alongside 13; the missing adventurer class roll 28 uses Cleric.
- Missing monster levels use dungeon level and are flagged in the debug log.
  Empty caches use one creature-equivalent at dungeon level. All treasure
  table lookups are capped at level 10; mixed parties use the highest creature
  level for gems and magic. Adventurer levels cannot fall below 1.
- Gem checks follow the stated +1 per creature rather than the inconsistent
  example. Magic-power thresholds use inclusive DC comparisons.
- Dragon type is selected uniformly from the six listed dragons. Bracers grant
  their power bonus to toughness because no bracer effect is defined. Healing
  powers above +4 use the highest defined effect, Raise dead.
- The printed minor-wound threshold 26 is treated as 16, preserving the
  progressive wound thresholds 13/16/19/22/25. Trap designs and concealed-door
  difficulty are generator rulings, not new claims about the source rules.

### Trap checks by character class

**Current generator limitation:** `dungeon_encounters.py`, function
`trap_description`, gives every trap the same unqualified detection DC 20
(WIS), bypass/disarm DC 20 (DEX), and activation on every failed disarm.
There is no Thief/non-Thief distinction in that text. Detection matches the
general action example, but disarming omits INT and does not match the Thief's
base DC or failure margin. The guidance below is for TM adjudication; it
**does not change generator code, existing encounter files, or logs**.

#### What the T&T rulebook specifies

References below are to `TreasuresAndTrollsBasicMD.md`.

| Action | Printed guidance | Source |
| --- | --- | --- |
| General trap detection | Medium action, DC 20 (WIS), with no class restriction stated | Standard Action Difficulty Classes, lines 153-175 |
| Thief detection | Base DC 15 (WIS), adjusted for how well the trap is concealed | Thief, line 1117 |
| Thief technical disarming | Base DC 17 (DEX + INT), adjusted for construction difficulty | Thief, lines 1115-1119 |
| Thief disarm failure | The trap activates if the modified check misses the DC by **more than four** | Thief, line 1119 |
| Non-Thief technical disarming | No dedicated procedure or blanket prohibition is stated; the general action framework supports TM adjudication | Standard Action Difficulty Classes, lines 185-187; Thief, line 1119 |

**Non-Thieves have guidance for detecting traps at all:** finding traps appears
among the general actions. The rules gap concerns a dedicated non-Thief
technical-disarming procedure, not an absence of all non-Thief detection rules.
The Thief's specialist skill is easier and improves with class progression.

General checks normally receive +1 per four levels unless otherwise noted
(Basic Dice Check Roll, line 149). Thief skills receive +1 per level above
first, or `level - 1` (Thief, line 1111). These passages do not explicitly
resolve stacking the general bonus with the Thief skill bonus: use the
applicable class progression rather than silently presenting both as an
unambiguous combined bonus.

Clerical spells also provide non-Thief detection. **Detect Poison** can
indirectly reveal a poisoned trap within 10 feet, subject to its visibility
conditions (lines 1211-1214). Level-2 **Find Traps** detects traps within
40 feet when the trap or trigger is in line of sight and reveals triggers
and safety switches. It does not reveal a required switch sequence or
automatically neutralize the trap (lines 1275-1278).

#### Selected campaign ruling

This is the chosen **campaign house rule**, not a claim that the printed
rulebook or every D&D edition imposes these restrictions. It replaces the
general DC 20 detection example for campaign trap adjudication, while retaining
the native Thief skill baselines:

| Action | Campaign check |
| --- | --- |
| Thief detects | Basic roll + WIS modifier + applicable Thief skill bonus >= the trap's detection DC |
| Non-Thief detects | Basic roll + WIS modifier + applicable general level bonus **- 4** >= the same detection DC; no Thief skill bonus |
| Thief technically disarms | Basic roll + DEX modifier + INT modifier + applicable Thief skill bonus >= the trap's disarm DC |
| Non-Thief technically disarms | Not permitted; no technical-disarm roll |

The ordinary **detection baseline is DC 15**, not a fixed DC for every trap.
The TM can set a lower DC for an easier trap or a higher DC for a more
concealed trap. Before ability and level bonuses, a non-Thief needs 19 for a
DC 15 trap, 22 for an illustrative harder DC 18 trap, or 16 for an easier
DC 12 trap. Apply the -4 penalty **once**; do not also raise the displayed DC
by four.

The ordinary **disarm baseline is DC 17 (DEX + INT)**, adjusted for the trap's
construction. A modified result equal to or above the DC succeeds. Missing
by 1-4 is unsuccessful but does not trigger the trap solely from that failed
check; missing by 5 or more triggers it. For an unmodified DC 17, a final
result of 13 misses by four, while 12 misses by five.

Thief-only technical disarming does **not** prohibit physical avoidance,
bypasses, or explicit spell effects. A non-Thief may go around a known
pressure plate, bridge a pit, or propose another plausible way past a trap.
The TM adjudicates the actual action and any risks; spotting the mechanism
is not automatically disarming it. Neither this ruling nor a detection spell
grants unlimited retries or automatic neutralization.

Detection/disarming checks are distinct from saving throws to avoid a
triggered trap. Under this project's previously selected reroll policy,
basic checks sum three dice valued 0-11 **without symbol rerolls**; player
saving throws retain symbol rerolls. That restriction is a project ruling,
not the literal general reroll wording of Basic Dice Check Roll (line 147).

#### Historical D&D comparison

D&D has not used one universal Thief-only rule across editions. The comparison
supports distinguishing general observation, specialist skills, and practical
bypasses, but the chosen -4 penalty and technical-disarm restriction remain
campaign decisions.

| Edition and source | Detection and disarming distinction |
| --- | --- |
| B/X (1981), [historical commentary](https://nilisnotnull.blogspot.com/2013/07/thieves-and-traps-in-bx-d.html) | The commentary quotes Moldvay B22 allowing any character a 1-in-6 trap search and dwarves 2-in-6, while noting contradictory Thief-only wording at B10. This is **secondary evidence**, not an independently inspected original rulebook or an unambiguous universal prohibition. |
| D&D 3.5, [SRD Trapfinding](https://www.d20srd.org/srd/classes/rogue.htm#trapfinding) and [Disable Device](https://www.d20srd.org/srd/skills/disableDevice.htm) | Trapfinding gates searches above DC 20 and technical disarming of magical traps. Disable Device is trained-only, but trained non-Rogues can disable mundane traps, including complex ones; the search restriction is not a blanket ban on disarming mundane devices above DC 20. The SRD separately describes physical ways to defeat traps. |
| D&D 5e (2014), [official Basic Rules: Detecting and Disabling a Trap](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/running-the-game#DetectingandDisablingaTrap) | Detection uses character checks, with tools/checks for disarming rather than Rogue-only access. Any character may attempt Arcana checks for magical traps, subject to the trap's rules. Clear observation, clever physical solutions, and spell effects can also matter. |

These findings do not establish the rules of unverified OD&D/AD&D editions,
and retroclones are not treated as original D&D sources.

#### Importing D20 trap DCs

**Appendix A - D20 System** (lines 2992-2996) specifies:
`T&T DC = imported D20 DC + 6`. Ordinary bonuses and penalties convert 1:1.
For example, an imported D&D DC 15 becomes T&T DC 21, but T&T's native Thief
detection/disarm baselines **15/17 remain 15/17**, and the non-Thief modifier
**-4 remains -4**. Do not double-convert native T&T values.

This is the rulebook's play conversion, not identical success probabilities
between a uniform d20 and the three-die bell curve. The +6 adjustment applies
to imported D20 DCs, not historical percentile or 1-in-6 trap checks.

## Python API

```python
from dungeon_map import GenerationOptions, generate_dungeon, render_rows, svg_document

svg = render_rows(["#####", "#...#", "#####"], seed=42)
result = generate_dungeon(GenerationOptions(width=40, height=30, seed=42))
svg = svg_document(result.grid, seed=result.seed)
ascii_text = result.grid.to_ascii()

stack = generate_dungeon(GenerationOptions(
    levels=3, stair_length=4, stairs_down=2, ramp_probability=25, seed=42,
))
for level in stack.levels:
    print(level.depth_feet, level.grid.to_ascii())
    svg = svg_document(level.grid, seed=stack.seed)

from dungeon_encounters import generate_encounters, encounter_document, encounter_log

contents = generate_encounters(stack, encounter_chance=11,
                               treasure_chest_dc=17, chest_trap_dc=19, chest_lock_dc=17)
guide = encounter_document(stack, contents, encounter_chance=11)
debug_log = encounter_log(stack, contents, encounter_chance=11)
for level, key in zip(stack.levels, contents):
    svg = svg_document(level.grid, seed=stack.seed, encounter_labels=key.labels)
```

`parse_ascii(text)` constructs a padded `DungeonMap`; `validate_map(grid)`
checks adjacency rules. `svg_document` validates automatically.
`is_connected(grid)` additionally checks traversable connectivity, respecting
partition walls; disconnected hand-authored maps are allowed by the renderer.
`GeneratedDungeon` exposes the seed, room areas, corridor lengths, and density.
Its `room_cells` stores the retained chamber footprints as tuples of zero-based
`(x, y)` coordinates, in the same order as `room_areas`. Encounter numbers use
label reading order instead; each `EncounterArea.cell` identifies its chamber
and `EncounterArea.debug` retains its generation diagnostics.
`EncounterArea.container` is `chest`, `bag`, `pack`, or `None` when there is
no treasure; `chest_trap` holds the trap description only for a trapped chest.
`chest_locked` is `True` or `False` for generated chests, and `None` for bags,
packs, or areas without treasure.
For compatibility, `result.grid` and its statistics describe the first level.
`result.levels` is a tuple of all levels in surface-to-bottom order, including
that first level. Each level exposes `depth_feet` and `stairways`, whose entries
contain `cells`, `tile`, `horizontal`, and `landings` (the two endpoint
coordinates). `entrance` identifies the accessible landing on this floor;
`closed_end` is stone here and opens on the adjacent level. `approach` contains
the two entry corridor squares; `walls` includes the stone sides and corners.
`clearance` includes both levels' approach reservations. `layout_notes`
reports corridor rerouting/removal and unreachable-room removal.
Single-level results also expose any requested `stairways` and use depth 0
(no implied surface elevation).
`GenerationOptions.stairs_down=None` selects the mode-dependent default.
API validation errors raise `ValueError`; CLI errors print to stderr and exit
nonzero. Existing output files are overwritten, but input/output collisions and
identical ASCII/SVG output paths are rejected.

Run the focused tests from `campaigns\ur`:

```powershell
python -m unittest test_dungeon_map
```

For the shared generator and strategy-game proofs, run from `tools`:

```powershell
python -m unittest test_dungeon_map test_dungeon_puzzles test_dungeon_games
```

The `chess` package is **test-only** (install with `python -m pip install chess`
if it is not already available); the generator still requires only Python's
standard library. The chess tests reconstruct the source-game positions,
check every defending branch, and independently search all legal moves to
verify both the claimed mate and the impossibility of a shorter forced mate.
