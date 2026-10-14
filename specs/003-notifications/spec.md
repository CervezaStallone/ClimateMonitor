# Feature Specification: Threshold Notifications via Telegram and E-mail

**Feature Branch**: `003-notifications`
**Created**: 2026-10-14
**Status**: Draft
**Input**: User description: "A notification system where the user enters a Telegram bot API key and a user or chat id. The user can set limits and thresholds, both global and per device, so notifications are sent when values are exceeded. Also allow notifications when values return to normal. Besides Telegram this must also work via an SMTP mail server. Everything configured in the browser."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Alert when a limit is exceeded (Priority: P1)

The owner of a cold store sets a global maximum of 8 °C. When a sensor stays above 8 °C, a
Telegram message and/or e-mail arrives with the sensor name, the value and the limit.

**Independent Test**: Configure Telegram, set a limit below the current value, receive a message
within the configured delay.

**Acceptance Scenarios**:

1. **Given** a global rule "temperature max 8 °C", **When** a sensor measures above 8 °C for
   longer than the alarm delay, **Then** exactly one alert is sent per enabled channel.
2. **Given** a value that exceeds the limit only briefly (shorter than the delay), **Then** no
   alert is sent.
3. **Given** an active alert, **When** the value stays above the limit, **Then** no repeated
   alerts are sent.

### User Story 2 - Back to normal (Priority: P1)

When the value returns within limits (beyond a hysteresis margin), a "back to normal" message
is sent, if enabled.

**Acceptance Scenarios**:

1. **Given** an active alert and "notify on recovery" enabled, **When** the value is back
   within the limit minus hysteresis, **Then** one recovery message is sent.
2. **Given** "notify on recovery" disabled, **Then** the alert resets silently.

### User Story 3 - Per-device limits (Priority: P1)

A greenhouse sensor needs different humidity limits than the office sensor. A rule for a
specific sensor overrides the global rule for the same quantity.

**Acceptance Scenarios**:

1. **Given** a global rule humidity max 70 % and a rule for "Kas" humidity max 90 %, **When**
   "Kas" measures 80 %, **Then** no alert; **When** the office sensor measures 80 %, **Then** alert.

### User Story 4 - Configure and test channels in the browser (Priority: P1)

In Settings the admin enters the Telegram bot token and chat id and/or the SMTP server, sender,
recipients, user and password, presses "Send test" and sees success or the error message.

**Acceptance Scenarios**:

1. **Given** valid Telegram settings, **When** "Send test" is pressed, **Then** a test message
   arrives and the UI reports success; with an invalid token the UI shows the error.
2. **Given** saved secrets (bot token, SMTP password), **When** Settings is opened, **Then** the
   secrets are not shown, only that they are set; leaving the field empty keeps the stored value.

### User Story 5 - Sensor offline alert (Priority: P2)

If a sensor delivers no valid data for the configured number of minutes, an "offline" alert is
sent, and an "online again" message when data returns.

### Edge Cases

- Telegram/SMTP unreachable: messages are retried with back-off (max 1 hour) and do not slow
  down measurements; the notification log shows the failure.
- Both min and max empty in a rule: rule is refused on save.
- min ≥ max: refused on save.
- A rule for a deleted sensor: removed together with the sensor.
- Restart during an active alert: state starts fresh; an alert may be sent again (acceptable).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Channels: Telegram (bot token, chat id) and SMTP (host, port, security
  none/STARTTLS/SSL, username, password, sender, one or more recipients), each enabled separately.
- **FR-002**: Rules: quantity (temperature, humidity, dew point, absolute humidity), optional
  minimum, optional maximum, scope "all sensors" or one sensor, enabled flag.
- **FR-003**: A sensor rule overrides the global rule for the same quantity.
- **FR-004**: An alert is raised when the limit is exceeded continuously for the alarm delay
  (default 60 s); one message per alert.
- **FR-005**: Recovery when the value is within the limit by at least the hysteresis (default
  temperature 0.5 °C / humidity 2 %), message only when "notify on recovery" is enabled.
- **FR-006**: Offline alert after N minutes without valid data (0 = off), and an "online" message.
- **FR-007**: Messages are in the default language and contain sensor name, quantity, value,
  limit and time.
- **FR-008**: Sending happens in the background with retries; it never blocks measuring.
- **FR-009**: The last 20 notifications with status (sent / failed + reason) are shown in Settings.
- **FR-010**: Secrets are write-only in the browser.
- **FR-011**: "Send test" per channel uses the values currently in the form (also unsaved).
- **FR-012**: All texts translated (NL, EN, DE, FR, ES).

### Key Entities

- **Alert rule**: scope (global / sensor), quantity, min, max, enabled.
- **Alert state** (runtime): per sensor and quantity: normal / pending / alarm.
- **Notification**: time, channel, text, status.

## Success Criteria *(mandatory)*

- **SC-001**: An exceeded limit reaches the user within delay + 30 s when the channel works.
- **SC-002**: A value hovering around the limit produces at most one alert and one recovery.
- **SC-003**: Channel outages never delay measurements (polling rate unchanged).
- **SC-004**: A non-technical user configures Telegram and a first rule in under 5 minutes.

## Assumptions

- Telegram bot is created by the user via @BotFather; the chat id is the user's or a group's id.
- Alert state is in memory (single process).
