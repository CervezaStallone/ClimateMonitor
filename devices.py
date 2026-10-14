"""Modbus bussen (RS-485 interfaces) en devices (slaves), opgeslagen in de database.

Een bus = één seriële interface (bijv. USB RS-485 dongle) met één of meer slaves.
Bij de eerste start wordt de oude .env configuratie (MODBUS_*) bus 1 met device 1.
"""
import os
import sqlite3
import threading
import time

from dotenv import load_dotenv

from settings import DB_FILE

load_dotenv()

BAUDRATES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
DEFAULT_PORT = 'COM11' if os.name == 'nt' else '/dev/ttyUSB0'

# veld -> type, default, .env naam (alleen voor migratie), validatie
BUS_FIELDS = {
    'name': {'type': str, 'default': 'Bus 1', 'max_len': 50},
    'port': {'type': str, 'default': DEFAULT_PORT, 'env': 'MODBUS_PORT', 'max_len': 255},
    'baudrate': {'type': int, 'default': 9600, 'env': 'MODBUS_BAUDRATE', 'choices': BAUDRATES},
    'bytesize': {'type': int, 'default': 8, 'env': 'MODBUS_BYTESIZE', 'choices': [7, 8]},
    'parity': {'type': str, 'default': 'N', 'env': 'MODBUS_PARITY', 'choices': ['N', 'E', 'O']},
    'stopbits': {'type': int, 'default': 1, 'env': 'MODBUS_STOPBITS', 'choices': [1, 2]},
    'timeout': {'type': float, 'default': 1.0, 'env': 'MODBUS_TIMEOUT', 'min': 0.05, 'max': 10},
    'enabled': {'type': bool, 'default': True},
}

DEVICE_FIELDS = {
    'name': {'type': str, 'default': 'Sensor 1', 'max_len': 50},
    'bus': {'type': str, 'default': 'Bus 1', 'max_len': 50},   # bus naam in de UI, bus_id in de database
    'slave_id': {'type': int, 'default': 1, 'env': 'MODBUS_SLAVE_ID', 'min': 1, 'max': 247},
    'function_code': {'type': int, 'default': 4, 'env': 'MODBUS_FUNCTION_CODE', 'choices': [3, 4]},
    'register_temp': {'type': int, 'default': 1, 'env': 'MODBUS_REGISTER_TEMP', 'min': 0, 'max': 65535},
    'register_humidity': {'type': int, 'default': 2, 'env': 'MODBUS_REGISTER_HUMIDITY', 'min': 0, 'max': 65535},
    'scale_temp': {'type': float, 'default': 0.1, 'min': -1000, 'max': 1000, 'nonzero': True},
    'scale_humidity': {'type': float, 'default': 0.1, 'min': -1000, 'max': 1000, 'nonzero': True},
    'enabled': {'type': bool, 'default': True},
}

_BUS_COLUMNS = list(BUS_FIELDS)
_DEVICE_COLUMNS = [f for f in DEVICE_FIELDS if f != 'bus'] + ['bus_id']

_lock = threading.Lock()
_version = 0          # verhoogd bij elke opgeslagen wijziging; de Modbus supervisor kijkt hiernaar
_status = {}          # device_id -> runtime status (laatste waarden / fout)


def _connect():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute('''CREATE TABLE IF NOT EXISTS buses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, port TEXT NOT NULL UNIQUE,
        baudrate INTEGER NOT NULL, bytesize INTEGER NOT NULL, parity TEXT NOT NULL, stopbits INTEGER NOT NULL,
        timeout REAL NOT NULL, enabled INTEGER NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, bus_id INTEGER NOT NULL REFERENCES buses(id), name TEXT NOT NULL UNIQUE,
        slave_id INTEGER NOT NULL, function_code INTEGER NOT NULL, register_temp INTEGER NOT NULL,
        register_humidity INTEGER NOT NULL, scale_temp REAL NOT NULL, scale_humidity REAL NOT NULL,
        enabled INTEGER NOT NULL, UNIQUE (bus_id, slave_id))''')
    return conn


def _coerce(spec, raw):
    """Zet invoer om naar het veldtype. ValueError bij ongeldige of lege invoer."""
    kind = spec['type']
    if kind is bool:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in ('true', '1', 'yes', 'on'):
            return True
        if text in ('false', '0', 'no', 'off'):
            return False
        raise ValueError(raw)
    if raw is None or str(raw).strip() == '':
        raise ValueError(raw)
    if kind is int:
        value = float(str(raw).replace(',', '.'))
        if value != int(value):
            raise ValueError(raw)
        return int(value)
    if kind is float:
        return float(str(raw).replace(',', '.'))
    value = str(raw).strip()
    return value.upper() if spec.get('choices') == ['N', 'E', 'O'] else value


def _check(spec, value):
    if 'choices' in spec and value not in spec['choices']:
        return 'err_choice'
    if 'min' in spec and not (spec['min'] <= value <= spec['max']):
        return 'err_range'
    if spec.get('nonzero') and value == 0:
        return 'err_range'
    if 'max_len' in spec and len(value) > spec['max_len']:
        return 'err_range'
    return None


def _clean_rows(rows, fields):
    """Valideer rijen veld voor veld. Geeft (schone rijen, {rij_index: {veld: foutcode}})."""
    clean, errors = [], {}
    for index, row in enumerate(rows):
        item, row_errors = {'id': row.get('id')}, {}
        for field, spec in fields.items():
            raw = row.get(field)
            if raw is None and spec['type'] is bool:
                raw = spec['default']
            try:
                value = _coerce(spec, raw)
            except (ValueError, TypeError):
                row_errors[field] = 'err_required' if raw is None or str(raw).strip() == '' else 'err_type'
                continue
            error = _check(spec, value)
            if error:
                row_errors[field] = error
            else:
                item[field] = value
        clean.append(item)
        if row_errors:
            errors[index] = row_errors
    return clean, errors


def _mark_duplicates(rows, field, errors, key):
    seen = set()
    for index, row in enumerate(rows):
        value = key(row)
        if value is None:
            continue
        if value in seen:
            errors.setdefault(index, {})[field] = 'err_duplicate'
        seen.add(value)


def validate_config(buses, devices):
    """Valideer de volledige configuratie. Geeft (schone bussen, schone devices, fouten).

    fouten: {'buses': {rij: {veld: code}}, 'devices': {rij: {veld: code}}} (leeg = geldig)
    """
    clean_buses, bus_errors = _clean_rows(buses, BUS_FIELDS)
    clean_devices, device_errors = _clean_rows(devices, DEVICE_FIELDS)

    _mark_duplicates(clean_buses, 'name', bus_errors, lambda r: r['name'].lower() if 'name' in r else None)
    _mark_duplicates(clean_buses, 'port', bus_errors, lambda r: r.get('port'))
    _mark_duplicates(clean_devices, 'name', device_errors, lambda r: r['name'].lower() if 'name' in r else None)
    _mark_duplicates(clean_devices, 'slave_id', device_errors,
                     lambda r: (r['bus'].lower(), r['slave_id']) if 'slave_id' in r and 'bus' in r else None)

    bus_names = {b['name'].lower() for b in clean_buses if 'name' in b}
    for index, device in enumerate(clean_devices):
        if 'bus' in device and device['bus'].lower() not in bus_names:
            device_errors.setdefault(index, {})['bus'] = 'err_bus_unknown'

    errors = {}
    if bus_errors:
        errors['buses'] = bus_errors
    if device_errors:
        errors['devices'] = device_errors
    return clean_buses, clean_devices, errors


def save_config(buses, devices):
    """Sla bussen en devices op (alles of niets). Geeft fouten terug; leeg dict = opgeslagen.

    Rijen met een bestaand 'id' worden bijgewerkt (historie blijft gekoppeld), rijen zonder id
    worden toegevoegd, bestaande rijen die ontbreken worden verwijderd (meetdata blijft bewaard).
    """
    global _version
    clean_buses, clean_devices, errors = validate_config(buses, devices)
    if errors:
        return errors
    with _lock:
        conn = _connect()
        try:
            conn.execute('BEGIN')
            existing_bus_ids = {row[0] for row in conn.execute('SELECT id FROM buses')}
            existing_device_ids = {row[0] for row in conn.execute('SELECT id FROM devices')}
            keep_bus_ids = {b['id'] for b in clean_buses if b.get('id') in existing_bus_ids}
            keep_device_ids = {d['id'] for d in clean_devices if d.get('id') in existing_device_ids}

            conn.executemany('DELETE FROM devices WHERE id = ?', [(i,) for i in existing_device_ids - keep_device_ids])
            conn.executemany('DELETE FROM buses WHERE id = ?', [(i,) for i in existing_bus_ids - keep_bus_ids])
            # Tijdelijke unieke waarden, zodat hernoemen of omwisselen geen UNIQUE conflict geeft
            conn.execute("UPDATE devices SET name = '~' || id, slave_id = -id")
            conn.execute("UPDATE buses SET name = '~' || id, port = '~' || id")

            bus_ids = {}
            for bus in clean_buses:
                values = [int(bus[c]) if isinstance(bus[c], bool) else bus[c] for c in _BUS_COLUMNS]
                if bus.get('id') in keep_bus_ids:
                    conn.execute(f"UPDATE buses SET {', '.join(c + ' = ?' for c in _BUS_COLUMNS)} WHERE id = ?",
                                 values + [bus['id']])
                    bus_ids[bus['name'].lower()] = bus['id']
                else:
                    cursor = conn.execute(f"INSERT INTO buses ({', '.join(_BUS_COLUMNS)}) "
                                          f"VALUES ({', '.join('?' * len(_BUS_COLUMNS))})", values)
                    bus_ids[bus['name'].lower()] = cursor.lastrowid

            for device in clean_devices:
                device = {**device, 'bus_id': bus_ids[device['bus'].lower()]}
                values = [int(device[c]) if isinstance(device[c], bool) else device[c] for c in _DEVICE_COLUMNS]
                if device.get('id') in keep_device_ids:
                    conn.execute(f"UPDATE devices SET {', '.join(c + ' = ?' for c in _DEVICE_COLUMNS)} WHERE id = ?",
                                 values + [device['id']])
                else:
                    conn.execute(f"INSERT INTO devices ({', '.join(_DEVICE_COLUMNS)}) "
                                 f"VALUES ({', '.join('?' * len(_DEVICE_COLUMNS))})", values)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        _version += 1
    return {}


def _initial_row(fields, name):
    """Rij voor de migratie uit .env: geldige .env waarden, anders defaults."""
    row = {}
    for field, spec in fields.items():
        value = spec['default']
        raw = os.getenv(spec['env']) if 'env' in spec else None
        if raw is not None:
            try:
                candidate = _coerce(spec, raw)
                if _check(spec, candidate) is not None:
                    raise ValueError(raw)
                value = candidate
            except (ValueError, TypeError):
                print(f"Waarschuwing: ongeldige waarde in .env voor {spec['env']}={raw!r}, standaardwaarde gebruikt")
        row[field] = value
    row['name'] = name
    return row


def init_devices():
    """Maak tabellen aan; bij een lege configuratie wordt .env bus 1 met device 1 (upgrade pad)."""
    conn = _connect()
    try:
        empty = conn.execute('SELECT COUNT(*) FROM buses').fetchone()[0] == 0
    finally:
        conn.close()
    if empty:
        bus = _initial_row(BUS_FIELDS, 'Bus 1')
        device = _initial_row(DEVICE_FIELDS, 'Sensor 1')
        device['bus'] = bus['name']
        errors = save_config([bus], [device])
        if errors:
            raise RuntimeError(f"Kan standaard Modbus configuratie niet aanmaken: {errors}")
        print(f"✓ Modbus configuratie aangemaakt: {bus['name']} ({bus['port']}) "
              f"met {device['name']} (slave {device['slave_id']})")


def load_config():
    """Geef (bussen, devices) als lijsten van dicts; devices hebben ook 'bus' (naam)."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        buses = [dict(r) for r in conn.execute('SELECT * FROM buses ORDER BY id')]
        devices = [dict(r) for r in conn.execute(
            'SELECT d.*, b.name AS bus FROM devices d JOIN buses b ON b.id = d.bus_id ORDER BY d.id')]
    finally:
        conn.close()
    for row in buses + devices:
        row['enabled'] = bool(row['enabled'])
    return buses, devices


def list_devices(enabled_only=False):
    """Devices voor het dashboard: [{'id', 'name', 'enabled'}]."""
    _, devices = load_config()
    return [{'id': d['id'], 'name': d['name'], 'enabled': d['enabled']}
            for d in devices if d['enabled'] or not enabled_only]


def version():
    return _version


def report_ok(device_id, temperature, humidity):
    _status[device_id] = {**_status.get(device_id, {}), 'ok_at': time.time(), 'temperature': temperature,
                          'humidity': humidity, 'error': None}


def report_error(device_id, message):
    _status[device_id] = {**_status.get(device_id, {}), 'error': str(message)[:200], 'error_at': time.time()}


def status(device_id):
    """Runtime status: {'ok_at', 'temperature', 'humidity', 'error', 'error_at'} (leeg = nog niets gelezen)."""
    return dict(_status.get(device_id, {}))


def available_ports():
    """Seriële poorten op dit apparaat, als suggestie in de Settings tab."""
    try:
        from serial.tools import list_ports
        return sorted(p.device for p in list_ports.comports())
    except Exception:
        return []
