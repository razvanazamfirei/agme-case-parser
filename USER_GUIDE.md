# Case Parser User Guide

## Overview

Case Parser converts raw anesthesia case logs into a standardized format and supports optional ACGME auto-fill via a Chrome extension.

## Quick Start (CLI)

1. Install dependencies.

```bash
uv sync
uv pip install -e .
```

2. Process a file.

```bash
case-parser input.xlsx output.xlsx
```

3. Review warnings or generate a validation report.

```bash
case-parser input.xlsx output.xlsx --validation-report validation.xlsx
```

## Data Requirements

The parser auto-detects common column names. Key fields:

- Date
- Episode ID
- Responsible Provider
- Age At Encounter
- ASA
- Emergent
- Procedure
- Services
- Procedure Notes

If your file uses different headers, override them with `--col-*` options.

## Input File Format (Exact)

- File types: `.xlsx`, `.xls`, or `.csv`.
- First row must be headers. One row per case.
- Required columns (exact header names unless overridden):
- `Date`
- `Episode ID`
- `Responsible Provider`
- `Age At Encounter`
- `ASA`
- `Final Anesthesia Type`
- `Procedure`
- `Services`
- Optional columns:
- `Emergent`
- `Procedure Notes`
- `Services` values must be newline-separated within the cell (multiple lines).
- `Date` must be parseable by pandas (recommended: `MM/DD/YYYY`). Unparseable or missing dates fall back to `--default-year` (defaults to 2025) with January 1 as the date.
- `Age At Encounter` must be numeric.
- `Emergent` accepts `E`, `Y`, `YES`, `TRUE`, or `1` (case-insensitive). If present and `ASA` lacks an `E`, the parser appends it.

## Common Workflows

1. Standardize your case log and keep a clean output for review.

```bash
case-parser input.xlsx output.xlsx --validation-report validation.txt
```

2. Export JSON for other systems.

```bash
case-parser input.xlsx output.xlsx --json-export cases.json --resident-id "1325527"
```

## Chrome Extension Setup

Install extension dependencies.

```bash
cd chrome-extension
bun install
bun run build
```

Load the extension in Chrome.

1. Open `chrome://extensions/`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select `chrome-extension/dist`.

## Chrome Extension Usage

1. Open the ACGME Case Entry page.
2. Click the extension icon.
3. Upload an Excel or CSV file.
4. Click Fill to populate the form.
5. Submit when ready.

## Troubleshooting

- If the extension does not appear, confirm Developer mode is on and the unpacked extension points to `chrome-extension/dist`.
- If fields do not fill, confirm you are on the Case Entry page and the file is `.xlsx`, `.xls`, or `.csv`.
- If columns are missing, run the CLI with `--col-*` overrides and re-upload the standardized output file.

## Next Steps

- See `README.md` for full project details.
- See `chrome-extension/README.md` for packaging and release workflows.
