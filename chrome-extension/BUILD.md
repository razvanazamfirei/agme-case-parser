# Build And Release

## Build System

The extension uses Vite with `@crxjs/vite-plugin` and Manifest V3.

Source of truth:

- `chrome-extension/manifest.json`
- `chrome-extension/src/`

Build output:

- `chrome-extension/dist/`

## Commands

```bash
cd chrome-extension
bun install

bun run dev
bun run build
bun run build:dev
bun run clean
```

## Local Packaging

```bash
cd chrome-extension
bun run package:zip
```

Output zip:

- `chrome-extension/acgme-case-submitter-v<version>.zip`

## Chrome Web Store Checklist

1. Build from a clean tree: `bun run clean && bun run build`
2. Verify `dist/manifest.json` has the expected version and permissions
3. Zip the `dist/` contents (not the project root)
4. Upload zip in Chrome Web Store Developer Dashboard
5. Keep release notes aligned with `CHANGELOG.md`

## GitHub Actions Release Workflow

Workflow file:

- `.github/workflows/chrome-extension-release.yml`

Behavior:

1. Installs dependencies in `chrome-extension/`
2. Builds extension in `chrome-extension/dist/`
3. Creates `acgme-case-submitter-v<version>.zip`
4. Publishes artifact on manual run or tag push (`v*`)
5. Validates tag version matches `chrome-extension/manifest.json`
