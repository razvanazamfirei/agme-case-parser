# Case Parser

A robust Python tool for processing anesthesia case data from Excel files and
converting it to standardized case log format with ACGME web form integration.

## Features

- **Pattern-Based Architecture**: Self-contained extraction modules with clear
  separation of concerns
- **Domain-Driven Design**: Typed domain models with comprehensive validation
  and confidence tracking.
- **Modern Output**: Professional terminal output with color-coding, tables, and
  panels using the rich library.
- **Flexible Configuration**: Customizable column mappings and processing rules
- **Comprehensive Extraction**: Airway management, vascular access, specialized
  monitoring
- **Intelligent Categorization**: Surgery-specific logic for cardiac, vascular,
  intracerebral, and OB/GYN procedures
- **Validation Reporting**: Detailed validation reports in text, JSON, or Excel
  format.
- **Chrome Extension**: Auto-fill ACGME case entry forms (see [Chrome Extension](#chrome-extension))
- **Debug Tools**: Interactive categorization debugger with rich formatting

## Requirements

- Python 3.11+
- `uv` (recommended) or `pip`

## Installation

### Using uv (recommended)

```bash
# Install dependencies
uv sync

# Install in development mode
uv pip install -e .

# Install with dev dependencies (ruff, pytest, type stubs)
uv sync --group dev
```

### Using pip

```bash
pip install -e .
```

## Usage

### Basic Usage

```bash
# Process a single file
python main.py input.xlsx output.xlsx

# Or use the installed command
case-parser input.xlsx output.xlsx
```

### Advanced Usage

```bash
# Specify sheet name and default year
case-parser input.xlsx output.xlsx --sheet "Data" --default-year 2024

# Override column mappings
case-parser input.xlsx output.xlsx --col-date "Date of Service" --col-age "Patient Age"

# Enable verbose logging
case-parser input.xlsx output.xlsx --verbose

# Generate validation report
case-parser input.xlsx output.xlsx --validation-report validation.txt
```

### CSV v2 Format (MPOG Export)

```bash
# Process a directory of CaseList/ProcedureList CSV pairs
case-parser /path/to/csv-dir/ output.xlsx --v2
```

### Batch Processing

```bash
# Process all residents in Output-Supervised/
python batch_process.py

# Custom directories
python batch_process.py --base-dir /path/to/supervised --output-dir /path/to/output

# Sort output files to match a names list
python sort-logs.py --names-file residents.txt --input-dir Output-Individual
```

### Debug Categorization

```bash
# Test a specific procedure categorization
python debug_categorization.py "CABG with CPB" "CARDIAC SURGERY"

# Test with multiple services
python debug_categorization.py "AVR" "CARDIAC,THORACIC"

# Interactive mode
python debug_categorization.py --interactive
```

The debug script displays:

- Rule matching trace with formatted tables
- Pattern matches and exclusions
- The final category with color-coded results
- Warnings and special cases

### Column Mapping

The tool automatically maps common column names, but you can override them using
command-line options:

- `--col-date`: Date column name (default: "Date")
- `--col-episode-id`: Episode ID column name (default: "Episode ID")
- `--col-anesthesiologist`: Anesthesiologist column name (default: "Responsible Provider")
- `--col-age`: Age column name (default: "Age At Encounter")
- `--col-emergent`: Emergent flag column name (default: "Emergent")
- `--col-asa`: ASA status column name (default: "ASA")
- `--col-final-anesthesia-type`: Anesthesia type column name (default: "Final Anesthesia Type")
- `--col-procedure-notes`: Procedure notes column name (default: "Procedure Notes")
- `--col-procedure`: Procedure column name (default: "Procedure")
- `--col-services`: Services column name (default: "Services")

### Input File Format

- File types: `.xlsx`, `.xls`, or `.csv`
- Header row required; one row per case
- Required columns (exact names unless overridden): `Date`, `Episode ID`,
  `Responsible Provider`, `Age At Encounter`, `ASA`, `Final Anesthesia Type`,
  `Procedure`, `Services`
- Optional columns: `Emergent`, `Procedure Notes`
- `Services` values must be newline-separated within the cell
- `Date` should be parseable by pandas (recommended: `MM/DD/YYYY`); missing/unparseable
  dates fall back to `--default-year` (default 2025, January 1)
- `Age At Encounter` must be numeric

For a step-by-step walkthrough, see `USER_GUIDE.md`.

## Chrome Extension

The ACGME case entry Chrome extension lives in the `chrome-extension/`
submodule:

**[razvanazamfirei/acgme-case-parser-extension](https://github.com/razvanazamfirei/acgme-case-parser-extension)**

The extension reads the Excel output produced by this tool and auto-fills ACGME
case entry forms.

To clone this repo with the extension included:

```bash
git clone --recurse-submodules https://github.com/razvanazamfirei/acgme-case-parser.git
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init
```

See `chrome-extension/README.md` for installation and usage instructions.

## Project Structure

```
case-parser/
├── src/
│   └── case_parser/
│       ├── __init__.py              # Package initialization
│       ├── models.py                # Data models and configuration
│       ├── domain.py                # Typed domain models
│       ├── processor.py             # Core data processing
│       ├── extractors.py            # Extraction function exports
│       ├── validation.py            # Validation and reporting
│       ├── csv_io.py                # CSV v2 format I/O
│       ├── io.py                    # Excel file I/O
│       ├── cli.py                   # Command line interface
│       ├── exceptions.py            # Custom exceptions
│       ├── logging_config.py        # Logging configuration
│       ├── ml/                      # ML-enhanced classification
│       │   ├── features.py          # Feature engineering
│       │   ├── hybrid.py            # Hybrid rule+ML classifier
│       │   ├── loader.py            # Model loader
│       │   └── predictor.py         # ML predictor
│       └── patterns/                # Pattern-based extraction
│           ├── __init__.py          # Pattern exports
│           ├── README.md            # Pattern documentation
│           ├── extraction_utils.py  # Shared utilities
│           ├── airway_patterns.py   # Airway management
│           ├── vascular_access_patterns.py  # Vascular access
│           ├── monitoring_patterns.py       # Specialized monitoring
│           ├── procedure_patterns.py        # Categorization rules
│           ├── categorization.py    # Categorization logic
│           ├── approach_patterns.py # Surgical approach detection
│           ├── age_patterns.py      # Age range categorization
│           └── anesthesia_patterns.py       # Anesthesia type mapping
├── chrome-extension/                # Chrome extension (git submodule)
├── tests/                           # Unit tests
├── batch_process.py                 # Batch process all residents
├── sort-logs.py                     # Sort output files by names list
├── debug_categorization.py          # Categorization debugger
├── main.py                          # Main entry point
├── pyproject.toml                   # Project configuration and dependencies
└── README.md                        # This file
```

## Data Processing

The tool processes anesthesia case data and extracts:

- **Case Information**: Episode ID, date, responsible provider
- **Patient Demographics**: Age categorization (ACGME categories a-e)
- **ASA Status**: Physical status with emergency flag handling
- **Procedure Details**: Original procedure text, intelligent categorization
- **Anesthesia Type**: Standardized anesthesia type mapping
- **Airway Management**: Intubation techniques (ETT, LMA, DLT), laryngoscopy
  types (DL, VL), difficult airway indicators
- **Vascular Access**: Arterial lines, central venous catheters, PA catheters
- **Specialized Monitoring**: TEE, electrophysiologic monitoring, CSF drains,
  invasive neuro monitoring

### Intelligent Categorization

Surgery-specific categorization logic:

- **Cardiac**: Distinguishes CPB vs non-CPB procedures (TAVR, CABG, valve
  replacements)
- **Vascular**: Detects endovascular vs open approach (EVAR, TEVAR, open AAA)
- **Intracerebral**: Categorizes by approach and pathology (endovascular,
  vascular open, nonvascular)
- **OB/GYN**: Differentiates cesarean vs vaginal delivery, detects labor
  epidurals

## Validation

The tool includes comprehensive validation with modern formatted reports:

- **Confidence Scoring**: Tracks extraction confidence for each field
- **Warning Detection**: Identifies missing data, unparseable fields, and low
  confidence extractions
- **Multiple Formats**: Generate reports as text (with rich formatting), JSON,
  or Excel.
- **Problematic Case Flagging**: Automatically identifies cases needing review

```bash
# Generate validation report
case-parser input.xlsx output.xlsx --validation-report validation.txt

# JSON format
case-parser input.xlsx output.xlsx --validation-report validation.json

# Excel format
case-parser input.xlsx output.xlsx --validation-report validation.xlsx
```

## Development

### Setup

```bash
# Install all dependencies including dev tools
uv sync --group dev

# Install the package in editable mode
uv pip install -e .
```

### Code Quality

```bash
# Format and lint
ruff format .
ruff check --fix .

# Run tests
uv run pytest
```

### Adding New Patterns

1. Edit the appropriate pattern file in `src/case_parser/patterns/`
2. Add your pattern to the relevant pattern list
3. Update the extraction function if needed
4. Test with the debug script
5. Run linting: `ruff format . && ruff check .`

See `src/case_parser/patterns/README.md` for detailed pattern documentation.

## Documentation

- **USER_GUIDE.md**: End-user guide with CLI walkthroughs
- **chrome-extension/README.md**: Chrome extension installation and usage
- **src/case_parser/patterns/README.md**: Comprehensive pattern documentation
  with examples and debugging tips
- **CLAUDE.md**: Detailed architectural guidance for AI-assisted development

## Error Handling

The tool includes comprehensive error handling:

- **File Validation**: Checks file existence and format before processing
- **Data Validation**: Validates required columns and data types
- **Processing Errors**: Graceful handling of individual row failures
- **Logging**: Detailed logging for debugging and monitoring
- **Modern Output**: Color-coded error messages with rich formatting

## License

MIT License — see LICENSE for details.

## Contributing

When contributing:

1. Follow the pattern-based architecture
2. Add business logic to pattern modules, not processors
3. Use the debug script to test categorization changes
4. Run `ruff format . && ruff check .` before committing
5. Update relevant documentation
