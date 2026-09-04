#!/usr/bin/env python3
"""Generate and verify the fixed Unicode 13 terminal tables without networking."""

from __future__ import annotations

import argparse
import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

UNICODE_VERSION = "13.0.0"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "apps" / "web" / "src" / "features" / "workspace" / "terminalUnicodeWidthData.ts"
)


@dataclass(frozen=True)
class Source:
    filename: str
    url: str
    sha256: str


SOURCES = (
    Source(
        "DerivedGeneralCategory.txt",
        "https://www.unicode.org/Public/13.0.0/ucd/extracted/DerivedGeneralCategory.txt",
        "4502f0969e4e6558c4b4c6ca4c23dad70b863d61dd3d5eed1a62a6c3c99fd570",
    ),
    Source(
        "EastAsianWidth.txt",
        "https://www.unicode.org/Public/13.0.0/ucd/EastAsianWidth.txt",
        "4f822ec7a9ebbb3138ad29bade8b9688d25b39c7a3c0b7431f01e7229e4fcb6e",
    ),
    Source(
        "PropList.txt",
        "https://www.unicode.org/Public/13.0.0/ucd/PropList.txt",
        "485b5a3ed25dbf1f94dfa5a9b69d8b4550ffd0c33045ccc55ccfd7c80b2a40cf",
    ),
    Source(
        "DerivedCoreProperties.txt",
        "https://www.unicode.org/Public/13.0.0/ucd/DerivedCoreProperties.txt",
        "a5d45f59b39deaab3c72ce8c1a2e212a5e086dff11b1f9d5bb0e352642e82248",
    ),
    Source(
        "GraphemeBreakProperty.txt",
        "https://www.unicode.org/Public/13.0.0/ucd/auxiliary/GraphemeBreakProperty.txt",
        "2bd3c5e2d62701ff81fb3ec318e179a4618cabb1493b1e0dd2b4e7e56c5437c4",
    ),
    Source(
        "emoji-data.txt",
        "https://www.unicode.org/Public/13.0.0/ucd/emoji/emoji-data.txt",
        "d2686f400a638c80775d7c662556fb8fa8dd3bbe4aa548d9d31624264c6e1bb1",
    ),
)

TABLE_NAMES = (
    "TERMINAL_COMBINING_RANGES",
    "TERMINAL_WIDE_RANGES",
    "TERMINAL_BIDI_CONTROL_RANGES",
    "TERMINAL_DEFAULT_IGNORABLE_RANGES",
    "TERMINAL_HANGUL_L_RANGES",
    "TERMINAL_HANGUL_V_RANGES",
    "TERMINAL_HANGUL_T_RANGES",
    "TERMINAL_HANGUL_LV_RANGES",
    "TERMINAL_HANGUL_LVT_RANGES",
    "TERMINAL_EMOJI_MODIFIER_RANGES",
    "TERMINAL_EMOJI_MODIFIER_BASE_RANGES",
)

EXPECTED_COUNTS = {
    "TERMINAL_COMBINING_RANGES": (1852, 324),
    "TERMINAL_WIDE_RANGES": (117134, 123),
    "TERMINAL_BIDI_CONTROL_RANGES": (12, 4),
    "TERMINAL_DEFAULT_IGNORABLE_RANGES": (4173, 17),
    "TERMINAL_HANGUL_L_RANGES": (125, 2),
    "TERMINAL_HANGUL_V_RANGES": (95, 2),
    "TERMINAL_HANGUL_T_RANGES": (137, 2),
    "TERMINAL_HANGUL_LV_RANGES": (399, 399),
    "TERMINAL_HANGUL_LVT_RANGES": (10773, 399),
    "TERMINAL_EMOJI_MODIFIER_RANGES": (5, 1),
    "TERMINAL_EMOJI_MODIFIER_BASE_RANGES": (122, 38),
}

LINE_RE = re.compile(r"^\s*([0-9A-F]{4,6})(?:\.\.([0-9A-F]{4,6}))?\s*;\s*([^\s#]+)")
RANGE_RE = re.compile(r"\[0x([0-9a-f]+), 0x([0-9a-f]+)\]")


Range = tuple[int, int]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_bytes(source_dir: Path) -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for source in SOURCES:
        data = (source_dir / source.filename).read_bytes()
        digest = _sha256(data)
        if digest != source.sha256:
            raise ValueError(f"{source.filename}: expected sha256 {source.sha256}, got {digest}")
        values[source.filename] = data
    return values


def _property_ranges(data: bytes, properties: set[str]) -> list[Range]:
    ranges: list[Range] = []
    for raw_line in data.decode("utf-8").splitlines():
        match = LINE_RE.match(raw_line)
        if not match or match.group(3) not in properties:
            continue
        start = int(match.group(1), 16)
        end = int(match.group(2) or match.group(1), 16)
        ranges.append((start, end))
    return _merge_ranges(ranges)


def _merge_ranges(ranges: Iterable[Range]) -> list[Range]:
    merged: list[Range] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _points(ranges: Iterable[Range]) -> set[int]:
    return {value for start, end in ranges for value in range(start, end + 1)}


def _from_points(points: Iterable[int]) -> list[Range]:
    values = sorted(set(points))
    if not values:
        return []
    ranges: list[Range] = []
    start = previous = values[0]
    for value in values[1:]:
        if value != previous + 1:
            ranges.append((start, previous))
            start = value
        previous = value
    ranges.append((start, previous))
    return ranges


def _build_tables(sources: dict[str, bytes]) -> dict[str, list[Range]]:
    categories = sources["DerivedGeneralCategory.txt"]
    combining = _property_ranges(categories, {"Mn", "Me"})
    assigned = _points(
        _property_ranges(
            categories,
            {
                "Cc",
                "Cf",
                "Co",
                "Cs",
                "Ll",
                "Lm",
                "Lo",
                "Lt",
                "Lu",
                "Mc",
                "Me",
                "Mn",
                "Nd",
                "Nl",
                "No",
                "Pc",
                "Pd",
                "Pe",
                "Pf",
                "Pi",
                "Po",
                "Ps",
                "Sc",
                "Sk",
                "Sm",
                "So",
                "Zl",
                "Zp",
                "Zs",
            },
        )
    )
    wide = _from_points(
        assigned & _points(_property_ranges(sources["EastAsianWidth.txt"], {"W", "F"}))
    )
    grapheme = sources["GraphemeBreakProperty.txt"]
    emoji = sources["emoji-data.txt"]
    tables = {
        "TERMINAL_COMBINING_RANGES": combining,
        "TERMINAL_WIDE_RANGES": wide,
        "TERMINAL_BIDI_CONTROL_RANGES": _property_ranges(sources["PropList.txt"], {"Bidi_Control"}),
        "TERMINAL_DEFAULT_IGNORABLE_RANGES": _property_ranges(
            sources["DerivedCoreProperties.txt"],
            {"Default_Ignorable_Code_Point"},
        ),
        "TERMINAL_HANGUL_L_RANGES": _property_ranges(grapheme, {"L"}),
        "TERMINAL_HANGUL_V_RANGES": _property_ranges(grapheme, {"V"}),
        "TERMINAL_HANGUL_T_RANGES": _property_ranges(grapheme, {"T"}),
        "TERMINAL_HANGUL_LV_RANGES": _property_ranges(grapheme, {"LV"}),
        "TERMINAL_HANGUL_LVT_RANGES": _property_ranges(grapheme, {"LVT"}),
        "TERMINAL_EMOJI_MODIFIER_RANGES": _property_ranges(emoji, {"Emoji_Modifier"}),
        "TERMINAL_EMOJI_MODIFIER_BASE_RANGES": _property_ranges(emoji, {"Emoji_Modifier_Base"}),
    }
    _check_counts(tables)
    return tables


def _check_counts(tables: dict[str, list[Range]]) -> None:
    for name, (expected_points, expected_ranges) in EXPECTED_COUNTS.items():
        ranges = tables[name]
        points = sum(end - start + 1 for start, end in ranges)
        actual = (points, len(ranges))
        if actual != (expected_points, expected_ranges):
            raise ValueError(f"{name}: expected {(expected_points, expected_ranges)}, got {actual}")


def _canonical_bytes(tables: dict[str, list[Range]]) -> bytes:
    lines = ["agentbox-terminal-unicode-v1", f"unicode={UNICODE_VERSION}"]
    for name in TABLE_NAMES:
        serialized = ",".join(f"{start:06X}-{end:06X}" for start, end in tables[name])
        lines.append(f"{name}={serialized}")
    return ("\n".join(lines) + "\n").encode("ascii")


def _render_ranges(name: str, ranges: list[Range]) -> str:
    declaration = f"export const {name}: readonly UnicodeRange[] ="
    serialized = [f"[0x{start:x}, 0x{end:x}]" for start, end in ranges]
    call_on_declaration = len(f"{declaration} freezeRanges(") <= 80
    prefix = f"{declaration} freezeRanges(" if call_on_declaration else declaration
    call_indent = "" if call_on_declaration else "  "
    call_prefix = "" if call_on_declaration else "freezeRanges("

    if len(serialized) == 1:
        inline = f"{call_prefix}[{serialized[0]}])"
        if len(f"{call_indent}{inline}") <= 80:
            if call_indent:
                return f"{prefix}\n{call_indent}{inline}"
            return f"{prefix}[{serialized[0]}])"

    array_on_call_line = (
        len(f"{prefix if call_on_declaration else call_indent + call_prefix}[") <= 80
    )
    if call_on_declaration and array_on_call_line:
        body = "\n".join(f"  {value}," for value in serialized)
        return f"{prefix}[\n{body}\n])"
    if call_on_declaration:
        body = "\n".join(f"    {value}," for value in serialized)
        return f"{prefix}\n  [\n{body}\n  ],\n)"
    body = "\n".join(f"    {value}," for value in serialized)
    return f"{prefix}\n  {call_prefix}[\n{body}\n  ])"


def _render(tables: dict[str, list[Range]]) -> str:
    digest = _sha256(_canonical_bytes(tables))
    sources = "\n".join(
        "  Object.freeze({\n"
        f"    filename: '{source.filename}',\n"
        f"    url: '{source.url}',\n"
        f"    sha256: '{source.sha256}',\n"
        "  }),"
        for source in SOURCES
    )
    arrays = "\n\n".join(_render_ranges(name, tables[name]) for name in TABLE_NAMES)
    return f"""/**
 * Fixed terminal data generated from Unicode Character Database {UNICODE_VERSION}.
 *
 * Run `python3 scripts/generate-terminal-unicode.py --check` to recompute the
 * canonical ASCII range serialization and its digest without network access.
 * Regeneration accepts only locally supplied official files with the exact
 * source hashes below; the generator never downloads data.
 */

export const TERMINAL_UNICODE_VERSION = '{UNICODE_VERSION}' as const
export const TERMINAL_UNICODE_RANGE_SHA256 =
  '{digest}' as const

export const TERMINAL_UNICODE_SOURCES = Object.freeze([
{sources}
])

export type UnicodeRange = readonly [start: number, end: number]

function freezeRanges(ranges: UnicodeRange[]): readonly UnicodeRange[] {{
  for (const range of ranges) Object.freeze(range)
  return Object.freeze(ranges)
}}

{arrays}
"""


def _parse_generated(data: str) -> dict[str, list[Range]]:
    tables: dict[str, list[Range]] = {}
    for index, name in enumerate(TABLE_NAMES):
        start = data.find(f"export const {name}")
        if start < 0:
            raise ValueError(f"missing generated table {name}")
        next_start = (
            data.find(f"export const {TABLE_NAMES[index + 1]}", start)
            if index + 1 < len(TABLE_NAMES)
            else len(data)
        )
        tables[name] = [
            (int(match.group(1), 16), int(match.group(2), 16))
            for match in RANGE_RE.finditer(data[start:next_start])
        ]
    _check_counts(tables)
    return tables


def _check_metadata(data: str, tables: dict[str, list[Range]]) -> None:
    version = re.search(r"TERMINAL_UNICODE_VERSION = '([^']+)'", data)
    digest = re.search(r"TERMINAL_UNICODE_RANGE_SHA256\s*=\s*\n?\s*'([a-f0-9]{64})'", data)
    if not version or version.group(1) != UNICODE_VERSION:
        raise ValueError("generated Unicode version does not match")
    expected_digest = _sha256(_canonical_bytes(tables))
    if not digest or digest.group(1) != expected_digest:
        raise ValueError("generated canonical range digest does not match")
    for source in SOURCES:
        if (
            f"filename: '{source.filename}'" not in data
            or f"url: '{source.url}'" not in data
            or f"sha256: '{source.sha256}'" not in data
        ):
            raise ValueError(f"generated source metadata missing {source.filename}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.source_dir:
        tables = _build_tables(_source_bytes(args.source_dir))
        rendered = _render(tables)
        if args.check:
            if args.output.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"generated file is stale: {args.output}")
        else:
            args.output.write_text(rendered, encoding="utf-8")
    else:
        if not args.check:
            parser.error("--source-dir is required when generating")
        data = args.output.read_text(encoding="utf-8")
        tables = _parse_generated(data)
        _check_metadata(data, tables)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
