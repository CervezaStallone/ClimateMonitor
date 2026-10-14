# Tasks: 003 Notifications

- [x] T001 `settings.py`: notification/alert keys, float type, optional and secret (write-only) fields, required-when-enabled validation
- [x] T002 `alerts.py`: rules (validate/save/load/effective), state machine, offline/online, Telegram + SMTP senders with secret redaction, Notifier thread with retries, log
- [x] T003 `modbus_reader.py`: evaluate after each valid reading; `app.py`: start notifier
- [x] T004 `settings_ui.py`: channel fields, test buttons, rules table, notification log, save + error highlighting
- [x] T005 Translations nl/en/de/fr/es
- [x] T006 Tests: settings secrets/required, rule validation/override, delay/single alert/hysteresis/recovery, offline, redaction, retries, login on all callbacks
- [x] T007 End-to-end: simulated buses + local SMTP sink: test mail, alarm, recovery, offline/online
- [x] T008 README, CI import/compile list
