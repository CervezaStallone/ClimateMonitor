# Feature Specification: Publish Measurements to an MQTT Broker

**Feature Branch**: `004-mqtt`
**Created**: 2026-10-14
**Status**: Draft
**Input**: User description: "The user can enter an MQTT server to which the application publishes the values per device when enabled. Everything configured in the browser."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Publish values per sensor (Priority: P1)

A user runs Home Assistant / Node-RED / a SCADA system with an MQTT broker. In Settings they
enter the broker address, optional login and TLS, a topic prefix, and enable MQTT. From then on
every sensor's current values are published under its own topic.

**Independent Test**: Subscribe to `<prefix>/#` on the broker, enable MQTT, see a JSON message
per sensor every publish interval and the status topic `online`.

**Acceptance Scenarios**:

1. **Given** MQTT enabled with prefix `xy-md02`, **When** sensor "Kas noord" is measured, **Then**
   `xy-md02/kas-noord/state` receives `{"device_id", "name", "temperature", "humidity",
   "dewpoint", "absolute_humidity", "timestamp"}` and `xy-md02/kas-noord/temperature` etc.
   receive the plain values, at most once per publish interval.
2. **Given** the app connects, **Then** `xy-md02/status` is `online` (retained); when the app
   stops or loses the connection, the broker publishes `offline` (last will).
3. **Given** MQTT disabled, **Then** nothing is published and no connection is kept.

### User Story 2 - Robust when the broker is unreachable (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the broker is down, **Then** measuring, the dashboard and notifications continue;
   the app reconnects automatically when the broker is back and Settings shows the status.

### User Story 3 - Configure and test in the browser (Priority: P1)

**Acceptance Scenarios**:

1. **Given** broker settings in the form, **When** "Test connection" is pressed, **Then** the UI
   reports success or the error (e.g. "not authorised", "connection refused").
2. **Given** a saved password, **Then** it is never shown again (write-only).
3. **Given** changed broker settings are saved, **Then** the app reconnects with the new settings
   without restart.

### Edge Cases

- Topic prefix with `#`, `+`, leading/trailing `/` or spaces: refused.
- Sensor names with spaces/special characters: topic uses a slug (`Kas noord` → `kas-noord`).
- Two sensors with the same slug (`Kas-1` / `Kas 1`): the second gets its id appended.
- Renaming a sensor changes its topic (documented); `device_id` in the payload stays the same.

## Requirements *(mandatory)*

- **FR-001**: Settings: enabled, host, port (default 1883), TLS, username, password (write-only),
  client ID (optional), topic prefix (default `xy-md02`), publish interval (default 10 s), QoS (0/1),
  retain (default on).
- **FR-002**: Per sensor publish a JSON state topic and one topic per quantity.
- **FR-003**: Availability topic `<prefix>/status` with last will `offline`.
- **FR-004**: Publishing never blocks measuring; automatic reconnect; status and last error in Settings.
- **FR-005**: "Test connection" with the current form values.
- **FR-006**: Changes apply without restart.
- **FR-007**: All texts translated (NL, EN, DE, FR, ES).

## Success Criteria *(mandatory)*

- **SC-001**: A subscriber receives every sensor's values within publish interval + 5 s.
- **SC-002**: A broker outage has no effect on measuring rate; publishing resumes within 60 s
  after the broker is back.

## Assumptions

- MQTT 3.1.1 over TCP (optionally TLS with the system CA store).
- Home Assistant MQTT discovery is out of scope (the JSON state topic can be used manually).
