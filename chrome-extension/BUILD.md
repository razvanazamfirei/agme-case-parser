# Build System

## Overview

The extension uses **Bun's bundler** for fast, zero-config bundling. Source files are in `src/`, built files go to `dist/`.

## Build Commands

```bash
# Production build (minified, no sourcemaps)
bun run build

# Development build (sourcemaps, no minification)
bun run build:dev

# Watch mode (auto-rebuild on changes)
bun run watch

# Clean build directory
bun run clean
```

## What Gets Bundled

### Bundled
- **src/popup/*.js** → **dist/popup.js**
  - All 11 popup modules bundled into one file
  - Minified in production (3.2KB)
  - With sourcemaps in development (16KB)
  - Tree-shaken and optimized

### Copied
- manifest.json
- popup.html (updated to use bundled popup.js)
- popup.css
- content.js (standalone, injected into ACGME pages)
- Icons (icon16.png, icon48.png, icon128.png)
- xlsx.min.js (external library, already minified)

## Build Process

1. **Clean** - Remove old dist/ directory
2. **Bundle** - Bun.build bundles src/popup/app.js and dependencies
3. **Copy** - Static files copied to dist/
4. **Transform** - popup.html updated to use single popup.js

## Development Workflow

### Initial Setup
```bash
bun install  # Install dependencies
bun run build  # Build extension
```

### During Development
```bash
bun run watch  # Start watch mode
# Edit files in src/
# Build auto-runs on save
# Reload extension in Chrome to see changes
```

### Testing Production Build
```bash
bun run clean
bun run build
# Load dist/ in Chrome
```

## Build Output Comparison

**Source (src/popup/):**
- 11 files, ~27KB total
- Readable, commented, formatted
- Multiple HTTP requests (if unbundled)

**Production (dist/popup.js):**
- 1 file, 3.2KB
- Minified, tree-shaken
- Single HTTP request
- **~88% size reduction**

**Development (dist/popup.js with --dev):**
- 1 file, 16KB (with inline sourcemaps)
- Not minified (easier debugging)
- Sourcemaps for Chrome DevTools

## Why Bun?

✓ **Fast** - Native bundler, faster than esbuild
✓ **Zero config** - Works out of the box
✓ **Already installed** - Using Bun for package management
✓ **Modern** - Supports latest JavaScript features
✓ **Tree shaking** - Removes unused code automatically
✓ **No dependencies** - No webpack/rollup/vite needed

## File Structure

```
chrome-extension/
├── src/                  # Source files (edit these)
│   └── popup/
│       ├── constants.js  # DOM IDs, constants
│       ├── state.js      # State management
│       ├── storage.js    # Chrome storage
│       ├── ui.js         # UI utilities
│       ├── excel.js      # Excel parsing
│       ├── form.js       # Form manipulation
│       ├── navigation.js # Navigation logic
│       ├── settings.js   # Settings UI
│       ├── confirmation.js # Dialogs
│       ├── acgme.js      # ACGME integration
│       └── app.js        # Entry point ⭐
├── dist/                 # Built files (load in Chrome)
│   ├── popup.js         # Bundled (3.2KB prod, 16KB dev)
│   ├── content.js       # Copied
│   ├── popup.html       # Transformed
│   └── ...              # Other copied files
├── build.js             # Build script
├── manifest.json        # Source manifest
├── popup.html           # Source HTML
└── *.png                # Icons
```

## Loading in Chrome

1. Build the extension:
   ```bash
   bun run build
   ```

2. Open Chrome: `chrome://extensions/`

3. Enable "Developer mode" (toggle top-right)

4. Click "Load unpacked"

5. Select `chrome-extension/dist/` directory

6. Extension loaded! 🎉

## Troubleshooting

**Build fails with "module not found":**
- Check that all files exist in src/popup/
- Run `ls src/popup/` to verify

**Extension doesn't load in Chrome:**
- Make sure you built first: `bun run build`
- Load the `dist/` directory, not the root
- Check Chrome console for errors

**Changes not showing up:**
- Did you reload the extension in chrome://extensions/?
- Clear extension storage: Right-click extension > "Clear storage data"
- Hard refresh the ACGME page (Cmd+Shift+R)

**Watch mode not rebuilding:**
- Check terminal for errors
- Restart watch mode
- Make sure you're editing files in `src/`, not `dist/`

## Distribution

To create a distributable zip:

```bash
bun run clean
bun run build
cd dist
zip -r ../acgme-case-submitter-v1.1.zip .
cd ..
```

Upload the zip file to Chrome Web Store or share with users.

## CI/CD Release Pipeline

This repo includes a GitHub Actions workflow that builds and packages the
extension automatically.

### Automatic Releases (recommended)

1. Bump `version` in `chrome-extension/manifest.json`
2. Tag the commit and push the tag:

```bash
git tag v1.2.0
git push origin v1.2.0
```

The workflow builds the extension, creates a versioned zip, and attaches it to
the GitHub Release as an asset.

### Manual Runs

You can also run the workflow from the GitHub Actions tab using
"Chrome Extension Release" → "Run workflow". This produces the zip as a build
artifact without creating a release.
