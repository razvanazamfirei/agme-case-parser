# Extension Architecture

## Overview

The ACGME Case Submitter extension is built with a modular architecture that separates concerns into focused, maintainable modules.

## Module Structure

```
chrome-extension/
├── popup/                  # Modular popup code
│   ├── constants.js       # Constants and configuration
│   ├── state.js           # Application state management
│   ├── storage.js         # Persistence layer
│   ├── ui.js              # UI utilities
│   ├── excel.js           # Excel file parsing
│   ├── form.js            # Form manipulation
│   ├── navigation.js      # Case navigation
│   ├── settings.js        # Settings management
│   ├── confirmation.js    # Confirmation dialog
│   ├── acgme.js           # ACGME form filling
│   └── app.js             # Event handlers & initialization
├── content.js             # ACGME page content script
├── popup.html             # Extension popup UI
├── popup.css              # Extension styles
├── popup.js               # Legacy monolithic version (backup)
└── manifest.json          # Extension manifest

```

## Module Responsibilities

### constants.js
Defines all constants used across modules:
- `DOM`: Element IDs for DOM manipulation
- `EXPECTED_COLUMNS`: Excel column headers
- `STORAGE_KEYS`: Chrome storage keys
- `STATUS_TYPES`: Case status enumeration
- `ACGME_URL_PATTERN`: URL pattern for ACGME pages

**Why separate?** Centralizes configuration and prevents magic strings.

### state.js
Manages application state:
- Cases array
- Current index
- Case statuses
- User settings
- Pending submission flag

**Key methods:**
- `getCurrentCase()` - Get active case
- `getCaseStatus(index)` - Get status of a case
- `findNextPending(fromIndex)` - Find next pending case
- `getStats()` - Get case statistics

**Why separate?** Single source of truth for state, easier testing.

### storage.js
Handles persistence:
- `loadState()` - Restore session from local storage
- `saveState()` - Persist session to local storage
- `clearState()` - Clear all session data
- `loadSettings()` - Load settings from sync storage
- `saveSettings()` - Save settings to sync storage

**Why separate?** Isolates Chrome storage API, easier to mock for testing.

### ui.js
UI manipulation utilities:
- `get(id)` - Quick element accessor
- `showStatus(msg, type)` - Display status messages
- `updateStats()` - Update case statistics display
- `toggleSection(id)` - Toggle section visibility

**Why separate?** Reduces DOM manipulation code duplication.

### excel.js
Excel file parsing:
- `parseFile(file)` - Main entry point
- `_parseRows(rows)` - Extract case data from rows
- `_mapColumns(headers)` - Map headers to indices
- `_formatDate(val)` - Handle Excel date formats

**Why separate?** Encapsulates complex parsing logic, easier to test.

### form.js
Form data manipulation:
- `setSelect(id, value)` - Set select with fuzzy matching
- `setCheckboxGroup(name, values)` - Set checkbox group
- `setRadioGroup(name, value)` - Set radio group
- `populate(caseData)` - Populate entire form
- `getData()` - Extract form data

**Why separate?** Centralizes form logic, reusable patterns.

### navigation.js
Case navigation:
- `goToCase(index)` - Navigate to specific case
- `goToNextPending()` - Skip to next pending case
- `update()` - Update navigation UI
- `showCaseView()` / `showUploadView()` - Toggle views

**Why separate?** Encapsulates navigation state and UI updates.

### settings.js
Settings management:
- `readFromUI()` - Extract settings from UI
- `applyToUI()` - Apply settings to UI
- `save()` - Persist settings
- `toggle()` - Toggle settings panel

**Why separate?** Isolates settings logic from main application.

### confirmation.js
Confirmation dialog:
- `show()` - Display confirmation with summary
- `hide()` - Hide confirmation
- `_buildSummary(caseData)` - Build HTML summary

**Why separate?** Self-contained dialog logic.

### acgme.js
ACGME form filling:
- `fill(andSubmit)` - Fill ACGME form
- `_fillFormScript()` - Injected script
- `_handleFillResult()` - Process fill result

**Why separate?** Isolates Chrome extension API calls.

### app.js
Application initialization:
- `FileUpload` - File handling
- `Session` - Session management
- `EventHandlers` - Event listener registration
- `App` - Application initialization

**Why separate?** Entry point that coordinates all modules.

## Data Flow

```
User Action
    ↓
Event Handler (app.js)
    ↓
Module Function (form.js, navigation.js, etc.)
    ↓
State Update (state.js)
    ↓
UI Update (ui.js, form.js, navigation.js)
    ↓
Persistence (storage.js)
```

## Key Patterns

### Module Pattern
Each module is a const object with public methods:
```javascript
const ModuleName = {
  publicMethod() {
    // implementation
  },

  _privateMethod() {
    // prefixed with _ by convention
  },
};
```

### Single Responsibility
Each module has one clear purpose:
- State.js manages state
- Storage.js handles persistence
- UI.js provides UI utilities

### No Direct DOM Access in Business Logic
Business logic modules (state.js, storage.js, excel.js) don't touch the DOM. Only UI modules (ui.js, form.js, navigation.js) manipulate the DOM.

### Fuzzy Matching
Form.js implements smart fuzzy matching for selects:
1. Exact match
2. Case-insensitive match
3. Partial match (starts with)
4. Fallback to empty

### Error Handling
All async operations use try-catch:
```javascript
async save() {
  try {
    await Storage.saveSettings(settings);
    UI.showStatus("Success", "success");
  } catch (error) {
    UI.showStatus("Error", "error");
  }
}
```

## Benefits of This Architecture

### Maintainability
- **Clear separation** - Each module has one job
- **Easy to locate code** - Predictable file structure
- **Small files** - No 800-line files

### Testability
- **Mockable dependencies** - Each module can be tested in isolation
- **Pure functions** - Many private methods have no side effects
- **Clear interfaces** - Public methods define contracts

### Readability
- **Logical grouping** - Related functions together
- **Consistent patterns** - Same structure across modules
- **Self-documenting** - Module names describe purpose

### Scalability
- **Easy to extend** - Add new modules without touching existing ones
- **Reduced conflicts** - Team members work on different modules
- **Hot-swappable** - Can replace modules without affecting others

## Migration from Monolithic popup.js

The original popup.js (824 lines) has been split into:
- constants.js (93 lines)
- state.js (67 lines)
- storage.js (79 lines)
- ui.js (40 lines)
- excel.js (95 lines)
- form.js (125 lines)
- navigation.js (66 lines)
- settings.js (48 lines)
- confirmation.js (47 lines)
- acgme.js (73 lines)
- app.js (158 lines)

Total: 891 lines (slightly more due to module boilerplate, but much more maintainable)

The old popup.js is kept as a backup but is not loaded by the HTML.

## Loading Order

popup.html loads modules in dependency order:
1. xlsx.min.js (external library)
2. constants.js (no dependencies)
3. state.js (uses constants)
4. storage.js (uses state, constants)
5. ui.js (uses constants)
6. excel.js (uses constants)
7. form.js (uses state, ui, constants)
8. navigation.js (uses state, ui, form, storage, constants)
9. settings.js (uses state, ui, storage, constants)
10. confirmation.js (uses state, ui, form, constants)
11. acgme.js (uses state, ui, form, navigation, storage, constants)
12. app.js (uses all modules)

## Future Improvements

- **TypeScript** - Add type safety
- **Unit tests** - Test each module independently
- **Build system** - Bundle and minify for production
- **Module imports** - Use ES6 modules when Chrome fully supports them
