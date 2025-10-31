# Case Parser

A robust Python tool for processing anesthesia case data from Excel files and converting it to standardized case log format.

## Features

- **Modular Architecture**: Clean separation of concerns with dedicated modules for data processing, I/O operations, and CLI
- **Robust Error Handling**: Comprehensive error handling with custom exceptions and logging
- **Flexible Configuration**: Customizable column mappings and processing rules
- **Data Validation**: Input validation and data quality checks
- **Excel I/O**: Automatic column sizing and professional output formatting
- **CLI Interface**: User-friendly command-line interface with helpful options

## Installation

### Using uv (recommended)

```bash
# Install dependencies
uv sync

# Install in development mode
uv pip install -e .
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

# Set logging level
case-parser input.xlsx output.xlsx --log-level DEBUG
```

### Column Mapping

The tool automatically maps common column names, but you can override them using command-line options:

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

## Project Structure

```
case-parser/
├── src/
│   └── case_parser/
│       ├── __init__.py          # Package initialization
│       ├── models.py            # Data models and configuration
│       ├── processors.py        # Data processing logic
│       ├── extractors.py        # Text extraction functions
│       ├── io.py               # File I/O operations
│       ├── cli.py              # Command line interface
│       ├── exceptions.py       # Custom exceptions
│       └── logging_config.py   # Logging configuration
├── main.py                     # Main entry point
├── pyproject.toml             # Project configuration
└── README.md                  # This file
```

## Data Processing

The tool processes anesthesia case data and extracts:

- **Case Information**: ID, date, supervisor
- **Patient Demographics**: Age categorization
- **Procedure Details**: Original procedure, category, anesthesia type
- **Airway Management**: Intubation techniques, devices used
- **Vascular Access**: Arterial lines, central venous catheters
- **Monitoring**: Specialized monitoring techniques

## Error Handling

The tool includes comprehensive error handling:

- **File Validation**: Checks file existence and format
- **Data Validation**: Validates required columns and data types
- **Processing Errors**: Graceful handling of data processing issues
- **Logging**: Detailed logging for debugging and monitoring

## Development

### Setup Development Environment

```bash
# Install with development dependencies
uv sync --extra dev

# Install pre-commit hooks
pre-commit install
```

### Code Quality

The project uses several tools for code quality:

- **Ruff**: Fast Python linter and formatter
- **Black**: Code formatting (in dev dependencies)
- **MyPy**: Type checking (in dev dependencies)

## License

MIT License - see LICENSE file for details.


