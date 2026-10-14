# Feature Specification: Settings Tab with Browser Configuration and Optional Login

**Feature Branch**: `001-settings-tab`
**Created**: 2026-10-14
**Status**: Draft
**Input**: User description: "Everything that is now in the .env file must be configurable from the web app itself in a tab called Settings, translated in all languages. Settings protection: the user chooses in Settings whether only Settings or the whole app requires a password. Everything must be configurable via the browser."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Change app configuration from the browser (Priority: P1)

An operator of a headless edge device opens the web app, goes to the Settings tab and changes
data retention, timezone, default language, debug logging or the listen address. After saving,
the app uses the new values without anyone touching files.

**Why this priority**: Today every change requires shell access to edit `.env` and restart the
app. This tab is the foundation for all later features: Modbus buses and devices (feature 002),
notifications and MQTT add their own sections here.

**Independent Test**: Open Settings, change the timezone, save, and see the dashboard time axis
shift accordingly on the next refresh.

**Acceptance Scenarios**:

1. **Given** the app runs with stored settings, **When** the operator opens the Settings tab,
   **Then** all current values (data retention, timezone, default language, debug logging,
   host/port, protection) are shown pre-filled.
2. **Given** the operator changes the timezone and saves, **When** the save succeeds, **Then** a
   confirmation is shown and the dashboard uses the new timezone without restart.
3. **Given** the operator enters an invalid value (e.g. timezone "Mars/Base" or retention -1),
   **When** saving, **Then** the save is refused, the field is marked with a translated error
   message and the previous settings stay active.
4. **Given** the operator changes host or port, **When** saving, **Then** the UI states that this
   takes effect after a restart of the app/service.

---

### User Story 2 - Protect settings with an admin password (Priority: P1)

The first time someone opens the Settings tab, the app asks to create an admin password. After
that, the Settings tab is only accessible after logging in. In Settings the admin can choose the
protection level: "Settings only" (dashboard stays public) or "Whole app" (dashboard requires
login too).

**Why this priority**: The app listens on all network interfaces. Without protection anyone on
the network could change the sensor configuration or, in later features, read notification
credentials. Must ship together with Story 1.

**Independent Test**: Fresh install, open Settings, set password, log out, verify the Settings
tab asks for the password and the dashboard is still visible; switch to "Whole app", log out,
verify the dashboard asks for the password too.

**Acceptance Scenarios**:

1. **Given** no admin password exists yet, **When** someone opens Settings, **Then** they must
   set a password (entered twice, minimum 8 characters) before any setting is shown.
2. **Given** protection is "Settings only", **When** a visitor who is not logged in opens the
   dashboard, **Then** the dashboard is shown and the Settings tab asks for the password.
3. **Given** protection is "Whole app", **When** a visitor who is not logged in opens any page,
   **Then** a login screen is shown and no measurement data is returned.
4. **Given** a logged-in admin, **When** they click "Log out" or the session is idle for longer
   than the session timeout, **Then** the next protected action asks for the password again.
5. **Given** 5 wrong password attempts within a short period, **When** a 6th attempt is made,
   **Then** login is temporarily blocked and a translated message says when to try again.
6. **Given** a logged-in admin, **When** they change the admin password (old + new twice),
   **Then** the new password is required from then on.

---

### User Story 3 - Seamless upgrade of existing installations (Priority: P2)

An existing user updates the app. Their `.env` values are taken over as the initial stored
settings, so the device keeps measuring with the same configuration after the update.

**Why this priority**: Installed devices are remote; an update must never break data
collection.

**Independent Test**: Run the previous version with a custom `.env`, update, start, and verify
the Settings tab shows the same values and measurements continue.

**Acceptance Scenarios**:

1. **Given** an installation with a `.env` and no stored settings, **When** the new version
   starts, **Then** the `.env` values become the stored settings.
2. **Given** stored settings exist, **When** `.env` is edited later, **Then** stored settings
   win; `.env` is only used as defaults when a setting has never been stored.
3. **Given** a fresh install without `.env`, **When** the app starts, **Then** built-in defaults
   are used and the app starts normally.

---

### User Story 4 - Recover a lost admin password (Priority: P3)

The admin forgot the password. Someone with physical or shell access to the device can reset
it, after which the next visit to Settings asks to create a new password.

**Why this priority**: Rare, but without it a locked-out device needs a full reinstall.

**Independent Test**: Run the documented reset command, open Settings, set a new password.

**Acceptance Scenarios**:

1. **Given** a forgotten password, **When** the documented reset command is run on the device,
   **Then** the admin password is removed (all other settings stay) and Settings asks to create
   a new one.

### Edge Cases

- Two browsers save settings at the same time: last save wins; both see the saved values on
  reload.
- The database is read-only or full: saving shows an error and nothing is half-applied.
- Language switch while in Settings: all labels, help texts and error messages switch language.
- Protection switched to "Whole app" while other visitors have the dashboard open: their next
  data refresh requires login.
- Port/host changed to a value that cannot be bound on restart: the app falls back to the
  `.env`/default host and port and logs the problem, so the device stays reachable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST provide a "Settings" tab next to the dashboard, reachable from the
  main header.
- **FR-002**: Settings MUST include all non-Modbus values currently configurable in `.env`: data
  retention days, timezone, default language, debug logging, listen host and listen port. The
  Modbus bus/device configuration moves to the browser in feature 002 (multiple buses, multiple
  slaves per bus) and is read from `.env` until then.
- **FR-003**: Settings MUST be persisted in the app's existing database and survive restarts.
- **FR-004**: On first start without stored settings, values MUST be initialised from `.env`
  when present, otherwise from built-in defaults.
- **FR-005**: Every setting MUST be validated on the server before saving (ranges, allowed
  values, types); invalid input is rejected with a per-field translated message.
- **FR-006**: Data retention, timezone, default language and debug logging MUST apply without
  restart. Host/port changes MUST be marked "requires restart".
- **FR-007**: The Settings tab MUST be protected by an admin password, created on first visit.
  Passwords MUST be stored only as a salted, slow hash.
- **FR-008**: The admin MUST be able to choose the protection level "Settings only" (default) or
  "Whole app".
- **FR-009**: With "Whole app", no measurement data or page content other than the login screen
  MUST be served to visitors who are not logged in.
- **FR-010**: Login sessions MUST expire after a period of inactivity (default 60 minutes,
  configurable) and on explicit log-out.
- **FR-011**: Repeated failed logins MUST be throttled (5 failures → temporary block of 5
  minutes per client).
- **FR-012**: Secret values (admin password now; SMTP/Telegram/MQTT secrets in later features)
  MUST never be sent to the browser; secret fields show only whether a value is set.
- **FR-013**: A documented command-line reset MUST remove the admin password without touching
  other settings.
- **FR-014**: All new user-visible text MUST be available in every supported language (NL, EN,
  DE, FR, ES).
- **FR-015**: A failing sensor connection MUST NOT stop the web UI or the settings page.

### Key Entities

- **Setting**: a named configuration value with type, default, validation rule, and a flag
  whether it applies live or requires restart.
- **Admin credential**: the single admin password hash and protection level.
- **Session**: a logged-in browser session with last-activity time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can change timezone, retention, language or debug logging from the
  browser and see the effect within 60 seconds, without shell access or restart.
- **SC-002**: 100% of the non-Modbus values that were in `.env` can be changed from the
  browser (Modbus follows in feature 002, completing the set).
- **SC-003**: An existing installation upgrades with zero manual configuration steps and no
  gap in measurements longer than the restart itself.
- **SC-004**: With "Whole app" protection, an unauthenticated visitor can retrieve zero
  measurement values.
- **SC-005**: All Settings texts are shown in the selected language for all 5 languages.

## Assumptions

- A single admin account is enough (no multi-user roles); the device is operated by one owner.
- HTTPS is out of scope for this feature; on untrusted networks the device is expected behind a
  VPN or reverse proxy (documented).
- The database file path stays a bootstrap setting in `.env` (it is needed before settings can
  be read); it is shown read-only in Settings.
- Modbus buses and devices (002), notifications (003) and MQTT (004) are separate features that
  add their own sections to this Settings tab.
