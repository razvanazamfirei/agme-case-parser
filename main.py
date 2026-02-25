#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "case-parser",
# ]
# ///
"""Main entry point for the case parser application."""

from case_parser.cli import main

if __name__ == "__main__":
    main()
