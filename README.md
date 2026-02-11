# Case Parser

A robust Python tool for processing anesthesia case data from Excel files and
converting it to standardized case log format with ACGME web form integration.

## Features

- **Pattern-Based Architecture**: Self-contained extraction modules with clear
  separation of concerns
- **Domain-Driven Design**: Typed domain models with comprehensive validation
  and confidence tracking
- **Modern Output**: Professional terminal output with color-coding, tables, and
  panels using the rich library
- **Flexible Configuration**: Customizable column mappings and processing rules
- **Comprehensive Extraction**: Airway management, vascular access, specialized
  monitoring
- **Intelligent Categorization**: Surgery-specific logic for cardiac, vascular,
  intracerebral, and OB/GYN procedures
- **Validation Reporting**: Detailed validation reports in text, JSON, or Excel
  format
- **Web Integration**: Chrome extension for auto-filling ACGME case entry forms
- **Debug Tools**: Interactive categorization debugger with rich formatting

## Requirements

- Python 3.11+
- `uv` (recommended) or `pip`
- For the Chrome extension: Node.js 18+ and `bun`

## Installation

### Using uv (recommended)

```bash
# Install Python dependencies
uv sync

# Install in development mode
uv pip install -e .

# Install with dev dependencies
uv sync --extra dev
```

### Using pip

```bash
pip install -e .
```

### Chrome Extension

```bash
# Install JavaScript dependencies
bun install
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

# Export to JSON for ACGME web form integration
case-parser input.xlsx output.xlsx --json-export cases.json --resident-id "1325527"
```

### Web Integration (ACGME Auto-Fill)

Use the Chrome extension to upload a case log spreadsheet and autofill ACGME case entry forms.

1. Build the extension from `chrome-extension/` (`bun run build`)
2. Load `chrome-extension/dist` in `chrome://extensions/` (Developer mode)
3. Open the ACGME Case Entry page
4. Upload your Excel file (`.xlsx`, `.xls`, or `.csv`) in the popup
5. Click Fill (and Submit when ready)

See [chrome-extension/README.md](chrome-extension/README.md) for full setup, packaging, and release details.

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
- Final category with color-coded results
- Warnings and special cases

### Column Mapping

The tool automatically maps common column names, but you can override them using
command-line options:

- `--col-date`: Date column name (default: "Date")
- `--col-episode-id`: Episode ID column name (default: "Episode ID")
- `--col-anesthesiologist`: Anesthesiologist column name (default: "Responsible
  Provider")
- `--col-age`: Age column name (default: "Age At Encounter")
- `--col-emergent`: Emergent flag column name (default: "Emergent")
- `--col-asa`: ASA status column name (default: "ASA")
- `--col-final-anesthesia-type`: Anesthesia type column name (default: "Final
  Anesthesia Type")
- `--col-procedure-notes`: Procedure notes column name (default: "Procedure
  Notes")
- `--col-procedure`: Procedure column name (default: "Procedure")
- `--col-services`: Services column name (default: "Services")

### Input File Format (Exact)

- File types: `.xlsx`, `.xls`, or `.csv`
- Header row required; one row per case
- Required columns (exact names unless overridden): `Date`, `Episode ID`, `Responsible Provider`, `Age At Encounter`, `ASA`, `Final Anesthesia Type`, `Procedure`, `Services`
- Optional columns: `Emergent`, `Procedure Notes`
- `Services` values must be newline-separated within the cell
- `Date` should be parseable by pandas (recommended: `MM/DD/YYYY`); missing/unparseable dates fall back to `--default-year` (default 2025, January 1)
- `Age At Encounter` must be numeric

For a step-by-step walkthrough, see `USER_GUIDE.md`.

## Project Structure

```
case-parser/
├── src/
│   └── case_parser/
│       ├── __init__.py              # Package initialization
│       ├── models.py                # Data models and configuration
│       ├── processors.py            # Core data processing
│       ├── enhanced_processor.py    # Enhanced processor with validation
│       ├── extractors.py            # Extraction function exports
│       ├── domain.py                # Typed domain models
│       ├── validation.py            # Validation and reporting
│       ├── io.py                    # File I/O operations
│       ├── cli.py                   # Command line interface
│       ├── exceptions.py            # Custom exceptions
│       ├── logging_config.py        # Logging configuration
│       ├── web_exporter.py          # JSON export for web integration
│       ├── acgme_submitter.py       # ACGME submission utilities
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
├── chrome-extension/
│   ├── manifest.json            # Extension manifest (MV3)
│   ├── src/
│   │   ├── content.js           # ACGME page content script
│   │   └── popup/               # Modular popup application
│   ├── public/                  # Static assets (icons, xlsx.min.js)
│   ├── dist/                    # Build output (load this in Chrome)
│   ├── README.md                # Extension usage and packaging
│   ├── BUILD.md                 # Build/release process
│   └── PRIVACY.md               # Privacy statement
├── tests/                       # Unit tests
├── debug_categorization.py      # Categorization debugger
├── main.py                      # Main entry point
├── pyproject.toml               # Project configuration
├── package.json                 # JavaScript tooling
├── biome.json                   # JavaScript linter config
├── USER_GUIDE.md                # End-user guide
└── README.md                    # This file
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
  or Excel
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

### Setup Development Environment

```bash
# Install with development dependencies
uv sync --extra dev

# Install JavaScript dependencies
bun install
```

### Code Quality

The project uses several tools for code quality:

```bash
# Python formatting and linting
ruff format .
ruff check --fix .

# JavaScript/CSS linting (Chrome extension)
bun run lint
bun run format
bun run check
```

### Testing

```bash
# Test pattern imports
python -c "from src.case_parser.patterns import *; print('OK')"

# Debug categorization
python debug_categorization.py "procedure" "service"

# Process a file
python main.py input.xlsx output.xlsx --validation-report validation.txt
```

### Adding New Patterns

1. Edit the appropriate pattern file in `src/case_parser/patterns/`
2. Add your pattern to the relevant pattern list
3. Update the extraction function if needed
4. Test with the debug script
5. Run linting: `ruff format . && ruff check .`

See `src/case_parser/patterns/README.md` for detailed pattern documentation.

## Chrome Extension Development

```bash
# Lint and format extension code
bun run check

# Lint only
bun run lint

# Format only
bun run format
```

Load the extension in Chrome:

1. Navigate to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select the `chrome-extension/dist` directory

## Documentation

- **USER_GUIDE.md**: End-user guide with CLI and extension walkthroughs
- **src/case_parser/patterns/README.md**: Comprehensive pattern documentation
  with examples and debugging tips
- **chrome-extension/README.md**: Extension installation, usage, and
  troubleshooting
- **chrome-extension/icons/ICONS_README.md**: Icon requirements and generation
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
4. Run linters before committing
5. Update relevant documentation

## Support

For issues or questions:

- Check the pattern documentation in `src/case_parser/patterns/README.md`
- Use the debug script to troubleshoot categorization
- Review validation reports for data quality issues
- Check Chrome extension README for web integration issues
