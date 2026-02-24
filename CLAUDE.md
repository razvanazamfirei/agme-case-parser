# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project Overview

Case Parser is a Python tool that processes anesthesia case data from Excel
files and converts it to a standardized case log format. The tool extracts and
categorizes medical procedures, patient demographics, airway management
techniques, vascular access, and specialized monitoring from unstructured
medical data.

The Chrome extension for autofilling ACGME web forms has been migrated to its
own repository:
[razvanazamfirei/agme-case-parser-extension.](https://github.com/razvanazamfirei/agme-case-parser-extension)

## Features

### Batch Processing

The tool can process multiple Excel files from a directory and combine them into a single output file:

- **Directory Input**: Specify a directory path instead of a single file.
- **Automatic Discovery**: Finds all `.xlsx` and `.xls` files in the directory
- **Combined Output**: All cases from all files are merged into one output file.
- **Validation**: Each file is validated separately, with a combined summary

**Use Cases**:
- Combining multiple months of case logs into one file
- Processing cases from multiple residents
- Merging data from different hospital sites
- Batch processing for annual reports

### CSV v2 Format (MPOG Export)

The tool supports MPOG-style supervised export directories with separate
CaseList and ProcedureList CSV files per resident:

- **Directory Input**: Point at a directory containing matching `*.CaseList.csv` and `*.ProcedureList.csv` pairs
- **Auto-discovery**: `discover_csv_pairs()` finds and validates all pairs
- **Join logic**: `join_case_and_procedures()` aggregates procedure data per case
- **Column mapping**: `map_csv_to_standard_columns()` normalizes to standard ColumnMap

### Resident Batch Scripts

Two standalone scripts for working with supervised export data:

- **`batch_process.py`**: Processes all residents in an `Output-Supervised/`
  directory tree, writes one Excel file per resident to `Output-Individual/`
- **`sort-logs.py`**: Matches Excel files to a names list and copies matched
  files to `Output-Residents/`

Both accept CLI arguments — run with `--help` for options.

## Commands

### Development Setup

```bash
# Install Python dependencies (recommended)
uv sync

# Install in development mode
uv pip install -e .

# Install with dev dependencies (ruff, pytest, type stubs)
uv sync --group dev
```

### Running the Application

```bash
# Direct invocation (single file)
python main.py input.xlsx output.xlsx

# Using installed command (single file)
case-parser input.xlsx output.xlsx

# Process all Excel files in a directory
case-parser /path/to/excel/files/ combined_output.xlsx

# With validation report
case-parser input.xlsx output.xlsx --validation-report validation.txt

# CSV v2 format (MPOG supervised export)
case-parser /path/to/csv-dir/ output.xlsx --v2

# Debug procedure categorization
python debug_categorization.py "CABG with CPB" "CARDIAC SURGERY"
python debug_categorization.py --interactive
```

### Code Quality

```bash
# Python formatting and linting
ruff check --fix .
ruff format .

# Run tests
uv run pytest
```

## Architecture

### Core Processing Pipeline

The application follows a domain-driven, pattern-based architecture:

1. **CLI Layer** (`cli.py`) - Argument parsing, validation, orchestration
2. **I/O Layer** (`io.py`, `csv_io.py`) - Excel and CSV file reading/writing
3. **Processing Layer** (`processor.py`) - Data transformation with ML support
4. **ML Layer** (`ml/`) - Hybrid rule+ML procedure classification
5. **Pattern Layer** (`patterns/`) - Self-contained extraction and categorization
6. **Domain Layer** (`domain.py`) - Typed domain models with validation
7. **Configuration Layer** (`models.py`) - Business rules and mappings

### Data Flow

```
Excel/CSV Input → read_excel() or read_csv_v2() → DataFrame →
CaseProcessor.process_dataframe() → process_row() for each row →
Pattern extraction + ML classification → ParsedCase domain models →
Validation → Transformed DataFrame → ExcelHandler.write_excel() → Output
```

### Pattern-Based Architecture

All extraction and categorization logic is organized in `src/case_parser/patterns/`:

```
patterns/
├── __init__.py                  # Exports all patterns and functions
├── README.md                    # Comprehensive pattern documentation
├── extraction_utils.py          # Shared extraction utilities
│
├── airway_patterns.py           # Airway management patterns + extraction
├── vascular_access_patterns.py  # Vascular access patterns + extraction
├── monitoring_patterns.py       # Monitoring patterns + extraction
│
├── procedure_patterns.py        # Procedure categorization rules
├── categorization.py            # Categorization logic (cardiac, vascular, etc.)
├── approach_patterns.py         # Surgical approach detection
│
├── age_patterns.py              # Age range categorization
└── anesthesia_patterns.py       # Anesthesia type mapping
```

Each pattern module is self-contained with:

- Pattern definitions (regex lists)
- Extraction/categorization functions
- Documentation and examples

**Key principle**: Business logic lives in pattern modules, not in processors.

### ML Layer

`src/case_parser/ml/` provides hybrid rule+ML classification:

- **`hybrid.py`** (`HybridClassifier`): Combines rule-based categorization with
  ML predictions. Falls back to rules when ML confidence is below the threshold.
- **`predictor.py`** (`MLPredictor`): Loads and runs a pickled scikit-learn model
  (`ml_models/procedure_classifier.pkl`). Returns category plus confidence.
- **`features.py`** (`FeatureExtractor`): TF-IDF + category features for the model.
- **`loader.py`** (`get_hybrid_classifier`): Instantiates the classifier; used by
  `CaseProcessor.__init__()`. Pass `use_ml=False` to skip ML.

Training scripts live in `ml_training/` (not committed to the repo).

### Domain-Driven Design

The processor uses typed domain models (`domain.py`):

- **ParsedCase**: Fully typed case representation with validation
- **ProcedureCategory**, **AirwayManagement**, **VascularAccess**, **MonitoringTechnique**: Enums
- **ExtractionFinding**: Tracks extraction confidence and sources

This provides:

- Type safety and IDE autocomplete
- Runtime validation with clear warnings
- Structured extraction metadata
- Separation of parsing from business rules

### Key Design Patterns

**Pattern-Based Extraction**: All extraction logic follows a consistent pattern:

- Pattern lists define what to match (e.g., `INTUBATION_PATTERNS`)
- Extraction functions use shared utilities (`extract_with_context`, `calculate_pattern_confidence`)
- Return typed enums + extraction findings with confidence scores
- No business logic in processors — all in pattern modules

**Immutable Configuration**: `ColumnMap`, `AgeRange`, and `ProcedureRule` use
frozen dataclasses to ensure configuration cannot be mutated during processing.

**Rule-Based Processing**: Procedure categorization uses ordered rule lists
(`PROCEDURE_RULES`) evaluated sequentially. Order matters — more specific rules
come before general ones.

**Modern Output Formatting**: All CLI and validation output uses the `rich`
library for:

- Color-coded messages (cyan/yellow/red)
- Bordered panels for sections
- Formatted tables for data
- Professional terminal appearance

**Error Resilience**: `process_row()` catches all exceptions and returns
empty-valued rows to maintain dataframe structure. Individual row failures do not
stop processing.

### Important Business Logic

**Procedure Categorization** (`patterns/categorization.py`):

- Main entry point: `categorize_procedure(procedure, services)`
- Service matching against `PROCEDURE_RULES` (first match wins)
- Specialized categorization for:
  - `categorize_cardiac()` - CPB vs. non-CPB detection; defaults to `CARDIAC_WITH_CPB` when ambiguous
  - `categorize_vascular()` - Endovascular vs open approach
  - `categorize_intracerebral()` - Approach plus pathology detection
  - `categorize_obgyn()` - Cesarean vs vaginal delivery

**Age Categorization** (`patterns/age_patterns.py`): Uses ordered `AGE_RANGES`
list. Returns the first category where age < upper_bound. Categories are labeled a-e
for ACGME residency requirement tracking.

**ASA Emergency Flag** (`processor.py`): If "Emergent" column indicates
emergency but ASA value lacks "E," automatically appends "E" to ASA status.

**Airway Extraction** (`patterns/airway_patterns.py`):

- Detects intubation, laryngoscopy types, supraglottic airways
- Returns confidence scores (base 0.5, +0.1 for supporting patterns, -0.3 for negations)
- Multiple extraction findings tracked per case

**Confidence Threshold**: `is_low_confidence()` uses a default threshold of 0.7.
Cases below this threshold are flagged in validation reports.

**Column Overrides**: All column mappings can be overridden via CLI arguments
(`--col-*` flags). The `columns_from_args()` function merges overrides with
defaults dynamically.

### Module Responsibilities

**Patterns/**: All extraction logic and business rules. Self-contained modules
with patterns, extraction functions, and documentation. To modify extraction
behavior, edit pattern files — never processors.

**Processor.py** (`CaseProcessor`): The main processor using typed domain models.
Orchestrates extraction, ML classification, validates extractions, tracks
confidence, generates structured warnings.

**ML/**: A hybrid classifier combining rule-based and ML approaches. Model file
(`ml_models/procedure_classifier.pkl`) is not committed — the system falls back
to rule-only mode if the model is absent.

**CSV_IO.py**: CSV v2 format support. Discovers CaseList/ProcedureList pairs,
joins them, maps columns to standard format.

**Domain.py**: Typed domain models with Pydantic validation. Represents parsed
cases as strongly typed objects with runtime validation.

**Models.py**: Configuration dataclasses (ColumnMap, ProcedureRule, AgeRange).
Immutable frozen dataclasses for business rules.

**Extractors.py**: Thin compatibility layer — re-exports extraction functions
from pattern modules.

**IO.py**: File system operations. `ExcelHandler` manages Excel me/O, column
sizing, and data summaries.

**CLI.py**: CLI interface with rich output. Handles argument parsing, validation
reporting, and user interaction with modern formatted output.

**Validation.py**: Validation reporting with rich formatting. Generates text,
JSON, and Excel validation reports with professional output.

## Configuration Files

**Ruff.toml**: Python linting rules. PLR2004 (magic values) ignored for inline
thresholds. `.claude/` excluded. Target version Python 3.13, requires-python is
3.11+ for compatibility. `preview = true` enables additional rules.

**Pyproject.toml**: Build configuration using hatchling backend. Package in
`src/case_parser/` following src-layout. Runtime dependencies:

- `pandas`, `openpyxl` for Excel I/O
- `pydantic` for domain model validation
- `rich` for terminal output
- `scikit-learn`, `scipy`, `numpy` for ML classification

Dev dependencies (`uv sync --group dev`): `ruff`, `pytest`, `pandas-stubs`, `ty`,
`types-pytz`.

Entry point: `case_parser.cli:main`

## Debugging and Development

**Debug categorization**:

```bash
# Test a specific categorization
python debug_categorization.py "TAVR" "CARDSURG"

# Interactive mode
python debug_categorization.py --interactive
```

The debug script uses rich formatting to display:

- Rule matching trace with tables
- Matched patterns and exclusions
- A final category with confidence
- Warnings and special cases

**Pattern development**:

1. Edit pattern files in `src/case_parser/patterns/`
2. Test with debug script or sample data
3. Run `ruff format` and `ruff check`
4. Verify with a validation report

## Documentation

- **patterns/README.md**: Comprehensive pattern documentation with examples
- **chrome-extension/README.md**: Chrome extension installation and usage (git submodule)

## Testing

```bash
# Run all tests
uv run pytest

# Run formatter and linter
ruff format .
ruff check --fix .

# Test pattern imports
python -c "from src.case_parser.patterns import *; print('OK')"

# Debug categorization
python debug_categorization.py "procedure" "service"

# Process sample file with validation
python main.py input.xlsx output.xlsx --validation-report validation.txt
```

## Common Modifications

**Add a new extraction pattern**:

1. Edit appropriate pattern file (e.g., `patterns/airway_patterns.py`)
2. Add the pattern to the relevant pattern list
3. Update the extraction function if needed
4. Test with the debug script

**Add a new procedure category**:

1. Add the category to `domain.py` ProcedureCategory enum
2. Add rule to `patterns/procedure_patterns.py` `PROCEDURE_RULES`
3. Test categorization with debug script

**Modify categorization logic**:

1. Edit `patterns/categorization.py` (NOT processor.py)
2. Modify specific categorization function (e.g., `categorize_cardiac()`)
3. Test with debug script and sample data
