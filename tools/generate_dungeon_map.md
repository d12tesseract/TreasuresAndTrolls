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

The generator writes `dungeon.txt` as well as `dungeon.svg`. Both programs use
`dungeon_map.py` for validation, wall geometry, symbols, and physical scaling.
The generator also uses that module for layout and feature placement.  
`generate_dungeon_map.py` also uses `dungeon_encounters.py` to generate random 
encounters in the dungeon if needed.

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
| space | Open floor with smooth worked walls |
| `.` | Open floor with rough cavern/hewn walls |
| `\` | Diagonal from top left to bottom right |
| `/` | Diagonal from bottom left to top right |
| `\|` | Smooth floor with a wall on its left |
| `_` | Smooth floor with a wall on its bottom |
| `L` | Smooth floor with walls on its left and bottom |
| `D` | Normal door |
| `S` | Secret door |
| `C` | Concealed door |
| `T` | Trap |
| `P` | Covered pit trap |
| `E` / `U` | Stairs down / up |
| `R` / `I` | Ramp down / up |

For example, this map joins a worked room to a cavern through a door:

```text
#############
#   #####...#
#   D.......#
#   #####...#
#############
```

### Diagonals, partitions, and doors

Diagonals represent a half-open square, **always with smooth floor**. For `\`,
the open neighbors must be north+east **or** south+west. For `/`, they must be
north+west **or** south+east. Both open neighbors must be literal spaces; both
remaining neighbors must be `#`. Periods and feature tiles are not allowed in
these four positions. The diagonal itself is the exposed wall of the solid
triangle; no extra square-edge walls are drawn across the open triangle.

`|` and `L` require a literal space to their left. `_` and `L` require a literal
space below. Their partitions are rendered once, even though both sides are
floor. These tiles are available in authored maps but are not generated.

`D`, `S`, and `C` require either north+south or east+west neighbors that are
literal spaces or periods, with `#` on the perpendicular sides. The two open
neighbors may have different terrain. Junction doors and doors directly
adjacent to other feature tiles are rejected. Doors span the passage width.

Feature tiles replace the floor character. A touching group of feature tiles
inherits rough wall texture only when it borders rough floor and no smooth
floor. Otherwise it is smooth, including isolated groups with no terrain to
infer from. Diagonal floor and partition tiles count as smooth terrain.

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
their diagonal corners are unaffected.
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
add `S`/`C` labels. Traps use an X and `T`; covered pits use a dashed square
and `P`. Stairs use treads, ramps use tapering sides, and both use arrows plus
their ASCII letter. In east-west passages their drawing rotates to match;
in north-south passages and ambiguous room locations it uses a north-south
axis. Down arrows point north (east when rotated), up arrows point the other
way. The labels make elevation direction explicit.

A straight, contiguous run of the same stair/ramp letter, such as `EEE`,
represents one passage spanning that many squares. The renderer draws one
full-length symbol, aligned to the run even in an open room. A single letter
uses the original one-square symbol and passage-based orientation; bent or
branching letter clusters retain individual symbols. This notation survives
ASCII editing and conversion back to SVG without a separate metadata file.
The multi-level generator aligns these runs between adjacent floors.

| Option (both programs) | Default | Meaning |
|---|---|---|
| `--feet-per-pixel` / `--feet-per-square` | `10` | Feet represented by one ASCII square |
| `--feet-per-inch` | `50` | Map feet per printed SVG inch |
| `--line-width` | `0.01` | Stroke width in printed inches |
| `--seed` | ASCII: `0`; generator: random | Reproducible rough geometry and generated layouts |
| `--roughness` | `0.12` | Maximum wall jitter in squares, from `0` to `0.2`; also sets the automatic corner radius |
| `--corner-radius` | automatic | Rough corner radius in map squares, `0` to `0.5`; maximum diameter is one square |
| `--rough-segments` | `6` | Line pieces per rough tile edge, from `2` to `32`; corner arcs use at least 6 pieces |
| `--player-view` | off | Hide `T`/`P` and draw `S`/`C` as ordinary wall segments |

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

The generator places separated rectangular worked rooms and irregular,
connected cavern footprints, then joins each new room to the nearest existing
room with an orthogonal corridor. Corridors are rough when both endpoint rooms
are rough, otherwise smooth; existing room/corridor terrain is preserved where
paths cross. Rough corridors meander by replacing short sections of that direct
route with lateral detours, rather than carving a straight shortcut alongside
them. Detour legs and intervening straight sections are 2-3 squares long,
except where room entrances, the original bend, or the destination interrupt
a section. Each detour returns farther along the original route, so passageways
always make progress toward their target. They deviate at most 3 squares from
that route, stay inside the map border, and keep a stone gap to nearby rooms
and other route segments.

`--meandering` sets the probability of taking an eligible detour: `0` restores
the original direct orthogonal corridors, `1` uses every available opportunity,
and the default is `0.6`. Lower settings leave longer straight stretches.
Insufficient space can prevent a detour even at `1`. Worked-stone corridors
are unaffected. Every generated walkable square remains connected, treating
doors and covered pits as passable.

| Option | Default | Meaning |
|---|---|---|
| `--width`, `--height` | `60`, `40` | Base map dimensions in squares, each at least 7; puzzle wings can increase width |
| `--levels` | `1` | Positive number of levels; 1 generates a single floor without automatic stairs |
| `--stair-length` | `3` | Positive integer length of each multi-level stairway or ramp, in squares |
| `--ramp-probability` | `0` | **Percentage, 0-100**, that a multi-level down stairway becomes a ramp |
| `--room-size` | `35` | Target average room floor area in squares, at least 4 |
| `--corridor-length` | `8` | Target new corridor squares per connection, positive |
| `--meandering` | `0.6` | Rough-corridor detour probability, from `0` (off) to `1` (maximum) |
| `--density` | `0.3` | Target open fraction of all map squares, strictly between 0 and 1 |
| `--rough-probability` | `0.4` | Probability each room is a cavern |
| `--door-probability` | `0.45` | Normal door probability at an eligible room entrance |
| `--secret-door-probability` | `0.1` | Secret door probability at an eligible entrance |
| `--concealed-door-probability` | `0.05` | Concealed door probability at an eligible entrance |
| `--doors`, `--secret-doors`, `--concealed-doors` | unset | Exact counts, overriding their respective probabilities |
| `--traps`, `--pits` | `0` | Exact trap / covered pit counts |
| `--stairs-down` | single: `0`; multi: random `1-3` | Exact one-square down stairs in single-level mode; passages per connection in multi-level mode, subject to ramp replacement |
| `--stairs-up` | `0` | Exact one-square up stairs in single-level mode; automatic in multi-level mode |
| `--ramps-down`, `--ramps-up` | `0` | Exact one-square ramps in single-level mode; multi-level down ramps are additional guaranteed passages, up ramps are automatic |
| `--chamfer-probability` | `0` | Probability of converting an eligible smooth room corner to a diagonal |
| `--generate-encounters` | off | Force ordinary encounter stocking when puzzles are disabled; enabled puzzles already imply stocking and TM output |
| `--puzzle-probability` | `0.35` | Independent probability, 0-1, for each puzzle slot per level; 0 disables puzzles |
| `--max-puzzles-per-level` | `2` | Number of independent puzzle slots, integer 0-40; 0 disables puzzles |
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
room spacing, and corridor intersections constrain them. Room dimensions vary,
are at least 3 by 3 before cavern shaping, and are capped to fit the map.
The program reports achieved open area, counting diagonal squares as half a
square. High densities or small maps may fall short; adding the last room can
overshoot. Corridor length counts newly carved squares outside room footprints,
not the distance between room centers. Longer target corridors generally use
more rock separation, but are not guaranteed for every pair of rooms. Room
spacing is chosen using the direct route length; meanders add extra corridor
squares afterward, and those squares count toward achieved corridor lengths
and map density.

Base feature counts are **exact**, with no overlap. Puzzle gates add their own
`D` tiles beyond the requested door counts; progression puzzles replace all
down passages with one gated stairway, as described below. Other features cannot replace the
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

The generator resolves stairway collisions in this order:

1. Place new stairways in another clear area of stone outside rooms, allowing
   enough space for the **entire length**, buffer, and both levels' approaches.
   Route an entry corridor to the new position. Collision-free positions are
   preferred over positions intersecting existing corridors.
2. If corridors intersect the reserved stairwell, reroute their full paths
   around it, preserving their endpoints and rough/worked terrain type.
   Inherited stairs cannot move: rooms are placed outside their reserved area
   from the start, and any crossing corridors must take the detour.
3. If no detour exists, remove the entire intersecting corridor, then remove
   rooms and corridor branches left unreachable. Shared cells still used by
   surviving rooms or corridors are retained. Required stairway entrances are
   never discarded: an impossible connection triggers a new layout attempt
   and ultimately an explicit error if all attempts fail.

Rerouted or removed corridors and unreachable rooms are reported in the CLI.
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
  connection. A progression puzzle explicitly replaces all these down passages
  with one gated stairway and reports the replacement. Without such a puzzle,
  counts are preserved; at least one passage per connection is required.
- Every descending passage is copied to the next level at **all the same
  coordinates**, with the same length and axis. `E` becomes `U`, and `R`
  becomes `I`. Up passages are inherited, not randomly placed. `--stairs-up`
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

The 40 puzzles in [dungeon_puzzles.md](dungeon_puzzles.md) are the live catalog,
loaded by `dungeon_puzzles.py`; keep both files together. The encounter key
includes the selected puzzles' setup, clues, solutions, failure guidance, and
rewards rather than requiring the TM to consult a separate catalog.

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
in the generated TM key. All give the party the first move and unlimited free
retries from the **identical position** after a loss; the playing tokens are
not repeatable treasure. Random selection of a dungeon puzzle is separate
from playing it: no move or outcome uses chance.

The Nim variants use three or four gem/coin piles, or markers on 3-by-9 and
4-by-9 boards labeled 0-8. All starting nim-sums are nonzero. Removing the
last object wins; these are not misere variants. The key explains how to
restore xor zero after every guardian move.

Chess uses the published Immortal Game continuation (mate in **3**) and the
Evergreen Game's announced mate (mate in **4**), with FENs, diagrams, citations,
and complete branches for every legal Black defense along the supplied White
strategy. A visible move counter counts **White's moves**, not both players'
moves or real time. Mate on the final allowed move or earlier succeeds; draws
or expiration reset the board. The regular tabletop mate in 3 appears only
on **Levels 1-3**; the giant spectral mate in 4 appears only on **Level 4+**.

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

#### Generation and placement

Generation proceeds in order: generate Level 1, stock its encounters, select
and install its puzzles, finalize its exits, then generate Level 2 with those
inherited exits. The same process continues downward. Puzzle selection has
its own seeded random stream; stocked levels in puzzle mode also use seeded
per-level encounter streams. Seed replay reproduces layouts, loot, selections,
and required-item locations. Disabling puzzles preserves the original layout
and encounter-generation streams.

**Layout changes:** Selected puzzles receive dedicated 5-by-5 chambers in a
single-entry wing appended to the right of the generated map. This deliberately
**increases the requested width**, rather than erasing stocked rooms or allowing
accidental alternate corridors; height and physical drawing scale do not change.
A lower level grows in width when necessary to contain its inherited stairwell.
The CLI and debug log report expansions and stair replacements. Corridor and
room metadata, ASCII, SVG, and encounter labels all describe the final layout.
The requested density and average room size remain soft targets.

Local puzzles (chests and temporary escape rooms) follow the wing's progression
puzzles and do not change the level's stairs. This also places their written
treasure and magical rewards inside the protected section when gates are present.
The ogre's and wizard's reward keys open their respective progression gates,
rather than being unassigned keys. A progression
puzzle has a **real `D` gate** at the exit of its chamber, with a corridor beyond
it. The TM key identifies the exact gate coordinate and all protected area
numbers. Treat it as impassable until solved, not as an ordinary pickable lock;
ASCII connectivity and SVG rendering represent the solved, passable state.
Puzzle contents and solutions never appear on the player SVG.

- On a non-final level, all previously generated down stairs **and ramps** are
  removed. One new down stairway, with the configured stair length, is placed
  beyond the gated chambers and their reward room. It is inherited at exactly
  the same coordinates by the next level. Puzzle progression intentionally
  takes precedence over requested down-passage counts and ramp probability.
- On the final level, including a one-level dungeon, the gates instead protect
  a new room section with **no up or down stairs or ramps and no other entrance**.
  Optional single-level stairs remain in the accessible original layout.
- Multiple progression puzzles form a serial chain: every one must be solved
  to reach the terminal reward and, where applicable, the next-level stairway.
  Catalog shortcuts and emergency releases never bypass these progression gates.

The final protected chamber receives the original level's highest-ranked
treasure **together with its guarding encounter, container, lock, and chest trap**.
Floor traps stay at their original locations. Loot is moved, not duplicated.
If the bottom level has a gated section, a final stocking pass exchanges hoards
as necessary to put the **entire dungeon's** highest-ranked generated treasure
there, not merely the best treasure originally rolled on that floor. Earlier
gated sections retain their best remaining local encounter. This pass does not
move map features or required puzzle items, so their keyed locations stay valid.
Ranking compares permanent/reusable magic-item count first (including wands
and staves), then potion/scroll count, then the combined coin and gem value
converted to copper pieces. Thus any permanent magic outranks any quantity of
consumables, and any magic outranks monetary treasure; money breaks remaining
ties. One of equally ranked best hoards is sufficient. If all rooms rolled no
loot, the protected chamber receives an unlocked chest containing 100 sp.
The catalog's suggested gate reward supplies flavor rather than an additional
generated hoard; local chest/item puzzles retain their written rewards.

**Required items:** Every external item is assigned to a numbered encounter
area on the same or an earlier level, never its own puzzle room or a section
behind any puzzle on its source level. Item placement does not depend on a
treasure roll. The TM key states both directions: the puzzle entry names the
item's source level/area, and that source area names the item, target puzzle,
and target level/area. Items are visible furnishings outside locked containers,
with a symbol or diagram hinting at their use. Generated locations supersede
the catalog's illustrative studies, workshops, guardrooms, and other locations.
These references are added after all levels have final chamber numbers, so
an earlier area's key includes items needed by later levels.

Before writing output, the generator checks that solved maps are connected,
closed progression gates cannot be bypassed, protected areas contain the best
loot and only permitted stairs, every prerequisite is accessible before its
puzzle, IDs are unique, and adjacent stair footprints match. Impossible safe
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
They are additional to chamber hazards and explicit T/P traps, do not add
ASCII symbols, and do not change exact feature counts. Container generation
uses its own seeded random stream, so changing the container DC overrides
does not change monsters, treasure quantities/items, or other map traps.
Lock generation has a separate stream too: changing `--chest-lock-dc`
does not change containers, chest traps, or any other generated contents.
The class-specific adjudication guidance below still applies; chest-trap
generation does not implement the previously documented class-rule changes.

Each chamber without an explicit T/P feature independently checks basic >= 23
for an improvised trap, regardless of monsters or treasure. These random traps
are keyed by chamber number in Markdown and **do not add ASCII T/P symbols** or
change exact `--traps` / `--pits` counts. Every existing T/P symbol, including
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

For the shared generator and strategy-game proofs, run from `Tools_temp`:

```powershell
python -m pip install -r requirements-test.txt
python -m unittest test_dungeon_map test_dungeon_puzzles test_dungeon_games
```

The `chess` package is **test-only**; the generator still requires only Python's
standard library. The chess tests reconstruct the source-game positions,
check every defending branch, and independently search all legal moves to
verify both the claimed mate and the impossibility of a shorter forced mate.
