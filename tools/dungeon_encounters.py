"""Seeded dungeon stocking using the repository's Treasures and Trolls rules."""

import random
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dungeon_map import Cell, GeneratedDungeon


RULES_PATH = Path(__file__).resolve().parents[2] / "TreasuresAndTrollsBasicMD.md"
RULINGS = (
    "All generation basic rolls are exactly 3 independent integers from 0 through 11, "
    "summed without symbol rerolls, including magic-item power. Symbol rerolls apply "
    "only to player attack rolls and saving throws.",
    "The indoor encounter row between 21 and 23 is treated as 22 (printed as a second 16). "
    "The missing magic-item result 12 uses Misc, alongside 13.",
    "Treasure uses each creature's listed level, not dungeon depth. Missing creature "
    "levels use dungeon level and are flagged below. Empty chambers check DC 21 for "
    "an abandoned cache, valued as one creature of dungeon level. Table levels are "
    "clamped to 1-10; mixed parties use their highest level for gems and magic.",
    "Gems use basic roll + monster count >= 23, following the stated +1 per monster "
    "rather than the inconsistent three-goblin example. Progressive magic bonuses "
    "use >= DC, as with other checks.",
    "Dragon type is selected uniformly from the six listed dragons. Hoards use "
    "dragon level + 2 (table cap 10), tenfold coins converted to gold, double gems, "
    "and double magic items with guaranteed treasure and magic checks.",
    "Dungeon encounter areas are the monsters' lairs, including dragon lairs. "
    "All generated treasure is in the encounter chamber. A successful chest "
    "check stores it in a chest; otherwise it is in a bag or pack. Only chests "
    "receive separate chest-trap and chest-lock checks. Locking is independent "
    "of trapping. These are generation thresholds, "
    "not player detection, opening or disarming DCs.",
    "Adventurer levels have a minimum of 1. The missing adventurer class result 28 "
    "uses Cleric. Party entries give a roster, not complete character sheets.",
    "Magic bracers grant their power bonus to toughness (an improvised effect; "
    "the rules do not specify one). Healing power above +4 uses the +4 Raise dead "
    "effect because the healing tables end there.",
    "Random chamber traps occur on basic roll >= 23, independently of monsters "
    "and treasure, unless the chamber already has an explicit T/P trap. Random "
    "traps are keyed by chamber number, not added to ASCII feature counts. Trap "
    "designs, triggers and DCs are improvised using the rules' saves and wound system.",
    "Secret doors require DC 20 (WIS, Medium); concealed doors require DC 17 "
    "(WIS, Easy). Roll basic + WIS modifier + applicable level/class bonus; "
    "meet or exceed the DC. There are no symbol rerolls for detection.",
)


def basic_roll(rng: random.Random) -> int:
    return sum(rng.randint(0, 11) for _ in range(3))


def dice(rng: random.Random, expression: str) -> int:
    match = re.fullmatch(r"(\d*)d\s*(\d+)(?:\s*\+\s*(\d+))?", expression.strip())
    if not match:
        raise ValueError("unsupported dice expression: {!r}".format(expression))
    count, sides, bonus = match.groups()
    return sum(rng.randint(1, int(sides)) for _ in range(int(count or 1))) + int(bonus or 0)


def _basic(rng: random.Random, debug: Optional[List[str]], purpose: str) -> int:
    result = basic_roll(rng)
    if debug is not None:
        debug.append("{}: basic roll = {}".format(purpose, result))
    return result


def _dice(rng: random.Random, expression: str, debug: Optional[List[str]], purpose: str) -> int:
    result = dice(rng, expression)
    if debug is not None:
        debug.append("{}: {} = {}".format(purpose, expression, result))
    return result


def _section(text: str, start: str, end: str) -> str:
    _, separator, remaining = text.partition(start)
    if not separator:
        raise ValueError("rules are missing section {!r}".format(start))
    section, separator, _ = remaining.partition(end)
    if not separator:
        raise ValueError("rules are missing section boundary {!r}".format(end))
    return section


def _table(text: str, header: Tuple[str, ...]) -> List[List[str]]:
    found = False
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip().strip("*").strip() for cell in line.strip("|").split("|")]
        if tuple(cells) == header:
            found = True
        elif found and re.fullmatch(r"\d+(?:-\d+)?", cells[0]):
            if len(cells) != len(header):
                raise ValueError("malformed rules table: {}".format(header))
            rows.append(cells)
    if not rows:
        raise ValueError("rules are missing table: {}".format(header))
    return rows


def _expand(rows: List[List[str]], first: int, last: int) -> Dict[int, List[str]]:
    result = {}
    for key, *values in rows:
        bounds = [int(value) for value in key.split("-")]
        for roll in range(bounds[0], bounds[-1] + 1):
            if roll in result:
                raise ValueError("duplicate rules table roll: {}".format(roll))
            result[roll] = values
    if set(result) != set(range(first, last + 1)):
        raise ValueError("rules table must cover {} through {}".format(first, last))
    return result


class EncounterRules:
    def __init__(self, path: Path = RULES_PATH) -> None:
        text = path.read_text(encoding="utf-8")
        indoor = _section(text, "## Indoor Adventuring", "## Outdoor Adventuring")
        encounters = _table(indoor, ("Roll", "Level 1-3", "Level 4-6", "Level 7-9"))
        if len(encounters) == 34 and encounters[22][0] == "16":
            encounters[22][0] = "22"
        self.encounters = _expand(encounters, 0, 33)
        self.races = _expand(_table(indoor, ("", "Race")), 0, 33)
        classes = _table(indoor, ("", "Class"))
        if classes[-1] == ["29-33", "Cleric"]:
            classes[-1][0] = "28-33"
        self.classes = _expand(classes, 0, 33)
        treasure = _section(text, "## Treasure\n", "## Combat")
        self.money = _expand(_table(
            _section(treasure, "### Money", "### Gems and Jewelry"),
            ("Monster Level", "Price (sp)"),
        ), 1, 10)
        self.gems = _expand(_table(
            _section(treasure, "### Gems and Jewelry", "### Magic items"),
            ("Monster Level", "Price (sp)"),
        ), 1, 10)
        categories = _table(treasure, ("Roll", "Item"))
        if ["13", "Misc"] in categories and not any(row[0] == "12" for row in categories):
            categories[categories.index(["13", "Misc"])][0] = "12-13"
        self.categories = _expand(categories, 0, 33)
        self.items = _expand(_table(treasure, (
            "Roll", "Weapon", "Armor", "Ring", "Wand/Staff", "Scroll", "Potion", "Misc",
        )), 1, 12)
        self.powers = _expand(_table(
            treasure, ("Monster Level", "+2", "+3", "+4", "+5"),
        ), 1, 10)
        creatures = _section(text, "# Creatures\n", "# Appendix A")
        self.creature_levels = {
            re.sub(r"\s+\d+$", "", name.strip()): int(level)
            for name, level in re.findall(r"\*\*([^*]+)\*\*\s*Level:\s*(\d+)", creatures)
        }

    def creature_level(self, name: str, depth: int) -> Tuple[int, bool]:
        aliases = {
            "Wolves": "Wolf", "Dire Wolves": "Dire Wolf", "Lizard Men": "Lizard Man",
            "Mummys": "Mummy", "Pegasi": "Pegasus", "Sphynx": "Sphinx",
            "Slime": "Green Slime", "Slimes": "Green Slime",
        }
        name = aliases.get(name, name)
        if name not in self.creature_levels and name.endswith("s"):
            name = name[:-1]
        if name in self.creature_levels:
            return self.creature_levels[name], False
        return depth, True


@dataclass(frozen=True)
class MonsterEncounter:
    description: str
    levels: Tuple[int, ...]
    dragon: bool = False


def monster_encounter(rules: EncounterRules, rng: random.Random, depth: int,
                      roll: int, debug: Optional[List[str]] = None) -> MonsterEncounter:
    entry = rules.encounters[roll][min((depth - 1) // 3, 2)]
    if entry == "Adventuring party":
        count = _dice(rng, "d6", debug, "Adventurer count")
        alignment = rng.choice(("Lawful", "Neutral", "Chaotic"))
        levels, roster = [], []
        for index in range(1, count + 1):
            purpose = "Adventurer {}".format(index)
            level = max(1, depth + _dice(rng, "d3", debug, purpose + " level offset") - 2)
            levels.append(level)
            race = rules.races[_basic(rng, debug, purpose + " race")][0]
            role = rules.classes[_basic(rng, debug, purpose + " class")][0]
            roster.append("{} {} (level {})".format(race, role, level))
        return MonsterEncounter(
            "{} adventurers, {}: {}".format(count, alignment, "; ".join(roster)),
            tuple(levels),
        )
    if entry == "Dragon":
        name = rng.choice(("Young Horntail", "Young Ironclaw", "Young Ridgeback",
                           "Horntail", "Ironclaw", "Ridgeback"))
        level = rules.creature_levels[name]
        return MonsterEncounter("1 {} (level {}), in its lair in this chamber".format(name, level),
                                (level,), True)
    match = re.match(r"^((?:\d*)d\s*\d+(?:\s*\+\s*\d+)?)\s*(.*)$", entry)
    count, name = (_dice(rng, match[1], debug, "Monster count"), match[2]) if match else (1, entry)
    level, inferred = rules.creature_level(name, depth)
    if inferred and debug is not None:
        debug.append("{}: level absent from rules, using dungeon level {}".format(name, depth))
    return MonsterEncounter("{} {} (level {} each)".format(count, name, level),
                            (level,) * count)


def _table_level(level: int) -> int:
    return max(1, min(level, 10))


def magic_item(rules: EncounterRules, rng: random.Random, level: int,
               debug: Optional[List[str]] = None) -> str:
    category = rules.categories[_basic(rng, debug, "Magic item category")][0]
    columns = {"Magic weapon": 0, "Magic Armor": 1, "Magic Ring": 2,
               "Magic Wand": 3, "Magic Staff": 3, "Magic Scroll": 4,
               "Magic Potion": 5, "Misc": 6}
    subtype = rules.items[_dice(rng, "d12", debug, "Magic item subtype")][columns[category]] if category in columns else ""
    roll = _basic(rng, debug, "Magic item power at table level {}".format(_table_level(level)))
    power = 1
    for bonus, threshold in enumerate(rules.powers[_table_level(level)], 2):
        if threshold and roll >= int(threshold):
            power = bonus
    name = "{}{}".format(category, ": " + subtype if subtype else "")
    effect = ""
    if category == "Magic weapon":
        effect = "+{} to hit and attack power".format(power)
    elif category in ("Magic Armor", "Magic Bracers") or subtype in ("Protection", "Cloak of Protection"):
        effect = "+{} toughness".format(power)
    elif category == "Magic Shield":
        effect = "-{} to hit for attacks blocked by the shield".format(power)
    elif subtype == "Attack Power":
        effect = "+{} to hit and attack power".format(power)
    elif subtype in ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"):
        effect = "+{} {}".format(power, subtype)
        if category == "Magic Potion":
            effect += " for 1 hour"
    elif subtype == "Boots of Speed":
        effect = "+{}% movement speed".format(power * 10)
    elif subtype == "Healing":
        healing = ("Cure minor wound", "Cure serious wound", "Cure mortal wound", "Raise dead")
        effect = healing[min(power, 4) - 1]
        if category in ("Magic Wand", "Magic Staff"):
            effect += "; cleric only, minimum level {}".format((1, 2, 4, 5)[min(power, 4) - 1])
    elif subtype == "Magic Missile":
        effect = "{} missiles per charge; minimum user level {}".format(power, max(1, 2 * (power - 1)))
    if category in ("Magic Wand", "Magic Staff"):
        effect += ("; " if effect else "") + "{} charges (maximum 24)".format(
            _dice(rng, "2d12", debug, "Magic item charges"))
        if category == "Magic Staff":
            effect += "; +{} to hit and AP as a quarterstaff".format(power)
    if category == "Magic Scroll":
        effect = "single use; caster level +2 for requirements and spell effects"
    description = name + ("; " + effect if effect else "") + " (power +{})".format(power)
    if debug is not None:
        debug.append("Magic item result: " + description)
    return description


def treasure(rules: EncounterRules, rng: random.Random, depth: int,
             encounter: Optional[MonsterEncounter], debug: Optional[List[str]] = None) -> Tuple[str, ...]:
    dragon = encounter is not None and encounter.dragon
    presence = _basic(rng, debug, "Treasure presence (DC 21{})".format(
        "; guaranteed for dragon" if dragon else ""))
    if presence < 21 and not dragon:
        return ("None.",)
    levels = encounter.levels if encounter else (depth,)
    if dragon:
        levels = tuple(level + 2 for level in levels)
    level = max(levels)
    coins = Counter()
    for index, individual in enumerate(levels, 1):
        expression, currency = rules.money[_table_level(individual)][0].rsplit(" ", 1)
        coins[currency] += _dice(rng, expression, debug, "Creature {} coins ({}, table level {})".format(
            index, currency, _table_level(individual)))
    if dragon:
        copper = sum(amount * {"cp": 1, "sp": 10, "gp": 100, "pp": 1000}[unit]
                     for unit, amount in coins.items())
        money = "{:g} gp".format(copper / 10)
    else:
        money = ", ".join("{} {}".format(amount, unit) for unit, amount in coins.items())
    lines = [
        ("Dragon hoard." if dragon else
         "Lair cache in this chamber." if encounter else "Abandoned chamber cache."),
        "Coins: {}.".format(money),
    ]
    gems_roll = _basic(rng, debug, "Gems/jewelry presence (DC 23, modifier +{})".format(len(levels)))
    if gems_roll + len(levels) >= 23:
        count = _dice(rng, "d6", debug, "Gem count{}".format(
            " (doubled for dragon)" if dragon else "")) * (2 if dragon else 1)
        expression, currency = rules.gems[_table_level(level)][0].rsplit(" ", 1)
        values = ["{} {}".format(_dice(rng, expression, debug, "Gem {} value ({}, table level {})".format(
            index, currency, _table_level(level))), currency) for index in range(1, count + 1)]
        lines.append("Gems/jewelry: {} pieces, worth {} individually.".format(count, ", ".join(values)))
    else:
        lines.append("Gems/jewelry: none.")
    modifier = 2 * max(0, level - 5)
    magic_roll = _basic(rng, debug, "Magic presence (DC 25, modifier +{}{})".format(
        modifier, "; guaranteed for dragon" if dragon else ""))
    if dragon or magic_roll + modifier >= 25:
        count = _dice(rng, "d3", debug, "Magic item count{}".format(
            " (doubled for dragon)" if dragon else "")) * (2 if dragon else 1)
        lines.append("Magic: {} items.".format(count))
        lines.extend(magic_item(rules, rng, level, debug) for _ in range(count))
    else:
        lines.append("Magic: none.")
    return tuple(lines)


def trap_description(rng: random.Random, pit: bool = False, chest: bool = False,
                     debug: Optional[List[str]] = None) -> str:
    kind = rng.choice((3, 4)) if chest else 0 if pit else rng.randrange(5)
    detection = "Detect with DC 20 (WIS); bypass/disarm with DC 20 (DEX). Failed disarm triggers it. "
    if kind == 0:
        depth = dice(rng, "d3") * 10
        return detection + (
            "Covered pit: weight breaks the lid; ST 20 (DEX / FALL) avoids the fall. "
            "Failure: fall {} feet, AP {} (5 + distance beyond 5 feet); adjust AP "
            "to actual falling distance if hanging from the edge."
        ).format(depth, depth)
    if kind == 1:
        return detection + (
            "Scything blade: a tripwire sweeps a blade across the entrant. "
            "ST 20 (DEX / BLADE) avoids it; failure causes one AP 8 damage roll."
        )
    if kind == 2:
        return detection + (
            "Falling stone: a pressure plate drops masonry on the entrant. "
            "ST 23 (DEX / CRUSH) avoids it; failure causes one AP 12 damage roll."
        )
    effect = rng.choice(("sleep", "paralysis", "deadly"))
    if debug is not None:
        debug.append("Poison trap: {}; effect {}".format("needle" if kind == 3 else "gas", effect))
    onset = _dice(rng, "d4", debug, "Poison onset (rounds)")
    duration = _dice(rng, "d6", debug, "Poison duration (rounds to death or hours affected)")
    outcome = (
        "incapacitation after {} rounds, then death {} rounds later".format(onset, duration)
        if effect == "deadly" else
        "{} after {} rounds, lasting {} hours".format(effect, onset, duration)
    )
    delivery = (
        "Poison needle: opening {} pricks the opener; ".format("the chest" if chest else "a concealed cache") +
        "ST 17 (DEX / NEEDLE) avoids the needle and poison. If pricked, "
        if kind == 3 else
        "Poison gas: opening the chest vents gas around the opener; " if chest else
        "Poison gas: a pressure plate vents gas into the entrant's square; "
    )
    return detection + delivery + (
        "ST 23 (CON / PSN-{}) prevents poisoning; failure causes {}. "
        "No separate wound damage. Sleeping victims cannot be roused; paralyzed "
        "victims remain aware but cannot act."
    ).format(effect.upper(), outcome)


@dataclass(frozen=True)
class EncounterArea:
    number: int
    cell: Cell
    presence_roll: int
    table_roll: Optional[int]
    monster: Optional[MonsterEncounter]
    treasure: Tuple[str, ...]
    trap: str
    debug: Tuple[str, ...] = ()
    container: Optional[str] = None
    chest_trap: Optional[str] = None
    chest_locked: Optional[bool] = None


@dataclass(frozen=True)
class EncounterLevel:
    areas: Tuple[EncounterArea, ...]
    traps: Tuple[Tuple[Cell, str], ...]
    doors: Tuple[Tuple[Cell, str, int], ...]

    @property
    def labels(self) -> Dict[Cell, str]:
        return {area.cell: str(area.number) for area in self.areas}


def generate_encounters(dungeon: GeneratedDungeon, encounter_chance: int = 11,
                        rules: Optional[EncounterRules] = None, *,
                        treasure_chest_dc: int = 17, chest_trap_dc: int = 19,
                        chest_lock_dc: int = 17) -> Tuple[EncounterLevel, ...]:
    for name, value, maximum in (("encounter_chance", encounter_chance, 33),
                                 ("treasure_chest_dc", treasure_chest_dc, 34),
                                 ("chest_trap_dc", chest_trap_dc, 34),
                                 ("chest_lock_dc", chest_lock_dc, 34)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
            raise ValueError("{} must be an integer from 0 through {}".format(name, maximum))
    rules = rules or EncounterRules()
    rng = random.Random("{}:encounters".format(dungeon.seed))
    container_rng = random.Random("{}:treasure-containers".format(dungeon.seed))
    lock_rng = random.Random("{}:chest-locks".format(dungeon.seed))
    levels = []
    for depth, level in enumerate(dungeon.levels, 1):
        if len(level.room_cells) != len(level.room_areas):
            raise ValueError("encounter generation requires retained chamber footprints")
        areas = []
        for number, cells in enumerate(level.room_cells, 1):
            cx = sum(x for x, y in cells) / len(cells)
            cy = sum(y for x, y in cells) / len(cells)
            floor = [cell for cell in cells if level.grid.tile(*cell) in " .TP"]
            if not floor:
                raise ValueError("chamber {} has no labelable floor".format(number))
            cell = min(floor, key=lambda p: (
                level.grid.tile(*p) not in " .", (p[0] - cx) ** 2 + (p[1] - cy) ** 2, p,
            ))
            presence = basic_roll(rng)
            roll = basic_roll(rng) if presence >= encounter_chance else None
            debug = []
            monster = monster_encounter(rules, rng, depth, roll, debug) if roll is not None else None
            loot = treasure(rules, rng, depth, monster, debug)
            explicit = any(level.grid.tile(*p) in "TP" for p in cells)
            trap = "See the explicit T/P trap key below." if explicit else (
                trap_description(rng) if basic_roll(rng) >= 23 else "None."
            )
            container, chest_trap, chest_locked = None, None, None
            if loot and loot != ("None.",):
                chest_roll = _basic(container_rng, debug, "Treasure chest (DC {})".format(treasure_chest_dc))
                if chest_roll >= treasure_chest_dc:
                    container = "chest"
                    trap_roll = _basic(container_rng, debug, "Chest trap (DC {})".format(chest_trap_dc))
                    if trap_roll >= chest_trap_dc:
                        chest_trap = trap_description(container_rng, chest=True, debug=debug)
                    chest_locked = _basic(lock_rng, debug, "Chest lock (DC {})".format(chest_lock_dc)) >= chest_lock_dc
                else:
                    container = container_rng.choice(("bag", "pack"))
            areas.append(EncounterArea(number, cell, presence, roll, monster, loot, trap,
                                       tuple(debug), container, chest_trap, chest_locked))
        areas = [replace(area, number=number) for number, area in enumerate(
            sorted(areas, key=lambda area: (area.cell[1], area.cell[0])), 1)]
        traps, doors = [], []
        for y, row in enumerate(level.grid.rows):
            for x, tile in enumerate(row):
                if tile in "TP":
                    traps.append(((x, y), trap_description(rng, pit=tile == "P")))
                elif tile in "SC":
                    doors.append(((x, y), "Secret" if tile == "S" else "Concealed",
                                  20 if tile == "S" else 17))
        levels.append(EncounterLevel(tuple(areas), tuple(traps), tuple(doors)))
    return tuple(levels)


def encounter_document(dungeon: GeneratedDungeon, levels: Tuple[EncounterLevel, ...],
                       encounter_chance: int) -> str:
    if len(levels) != len(dungeon.levels):
        raise ValueError("encounter key must include every dungeon level")
    lines = [
        "# Dungeon encounter key",
        "", "Chamber numbers restart on each level and match the SVG encounter labels.",
        "Unnumbered trap and door coordinates are one-based (column, row) from the upper-left square.",
    ]
    for index, (layout, contents) in enumerate(zip(dungeon.levels, levels), 1):
        lines.extend(["", "## Level {}".format(index), "",
                      "Depth: {} feet.".format(layout.depth_feet)])
        for area in contents.areas:
            loot = [item for item in area.treasure
                    if item not in ("None.", "Gems/jewelry: none.", "Magic: none.",
                                    "Lair cache in this chamber.", "Abandoned chamber cache.",
                                    "Dragon hoard.")]
            has_trap = bool(area.trap) and area.trap != "None."
            lines.extend(["", "### {}".format(area.number), ""])
            if not area.monster and not loot and not has_trap and not area.chest_trap:
                lines.append("Empty")
                continue
            if area.monster:
                lines.append("**Encounter:** {}.".format(area.monster.description))
            if loot:
                lines.extend(["", "**Treasure:**"])
                if area.container:
                    container = area.container
                    if container == "chest" and area.chest_locked is not None:
                        container = "locked chest" if area.chest_locked else "unlocked chest"
                    lines.append("- {}.".format(container.capitalize()))
                lines.extend("- " + item for item in loot)
            elif area.monster:
                lines.extend(["", "**Treasure:** None."])
            if has_trap:
                lines.extend(["", "**Trap:** " + area.trap])
            if area.chest_trap:
                lines.extend(["", "**Chest trap:** " + area.chest_trap])
        if contents.traps:
            lines.extend(["", "### Explicit map traps (T/P)", ""])
            lines.extend("- Column {}, row {}: {}".format(cell[0] + 1, cell[1] + 1, description)
                         for cell, description in contents.traps)
        if contents.doors:
            lines.extend(["", "### Secret and concealed doors", ""])
            lines.extend("- {} door at column {}, row {}: DC {} (WIS) to detect.".format(
                kind, cell[0] + 1, cell[1] + 1, dc) for cell, kind, dc in contents.doors)
    return "\n".join(lines) + "\n"


def encounter_log(dungeon: GeneratedDungeon, levels: Tuple[EncounterLevel, ...],
                  encounter_chance: int) -> str:
    if len(levels) != len(dungeon.levels):
        raise ValueError("encounter log must include every dungeon level")
    lines = [
        "Dungeon encounter generation - DEBUG / TM ONLY",
        "Seed: {}".format(dungeon.seed),
        "Monster presence threshold: {}".format(encounter_chance),
        "Source: TreasuresAndTrollsBasicMD.md",
        "", "Generator rulings:",
    ]
    lines.extend("- " + ruling for ruling in RULINGS)
    lines.append("- Minor-wound threshold 26 is treated as 16 (progressive 13/16/19/22/25).")
    for index, contents in enumerate(levels, 1):
        band = ("1-3", "4-6", "7-9")[min((index - 1) // 3, 2)]
        lines.extend(["", "Level {}".format(index), "Encounter table: levels {}.".format(band)])
        for area in contents.areas:
            lines.extend([
                "", "Area {} (column {}, row {})".format(area.number, area.cell[0] + 1, area.cell[1] + 1),
                "Monster presence roll: {} vs DC {}.".format(area.presence_roll, encounter_chance),
                "Monster table roll: {}.".format(area.table_roll if area.table_roll is not None else "not rolled"),
            ])
            lines.extend(area.debug)
            lines.append("Encounter result: " + (area.monster.description if area.monster else "No monster"))
            lines.extend("Treasure result: " + item for item in area.treasure)
            if area.container:
                lines.append("Treasure container: " + area.container)
            if area.container == "chest":
                if area.chest_locked is not None:
                    lines.append("Chest lock result: " + ("locked" if area.chest_locked else "unlocked"))
                lines.append("Chest trap result: " + (area.chest_trap or "None."))
    return "\n".join(lines) + "\n"
