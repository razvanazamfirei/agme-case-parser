# ACGME Case Submitter - Chrome Extension

Auto-fill ACGME case entry forms from Excel case logs.

## Development

### Setup

```bash
bun install
```

### Build

```bash
# Production build (minified)
bun run build

# Development build (with sourcemaps)
bun run build:dev

# Watch mode (rebuilds on file changes)
bun run watch
```

### Project Structure

```
chrome-extension/
├── src/                    # Source files
│   └── popup/             # Popup UI modules
│       ├── constants.js   # Configuration
│       ├── state.js       # State management
│       ├── storage.js     # Persistence
│       ├── ui.js          # UI utilities
│       ├── excel.js       # Excel parsing
│       ├── form.js        # Form handling
│       ├── navigation.js  # Navigation
│       ├── settings.js    # Settings
│       ├── confirmation.js # Dialogs
│       ├── acgme.js       # ACGME integration
│       └── app.js         # Entry point
├── dist/                  # Built extension (load this in Chrome)
├── manifest.json          # Extension manifest
├── popup.html            # Popup UI
├── popup.css             # Styles
├── content.js            # ACGME page script
├── build.js              # Build script
└── *.png                 # Icons
```

### Loading Extension

1. Build the extension:
   ```bash
   bun run build
   ```

2. Open Chrome and navigate to `chrome://extensions/`

3. Enable "Developer mode" (toggle in top-right)

4. Click "Load unpacked"

5. Select the `chrome-extension/dist/` directory

### Development Workflow

```bash
# Start watch mode
bun run watch

# Make changes to files in src/
# Extension auto-rebuilds
# Reload extension in Chrome to see changes
```

### Code Quality

```bash
# Lint code
bun run lint

# Format code
bun run format

# Check formatting and linting
bun run check
```

## Usage

See [SETTINGS.md](SETTINGS.md) for configuration options and [ARCHITECTURE.md](ARCHITECTURE.md) for technical details.

## Building for Distribution

```bash
# Clean build
bun run clean
bun run build

# The dist/ directory contains the production-ready extension
# Zip it for distribution:
cd chrome-extension/dist && zip -r ../acgme-case-submitter.zip . && cd ../..
```
