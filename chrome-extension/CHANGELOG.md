# Chrome Extension Changelog

## 1.1.0 - 2026-02-11

### Added

- Explicit `icons` block in manifest for Chrome Web Store packaging clarity
- `PRIVACY.md` for submission-ready privacy disclosure
- `package:zip` script for one-step distributable packaging

### Changed

- Manifest permissions reduced to least privilege:
  - removed unused `scripting`
  - removed broad `activeTab`
  - host scope narrowed to Case Entry URL path only
- Popup fill flow now enables Submit only after successful fill
- Submit status is now validated before marking cases as submitted
- Release workflow now builds from `chrome-extension/` directly
- Documentation rewritten to match actual Vite + CRX build and modular source layout

### Removed

- Unused `manifest.config.ts`
- Unused `src/popup/confirmation.js` and related stale state flag
