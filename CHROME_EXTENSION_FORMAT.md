# Chrome Extension Data Format Specification

This document describes the TypeScript-typed JSON data format exported by the case parser for Chrome extension consumption. The exported JSON comes with TypeScript type definitions for full type safety.

## Overview

The case parser can export parsed cases to JSON format suitable for Chrome extensions to consume and fill web forms. The export supports both single-file (all cases) and individual-file (one per case) modes.

## Export Options

### Single File Export with TypeScript Types

Export all cases to a single JSON file with TypeScript type definitions:

```bash
case-parser input.xlsx output.xlsx \
    --use-enhanced \
    --export-json cases.json \
    --export-with-types
```

This generates:
- `cases.json` - The JSON data
- `cases.d.ts` - TypeScript type definitions

### Single File Export (JSON Only)

Export all cases to a single JSON file without types:

```bash
case-parser input.xlsx output.xlsx \
    --use-enhanced \
    --export-json cases.json
```

### Generate Types Independently

Generate TypeScript types from a separate command:

```bash
case-parser input.xlsx output.xlsx \
    --use-enhanced \
    --generate-types types.d.ts
```

### Individual Files Export

Export each case to a separate JSON file:

```bash
case-parser input.xlsx output.xlsx \
    --use-enhanced \
    --export-json-dir ./cases/
```

### Export Options

- `--json-include-raw`: Include raw/original field values (useful for debugging)
- `--json-no-metadata`: Exclude metadata (warnings, confidence scores)

## JSON Structure

### Single File Format

When exporting to a single file, the JSON structure is:

```json
{
  "version": "1.0",
  "total_cases": 5,
  "summary": {
    "cases_with_warnings": 1,
    "low_confidence_cases": 0,
    "average_confidence": 0.95
  },
  "cases": [
    {
      "episode_id": "12345",
      "case_date": "2025-08-27",
      "responsible_provider": "Dr. Smith",
      "age_category": "d. >= 12 yr. and < 65 yr.",
      "procedure": "Hip Replacement",
      "asa_physical_status": "2",
      "anesthesia_type": "GA",
      "procedure_category": "Other (procedure cat)",
      "emergent": false,
      "airway_management": ["Oral ETT", "Direct Laryngoscope"],
      "vascular_access": ["Arterial Catheter"],
      "monitoring": ["TEE"],
      "services": ["ORTHO"],
      "metadata": {
        "confidence_score": 0.95,
        "has_warnings": false,
        "warning_count": 0,
        "warnings": [],
        "extraction_findings": [...]
      }
    }
  ]
}
```

### Individual File Format

When exporting to individual files, each file contains a single case object (without the wrapper structure):

```json
{
  "episode_id": "12345",
  "case_date": "2025-08-27",
  "responsible_provider": "Dr. Smith",
  "age_category": "d. >= 12 yr. and < 65 yr.",
  "procedure": "Hip Replacement",
  "asa_physical_status": "2",
  "anesthesia_type": "GA",
  "procedure_category": "Other (procedure cat)",
  "emergent": false,
  "airway_management": ["Oral ETT", "Direct Laryngoscope"],
  "vascular_access": ["Arterial Catheter"],
  "monitoring": ["TEE"],
  "services": ["ORTHO"],
  "metadata": { ... }
}
```

## Field Descriptions

### Core Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `episode_id` | `string \| null` | Case episode identifier | `"12345"` |
| `case_date` | `string` | ISO format date (YYYY-MM-DD) | `"2025-08-27"` |
| `responsible_provider` | `string \| null` | Anesthesiologist/provider name | `"Dr. Smith"` |
| `age_category` | `string \| null` | Age category classification | `"d. >= 12 yr. and < 65 yr."` |
| `procedure` | `string \| null` | Procedure description | `"Hip Replacement"` |
| `asa_physical_status` | `string` | ASA physical status | `"2"` or `"3E"` |
| `anesthesia_type` | `string \| null` | Standardized anesthesia type | `"GA"`, `"MAC"`, `"Spinal"` |
| `procedure_category` | `string` | Procedure category | `"Cardiac"`, `"Other (procedure cat)"` |
| `emergent` | `boolean` | Emergency case flag | `true` or `false` |
| `airway_management` | `string[]` | Array of airway techniques | `["Oral ETT", "Direct Laryngoscope"]` |
| `vascular_access` | `string[]` | Array of vascular access types | `["Arterial Catheter"]` |
| `monitoring` | `string[]` | Array of monitoring techniques | `["TEE"]` |
| `services` | `string[]` | Array of service departments | `["ORTHO", "TRAUMA"]` |

### Metadata Fields (if `--json-no-metadata` not used)

| Field | Type | Description |
|-------|------|-------------|
| `metadata.confidence_score` | `number` | Overall confidence in parsing (0-1) |
| `metadata.has_warnings` | `boolean` | Whether case has parsing warnings |
| `metadata.warning_count` | `number` | Number of warnings |
| `metadata.warnings` | `string[]` | Array of warning messages |
| `metadata.extraction_findings` | `object[]` | Detailed extraction results |

### Raw Fields (if `--json-include-raw` used)

| Field | Type | Description |
|-------|------|-------------|
| `raw.date` | `string \| null` | Original date value from input |
| `raw.age` | `number \| null` | Original age value |
| `raw.asa` | `string \| null` | Original ASA value |
| `raw.anesthesia_type` | `string \| null` | Original anesthesia type text |
| `procedure_notes` | `string \| null` | Free-text procedure notes |

## Enum Values

### Age Categories

- `"a. < 3 months"`
- `"b. >= 3 mos. and < 3 yr."`
- `"c. >= 3 yr. and < 12 yr."`
- `"d. >= 12 yr. and < 65 yr."`
- `"e. >= 65 year"`

### Anesthesia Types

- `"GA"` - General Anesthesia
- `"MAC"` - Monitored Anesthesia Care
- `"Spinal"` - Spinal
- `"Epidural"` - Epidural
- `"CSE"` - Combined Spinal-Epidural
- `"Peripheral nerve block"` - Peripheral Nerve Block

### Procedure Categories

- `"Cardiac"`
- `"Intracerebral"`
- `"Intrathoracic non-cardiac"`
- `"Procedures Major Vessels"`
- `"Cesarean del"`
- `"Other (procedure cat)"`

### Airway Management Values

- `"Oral ETT"`
- `"Nasal ETT"`
- `"Direct Laryngoscope"`
- `"Video Laryngoscope"`
- `"Supraglottic Airway"`
- `"Flexible Bronchoscopic"`
- `"Mask"`
- `"Difficult Airway"`

### Vascular Access Values

- `"Arterial Catheter"`
- `"Central Venous Catheter"`
- `"Pulmonary Artery Catheter"`

### Monitoring Technique Values

- `"TEE"`
- `"Electrophysiologic mon"`
- `"CSF Drain"`
- `"Invasive neuro mon"`

## Usage in Chrome Extension

### Reading Single File

```javascript
// Load the JSON file
const response = await fetch('cases.json');
const data = await response.json();

// Iterate through cases
data.cases.forEach(case => {
  // Fill form fields
  document.querySelector('#episode-id').value = case.episode_id || '';
  document.querySelector('#case-date').value = case.case_date;
  // ... etc
});
```

### Reading Individual Files

```javascript
// Load a specific case file
const response = await fetch(`cases/${episodeId}.json`);
const case = await response.json();

// Fill form fields
document.querySelector('#episode-id').value = case.episode_id || '';
// ... etc
```

### Handling List Fields

List fields (`airway_management`, `vascular_access`, `monitoring`, `services`) are arrays. Depending on the form structure, you may need to:

1. **Join as semicolon-separated string**:
   ```javascript
   const airwayValue = case.airway_management.join('; ');
   ```

2. **Select multiple checkboxes**:
   ```javascript
   case.airway_management.forEach(value => {
     const checkbox = document.querySelector(`input[value="${value}"]`);
     if (checkbox) checkbox.checked = true;
   });
   ```

3. **Fill multi-select dropdown**:
   ```javascript
   const select = document.querySelector('#airway-management');
   case.airway_management.forEach(value => {
     const option = Array.from(select.options).find(opt => opt.text === value);
     if (option) option.selected = true;
   });
   ```

### Handling Null Values

Many fields can be `null`. Always check before setting form values:

```javascript
if (case.episode_id) {
  document.querySelector('#episode-id').value = case.episode_id;
}
```

Or use nullish coalescing:

```javascript
document.querySelector('#episode-id').value = case.episode_id || '';
```

## Form Field Mapping

The Chrome extension will need to map `ParsedCase` fields to actual web form field names/IDs. This mapping is typically handled in the extension's configuration. Example mapping:

```json
{
  "field_mapping": {
    "episode_id": "#case-id-input",
    "case_date": "#date-input",
    "responsible_provider": "#provider-select",
    "age_category": "input[name='age-category']",
    "airway_management": "#airway-mgmt-multiselect"
  }
}
```

## Best Practices

1. **Validate data before submission**: Check for required fields and handle null values
2. **Use metadata for quality checks**: Warn users if `has_warnings` is true or `confidence_score` is low
3. **Handle errors gracefully**: Some cases may have missing or invalid data
4. **Support both export formats**: Choose single-file for batch processing, individual files for selective loading
5. **Consider metadata inclusion**: Include metadata for debugging, exclude for production

## Example: Complete Chrome Extension Integration

```javascript
// Load cases JSON
const response = await fetch('cases.json');
const { cases, summary } = await response.json();

// Display summary
console.log(`Loaded ${cases.length} cases`);
if (summary.cases_with_warnings > 0) {
  console.warn(`${summary.cases_with_warnings} cases have warnings`);
}

// Fill form for first case
const firstCase = cases[0];
fillForm(firstCase);

function fillForm(caseData) {
  // Map fields to form elements
  const fieldMapping = {
    episode_id: '#case-id',
    case_date: '#date',
    responsible_provider: '#provider',
    // ... etc
  };

  // Fill simple fields
  Object.entries(fieldMapping).forEach(([field, selector]) => {
    const element = document.querySelector(selector);
    if (element && caseData[field]) {
      element.value = caseData[field];
    }
  });

  // Handle list fields (e.g., airway_management)
  const airwaySelect = document.querySelector('#airway-mgmt');
  caseData.airway_management.forEach(value => {
    const option = Array.from(airwaySelect.options)
      .find(opt => opt.text.includes(value));
    if (option) option.selected = true;
  });

  // Warn if low confidence
  if (caseData.metadata && caseData.metadata.confidence_score < 0.7) {
    console.warn('Low confidence case:', caseData.metadata);
  }
}
```

## Version History

- **1.0** (Current): Initial format specification with core fields, metadata, and raw data support

