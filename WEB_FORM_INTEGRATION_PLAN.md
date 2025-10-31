# Chrome Extension Integration Plan

This document outlines the steps needed to integrate the parsed case data with a Chrome extension for web form submission.

## Current State Analysis

### ✅ What We Have
1. **Typed Intermediate Representation**: `ParsedCase` model with full type safety
2. **Data Validation**: Comprehensive validation via Pydantic
3. **JSON Export**: ValidationReport can export JSON
4. **Excel Output**: `to_output_dict()` method for Excel format
5. **Extraction Findings**: Detailed extraction metadata with confidence scores

### ❌ What's Missing for Chrome Extension Integration
1. **JSON Export Method**: No dedicated JSON export on `ParsedCase` for Chrome extension consumption
2. **Form Field Mapping**: No mapping configuration between `ParsedCase` fields and web form field names/IDs
3. **Batch JSON Export**: No CLI flag or service to export multiple cases as JSON
4. **Extension-Friendly Format**: Need standardized format that Chrome extension can easily parse
5. **Export Documentation**: Need data format specification for extension developers

## Implementation Steps

### Step 1: Form Field Mapping Configuration

**Purpose**: Map `ParsedCase` fields to web form field names

**Location**: `src/case_parser/form_mapping.py` (new file)

**Requirements**:
- Configuration-driven field mapping
- Support for nested form fields
- Support for checkbox/radio button values
- Support for multi-select fields (airway management, vascular access, etc.)
- Default value mapping
- Optional field handling

**Example Structure**:
```python
@dataclass(frozen=True)
class FormFieldMapping:
    """Mapping between ParsedCase fields and web form field names."""
    
    case_id_field: str = "episode_id"
    date_field: str = "case_date"
    age_category_field: str = "age_category"
    # ... etc
```

### Step 2: Form Payload Generation

**Purpose**: Convert `ParsedCase` to web form submission format

**Location**: Add method to `ParsedCase` class in `src/case_parser/domain.py`

**Methods Needed**:
- `to_form_payload(mapping: FormFieldMapping) -> dict[str, Any]`
- Handle enum value conversions (AgeCategory, AnesthesiaType, etc.)
- Convert lists to form-appropriate formats (semicolon-separated, JSON arrays, etc.)
- Handle date formatting for web forms
- Map empty/None values appropriately

### Step 3: HTTP Client Module

**Purpose**: Handle HTTP requests for form submission

**Location**: `src/case_parser/web_client.py` (new file)

**Requirements**:
- HTTP POST/PUT requests
- Cookie/session management
- Authentication handling (basic auth, token-based, etc.)
- Request/response logging
- Timeout handling
- SSL/TLS certificate validation

**Dependencies**: Add `httpx` or `requests` to `pyproject.toml`

### Step 4: Web Form Submission Service

**Purpose**: Orchestrate form submission with error handling

**Location**: `src/case_parser/submission_service.py` (new file)

**Features**:
- Single case submission
- Batch case submission
- Retry logic with exponential backoff
- Error categorization (network, validation, server errors)
- Submission status tracking
- Success/failure reporting

**Example Interface**:
```python
class FormSubmissionService:
    def submit_case(
        self, 
        case: ParsedCase, 
        form_url: str,
        mapping: FormFieldMapping,
        auth_config: AuthConfig | None = None
    ) -> SubmissionResult:
        """Submit a single case to web form."""
        
    def submit_batch(
        self,
        cases: list[ParsedCase],
        form_url: str,
        mapping: FormFieldMapping,
        auth_config: AuthConfig | None = None,
        max_concurrent: int = 1
    ) -> list[SubmissionResult]:
        """Submit multiple cases with optional concurrency."""
```

### Step 5: Submission Result Tracking

**Purpose**: Track submission outcomes

**Location**: `src/case_parser/submission_models.py` (new file)

**Models Needed**:
- `SubmissionResult`: Success/failure status, response data, errors
- `SubmissionStatus`: Enum for tracking states (pending, success, failed, retrying)
- `SubmissionReport`: Aggregate statistics for batch submissions

### Step 6: Authentication Configuration

**Purpose**: Support various authentication methods

**Location**: `src/case_parser/auth_config.py` (new file)

**Support**:
- Basic authentication
- Bearer token authentication
- Session-based authentication (cookie handling)
- OAuth2 (if needed)
- Custom headers for API keys

### Step 7: CLI Integration

**Purpose**: Add CLI commands for web form submission

**Location**: Extend `src/case_parser/cli.py`

**New Commands**:
- `--submit-to-web`: Enable web submission mode
- `--form-url`: Web form URL/endpoint
- `--auth-type`: Authentication type (basic, token, none)
- `--auth-token`: Authentication token
- `--form-mapping`: Path to form mapping configuration file
- `--batch-size`: Number of cases to submit concurrently
- `--dry-run`: Validate without actually submitting

### Step 8: Configuration File Support

**Purpose**: Externalize web form configuration

**Location**: `src/case_parser/web_config.py` (new file)

**Format Options**:
- JSON configuration file
- YAML configuration file (if desired)

**Configuration Structure**:
```json
{
  "form_url": "https://example.com/api/cases",
  "auth": {
    "type": "bearer",
    "token": "${AUTH_TOKEN}"
  },
  "field_mapping": {
    "episode_id": "case_id",
    "case_date": "date",
    ...
  },
  "submission": {
    "retry_attempts": 3,
    "retry_delay": 1.0,
    "timeout": 30
  }
}
```

### Step 9: Error Handling & Validation

**Purpose**: Web-specific validation and error recovery

**Location**: Extend `src/case_parser/validation.py` or create `src/case_parser/web_validation.py`

**Features**:
- Pre-submission validation (required fields, format checks)
- Response validation (check for form errors in response)
- Error message extraction from form responses
- Validation error mapping back to `ParsedCase` fields

### Step 10: Testing Infrastructure

**Purpose**: Test web form integration without hitting real endpoints

**Location**: `tests/test_web_integration.py`

**Requirements**:
- Mock HTTP server for testing
- Test fixtures for form mapping
- Test cases for various error scenarios
- Integration tests with real form (optional, behind flag)

## File Structure

```
src/case_parser/
├── domain.py                 # ParsedCase model (add to_form_payload)
├── form_mapping.py          # NEW: Form field mapping configuration
├── web_client.py            # NEW: HTTP client wrapper
├── submission_service.py    # NEW: Form submission orchestration
├── submission_models.py     # NEW: Submission result models
├── auth_config.py           # NEW: Authentication configuration
├── web_config.py            # NEW: Web form configuration loader
└── web_validation.py        # NEW: Web-specific validation

tests/
├── test_form_mapping.py     # NEW
├── test_web_client.py       # NEW
├── test_submission_service.py # NEW
└── fixtures/
    └── form_mapping.json    # NEW: Example mapping configuration
```

## Dependencies to Add

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "httpx>=0.24.0",  # Modern async HTTP client (or requests if prefer sync)
    "pyyaml>=6.0",    # Optional: for YAML config support
]
```

## Implementation Priority

### Phase 1: Core Infrastructure (MVP)
1. ✅ Form field mapping configuration
2. ✅ `to_form_payload()` method on ParsedCase
3. ✅ Basic HTTP client
4. ✅ Simple submission service (single case, no retries)
5. ✅ CLI integration with basic flags

### Phase 2: Robustness
6. ✅ Error handling and retry logic
7. ✅ Batch submission support
8. ✅ Authentication configuration
9. ✅ Submission tracking/reporting

### Phase 3: Advanced Features
10. ✅ Configuration file support
11. ✅ Async/concurrent batch processing
12. ✅ Comprehensive testing
13. ✅ Documentation

## Example Usage

### CLI Usage
```bash
# Submit parsed cases to web form
case-parser input.xlsx output.xlsx \
    --use-enhanced \
    --submit-to-web \
    --form-url "https://example.com/api/cases" \
    --auth-type bearer \
    --auth-token "$API_TOKEN" \
    --batch-size 5
```

### Programmatic Usage
```python
from case_parser import EnhancedCaseProcessor, FormSubmissionService
from case_parser.form_mapping import FormFieldMapping

# Parse cases
processor = EnhancedCaseProcessor(column_map, default_year=2025)
cases = processor.process_dataframe(df)

# Submit to web form
submission_service = FormSubmissionService()
mapping = FormFieldMapping.from_config("form_mapping.json")

results = submission_service.submit_batch(
    cases=cases,
    form_url="https://example.com/api/cases",
    mapping=mapping,
    auth_config=AuthConfig.bearer(token="..."),
    max_concurrent=5
)

# Check results
for result in results:
    if result.success:
        print(f"Case {result.case_id} submitted successfully")
    else:
        print(f"Case {result.case_id} failed: {result.error}")
```

## Key Design Decisions

1. **HTTP Library Choice**: 
   - **httpx**: Modern, async-capable, type-hinted (recommended)
   - **requests**: Mature, widely used, synchronous-only

2. **Form Payload Format**:
   - **Form-encoded (application/x-www-form-urlencoded)**: Standard web forms
   - **JSON**: Modern APIs prefer JSON
   - **Support both**: Make format configurable

3. **Concurrency Model**:
   - **Synchronous**: Simpler, good for small batches
   - **Asynchronous**: Better for large batches, requires async/await
   - **Thread pool**: Middle ground, easier migration path

4. **Configuration Location**:
   - **Code (defaults)**: Quick start, hard to change
   - **Config file**: Flexible, externalizable
   - **Environment variables**: Good for secrets
   - **Support all three**: Most flexible

## Next Steps

1. Review this plan and confirm approach
2. Start with Phase 1 implementation
3. Test with real web form endpoint (if available)
4. Iterate based on feedback
5. Document final API

