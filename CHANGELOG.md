# Changelog

All notable changes to Climate Monitor. Older versions: see the [GitHub releases](https://github.com/CervezaStallone/ClimateMonitor/releases).

## [2.3.1-beta2] - 2026-11-03 (pre-release)

### Added
- **Reports** (Settings → Reports): weekly or monthly PDF with the daily wood moisture per sensor and a table with min/max temperature, humidity and wood moisture (yellow above 16 %, orange above 18 %, red above 20 %). Sent by e-mail to the notification recipients and downloadable; language selectable.

### Changed
- New dependency: matplotlib (PDF report). `start.sh` installs it automatically; otherwise run `pip install -r requirements.txt`.

## [2.3.1-beta] - 2026-11-03 (pre-release)

### Added
- **Home Assistant discovery** (Settings → MQTT): every sensor shows up in Home Assistant as a device with the sensor's name and manufacturer BRDC, with an entity per quantity.

## [2.3.0] - 2026-11-02

### Added
- **Wood moisture** (equilibrium moisture content, USDA Wood Handbook) per sensor, with its own diagram, a correction for the wood species and a response time (averaged value, so short peaks do not trigger alarms). On/off in Settings → Display.
- **Warning and alarm level** per limit, e.g. a warning at 18 % and an alarm at 20 % wood moisture.
- **Zones** in the wood diagram: coloured areas of temperature × humidity with a notification when a sensor leaves a desired zone or enters a danger zone. A zone starts as a square; drag the corners, drag the dot in the middle of a side to add a corner, double-click a corner to remove it. Click a zone to change or delete it.
- **Limits in the time chart** as dashed lines (yellow = warning, red = alarm).
- **Alarm window** from the top bar with muting per alarm (15 minutes to 24 hours).
- **Dark/light toggle** in the top bar, remembered per browser.
- **Logo** in the top bar and as favicon.
- Per sensor: **data type** (int16, uint16, int32, uint32, float32), **byte order** (ABCD, DCBA, BADC, CDAB) and a **calibration correction** for temperature and humidity.
- **Scan** in Settings → Modbus finds which slave addresses answer on a bus.

### Changed
- Buses, sensors and limits are edited with normal form fields instead of a table: arrow keys move the cursor and the dropdowns work reliably. The port field suggests detected adapters (stable `/dev/serial/by-id` names first).
- Dew point uses the Magnus formula instead of a rule of thumb (new measurements only); the comfort score uses the same dew point.
- `?tab=settings` disappears from the address bar when you go back to the dashboard.

### Fixed
- Saving settings no longer repeats notifications for alarms that are already active.
- An impossible raw humidity is rejected instead of being shown as 0 %.
- Long status texts on the meter cards no longer overflow.

**Upgrading:** see [Updating to a new version](README.md#updating-to-a-new-version). The database is upgraded automatically: existing sensors become int16 / ABCD without correction (same readings as before), existing limits get the level *Alarm*. Reload the dashboard with `Ctrl+F5` afterwards.

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
