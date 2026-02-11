# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project Overview

Case Parser is a Python tool that processes anesthesia case data from Excel
files and converts it to standardized case log format. The tool extracts and
categorizes medical procedures, patient demographics, airway management
techniques, vascular access, and specialized monitoring from unstructured
medical data.

The project includes a Chrome extension for auto-filling ACGME web forms with
parsed case data.

## Commands

### Development Setup

```bash
# Install Python dependencies (recommended)
uv sync

# Install in development mode
uv pip install -e .

# Install with dev dependencies
uv sync --extra dev

# Install JavaScript dependencies for extension linting
bun install
```

### Running the Application

```bash
# Direct invocation
python main.py input.xlsx output.xlsx

# Using installed command
case-parser input.xlsx output.xlsx

# With validation report
case-parser input.xlsx output.xlsx --validation-report validation.txt

# Generate JSON export for Chrome extension
case-parser input.xlsx output.xlsx --json-export cases.json --resident-id "123"

# Debug procedure categorization
python debug_categorization.py "CABG with CPB" "CARDIAC SURGERY"
python debug_categorization.py --interactive
```

### Code Quality

```bash
# Python formatting and linting
ruff check --fix .
ruff format .

# JavaScript/CSS linting (Chrome extension)
bun run lint
bun run format
bun run check
```

## Architecture

### Core Processing Pipeline

The application follows a domain-driven, pattern-based architecture:

1. **CLI Layer** (`cli.py`) - Argument parsing, validation, orchestration
2. **I/O Layer** (`io.py`) - Excel file reading/writing with openpyxl
3. **Processing Layer** (`processors.py`, `enhanced_processor.py`) - Data transformation
4. **Pattern Layer** (`patterns/`) - Self-contained extraction and categorization
5. **Domain Layer** (`domain.py`) - Typed domain models with validation
6. **Configuration Layer** (`models.py`) - Business rules and mappings

### Data Flow

```
Excel Input → read_excel() → DataFrame → CaseProcessor.process_dataframe() →
process_row() for each row → Pattern extraction functions → ParsedCase domain models →
Validation → Transformed DataFrame → ExcelHandler.write_excel() → Formatted Output

Alternative flow for web integration:
ParsedCase models → JSON export → Chrome extension → ACGME web form auto-fill
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

### Domain-Driven Design

The enhanced processor uses typed domain models (`domain.py`):

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
- No business logic in processors - all in pattern modules

**Immutable Configuration**: `ColumnMap`, `AgeRange`, and `ProcedureRule` use
frozen dataclasses to ensure configuration cannot be mutated during processing.

**Rule-Based Processing**: Procedure categorization uses ordered rule lists
(`PROCEDURE_RULES`) evaluated sequentially. Order matters - more specific rules
come before general ones.

**Modern Output Formatting**: All CLI and validation output uses the `rich`
library for:

- Color-coded messages (cyan/yellow/red)
- Bordered panels for sections
- Formatted tables for data
- Professional terminal appearance

**Error Resilience**: `process_row()` catches all exceptions and returns
empty-valued rows to maintain dataframe structure. Individual row failures don't
stop processing.

### Important Business Logic

**Procedure Categorization** (`patterns/categorization.py`):

- Main entry point: `categorize_procedure(procedure, services)`
- Service matching against `PROCEDURE_RULES` (first match wins)
- Specialized categorization for:
  - `categorize_cardiac()` - CPB vs non-CPB detection
  - `categorize_vascular()` - Endovascular vs open approach
  - `categorize_intracerebral()` - Approach + pathology detection
  - `categorize_obgyn()` - Cesarean vs vaginal delivery

**Age Categorization** (`patterns/age_patterns.py`): Uses ordered `AGE_RANGES`
list. Returns first category where age < upper_bound. Categories are labeled a-e
for ACGME residency requirement tracking.

**ASA Emergency Flag** (`processors.py`): If "Emergent" column indicates
emergency but ASA value lacks "E", automatically appends "E" to ASA status.

**Airway Extraction** (`patterns/airway_patterns.py`):

- Detects intubation, laryngoscopy types, supraglottic airways
- Returns confidence scores (base 0.5, +0.1 for supporting patterns, -0.3 for negations)
- Multiple extraction findings tracked per case

**Column Overrides**: All column mappings can be overridden via CLI arguments
(`--col-*` flags). The `columns_from_args()` function merges overrides with
defaults dynamically.

### Module Responsibilities

**patterns/**: All extraction logic and business rules. Self-contained modules
with patterns, extraction functions, and documentation. To modify extraction
behavior, edit pattern files - never processors.

**processors.py**: Legacy processor - orchestrates extraction, delegates to
pattern modules. No business logic beyond calling extraction functions.

**enhanced_processor.py**: Domain-driven processor using typed models. Validates
extractions, tracks confidence, generates structured warnings.

**domain.py**: Typed domain models with Pydantic validation. Represents parsed
cases as strongly-typed objects with runtime validation.

**models.py**: Configuration dataclasses (ColumnMap, ProcedureRule, AgeRange).
Immutable frozen dataclasses for business rules.

**extractors.py**: Thin compatibility layer - re-exports extraction functions
from pattern modules. Legacy interface for backward compatibility.

**io.py**: File system operations. `ExcelHandler` manages Excel I/O, column
sizing, and data summaries.

**cli.py**: CLI interface with rich output. Handles argument parsing, validation
reporting, and user interaction with modern formatted output.

**validation.py**: Validation reporting with rich formatting. Generates text,
JSON, and Excel validation reports with professional output.

### Chrome Extension Integration

The `chrome-extension/` directory contains a Manifest V3 Chrome extension for
auto-filling ACGME case entry forms:

- **manifest.json**: Extension configuration
- **popup.html/js/css**: Extension UI for file upload and case selection
- **content.js**: Form auto-fill logic with ACGME code mappings
- **xlsx.min.js**: Client-side Excel parsing (SheetJS)

**Integration flow**:

1. Python tool exports cases to JSON
2. User loads JSON in Chrome extension
3. Extension parses JSON and displays case list
4. User navigates to ACGME form, selects case, clicks "Fill Form"
5. Content script maps parsed data to ACGME form codes
6. User reviews and manually submits

**Cardiac case auto-fill**: For cardiac procedures, the extension automatically
checks common monitoring/access (TEE, arterial line, central line, PA catheter,
ultrasound guidance) unless explicitly disabled.

## Configuration Files

**ruff.toml**: Python linting rules. PLR2004 (magic values) ignored for inline
thresholds. Target version Python 3.13, but requires-python is 3.11+ for
compatibility.

**pyproject.toml**: Build configuration using hatchling backend. Package in
`src/case_parser/` following src-layout. Dependencies include:

- pandas, openpyxl for Excel I/O
- pydantic for domain model validation
- rich for modern terminal output
  Entry point: `case_parser.cli:main`

**biome.json**: JavaScript/CSS linting for Chrome extension. Configured for:

- 2-space indents, 80-char line width
- Double quotes, semicolons, trailing commas
- Excludes `xlsx.min.js` from linting

**package.json**: JavaScript tooling. Scripts:

- `bun run lint` - Lint extension code
- `bun run format` - Format extension code
- `bun run check` - Lint + format check

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
- Final category with confidence
- Warnings and special cases

**Pattern development**:

1. Edit pattern files in `src/case_parser/patterns/`
2. Test with debug script or sample data
3. Run `ruff format` and `ruff check`
4. Verify with validation report

**Extension development**:

1. Edit extension files in `chrome-extension/src/`
2. Run `bun run dev` for development with HMR
3. Or run `bun run build` for production build
4. Run `bun run check` to lint and format
5. Load unpacked extension from `chrome-extension/dist/` in Chrome
6. Test on ACGME forms

## Documentation

- **patterns/README.md**: Comprehensive pattern documentation with examples
- **chrome-extension/README.md**: Extension installation and usage
- **chrome-extension/icons/ICONS_README.md**: Icon requirements

## Testing

```bash
# Run Python formatter and linter
ruff format .
ruff check --fix .

# Test pattern imports
python -c "from src.case_parser.patterns import *; print('OK')"

# Run debug script
python debug_categorization.py "procedure" "service"

# Process sample file with validation
python main.py input.xlsx output.xlsx --validation-report validation.txt

# Lint extension code
bun run check
```

## Common Modifications

**Add a new extraction pattern**:

1. Edit appropriate pattern file (e.g., `patterns/airway_patterns.py`)
2. Add pattern to relevant pattern list
3. Update extraction function if needed
4. Test with debug script

**Add a new procedure category**:

1. Add category to `domain.py` ProcedureCategory enum
2. Add rule to `patterns/procedure_patterns.py` PROCEDURE_RULES
3. Add mapping in `chrome-extension/content.js` if needed
4. Test categorization with debug script

**Modify categorization logic**:

1. Edit `patterns/categorization.py` (NOT processors)
2. Modify specific categorization function (e.g., `categorize_cardiac()`)
3. Test with debug script and sample data

**Add ACGME form field mapping**:

1. Edit `chrome-extension/content.js`
2. Add mapping to appropriate constant (e.g., `AIRWAY_MAP`)
3. Update `fillCase()` function if needed
4. Test on actual ACGME form
