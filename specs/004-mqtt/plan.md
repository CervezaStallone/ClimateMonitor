# Implementation Plan: MQTT Publishing

**Branch**: `004-mqtt` | **Spec**: [spec.md](spec.md)

## Summary
New `mqtt_publisher.py`: the poller stores the latest values per sensor in memory (non-blocking);
a `Publisher` thread owns a paho-mqtt client, (re)connects when settings change, and publishes the
latest values every interval. Settings keys in `settings.SCHEMA` (section `mqtt`).

## Technical Context
**New dependency**: `paho-mqtt==2.1.0` — the de-facto Python MQTT client (reconnect, LWT, TLS, QoS);
implementing MQTT by hand would be more code and less robust (constitution V: justified).
**Testing**: unit tests with a fake client; end-to-end against a local broker (amqtt via uvx).

## Constitution Check
| Principle | Status |
|-----------|--------|
| I. Unattended edge reliability | PASS — publishing in its own thread, paho reconnect with back-off, poller only writes a dict |
| II. Browser-first configuration | PASS |
| III. Secure by default | PASS — password write-only, TLS option, login required |
| IV. Every string translated | PASS |
| V. Simplicity | PASS — one justified dependency |
