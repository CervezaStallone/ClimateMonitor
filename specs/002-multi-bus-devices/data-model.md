# Data Model: 002 Multiple Buses and Devices

## buses
| Column | Type | Validation |
|--------|------|------------|
| id | INTEGER PK | |
| name | TEXT | 1–50 chars, unique |
| port | TEXT | 1–100 chars, unique |
| baudrate | INTEGER | 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200 |
| bytesize | INTEGER | 7, 8 |
| parity | TEXT | N, E, O |
| stopbits | INTEGER | 1, 2 |
| timeout | REAL | 0.05–10 s |
| enabled | INTEGER | 0/1 |

## devices
| Column | Type | Validation |
|--------|------|------------|
| id | INTEGER PK | stable identifier |
| bus_id | INTEGER | existing bus |
| name | TEXT | 1–50 chars, unique |
| slave_id | INTEGER | 1–247, unique per bus |
| function_code | INTEGER | 3 (holding) or 4 (input) |
| register_temp | INTEGER | 0–65535 |
| register_humidity | INTEGER | 0–65535 |
| scale_temp | REAL | non-zero, −1000…1000 (default 0.1) |
| scale_humidity | REAL | non-zero, −1000…1000 (default 0.1) |
| enabled | INTEGER | 0/1 |

## measurements_YYYYMMDD
Existing columns plus `device_id INTEGER NOT NULL DEFAULT 1`; index `(device_id, timestamp)`.

## Migration (first start of this version)
If `buses` is empty: bus 1 from `MODBUS_PORT/BAUDRATE/BYTESIZE/PARITY/STOPBITS/TIMEOUT`, device 1
"Sensor 1" from `MODBUS_SLAVE_ID/FUNCTION_CODE/REGISTER_TEMP/REGISTER_HUMIDITY` (invalid or
missing values → defaults). Existing measurement tables get `device_id` = 1.

## Settings key (settings.SCHEMA)
`poll_interval_seconds` int 1–3600, default 1, section `modbus`.
