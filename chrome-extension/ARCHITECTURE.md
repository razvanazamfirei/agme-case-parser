# Extension Architecture

## Overview

The extension has two runtime surfaces:

1. Popup app (`src/popup/*`)
2. Content script (`src/content.js`)

Popup manages file parsing, review state, and user actions.
Content script performs DOM mapping/filling on ACGME pages.

## Modules

### Popup (`src/popup/`)

- `app.js`: bootstrap + event wiring
- `constants.js`: IDs, storage keys, enums, URL pattern
- `state.js`: in-memory session state
- `storage.js`: persistence layer for local/sync storage
- `excel.js`: spreadsheet parsing and column mapping
- `form.js`: popup form populate/read/validation
- `navigation.js`: case navigation and counters
- `settings.js`: settings read/write and UI sync
- `ui.js`: common UI helpers and status rendering
- `acgme.js`: bridge between popup and content script messaging
- `index.html`, `popup.css`: popup UI

### Content Script

- `src/content.js`:
  - maps case values to ACGME control IDs
  - applies fill actions
  - optionally clicks submit button
  - responds to popup messages

## Data Flow

1. User uploads Excel file in popup
2. `excel.js` parses rows into case objects
3. `state.js` stores cases and status
4. User clicks Fill or Submit
5. `acgme.js` sends case payload to `content.js`
6. `content.js` fills ACGME form and returns result
7. Popup updates status and persists progress

## Storage

- `chrome.storage.local`:
  - loaded cases
  - active case index
  - per-case status
- `chrome.storage.sync`:
  - user settings

## Reliability Rules

- Fill result must be successful before enabling Submit
- Submit result must be successful before marking case as submitted
- Unknown or partial matches generate warnings instead of hard failures
