# Chrome Extension Changelog

## Version 1.1 - Enhanced Features and Best Practices

### New Features

#### 1. Difficult Airway Management Support
- Added radio buttons in popup UI for Difficult Airway classification
- Options: Anticipated, Unanticipated, None (default)
- Properly maps to ACGME form codes:
  - Anticipated: 148 (CaseTypes_148)
  - Unanticipated: 149 (CaseTypes_149)

#### 2. Life-Threatening Pathology Support
- Added radio buttons in popup UI for Life-Threatening Pathology
- Options: Non-Trauma, Trauma, None (default)
- Properly maps to ACGME form codes:
  - Non-Trauma: 46 (CaseTypes_46)
  - Trauma: 134 (CaseTypes_134)
- **Auto-check for 5E cases**: Automatically selects "Non-Trauma Life-Threatening Pathology" for all 5E ASA cases
  - Triggers automatically when ASA 5E is selected in the popup
  - Triggers automatically when form is filled on ACGME page
  - Shows warning message to user

### User Settings Improvements

Added comprehensive user settings to control extension behavior:

1. **Auto-check Non-Trauma pathology for 5E cases** (default: ON)
   - Allows users to disable automatic 5E pathology selection
   - Respects user preference in both popup and form-filling

2. **Show confirmation before auto-submit** (default: ON)
   - Users can disable confirmation dialog for faster workflow
   - Directly submits when disabled

3. **Show warnings for missing/fuzzy matches** (default: ON)
   - Users can hide warning messages for cleaner experience
   - Warnings still logged to console for debugging

4. **Cardiac auto-fill** (existing, default: ON)
   - Toggle for automatic cardiac case extras
   - Previously existed, now grouped with other settings

All settings:
- Persist across sessions using chrome.storage.sync
- Apply to all devices where user is signed in to Chrome
- Clear defaults for new users
- Accessible via settings gear icon in popup

### Improvements

#### Complete Procedure Category Mappings
- Added missing "Vaginal Delivery" mapping (code 156690)
- Added "Cardiac" fallback mapping for cases without CPB specification
- Added explicit "Other (procedure cat)" mapping
- All procedure categories from domain.py are now fully mapped

#### Best Practices Implementation

1. **Content Security Policy (CSP)**
   - Added strict CSP to manifest.json
   - Prevents inline script execution
   - Follows Chrome extension security best practices

2. **Manifest V3 Compliance**
   - Updated to version 1.1
   - Added `run_at: "document_idle"` for content script timing
   - Proper permissions scope (activeTab, scripting, storage)
   - Host permissions limited to apps.acgme.org

3. **Improved Form Handling**
   - Added `checkRadioProcedure()` function for radio button handling
   - Distinguishes between checkboxes and radio buttons
   - Better error handling and console warnings

4. **Enhanced User Experience**
   - Auto-populates Non-Trauma Life-Threatening Pathology for 5E cases in popup
   - Real-time ASA change detection
   - Clear visual grouping of related fields
   - Proper radio button reset to "None" option

### Technical Changes

#### content.js
- Added `DIFFICULT_AIRWAY_MAP` constant
- Added `LIFE_THREATENING_PATHOLOGY_MAP` constant
- Added `checkRadioProcedure()` helper function
- Enhanced `fillCase()` with difficult airway and pathology logic
- Auto-check Non-Trauma for 5E cases with warning message

#### popup.html
- Added Difficult Airway radio button group
- Added Life-Threatening Pathology radio button group
- Proper form field organization
- Radio buttons with "None" default option

#### popup.js
- Added `setRadioGroup()` helper function
- Added `getRadioGroup()` helper function
- Enhanced `populateForm()` with radio group support
- Enhanced `getFormData()` to include new fields
- Added ASA change event listener for auto-checking 5E pathology

#### manifest.json
- Version bumped to 1.1
- Added Content Security Policy
- Enhanced description
- Added `run_at` directive for content script

### Code Quality

- All JavaScript code passes Biome linting
- Consistent code style with 2-space indentation
- Proper error handling and logging
- Clear separation of concerns

### Migration Notes

Existing users upgrading from 1.0 to 1.1:
- No breaking changes
- New fields will be empty/None by default
- 5E cases will automatically trigger Non-Trauma pathology selection
- Settings and session data preserved

### Testing Recommendations

1. Test difficult airway selection (Anticipated/Unanticipated)
2. Test life-threatening pathology selection (Non-Trauma/Trauma)
3. Verify 5E cases auto-check Non-Trauma pathology
4. Verify all procedure categories map correctly
5. Test ASA change triggering pathology selection
6. Verify radio button resets work correctly
