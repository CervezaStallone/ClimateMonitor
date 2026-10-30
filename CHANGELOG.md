# Changelog

All notable changes to Climate Monitor. Older versions: see the [GitHub releases](https://github.com/CervezaStallone/ClimateMonitor/releases).

## [2.2.0] - 2026-10-30

### Changed
- Dash 3.3 → 4.4.1. Dash 4 replaces the dropdowns, number fields, slider and date picker with new components; they are styled to match the dark and light theme.
- The time slider of the historical replay no longer shows a separate number field.

### Fixed
- The sensor choice above the chart shows "All sensors" right after loading instead of an empty box.

### Dependencies
- certifi 2026.10.23, importlib-metadata 9.0.1, packaging 26.3, python-dateutil 3.0.0, pytz 2026.5.

**Upgrading:** see [Updating to a new version](README.md#updating-to-a-new-version). Reload the dashboard with `Ctrl+F5` afterwards, because the browser may still have the old Dash components cached.

## [2.1.1] - 2026-10-30

### Security
- **certifi** 2026.7.22 → 2026.10.19 (critical, [GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)): the bundled certificate list contained emSign root CAs whose intermediate CA keys were compromised. Used for the Telegram, e-mail (SMTP) and MQTT connections. Updating is recommended.
- **setuptools** 84.0.0 → 84.2.1 (low, [GHSA-xmj3-9gf7-h52w](https://github.com/advisories/GHSA-xmj3-9gf7-h52w)): Windows path escape when installing legacy wheels.

**Upgrading:** see [Updating to a new version](README.md#updating-to-a-new-version).

## [2.1.0] - 2026-10-30

### Fixed
- The history chart is drawn again with a lot of data or many sensors. Measurements are now averaged per interval in the database instead of loading every raw row each second; before, a request could take longer than the refresh interval, so the chart stayed empty while the board still showed values. Long time ranges refresh at most every 30 seconds.
- Dropdowns in the bus, sensor and alert tables in **Settings** are no longer cut off, use the theme colours instead of pink and white, and also work on phones.

### Added
- **Settings → Display → Show comfort**: hides the comfort tab and the comfort column on the board.
- **Settings → Display → Show Mollier diagram**: hides the Mollier diagram.
- Both are on by default and apply as soon as you press **Save**.

**Upgrading:** see [Updating to a new version](README.md#updating-to-a-new-version).
