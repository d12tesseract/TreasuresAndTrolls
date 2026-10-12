

## Usage

The standalone `merge_svg.py` utility combines one or more SVGs using a
YAML layout. Install its dependencies and run it from the repository root:

```powershell
python -m pip install -r tools/requirements.txt
python tools/merge_svg.py layout.yaml combined.svg
```

The YAML input is a non-empty list. Each item is either a filename or a mapping:

```yaml
- background.svg
- file: map.svg
  scale: 0.5
  stroke_scale: 1.5
  flipx: true
  flipy: false
  rotation: 90
  offset: [120, 48]
```

Paths are relative to the YAML file. `scale` defaults to `1` and must be
positive; `rotation` defaults to `0` and is in degrees (positive angles turn
clockwise in SVG's usual downward-pointing Y axis). `offset` defaults to
`[0, 0]`. `flipx` and `flipy` default to `false` and must be YAML booleans.
Each SVG is uniformly scaled and optionally reflected in the X/Y coordinates
about `(0, 0)`, then rotated, then translated. Reflections reverse orientation,
but uniform scaling, reflections, and rotations preserve aspect ratios and
angle magnitudes. **Offsets use final output units (pixels)** and are unaffected
by scale, reflection, or rotation. Output dimensions and `viewBox` coordinates
are unitless; absolute input units are converted at 96 pixels per inch.
This restores the pixel/unitless layout behavior preceding the inch-output change.
Files are drawn in list order, with later files on top.

`stroke_scale` is a separate finite, nonnegative line-width multiplier, defaulting
to `1` (zero hides strokes). Geometry `scale` does **not** change apparent stroke
widths: ordinary strokes are compensated by `stroke_scale / scale`, while existing
`vector-effect: non-scaling-stroke` strokes receive only `stroke_scale`.
Source `viewBox` scaling and nested transforms are retained, not replaced with
non-scaling strokes. Static presentation attributes, inline styles, and embedded
CSS participate in their original cascade, including specificity, `!important`,
inherited widths, and the default width of one source user unit.

The output canvas includes the origin and all transformed viewport corners,
including negative offsets and rotations. Source `viewBox` and aspect-ratio
settings are preserved using nested SVGs. A source `preserveAspectRatio="none"`
with mismatched viewport and `viewBox` aspect ratios is rejected rather than
introducing anisotropic distortion; use a uniform `meet` or `slice` setting.
Sources need absolute width/height
(unitless, px, in, cm, mm, pt, or pc) or a `viewBox`; missing dimensions are
inferred from the `viewBox`. If both dimensions are absent, `viewBox` width and
height are treated as pixels at 96 pixels per inch. Percentage dimensions are
not supported.

IDs and local `href`, `url(#id)`, simple CSS ID selectors, and accessibility
references are renamed per input to avoid collisions. General CSS selectors
(such as classes and element names) remain shared across the combined document;
use inline styles/presentation attributes for independent artwork. Stroke widths
are resolved independently per source before merging, then emitted using CSS
typed CSS custom properties (`@property`) and `calc()` (a modern SVG/CSS renderer
supporting property registration is required; unregistered-property fallbacks
do not preserve font-relative inheritance).
Widths support numeric unitless, px, in, cm, mm, pt, pc, %, em, and rem values;
`em` widths compute in each element's context, including `<use>` shadow trees,
and descendants inherit the computed width without recomputing it for their
own font size. Explicit `vector-effect:inherit` follows the instance ancestors.
Common static `font` shorthands (size and family, optionally style, weight,
variant, stretch, and line height) participate in the font-size cascade, including
`!important`, declaration order, and `inherit`/`unset`/`initial`. System-font
shorthands, variable/calculated shorthands, and oblique-angle shorthands are
rejected with an explicit error.
Calculated/variable stroke widths, cascade rollback keywords, conditional
stylesheets (`@media`, `@supports`, `@layer`, etc.), imports, and CSS keyframes
are rejected. Remote stylesheets, dynamic pseudo-class changes, scripts, SMIL
animation, and font-relative widths using font metrics (`ex`, `ch`) are not
supported for stroke compensation. SMIL references are not rewritten.
Linked images and other external resources are not embedded; relative `href`
and CSS `url(...)` references are made absolute against the original SVG
location (including any `xml:base`). Those resources must remain available.
Use trusted SVG inputs: this utility does not sanitize active SVG content.
SVGs containing a DOCTYPE are rejected, and YAML uses a safe loader.
