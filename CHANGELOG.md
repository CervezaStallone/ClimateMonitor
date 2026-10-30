# Changelog

All notable changes to Climate Monitor. Older versions: see the [GitHub releases](https://github.com/CervezaStallone/ClimateMonitor/releases).

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
