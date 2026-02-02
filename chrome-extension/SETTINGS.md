# Extension Settings Guide

## Accessing Settings

Click the gear icon in the top-right corner of the extension popup to access settings.

## Available Settings

### Default Institution
**Type:** Dropdown
**Default:** None
**Description:** Select your default institution (CHOP, HUP, PPMC, Penn Hospital). This will be used when filling forms if not specified in the Excel file.

### Default Attending
**Type:** Text input
**Default:** None
**Format:** `LASTNAME, FIRSTNAME`
**Description:** Specify a default attending physician to use when the attending is not found in the Excel file or ACGME dropdown. The extension will:
1. First try to match the attending from the Excel file
2. If not found, try fuzzy matching
3. If still not found, use this default
4. Final fallback: "FACULTY, FACULTY"

### Auto-submit Delay
**Type:** Slider (0-2 seconds)
**Default:** 0.5 seconds
**Description:** Delay between filling the form and auto-submitting when using "Fill & Submit". Provides time to verify the form was filled correctly before submission.

### Auto-fill Cardiac Case Extras
**Type:** Checkbox
**Default:** ON
**Description:** Automatically check standard monitoring and vascular access for cardiac cases:
- TEE (Transesophageal Echocardiography)
- Arterial catheter
- Central venous catheter
- PA catheter
- Ultrasound guidance

Only adds items not already specified in the Excel file. Applies to both "Cardiac with CPB" and "Cardiac without CPB" cases.

### Auto-check Non-Trauma Pathology for 5E Cases
**Type:** Checkbox
**Default:** ON
**Description:** Automatically selects "Non-Trauma Life-Threatening Pathology" for all ASA 5E cases. This is a requirement for most 5E cases and saves manual selection.

**When to disable:** If you have 5E trauma cases or want full manual control.

### Show Confirmation Before Auto-submit
**Type:** Checkbox
**Default:** ON
**Description:** Shows a confirmation dialog with case summary before auto-submitting when using "Fill & Submit" button.

**When to disable:** For faster workflow if you trust the data and want immediate submission.

### Show Warnings for Missing/Fuzzy Matches
**Type:** Checkbox
**Default:** ON
**Description:** Displays warning messages when:
- Attending physician name requires fuzzy matching
- Default attending is used instead of case attending
- 5E case auto-checks Non-Trauma pathology
- Other data matching issues occur

**When to disable:** If warnings are cluttering your workflow and you're confident in your data quality. Warnings are still logged to browser console for debugging.

## Settings Persistence

All settings are saved to `chrome.storage.sync`, which means:
- Settings persist across browser sessions
- Settings sync across all Chrome browsers where you're signed in
- Clearing browser data will NOT clear settings (unless you specifically clear extension data)
- Use "Clear Session" button to clear only case data, not settings

## Recommended Settings

### For Speed (Experienced Users)
```
- Auto-submit delay: 0 seconds
- Show confirmation: OFF
- Show warnings: OFF
- Other settings: As needed
```

### For Accuracy (New Users)
```
- Auto-submit delay: 1-2 seconds
- Show confirmation: ON
- Show warnings: ON
- All auto-fill features: ON
```

### For Trauma Cases
```
- Auto-check Non-Trauma for 5E: OFF
  (Manually select Trauma pathology when needed)
- Other settings: As needed
```

## Keyboard Shortcuts

- `←` / `→` Arrow keys: Navigate between cases
- `Escape`: Cancel pending submission confirmation

## Tips

1. **First-time setup:** Configure your default institution and attending before processing your first batch of cases.

2. **Batch processing:** Once configured, the extension remembers your position in the Excel file, so you can close and reopen the popup without losing progress.

3. **Verification:** Even with auto-submit enabled, always verify the first few cases to ensure mappings are correct for your data format.

4. **Warnings:** Keep warnings enabled initially to identify any data quality issues in your Excel files.

5. **Case jumping:** Use the "Jump to" dropdown to navigate directly to specific cases or filter to show only pending cases.
