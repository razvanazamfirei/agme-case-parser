"""Match and copy resident Excel files based on a names list."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


def normalize_name(raw: str) -> list[str]:
    """Return candidate lookup keys for a name, handling parenthetical variants."""
    no_parens = re.sub(r"\s*\([^)]+\)", "", raw).strip()
    no_quotes = re.sub(r'\s*"[^"]+"\s*', " ", no_parens).strip()
    words = no_quotes.split()
    candidates = [no_quotes]
    if len(words) >= 3:
        candidates.append(f"{words[0]} {words[-1]}")
    alternative = re.search(r"\(([^)]+)\)", raw)
    if alternative:
        candidates.append(f"{alternative.group(1)} {no_quotes.split()[-1]}")
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Match and copy resident Excel files based on a names list"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("Output-Individual"),
        help="Directory containing processed Excel files (default: Output-Individual)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("Output-Residents"),
        help="Directory to copy matched files into (default: Output-Residents)",
    )
    parser.add_argument(
        "--names-file",
        type=Path,
        default=Path("anesthesia-residents.txt"),
        help="Text file with one resident name per line "
        "(default: anesthesia-residents.txt)",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy files even when there are unmatched residents "
        "(default: only copy if all matched)",
    )
    args = parser.parse_args()

    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir
    names_file: Path = args.names_file

    if not input_dir.exists():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    if not names_file.exists():
        print(f"Error: names file not found: {names_file}", file=sys.stderr)
        sys.exit(1)

    available = {f.stem.lower(): f for f in input_dir.glob("*.xlsx")}
    if not available:
        print(f"Warning: no .xlsx files found in {input_dir}", file=sys.stderr)

    names = [
        line.strip()
        for line in names_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    matched: dict[str, Path] = {}
    unmatched: list[tuple[str, list[str]]] = []

    for name in names:
        candidates = normalize_name(name)
        found = next(
            (available[c.lower()] for c in candidates if c.lower() in available), None
        )
        if found:
            matched[name] = found
        else:
            unmatched.append((name, candidates))

    print(f"Matched: {len(matched)}/{len(names)}")

    if unmatched:
        print("Unmatched:")
        for name, candidates in unmatched:
            print(f"  {name!r} -> tried: {candidates}")
        if not args.copy:
            print("\nNo files copied. Use --copy to copy matched files anyway.")
            sys.exit(1)

    output_dir.mkdir(exist_ok=True)
    for src in matched.values():
        shutil.copy2(src, output_dir / src.name)
    print(f"\nCopied {len(matched)} files to {output_dir}/")


if __name__ == "__main__":
    main()
