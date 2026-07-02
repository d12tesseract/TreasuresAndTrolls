#!/usr/bin/env python3
"""Compute Elven Urish calendar details from the formulas in ur.md.

Example:
    python ur_calendar.py 315
    python ur_calendar.py 315 --json
    python ur_calendar.py --check-example
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, getcontext
from fractions import Fraction
from typing import Any


getcontext().prec = 28

YPA = 883
MPA = 11166
DPA = 316152
EDPM = Decimal("0.3138")

MONTH_NAMES = (
    "Balard",
    "Caerbanuary",
    "Afranus",
    "Tarwa",
    "Heluary",
    "Derwember",
    "Arle",
    "Gwanuary",
    "Nassaras",
    "Ularthus",
    "Athlanuary",
    "Reithamber",
    "Dothember",
)

SEASONAL_EVENTS = (
    ("Spring equinox", Fraction(1, 4)),
    ("Summer solstice", Fraction(1, 2)),
    ("Fall equinox", Fraction(3, 4)),
    ("Winter solstice", Fraction(1, 1)),
)

FESTIVAL_NAMES = (
    "New year festival",
    "Spring festival",
    "Summer festival",
    "Harvest festival",
)

WEEK_NAMES = ("Sunweek", "Avenweek", "Moonweek", "Elderweek")
YEAR_TYPE_NAMES = ("Sun year", "Aven year", "Moon year", "Elder year")


def s_int(value: Fraction) -> int:
    """Spreadsheet-style INT for positive values."""
    return value.numerator // value.denominator


def s_frac(value: Fraction) -> Fraction:
    return value - s_int(value)


def float_text(value: Fraction | float, digits: int = 15) -> str:
    return f"{float(value):.{digits}g}"


def decimal_fraction(value: Decimal) -> Decimal:
    return value - Decimal(int(value))


def calculate_calendar(aegon_year: int) -> dict[str, Any]:
    if 1 > aegon_year or YPA < aegon_year:
        raise ValueError(f"aegon_year must be in the range 1..{YPA}")

    zby = aegon_year - 1
    mpy = Fraction(MPA, YPA)
    lom = Fraction(DPA, MPA)
    loy = Fraction(DPA, YPA)
    lyws = Fraction(zby * MPA, YPA)
    mbys = s_int(lyws)
    tds = Decimal(mbys) * EDPM
    dbofm = decimal_fraction(tds)

    seasonal_events: list[dict[str, Any]] = []
    for name, year_fraction in SEASONAL_EVENTS:
        month_value = lyws + (mpy * year_fraction) - mbys
        month = s_int(month_value)
        if 1 > month or len(MONTH_NAMES) < month:
            raise ValueError(f"{name} calculated outside the supported month range: {month}")

        zero_based_day_value = s_frac(month_value) * lom
        day = s_int(zero_based_day_value) + 1
        seasonal_events.append(
            {
                "event_name": name,
                "month_position_in_year": month_value,
                "month_number": month,
                "month_name": MONTH_NAMES[month - 1],
                "zero_based_day_in_month": zero_based_day_value,
                "day_of_month": day,
            }
        )

    months_in_year = seasonal_events[-1]["month_number"]
    month_lengths = calculate_month_lengths(mbys, months_in_year)

    return {
        "aegon_year": aegon_year,
        "year_since_start_of_aegon": zby,
        "calendar_constants": {
            "years_per_aegon": YPA,
            "months_per_aegon": MPA,
            "days_per_aegon": DPA,
            "length_of_year": loy,
            "length_of_month": lom,
            "months_per_year": mpy,
            "extra_days_per_month": EDPM,
        },
        "year_start_calculations": {
            "last_year_winter_solstice_in_months": lyws,
            "months_before_year_starts": mbys,
            "total_days_short": tds,
            "days_behind_on_first_month": dbofm,
        },
        "months_in_year": months_in_year,
        "seasonal_events": seasonal_events,
        "month_lengths": month_lengths,
    }


def calculate_month_lengths(mbys: int, months_in_year: int) -> list[dict[str, Any]]:
    days_behind = decimal_fraction(Decimal(mbys) * EDPM)
    month_lengths: list[dict[str, Any]] = []

    for month in range(1, months_in_year + 1):
        days_behind += EDPM
        if Decimal(1) <= days_behind:
            days = 29
            days_behind -= Decimal(1)
        else:
            days = 28

        month_lengths.append(
            {
                "month_number": month,
                "month_name": MONTH_NAMES[month - 1],
                "days_in_month": days,
                "days_behind_at_end_of_month": days_behind,
            }
        )

    return month_lengths


def to_jsonable(calendar: dict[str, Any]) -> dict[str, Any]:
    return jsonable_value(calendar)


def jsonable_value(value: Any) -> Any:
    if isinstance(value, Fraction):
        return float(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: jsonable_value(child_value) for key, child_value in value.items()}
    if isinstance(value, list):
        return [jsonable_value(child_value) for child_value in value]
    return value


def months_before_year_start(aegon_year: int) -> int:
    return s_int(Fraction((aegon_year - 1) * MPA, YPA))


def months_in_aegon_year(aegon_year: int) -> int:
    year_start = months_before_year_start(aegon_year)
    next_year_start = MPA if YPA == aegon_year else months_before_year_start(aegon_year + 1)
    return next_year_start - year_start


def week_index_for_day(day_of_month: int) -> int:
    return min((day_of_month - 1) // 7, len(WEEK_NAMES) - 1)


def year_start_details(calendar: dict[str, Any]) -> dict[str, Any]:
    aegon_year = calendar["aegon_year"]
    prior_year = YPA if 1 == aegon_year else aegon_year - 1
    prior_months_in_year = months_in_aegon_year(prior_year)
    prior_month_lengths = calculate_month_lengths(
        months_before_year_start(prior_year), prior_months_in_year
    )
    prior_last_month = prior_month_lengths[-1]

    solstice_month_position = calendar["year_start_calculations"][
        "last_year_winter_solstice_in_months"
    ]
    solstice_zero_based_day = (
        s_frac(solstice_month_position) * calendar["calendar_constants"]["length_of_month"]
    )
    solstice_day = s_int(solstice_zero_based_day) + 1
    days_after_solstice = max(0, prior_last_month["days_in_month"] - solstice_day)
    year_type_index = week_index_for_day(solstice_day)
    prior_solstice_week = WEEK_NAMES[year_type_index]

    return {
        "year_type": YEAR_TYPE_NAMES[year_type_index],
        "new_year_begins_week": WEEK_NAMES[year_type_index],
        "days_after_prior_solstice": days_after_solstice,
        "prior_year": prior_year,
        "prior_solstice_month_name": prior_last_month["month_name"],
        "prior_solstice_month_number": prior_last_month["month_number"],
        "prior_solstice_day_of_month": solstice_day,
        "prior_solstice_week": prior_solstice_week,
    }


def festival_name(festival_index: int) -> str:
    if festival_index < len(FESTIVAL_NAMES):
        return FESTIVAL_NAMES[festival_index]
    return "Additional festival"


def print_calendar(calendar: dict[str, Any]) -> None:
    details = year_start_details(calendar)
    print(
        f"Aegon year {calendar['aegon_year']} ({details['year_type']}) "
        f"(zby {calendar['year_since_start_of_aegon']})"
    )

    print(
        f"The prior year winter solstice is on {details['prior_solstice_month_name']} "
        f"{details['prior_solstice_day_of_month']} "
        f"({details['prior_solstice_week']}) of year {details['prior_year']}"
    )
    print()
    print(f"Seasonal events ({calendar['months_in_year']} months in this year)")
    for event in calendar["seasonal_events"]:
        print(
            f"  {event['event_name']}: {event['month_number']}/{event['day_of_month']} "
            f"({event['month_name']}; month_position_in_year="
            f"{float_text(event['month_position_in_year'])}, "
            f"zero_based_day_in_month={float_text(event['zero_based_day_in_month'])})"
        )

    print()
    print("Festivals (29-day months; all other months have 28 days)")
    festival_months = [
        month for month in calendar["month_lengths"] if 29 == month["days_in_month"]
    ]
    for festival_index, month in enumerate(festival_months):
        print(
            f"  {festival_name(festival_index)}: "
            f"{month['month_name']} (month {month['month_number']}, day 29)"
        )


def check_example() -> None:
    calendar = calculate_calendar(315)
    details = year_start_details(calendar)
    events_by_name = {event["event_name"]: event for event in calendar["seasonal_events"]}

    if "Moon year" != details["year_type"]:
        raise AssertionError(f"year_type: expected Moon year, got {details['year_type']}")
    if "Moonweek" != details["prior_solstice_week"]:
        raise AssertionError(
            f"prior_solstice_week: expected Moonweek, got {details['prior_solstice_week']}"
        )

    expected_event_dates = {
        "Spring equinox": (3, 25),
        "Summer solstice": (7, 1),
        "Fall equinox": (10, 6),
        "Winter solstice": (13, 10),
    }
    for event_name, expected in expected_event_dates.items():
        event = events_by_name[event_name]
        actual = (event["month_number"], event["day_of_month"])
        if actual != expected:
            raise AssertionError(f"{event_name}: expected {expected}, got {actual}")

    expected_month_lengths = [29, 28, 28, 29, 28, 28, 28, 29, 28, 28, 29, 28, 28]
    actual_month_lengths = [month["days_in_month"] for month in calendar["month_lengths"]]
    if actual_month_lengths != expected_month_lengths:
        raise AssertionError(
            f"month lengths: expected {expected_month_lengths}, got {actual_month_lengths}"
        )

    expected_values = {
        "lyws": 3970.69535673839,
        "se": 3.85673839184574,
        "ss": 7.01812004529984,
        "fe": 10.1795016987539,
        "ws": 13.340883352208,
        "sedom": 24.2575278576763,
        "ssdom": 0.513047515818956,
        "fedom": 5.08237695364993,
        "wsdom": 9.65170639148091,
    }
    actual_values = {
        "lyws": float(
            calendar["year_start_calculations"]["last_year_winter_solstice_in_months"]
        ),
        "se": float(events_by_name["Spring equinox"]["month_position_in_year"]),
        "ss": float(events_by_name["Summer solstice"]["month_position_in_year"]),
        "fe": float(events_by_name["Fall equinox"]["month_position_in_year"]),
        "ws": float(events_by_name["Winter solstice"]["month_position_in_year"]),
        "sedom": float(events_by_name["Spring equinox"]["zero_based_day_in_month"]),
        "ssdom": float(events_by_name["Summer solstice"]["zero_based_day_in_month"]),
        "fedom": float(events_by_name["Fall equinox"]["zero_based_day_in_month"]),
        "wsdom": float(events_by_name["Winter solstice"]["zero_based_day_in_month"]),
    }
    for name, expected in expected_values.items():
        actual = actual_values[name]
        if abs(actual - expected) > 1e-11:
            raise AssertionError(f"{name}: expected {expected}, got {actual}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute Urish calendar details for an Aegon year."
    )
    parser.add_argument(
        "aegon_year",
        nargs="?",
        type=int,
        help=f"1-based year within the {YPA}-year aegon, for example 315",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--check-example",
        action="store_true",
        help="verify that year 315 matches the worked example in ur.md",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.check_example:
        check_example()
        print("Example check passed for Aegon year 315.")
        if args.aegon_year is None:
            return 0

    if args.aegon_year is None:
        print("error: aegon_year is required unless --check-example is used", file=sys.stderr)
        return 2

    try:
        calendar = calculate_calendar(args.aegon_year)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(to_jsonable(calendar), indent=2))
    else:
        print_calendar(calendar)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
