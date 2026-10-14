# Feature Specification: Multiple RS-485 Buses and Devices

**Feature Branch**: `002-multi-bus-devices`
**Created**: 2026-10-14
**Status**: Draft
**Input**: User description: "Add multiple devices (Modbus slaves), visible in separate graphs but also in combined graphs and views. Per device the name and the temperature/humidity registers can be set. Multiple RS-485 dongles/interfaces (buses) must be supported, and every bus can have multiple slaves. Everything configured in the browser." Related: GitHub issue #18 (multiple XY-MD04 sensors over RS-485, each with a clear unique identifier).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure buses and devices in the browser (Priority: P1)

An installer connects two USB RS-485 dongles to an edge device. On the first dongle three
sensors are daisy-chained (slave IDs 1, 2, 3), on the second one sensor (slave ID 1). In the
Settings tab the installer adds two buses (serial port, baud rate, parity, …) and four devices
(name, bus, slave ID, temperature register, humidity register, scale), saves, and all four
sensors start reporting.

**Why this priority**: Core of the feature and of issue #18; without it nothing else works.

**Independent Test**: With two serial interfaces and several sensors, configure them in Settings
and verify each device shows fresh values within one poll cycle after saving.

**Acceptance Scenarios**:

1. **Given** the Modbus section in Settings, **When** the admin adds a bus and a device and
   saves, **Then** the device is polled without restarting the app.
2. **Given** two devices on the same bus with the same slave ID, **When** saving, **Then** the
   save is refused with a translated error on the conflicting rows.
3. **Given** a device name that is already used, **When** saving, **Then** the save is refused
   (names identify devices uniquely).
4. **Given** a device is disabled, **When** saved, **Then** it is no longer polled and its
   historical data stays available.
5. **Given** a bus is removed while devices still use it, **When** saving, **Then** the save is
   refused and tells which devices still use the bus.
6. **Given** the Settings device list, **When** it is shown, **Then** each device shows its live
   status: last values and time, or the last error (e.g. "no response").

---

### User Story 2 - See devices separately and combined (Priority: P1)

A user opens the dashboard and chooses "All devices" to see one graph per quantity
(temperature, humidity, dew point, absolute humidity, comfort) with one line per device, plus
a card per device with its current values and online/offline state. Choosing one device shows
the familiar detailed view for that device only.

**Why this priority**: Multiple devices are only useful when their data can be compared and
inspected individually.

**Independent Test**: With two devices producing different values, switch between "All
devices" and each single device and verify lines, cards and Mollier diagram match.

**Acceptance Scenarios**:

1. **Given** "All devices", **When** the graph updates, **Then** every enabled device has its own
   line (with its name in the legend) in each graph.
2. **Given** a single device is selected, **When** the graph updates, **Then** only that device's
   data and current values are shown.
3. **Given** a device has not delivered data for more than 3 poll intervals (minimum 30 s),
   **When** the overview is shown, **Then** its card is marked offline with the time of the
   last value.
4. **Given** "All devices", **When** the Mollier diagram is shown, **Then** the current state of
   every device is plotted as a labelled point.
5. **Given** a single device is selected, **When** historical replay is used, **Then** it replays
   that device's data.

---

### User Story 3 - Upgrade keeps the existing sensor (Priority: P1)

An existing single-sensor installation is updated. Its `.env` Modbus settings become bus 1 and
device 1 ("Sensor 1"), and all historical measurements belong to that device.

**Why this priority**: Remote devices must keep measuring after an update without manual work.

**Independent Test**: Update a running installation with history; verify the dashboard shows
the old data under "Sensor 1" and new values keep arriving.

**Acceptance Scenarios**:

1. **Given** an installation without bus/device configuration, **When** the new version starts,
   **Then** one bus and one device are created from `.env` (or defaults) and all existing
   measurements are attributed to that device.

---

### User Story 4 - A failing bus or sensor does not affect others (Priority: P2)

A dongle is unplugged or a sensor fails. The other buses and sensors keep reporting; the
failed ones are retried automatically and resume when they come back.

**Acceptance Scenarios**:

1. **Given** a configured serial port that does not exist at startup, **When** it appears later,
   **Then** polling starts automatically without restart.
2. **Given** one sensor on a bus does not respond, **When** polling, **Then** the other sensors on
   that bus and on other buses keep their normal update rate (slow sensor ≤ its timeout).

### Edge Cases

- Negative temperatures are read correctly (signed registers).
- Values outside physical ranges (temperature −50…100 °C, humidity 0…100 %) are discarded and
  reported in the device status.
- Two buses configured with the same serial port: refused on save.
- A device is renamed: history stays attached (devices are identified by an internal id).
- Large existing databases: the upgrade must not rewrite existing data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Admin MUST be able to create, edit, enable/disable and delete buses: name, serial
  port, baud rate, byte size, parity, stop bits, timeout.
- **FR-002**: Admin MUST be able to create, edit, enable/disable and delete devices: name
  (unique), bus, slave ID (1–247, unique per bus), function code (3/4), temperature register,
  humidity register, temperature scale, humidity scale.
- **FR-003**: Every device MUST have a stable unique identifier (shown in Settings) that does not
  change when the device is renamed.
- **FR-004**: Configuration changes MUST be validated server-side (all-or-nothing) and applied
  without restart; only the buses whose configuration changed are restarted.
- **FR-005**: Buses MUST be polled independently and concurrently; devices on a bus are polled
  sequentially (RS-485 is half duplex). Poll interval is a global setting (default 1 s).
- **FR-006**: A missing or failing serial port or device MUST be retried with back-off and MUST
  NOT stop other buses/devices or the web UI.
- **FR-007**: Measurements MUST be stored per device; existing measurements belong to the first
  device after upgrade.
- **FR-008**: Dashboard MUST offer "All devices (combined)" and every single device.
- **FR-009**: Combined view MUST show one line per device in each graph, a card per device with
  current values and online/offline status, and all devices in the Mollier diagram.
- **FR-010**: Single-device view MUST show the existing detailed graphs, cards, Mollier diagram
  and historical replay for that device.
- **FR-011**: Registers MUST be read as signed 16-bit values multiplied by the device's scale.
- **FR-012**: The Settings tab MUST list available serial ports on the host as suggestions.
- **FR-013**: All new texts MUST be translated in NL, EN, DE, FR, ES.

### Key Entities

- **Bus**: one serial interface (RS-485 dongle) with its serial parameters; has many devices.
- **Device**: one Modbus slave on a bus; id, unique name, register map and scales.
- **Measurement**: timestamped temperature/humidity (+ derived values) of one device.
- **Device status** (runtime): last values/time, last error, online/offline.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An installer configures 2 buses with 4 devices from the browser in under 5 minutes
  without shell access.
- **SC-002**: With one bus disconnected, devices on other buses keep updating at their normal
  rate (no missed poll cycles caused by the failing bus).
- **SC-003**: Upgrading an existing installation needs zero manual steps and loses no history.
- **SC-004**: A user can tell within 5 seconds which device is offline from the dashboard.

## Assumptions

- Sensors are XY-MD02/XY-MD04-like: temperature and humidity in holding/input registers; other
  sensor types are configured through registers and scale.
- Up to ~16 devices per installation; poll rate is shared (global interval).
- Deleting a device removes it from configuration and dashboard but keeps its stored
  measurements in the database.
- Notifications (003) and MQTT (004) will refer to devices by id and name.
