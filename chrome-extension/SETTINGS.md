# Settings

Open settings from the gear icon in the popup header.

## Default Institution

- Type: select
- Values: `CHOP`, `HUP`, `PPMC`, `Penn Hospital`
- Used when filling the ACGME institution field

## Default Attending

- Type: text (`LASTNAME, FIRSTNAME`)
- Used when case-level attending cannot be matched
- Final fallback remains `FACULTY, FACULTY` if available in ACGME dropdown

## Auto-submit Delay

- Type: range (`0` to `2` seconds)
- Delay between fill completion and submit click

## Auto-fill Cardiac Case Extras

When enabled, cardiac cases auto-apply common checks (if not already present):

- TEE
- Arterial catheter
- Central venous catheter
- PA catheter
- Ultrasound guidance

## Auto-check Non-Trauma For ASA 5E

When enabled, ASA `5E` with empty pathology automatically selects `Non-Trauma`.

## Show Warnings

Controls warning display in popup status messages for fuzzy/default mappings.

## Persistence

- Session state: `chrome.storage.local`
- Settings: `chrome.storage.sync`

## Keyboard Shortcuts

- `ArrowLeft`: previous case
- `ArrowRight`: next case
