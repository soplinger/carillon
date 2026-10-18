#!/usr/bin/env python3
"""Carillon: an offline change-ringing method checker.

Reads a plain-text method file (stage plus place notation), expands the lead
into rows, and reports whether one plain course is true, how much of the
permutation space it covers, where each bell travels, and how long it rings.
Standard library only. No network access, no accounts.
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

BELL_SYMBOLS = "1234567890ET"  # bells 10, 11 and 12 are written 0, E and T
MIN_STAGE = 2
MAX_STAGE = 12
METHOD_KEYS = ("name", "stage", "lead")
DEFAULT_CHANGES = 5000
DEFAULT_PER_CHANGE = "3"
EXIT_OK = 0
EXIT_FALSE = 1
EXIT_INPUT_ERROR = 2

_TOKEN_RE = re.compile(r"[X\-]|[0-9ET]+|\s+|[,.]+")


class CarillonError(Exception):
    """Input that cannot be understood. Carries an optional 1-based line number."""

    def __init__(self, message, line=None):
        super().__init__(message)
        self.message = message
        self.line = line


@dataclass(frozen=True)
class Change:
    """One change: its written label, the places it makes, and the row mapping.

    The new row is built as new[i] = old[src[i]] (0-based positions).
    """

    label: str
    places: tuple
    src: tuple


@dataclass(frozen=True)
class Method:
    name: str
    stage: int
    lead: tuple


def change_permutation(places, stage, line=None):
    """Work out which adjacent pairs swap for a change with the given places.

    Places are positions that stay put. Every other position is paired with
    its neighbour, scanning from the front. On an odd stage the last position
    is an implicit place when nothing pairs with it.
    """
    listed = set(places)
    src = list(range(stage))
    pos = 1
    while pos <= stage:
        if pos in listed:
            pos += 1
        elif pos < stage and pos + 1 not in listed:
            src[pos - 1], src[pos] = src[pos], src[pos - 1]
            pos += 2
        elif pos == stage and stage % 2 == 1:
            pos += 1
        else:
            raise CarillonError(
                f"position {pos} has no partner to swap with at stage {stage}", line
            )
    return tuple(src)


def parse_notation(text, stage, line=None):
    """Split place notation into (label, places) pairs, one per change.

    'x' or '-' is a change with no places. A run of place symbols such as
    '16' is a single change. Spaces, commas and dots are optional separators.
    """
    text = text.upper()
    changes = []
    pos = 0
    for match in _TOKEN_RE.finditer(text):
        if match.start() != pos:
            raise CarillonError(f"unexpected character {text[pos]!r} in notation", line)
        pos = match.end()
        token = match.group()
        if token in ("X", "-"):
            changes.append(("x", ()))
            continue
        if token[0] in ",." or token[0].isspace():
            continue
        places = []
        for symbol in token:
            value = BELL_SYMBOLS.index(symbol) + 1
            if value > stage:
                raise CarillonError(f"place {symbol} is outside stage {stage}", line)
            if places and value <= places[-1]:
                raise CarillonError(f"places in {token!r} must be strictly ascending", line)
            places.append(value)
        changes.append((token, tuple(places)))
    if pos != len(text):
        raise CarillonError(f"unexpected character {text[pos]!r} in notation", line)
    return changes


def make_change(label, places, stage, line=None):
    return Change(label, places, change_permutation(places, stage, line))


def parse_method(text):
    """Parse the text of a method file. Raises CarillonError with a line number."""
    fields = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise CarillonError("expected 'key = value'", number)
        key, value = (part.strip() for part in line.split("=", 1))
        key = key.lower()
        if key not in METHOD_KEYS:
            raise CarillonError(
                f"unknown key {key!r} (expected name, stage or lead)", number
            )
        if key in fields:
            raise CarillonError(
                f"duplicate key {key!r}, first set on line {fields[key][1]}", number
            )
        if not value:
            raise CarillonError(f"key {key!r} has no value", number)
        fields[key] = (value, number)

    for key in ("stage", "lead"):
        if key not in fields:
            raise CarillonError(f"missing required key {key!r}")

    stage_text, stage_line = fields["stage"]
    try:
        stage = int(stage_text)
    except ValueError:
        raise CarillonError(
            f"stage must be a whole number, got {stage_text!r}", stage_line
        ) from None
    if not MIN_STAGE <= stage <= MAX_STAGE:
        raise CarillonError(
            f"stage must be between {MIN_STAGE} and {MAX_STAGE}, got {stage}", stage_line
        )

    lead_text, lead_line = fields["lead"]
    pairs = parse_notation(lead_text, stage, lead_line)
    if not pairs:
        raise CarillonError("lead has no changes", lead_line)
    lead = tuple(make_change(label, places, stage, lead_line) for label, places in pairs)

    name = fields.get("name", ("Unnamed method", 0))[0]
    return Method(name=name, stage=stage, lead=lead)


def load_method(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
    except UnicodeDecodeError:
        raise CarillonError("file is not UTF-8 text") from None
    except OSError as error:
        raise CarillonError(f"cannot read file: {error.strerror}") from None
    return parse_method(text)


def apply_change(row, change):
    return tuple(row[index] for index in change.src)


def rows_text(row):
    return "".join(BELL_SYMBOLS[bell - 1] for bell in row)


def plain_course(method):
    """Rows of one plain course: rounds, then every change up to the next rounds.

    The first and last rows are both rounds.
    """
    rounds = tuple(range(1, method.stage + 1))
    rows = [rounds]
    row = rounds
    while True:
        for change in method.lead:
            row = apply_change(row, change)
            rows.append(row)
            if row == rounds:
                return rows


def repeated_rows(rows):
    """Pairs (first, later) of row indexes where a row repeats within one course."""
    first_seen = {}
    repeats = []
    for index, row in enumerate(rows[:-1]):
        if row in first_seen:
            repeats.append((first_seen[row], index))
        else:
            first_seen[row] = index
    return repeats


def format_fraction(value):
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):.2f}"


def format_duration(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02}:{secs:02}"
    return f"{minutes}:{secs:02}"


def places_text(change):
    return ",".join(str(place) for place in change.places) or "none"


def cmd_check(args):
    method = load_method(args.file)
    rows = plain_course(method)
    repeats = repeated_rows(rows)
    print(f"{args.file}: {method.name} (stage {method.stage}) is valid")
    print(f"course: {len(rows) - 1} changes")
    if not repeats:
        print("TRUE: no row repeats within the plain course")
        return EXIT_OK
    for first, later in repeats:
        print(
            f"row {later} repeats row {first}: {rows_text(rows[later])}"
        )
    print(f"FALSE: {len(repeats)} repeated row(s) in the plain course")
    return EXIT_FALSE


def build_summary(method):
    rows = plain_course(method)
    course_changes = len(rows) - 1
    distinct = len(set(rows[:-1]))
    total = math.factorial(method.stage)
    return {
        "name": method.name,
        "stage": method.stage,
        "lead_changes": len(method.lead),
        "course_changes": course_changes,
        "leads": float(Fraction(course_changes, len(method.lead))),
        "true": not repeated_rows(rows),
        "repeated_rows": len(repeated_rows(rows)),
        "distinct_rows": distinct,
        "possible_rows": total,
        "extent_percent": round(100 * distinct / total, 2),
    }


def cmd_summary(args):
    summary = build_summary(load_method(args.file))
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return EXIT_OK
    print(f"{summary['name']} (stage {summary['stage']})")
    print(f"  lead:    {summary['lead_changes']} changes")
    print(
        f"  course:  {summary['course_changes']} changes "
        f"({format_fraction(Fraction(summary['course_changes'], summary['lead_changes']))} leads)"
    )
    truth = "TRUE" if summary["true"] else f"FALSE ({summary['repeated_rows']} repeated rows)"
    print(f"  truth:   {truth}")
    print(
        f"  extent:  {summary['distinct_rows']} of {summary['possible_rows']} rows "
        f"({summary['extent_percent']:.2f}%)"
    )
    return EXIT_OK


def cmd_explain(args):
    method = load_method(args.file)
    rows = plain_course(method)
    print(f"{method.name}: first lead from rounds")
    for index in range(min(len(method.lead), len(rows) - 1)):
        change = method.lead[index]
        print(
            f"{index + 1:>3}  {change.label:<6} {rows_text(rows[index])} -> "
            f"{rows_text(rows[index + 1])}   places: {places_text(change)}"
        )
    return EXIT_OK


def cmd_rows(args):
    method = load_method(args.file)
    rows = plain_course(method)
    lead_length = len(method.lead)
    last = len(rows) - 1
    for index, row in enumerate(rows):
        note = ""
        if index == last:
            note = "  -- rounds, course end"
        elif index and index % lead_length == 0:
            note = "  -- lead end"
        print(f"{index:>4}  {rows_text(row)}{note}")
    return EXIT_OK


def cmd_path(args):
    method = load_method(args.file)
    if not 1 <= args.bell <= method.stage:
        raise CarillonError(f"bell must be between 1 and {method.stage}")
    rows = plain_course(method)[:-1]
    counts = Counter()
    for index, row in enumerate(rows):
        position = row.index(args.bell) + 1
        counts[position] += 1
        print(f"{index:>4}  {rows_text(row)}  {'  ' * (position - 1)}o")
    shares = "  ".join(f"{pos}:{counts[pos]}" for pos in range(1, method.stage + 1))
    print(f"bell {args.bell} rows at each position: {shares}")
    return EXIT_OK


def cmd_time(args):
    method = load_method(args.file)
    course_length = len(plain_course(method)) - 1
    try:
        per_change = Fraction(args.per_change)
    except (ValueError, ZeroDivisionError):
        raise CarillonError(
            f"--per-change must be a number of seconds, got {args.per_change!r}"
        ) from None
    if per_change <= 0:
        raise CarillonError("--per-change must be greater than zero")
    if args.changes < 1:
        raise CarillonError("changes must be at least 1")
    seconds = round(args.changes * per_change)
    courses = Fraction(args.changes, course_length)
    print(f"{method.name}: {args.changes} changes at {format_fraction(per_change)} s per change")
    print(f"  courses: {format_fraction(courses)} ({course_length} changes per course)")
    print(f"  time:    {format_duration(seconds)}")
    return EXIT_OK


def cmd_change(args):
    if not MIN_STAGE <= args.stage <= MAX_STAGE:
        raise CarillonError(f"stage must be between {MIN_STAGE} and {MAX_STAGE}")
    pairs = parse_notation(args.notation, args.stage)
    if not pairs:
        raise CarillonError("notation has no changes")
    row = tuple(range(1, args.stage + 1))
    print(f"start  {rows_text(row)}")
    for label, places in pairs:
        change = make_change(label, places, args.stage)
        row = apply_change(row, change)
        print(f"{label:<6} {rows_text(row)}")
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(
        prog="carillon",
        description="Offline change-ringing method checker. Exit codes: 0 ok, "
        "1 method is false, 2 input error.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="validate a method file and test truth")
    check.add_argument("file")
    check.set_defaults(handler=cmd_check)

    summary = commands.add_parser("summary", help="course length, truth and extent")
    summary.add_argument("file")
    summary.add_argument("--json", action="store_true", help="print JSON")
    summary.set_defaults(handler=cmd_summary)

    explain = commands.add_parser("explain", help="show each change of the first lead")
    explain.add_argument("file")
    explain.set_defaults(handler=cmd_explain)

    rows = commands.add_parser("rows", help="print every row of one plain course")
    rows.add_argument("file")
    rows.set_defaults(handler=cmd_rows)

    path = commands.add_parser("path", help="trace one bell through the course")
    path.add_argument("file")
    path.add_argument("bell", type=int)
    path.set_defaults(handler=cmd_path)

    time = commands.add_parser("time", help="estimate ringing time for a number of changes")
    time.add_argument("file")
    time.add_argument("--changes", type=int, default=DEFAULT_CHANGES)
    time.add_argument("--per-change", default=DEFAULT_PER_CHANGE, help="seconds per change")
    time.set_defaults(handler=cmd_time)

    change = commands.add_parser("change", help="expand inline place notation")
    change.add_argument("stage", type=int)
    change.add_argument("notation")
    change.set_defaults(handler=cmd_change)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except CarillonError as error:
        source = getattr(args, "file", "carillon")
        location = f"{source}:{error.line}" if error.line else source
        print(f"{location}: error: {error.message}", file=sys.stderr)
        return EXIT_INPUT_ERROR


if __name__ == "__main__":
    sys.exit(main())
