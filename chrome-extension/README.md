# ACGME Case Submitter Chrome Extension

Chrome extension that reads an Excel case log and fills the ACGME Case Entry form at:

- `https://apps.acgme.org/ads/CaseLogs/CaseEntry/*`

## Features

- Parse `.xlsx`, `.xls`, and `.csv` case files in-popup
- Navigate case-by-case with pending/submitted/skipped tracking
- Fill ACGME form fields from standardized values
- Optional delayed auto-submit after fill
- Session persistence (`chrome.storage.local`) and settings sync (`chrome.storage.sync`)

## Quick Start

```bash
cd chrome-extension
bun install
bun run build
```

Load in Chrome:

1. Open `chrome://extensions/`
2. Enable Developer mode
3. Click Load unpacked
4. Select `chrome-extension/dist`

## Getting Started

1. Open the ACGME Case Entry page.
2. Click the extension icon.
3. Upload an Excel or CSV case file.
4. Click Fill to populate the form.
5. Submit when ready.

## Development

```bash
cd chrome-extension
bun run dev         # Vite dev server for popup iteration
bun run build       # Production build
bun run build:dev   # Unminified build with sourcemaps
bun run clean

bun run lint
bun run lint:fix
bun run format
bun run check
```

## Packaging For Chrome Web Store

```bash
cd chrome-extension
bun run package:zip
```

This creates `chrome-extension/acgme-case-submitter-v1.1.0.zip`.

## Permissions

- `storage`
- Host access only for `https://apps.acgme.org/ads/CaseLogs/CaseEntry/*`

No remote code execution, no external network calls, no third-party telemetry.

## Documentation

- `BUILD.md`: Build and release pipeline
- `ARCHITECTURE.md`: Module boundaries and data flow
- `SETTINGS.md`: Runtime options
- `PRIVACY.md`: Data handling and privacy statement
- `CHANGELOG.md`: Release history
