#!/usr/bin/env python3
"""Merge SVG files listed in YAML: python merge_svg.py layout.yaml output.svg."""

import argparse
import math
from pathlib import Path
import re
import sys
from urllib.parse import urldefrag, urljoin
import xml.etree.ElementTree as ET

import cssselect2
import tinycss2
import yaml


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


class SafeTreeBuilder(ET.TreeBuilder):
    def doctype(self, name, public_id, system_id):
        """Reject SVG document type declarations during parsing."""
        raise ValueError("SVG documents with a DOCTYPE are not supported")


def number(value, label):
    """Validate and convert a finite numeric layout value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        resolved_value = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{label} must be a finite number") from error
    if not math.isfinite(resolved_value):
        raise ValueError(f"{label} must be a finite number")
    return resolved_value


def length(raw_value, label):
    """Resolve a positive SVG absolute length to pixels."""
    match = re.fullmatch(
        r"\s*([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
        r"\s*(px|in|cm|mm|pt|pc)?\s*", raw_value
    )
    if match is None:
        raise ValueError(f"{label} must use absolute units (not percentages)")
    factors = {"": 1, "px": 1, "in": 96, "cm": 96 / 2.54,
               "mm": 96 / 25.4, "pt": 96 / 72, "pc": 16}
    resolved_value = float(match[1]) * factors[match[2] or ""]
    if not math.isfinite(resolved_value) or resolved_value <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return resolved_value


def dimensions(root):
    """Resolve SVG viewport dimensions without distorting its aspect ratio."""
    view_box = None
    if "viewBox" in root.attrib:
        try:
            view_box = [float(part) for part in
                       re.split(r"[\s,]+", root.attrib["viewBox"].strip())]
        except ValueError as error:
            raise ValueError(
                "SVG viewBox must contain four finite numbers"
            ) from error
        if (len(view_box) != 4
                or not all(math.isfinite(component) for component in view_box)
                or view_box[2] <= 0 or view_box[3] <= 0):
            raise ValueError("SVG viewBox must have positive width and height")
    width = (
        length(root.attrib["width"], "SVG width")
        if "width" in root.attrib else None
    )
    height = (
        length(root.attrib["height"], "SVG height")
        if "height" in root.attrib else None
    )
    if view_box is not None:
        if width is None and height is None:
            width, height = view_box[2:]
        elif width is None:
            width = height * view_box[2] / view_box[3]
        elif height is None:
            height = width * view_box[3] / view_box[2]
    if width is None or height is None:
        raise ValueError("SVG needs width and height, or a viewBox")
    if not all(
        math.isfinite(resolved_value) and resolved_value > 0
        for resolved_value in (width, height)
    ):
        raise ValueError("SVG dimensions must be positive and finite")
    if (view_box is not None
            and "none" in root.get("preserveAspectRatio", "").split()
            and not math.isclose(width / height, view_box[2] / view_box[3])):
        raise ValueError("preserveAspectRatio='none' would distort angles; use meet or slice")
    return width, height


def declarations(text):
    """Parse CSS declarations, omitting whitespace, comments, and invalid entries."""
    return [declaration for declaration in tinycss2.parse_declaration_list(
        text, skip_comments=True, skip_whitespace=True
    ) if declaration.type == "declaration"]


def css_value(tokens):
    """Serialize a CSS value without comments or surrounding whitespace."""
    return tinycss2.serialize([
        token for token in tokens if token.type != "comment"
    ]).strip()


def css_urls(tokens, replace):
    """Recursively rewrite URL tokens in a mutable CSS token list."""
    for index, token in enumerate(tokens):
        if (token.type == "url"
                or (token.type == "function" and token.lower_name == "url")):
            tokens[index:index + 1] = tinycss2.parse_component_value_list(
                replace(tinycss2.serialize([token]))
            )
        elif token.type == "function":
            css_urls(token.arguments, replace)
        elif hasattr(token, "content"):
            css_urls(token.content, replace)


def css_references(text, replace):
    """Rewrite URL references while retaining parsed CSS structure."""
    tokens = tinycss2.parse_component_value_list(text)
    css_urls(tokens, replace)
    return tinycss2.serialize(tokens)


def stroke_matcher(root):
    """Compile supported source stylesheet rules into a cascade matcher."""
    matcher = cssselect2.Matcher()
    for element in root.iter(f"{{{SVG_NS}}}style"):
        for rule in tinycss2.parse_stylesheet(
            element.text or "", skip_comments=True, skip_whitespace=True
        ):
            if rule.type == "at-rule":
                if rule.lower_at_keyword in (
                    "import", "media", "supports", "layer",
                    "container", "scope", "keyframes"
                ):
                    raise ValueError("external or conditional stylesheets are not supported")
                continue
            if rule.type != "qualified-rule":
                continue
            try:
                selectors = cssselect2.compile_selector_list(rule.prelude)
            except cssselect2.SelectorError as error:
                raise ValueError(
                    f"unsupported CSS selector: {error}"
                ) from error
            rules = declarations(tinycss2.serialize(rule.content))
            for selector in selectors:
                if selector.pseudo_element is None:
                    matcher.add_selector(selector, rules)

    return matcher


def cascade_winners(wrapper, matcher):
    """Resolve presentation, stylesheet, and inline declarations by priority."""
    element = wrapper.etree_element
    winners = {}

    def apply(name, raw_value, priority):
        """Record a winning declaration, expanding font shorthand size first."""
        if name == "font":
            apply("font-size", font_shorthand_size(raw_value), priority)
        if name not in winners or priority >= winners[name][0]:
            winners[name] = (priority, raw_value.strip())

    for name in ("stroke-width", "vector-effect", "font-size"):
        if name in element.attrib:
            apply(name, element.attrib[name], (False, 0, (0, 0, 0), 0, 0))
    for specificity, order, pseudo_element, rules in matcher.match(wrapper):
        for declaration_index, declaration in enumerate(rules):
            apply(
                declaration.lower_name, css_value(declaration.value),
                (
                    declaration.important, 0, specificity, order,
                    declaration_index
                )
            )
    for declaration_index, declaration in enumerate(
        declarations(element.get("style", ""))
    ):
        apply(declaration.lower_name, css_value(declaration.value),
              (declaration.important, 1, (0, 0, 0), 0, declaration_index))

    return winners


def apply_stroke_style(
    wrapper, winners, styles, root, stroke_property, factor_property,
    stroke_scale, ordinary_factor,
):
    """Pin one element's cascade with typed, instance-aware stroke factors."""
    element = wrapper.etree_element
    parent_style = (
        styles.get(wrapper.parent.etree_element) if wrapper.parent else None
    )
    parent_font_size = parent_style[1] if parent_style else 16
    font_value = winners.get("font-size", (None, "inherit"))[1]
    resolved_font_size = font_size(
        font_value, parent_font_size, styles.get(root, ("none", 16))[1]
    )
    vector_effect = winners.get("vector-effect", (None, "none"))[1]
    if vector_effect in ("initial", "unset"):
        vector_effect = "none"
    if vector_effect not in ("none", "non-scaling-stroke", "inherit"):
        raise ValueError(f"unsupported vector-effect: {vector_effect}")
    styles[element] = (vector_effect, resolved_font_size)

    stroke_width = winners.get("stroke-width", (None, None))[1]
    if stroke_width in ("inherit", "unset"):
        stroke_width = None
    elif stroke_width == "initial":
        stroke_width = "1"
    elif stroke_width in ("revert", "revert-layer"):
        raise ValueError("stroke-width cascade rollback keywords are not supported")
    if stroke_width is None and element is root:
        stroke_width = "1"
    style = element.get("style", "").rstrip()
    if style and not style.endswith(";"):
        style += ";"
    if stroke_width is not None:
        stroke_width = stroke_length(stroke_width, styles[root][1])
        style += f"{stroke_property}:{stroke_width} !important;"
    stroke_factor = (
        "inherit" if vector_effect == "inherit" else repr(
            stroke_scale if vector_effect == "non-scaling-stroke"
            else ordinary_factor
        )
    )
    # Pin the source cascade without freezing relative font sizes in definitions.
    # A registered length computes em before inheritance, including in use shadows.
    if (element is root or font_value.endswith("rem") or
            re.fullmatch(
                r"[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", font_value
            )):
        font_value = f"{resolved_font_size!r}px"
    element.set("style", style + (
        f"font-size:{font_value} !important;"
        f"vector-effect:{vector_effect} !important;"
        f"{factor_property}:{stroke_factor} !important;"
        f"stroke-width:calc(var({stroke_property}) * "
        f"var({factor_property})) !important;"
    ))


def stroke_styles(root, scale, stroke_scale, index):
    """Resolve the cascade, leaving instance-dependent work to typed CSS."""
    matcher = stroke_matcher(root)
    stroke_property = f"--svg{index}-original-stroke-width"
    factor_property = f"--svg{index}-stroke-factor"
    ordinary_factor = stroke_scale / scale
    if not math.isfinite(ordinary_factor):
        raise ValueError("stroke width multiplier must be finite")
    styles = {}
    for wrapper in (
        cssselect2.ElementWrapper.from_xml_root(root).iter_subtree()
    ):
        winners = cascade_winners(wrapper, matcher)
        apply_stroke_style(
            wrapper, winners, styles, root, stroke_property, factor_property,
            stroke_scale, ordinary_factor
        )
    # Registration is document-wide, and names are unique for each input. Untyped
    # properties would inherit the text "1em" and recompute it on every descendant.
    registration = ET.SubElement(root, f"{{{SVG_NS}}}style")
    registration.text = (
        f'@property {stroke_property} {{syntax:"<length-percentage>";'
        'inherits:true;initial-value:1px;}'
        f'@property {factor_property} {{syntax:"<number>";inherits:false;'
        f'initial-value:{ordinary_factor!r};}}'
    )


def font_shorthand_size(raw_value):
    """Extract a supported font size from a complete CSS font shorthand."""
    if raw_value in ("inherit", "unset", "initial"):
        return raw_value
    tokens = [token for token in tinycss2.parse_component_value_list(raw_value)
              if token.type not in ("whitespace", "comment")]
    sizes = {"xx-small", "x-small", "small", "medium", "large", "x-large",
             "xx-large", "xxx-large", "larger", "smaller"}
    prefixes = {"normal", "italic", "oblique", "small-caps", "bold", "bolder",
                "lighter", "ultra-condensed", "extra-condensed", "condensed",
                "semi-condensed", "semi-expanded", "expanded", "extra-expanded",
                "ultra-expanded"}
    for index, token in enumerate(tokens):
        if (token.type in ("dimension", "percentage") or
                (token.type == "ident" and token.lower_value in sizes) or
                (token.type == "number" and token.value == 0)):
            size_value = css_value([token])
            try:
                font_size(size_value, 16, 16)
            except ValueError as error:
                raise ValueError(
                    f"unsupported font shorthand for stroke resolution: "
                    f"{raw_value}"
                ) from error
            family_index = index + 1
            if (family_index < len(tokens)
                    and tokens[family_index].type == "literal"
                    and tokens[family_index].value == "/"):
                family_index += 1
                if family_index >= len(tokens):
                    break
                line_height = tokens[family_index]
                if not (
                    line_height.type in ("dimension", "percentage", "number")
                    or (line_height.type == "ident"
                        and line_height.lower_value == "normal")
                ):
                    break
                if line_height.type != "ident" and line_height.value < 0:
                    break
                family_index += 1
            family = tokens[family_index:]
            if (
                not family or family[0].type == "literal"
                or family[-1].type == "literal"
                or any(
                    part.type not in ("ident", "string")
                    and not (part.type == "literal" and part.value == ",")
                    for part in family
                )
            ):
                break
            return size_value
        if not ((token.type == "ident" and token.lower_value in prefixes) or
                (token.type == "number" and 1 <= token.value <= 1000)):
            break
    raise ValueError(
        f"unsupported font shorthand for stroke resolution: {raw_value}"
    )


def font_size(raw_value, parent_size, root_size):
    """Resolve a supported font size against its parent and root sizes."""
    if raw_value in ("inherit", "unset"):
        return parent_size
    sizes = {
        "xx-small": 9, "x-small": 10, "small": 13, "medium": 16,
        "large": 18, "x-large": 24, "xx-large": 32, "xxx-large": 48,
        "initial": 16, "larger": parent_size * 1.2,
        "smaller": parent_size / 1.2
    }
    if raw_value in sizes:
        return sizes[raw_value]
    match = re.fullmatch(
        r"([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([a-z%]*)",
        raw_value
    )
    if match is None:
        raise ValueError(
            f"unsupported font-size for stroke resolution: {raw_value}"
        )
    resolved_value = float(match[1])
    unit = match[2]
    if unit in ("em", "%", "rem"):
        resolved_value *= {
            "em": parent_size, "%": parent_size / 100, "rem": root_size
        }[unit]
    elif unit not in ("", "px"):
        resolved_value = length(raw_value, "font-size")
    if not math.isfinite(resolved_value) or resolved_value < 0:
        raise ValueError("font-size must be nonnegative and finite")
    return resolved_value


def stroke_length(raw_value, root_font_size):
    """Validate a static stroke length and resolve root-relative units."""
    match = re.fullmatch(
        r"\s*([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-z%]*)\s*",
        raw_value
    )
    if match is None or match[2] not in (
        "", "px", "in", "cm", "mm", "pt", "pc", "%", "em", "rem"
    ):
        raise ValueError(
            f"stroke-width must be a nonnegative static length: {raw_value}"
        )
    resolved_value = float(match[1])
    if not math.isfinite(resolved_value):
        raise ValueError("stroke-width must be finite")
    unit = match[2]
    if unit == "rem":
        resolved_value *= root_font_size
        unit = "px"
    if not math.isfinite(resolved_value):
        raise ValueError("resolved stroke-width must be finite")
    return f"{resolved_value!r}{unit or 'px'}"


def collect_ids(root, index):
    """Assign input-specific identifiers, rejecting duplicate source IDs."""
    ids = {}
    for element in root.iter():
        identifier = element.get("id")
        if identifier is not None:
            if identifier in ids:
                raise ValueError(f"duplicate SVG id: {identifier}")
            ids[identifier] = f"svg{index}_{identifier}"
    return ids


def isolate_ids(root, index):
    """Namespace IDs and rewrite their XML, accessibility, and CSS references."""
    ids = collect_ids(root, index)

    def replace_url(match):
        """Replace a known local fragment while retaining unknown URL text."""
        identifier = match["id"]
        if identifier not in ids:
            return match[0]
        return f"url(#{ids[identifier]})"

    def references(text):
        """Rewrite local fragment URLs in an attribute or CSS value."""
        return re.sub(
            r"""url\(\s*(?P<quote>['"]?)#(?P<id>[^'")\s]+)(?P=quote)\s*\)""",
            replace_url, text
        )

    def selectors(tokens):
        """Rewrite identifier hashes in selectors and nested selector functions."""
        for token in tokens:
            if token.type == "hash" and token.is_identifier:
                token.value = ids.get(token.value, token.value)
            elif token.type == "function":
                selectors(token.arguments)

    for element in root.iter():
        for attribute_name, raw_value in list(element.attrib.items()):
            if attribute_name == "id":
                element.set(attribute_name, ids[raw_value])
            elif (attribute_name in ("href", f"{{{XLINK_NS}}}href")
                    and raw_value.startswith("#")):
                element.set(
                    attribute_name, "#" + ids.get(raw_value[1:], raw_value[1:])
                )
            elif attribute_name in ("aria-labelledby", "aria-describedby"):
                element.set(attribute_name, " ".join(
                    ids.get(identifier, identifier)
                    for identifier in raw_value.split()
                ))
            elif attribute_name == "style":
                element.set(
                    attribute_name, css_references(raw_value, references)
                )
            else:
                element.set(attribute_name, references(raw_value))
        if element.tag == f"{{{SVG_NS}}}style" and element.text:
            rules = tinycss2.parse_stylesheet(element.text)
            for rule in rules:
                if rule.type == "qualified-rule":
                    selectors(rule.prelude)
                    css_urls(rule.content, references)
                elif rule.type == "at-rule":
                    css_urls(rule.prelude, references)
                    if rule.content is not None:
                        css_urls(rule.content, references)
            element.text = tinycss2.serialize(rules)


def resolve_resources(element, base_url, document_url):
    """Resolve XML bases and external URLs, retaining local fragments."""
    base_url = urljoin(base_url, element.attrib.pop(f"{{{XML_NS}}}base", ""))

    def reference(url):
        """Resolve one URL and collapse same-document fragment references."""
        resolved_url = urljoin(base_url, url)
        target_url, fragment = urldefrag(resolved_url)
        if fragment and target_url == urldefrag(document_url)[0]:
            return "#" + fragment
        return resolved_url

    def absolute_url(match):
        """Rewrite a CSS URL while preserving its optional quoting."""
        quote = match[1] or ""
        url = (match[2] if match[1] else match[3]).strip()
        if not url:
            return match[0]
        return f"url({quote}{reference(url)}{quote})"

    def urls(text):
        """Resolve every CSS URL embedded in the supplied text."""
        return re.sub(
            r"""url\(\s*(?:(['"])(.*?)\1|([^)]*?))\s*\)""", absolute_url, text
        )

    for attribute_name, raw_value in list(element.attrib.items()):
        if attribute_name in ("href", f"{{{XLINK_NS}}}href") and raw_value:
            element.set(attribute_name, reference(raw_value))
        elif attribute_name == "style":
            element.set(attribute_name, css_references(raw_value, urls))
        else:
            element.set(attribute_name, urls(raw_value))
    if element.tag == f"{{{SVG_NS}}}style" and element.text:
        element.text = css_references(element.text, urls)
    for child in element:
        resolve_resources(child, base_url, document_url)


def layout_entry(entry, index, layout_path, output_path):
    """Validate an entry and resolve its source and transform parameters."""
    if isinstance(entry, str):
        entry = {"file": entry}
    if not isinstance(entry, dict) or set(entry) - {
            "file", "scale", "rotation", "offset",
            "stroke_scale", "flipx", "flipy"}:
        raise ValueError(f"entry {index + 1}: unexpected SVG layout fields")
    filename = entry.get("file")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError(f"entry {index + 1}: file must be a non-empty string")
    scale = number(entry.get("scale", 1), "scale")
    if scale <= 0:
        raise ValueError("scale must be positive")
    stroke_scale = number(entry.get("stroke_scale", 1), "stroke_scale")
    if stroke_scale < 0:
        raise ValueError("stroke_scale must be nonnegative")
    for field in ("flipx", "flipy"):
        if not isinstance(entry.get(field, False), bool):
            raise ValueError(f"{field} must be a boolean")
    scale_x = -scale if entry.get("flipx", False) else scale
    scale_y = -scale if entry.get("flipy", False) else scale
    rotation = number(entry.get("rotation", 0), "rotation") % 360
    offset = entry.get("offset", [0, 0])
    if not isinstance(offset, list) or len(offset) != 2:
        raise ValueError("offset must be a two-number list [x, y]")
    x, y = (number(value, "offset") for value in offset)
    svg_path = (layout_path.parent / filename).resolve()
    if svg_path == output_path.resolve():
        raise ValueError("output must not overwrite an input SVG")
    return svg_path, scale, stroke_scale, scale_x, scale_y, rotation, x, y


def load_svg(svg_path, scale, stroke_scale, index):
    """Parse and isolate a source SVG, attaching its path to expected errors."""
    try:
        root = ET.parse(
            svg_path, parser=ET.XMLParser(target=SafeTreeBuilder())
        ).getroot()
        if root.tag != f"{{{SVG_NS}}}svg":
            raise ValueError("document root must be an SVG in the SVG namespace")
        width, height = dimensions(root)
        stroke_styles(root, scale, stroke_scale, index)
        resolve_resources(root, svg_path.as_uri(), svg_path.as_uri())
        isolate_ids(root, index)
    except (OSError, ET.ParseError, ValueError) as error:
        raise ValueError(f"{svg_path}: {error}") from error
    return root, width, height


def place_svg(output, bounds, root, width, height,
              scale_x, scale_y, rotation, x, y):
    """Append a transformed viewport and accumulate its finite corner bounds."""
    cosine = math.cos(math.radians(rotation))
    sine = math.sin(math.radians(rotation))
    # Keep exact quarter turns from adding tiny floating-point margins.
    if abs(cosine) < 1e-15:
        cosine = 0
    if abs(sine) < 1e-15:
        sine = 0
    corners = [
        (x + cosine * scale_x * corner_x - sine * scale_y * corner_y,
         y + sine * scale_x * corner_x + cosine * scale_y * corner_y)
        for corner_x, corner_y in (
            (0, 0), (width, 0), (0, height), (width, height)
        )
    ]
    if not all(
        math.isfinite(resolved_value)
        for corner in corners for resolved_value in corner
    ):
        raise ValueError("scaled SVG bounds must be finite")
    bounds.append((min(corner[0] for corner in corners),
                   min(corner[1] for corner in corners),
                   max(corner[0] for corner in corners),
                   max(corner[1] for corner in corners)))
    group = ET.SubElement(output, f"{{{SVG_NS}}}g", {
        "transform": (f"translate({x!r} {y!r}) rotate({rotation!r}) "
                      + (f"scale({scale_x!r} {scale_y!r})"
                         if scale_x != scale_y else f"scale({scale_x!r})"))
    })
    root.set("x", "0")
    root.set("y", "0")
    root.set("width", repr(width))
    root.set("height", repr(height))
    group.append(root)


def merge_svg(layout_path, output_path):
    """Merge layout entries into a bounded, resource-safe SVG document."""
    with layout_path.open(encoding="utf-8") as stream:
        entries = yaml.safe_load(stream)
    if not isinstance(entries, list) or not entries:
        raise ValueError("YAML must contain a non-empty list of SVG files")

    output = ET.Element(f"{{{SVG_NS}}}svg", {"version": "1.1"})
    bounds = []
    for index, entry in enumerate(entries):
        (svg_path, scale, stroke_scale, scale_x,
         scale_y, rotation, x, y) = layout_entry(
            entry, index, layout_path, output_path
        )
        root, width, height = load_svg(svg_path, scale, stroke_scale, index)
        place_svg(output, bounds, root, width, height,
                  scale_x, scale_y, rotation, x, y)

    left = min(0, *(bound[0] for bound in bounds))
    top = min(0, *(bound[1] for bound in bounds))
    width = max(0, *(bound[2] for bound in bounds)) - left
    height = max(0, *(bound[3] for bound in bounds)) - top
    if not all(
        math.isfinite(resolved_value) and resolved_value > 0
        for resolved_value in (width, height)
    ):
        raise ValueError("output dimensions must be positive and finite")
    output.set("viewBox", " ".join(
        repr(resolved_value) for resolved_value in (left, top, width, height)
    ))
    output.set("width", repr(width))
    output.set("height", repr(height))
    if output_path.resolve() == layout_path.resolve():
        raise ValueError("output must not overwrite the YAML input")
    ET.ElementTree(output).write(
        output_path, encoding="utf-8", xml_declaration=True
    )


def main():
    """Run the merger CLI and report supported input and filesystem failures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "layout", type=Path,
        help="YAML list; file paths are relative to this file"
    )
    parser.add_argument("output", type=Path, help="destination SVG")
    args = parser.parse_args()
    try:
        merge_svg(args.layout.resolve(), args.output)
    except (OSError, ValueError, ET.ParseError, yaml.YAMLError) as error:
        parser.exit(1, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
