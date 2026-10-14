# Tasks: 004 MQTT

- [x] T001 `settings.py`: mqtt_* keys, topic prefix validation, required-when-enabled
- [x] T002 `mqtt_publisher.py`: latest values store, slugs, Publisher thread (connect/reconnect on settings change, LWT, publish loop), status, test_connection
- [x] T003 `modbus_reader.py`: store values after each valid reading; `app.py`: start publisher
- [x] T004 `settings_ui.py`: MQTT section with test button and status
- [x] T005 Translations; requirements.txt + pyproject.toml (paho-mqtt)
- [x] T006 Tests (fake client) + end-to-end with local broker
- [x] T007 README, CI
