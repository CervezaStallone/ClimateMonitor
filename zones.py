"""Zones in het Mollier- en houtdiagram: gebieden in temperatuur × RV met een kleur en optioneel een alarm.

Een zone is een veelhoek van (temperatuur, RV) punten: een rechthoek uit min/max in Settings, of vrij
getekend in het Mollier-diagram. Per zone een alarmsoort: 'keep_inside' (gewenst klimaat, melding bij
verlaten), 'keep_outside' (gevarengebied, melding bij binnengaan) of 'none' (alleen tonen).
"""
import json
import os
import sqlite3
import threading

import devices
from settings import DB_FILE

COLORS = {'green': '#1baf7a', 'blue': '#2a78d6', 'orange': '#eb6834', 'red': '#e34948', 'purple': '#6250d6',
          'yellow': '#eda100'}
MODES = ['keep_inside', 'keep_outside', 'none']
LEVELS = ['alarm', 'warning']
SHAPES = ['rect', 'polygon']

_lock = threading.Lock()
_cache = None   # [zone dicts], None = opnieuw laden


def _connect():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute('''CREATE TABLE IF NOT EXISTS zones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, device_id INTEGER, name TEXT NOT NULL, color TEXT NOT NULL,
        mode TEXT NOT NULL, level TEXT NOT NULL, shape TEXT NOT NULL, points TEXT NOT NULL, enabled INTEGER NOT NULL)''')
    return conn


def _number(raw):
    """float, of ValueError bij lege/ongeldige invoer."""
    if raw is None or str(raw).strip() == '':
        raise ValueError(raw)
    return float(str(raw).replace(',', '.'))


def _points(row, errors):
    """Hoekpunten [[temperatuur, rv], ...] uit een formulierregel; fouten in errors."""
    if (row.get('shape') or 'rect') == 'polygon':
        try:
            points = [[float(t), float(h)] for t, h in json.loads(row.get('points') or '[]')]
        except (TypeError, ValueError):
            points = []
        if len(points) < 3:
            errors['shape'] = 'err_zone_points'
        return points
    values = {}
    for field in ('temp_min', 'temp_max', 'rh_min', 'rh_max'):
        try:
            values[field] = _number(row.get(field))
        except (TypeError, ValueError):
            errors[field] = 'err_required' if row.get(field) in (None, '') else 'err_type'
    if 'temp_min' in values and 'temp_max' in values and values['temp_min'] >= values['temp_max']:
        errors['temp_max'] = 'err_min_max'
    for field in ('rh_min', 'rh_max'):
        if field in values and not 0 <= values[field] <= 100:
            errors[field] = 'err_range'
    if 'rh_min' in values and 'rh_max' in values and values['rh_min'] >= values['rh_max'] and 'rh_max' not in errors:
        errors['rh_max'] = 'err_min_max'
    if errors:
        return []
    t0, t1, h0, h1 = values['temp_min'], values['temp_max'], values['rh_min'], values['rh_max']
    return [[t0, h0], [t1, h0], [t1, h1], [t0, h1]]


def validate(rows):
    """Valideer zones uit de UI. Geeft (schone zones, {rij: {veld: foutcode}})."""
    device_ids = {d['id'] for d in devices.list_devices()}
    clean, errors = [], {}
    for index, row in enumerate(rows):
        row_errors = {}
        try:
            scope = int(row.get('scope') or 0)
        except (TypeError, ValueError):
            scope = -1
        if scope != 0 and scope not in device_ids:
            row_errors['scope'] = 'err_choice'
        name = str(row.get('name') or '').strip()
        if not name or len(name) > 50:
            row_errors['name'] = 'err_required' if not name else 'err_range'
        for field, choices in (('color', COLORS), ('mode', MODES), ('level', LEVELS)):
            if row.get(field) not in choices:
                row_errors[field] = 'err_choice'
        shape = row.get('shape') or 'rect'
        points = _points(row, row_errors) if shape in SHAPES else []
        if row_errors:
            errors[index] = row_errors
        clean.append({'device_id': scope or None, 'name': name, 'color': row.get('color'), 'mode': row.get('mode'),
                      'level': row.get('level'), 'shape': shape, 'points': points,
                      'enabled': str(row.get('enabled', 'true')).lower() in ('true', '1')})
    return clean, errors


def save(rows):
    """Sla alle zones op (alles of niets). Geeft fouten terug; leeg dict = opgeslagen."""
    global _cache
    clean, errors = validate(rows)
    if errors:
        return errors
    with _lock:
        conn = _connect()
        try:
            conn.execute('BEGIN')
            conn.execute('DELETE FROM zones')
            conn.executemany('INSERT INTO zones (device_id, name, color, mode, level, shape, points, enabled) '
                             'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                             [(z['device_id'], z['name'], z['color'], z['mode'], z['level'], z['shape'],
                               json.dumps(z['points']), int(z['enabled'])) for z in clean])
            conn.commit()
        finally:
            conn.close()
        _cache = None
    return {}


def load():
    """Alle zones (punten als lijst, min/max van de omhullende rechthoek erbij voor het formulier)."""
    global _cache
    with _lock:
        if _cache is None:
            conn = _connect()
            conn.row_factory = sqlite3.Row
            try:
                rows = [dict(r) for r in conn.execute('SELECT * FROM zones ORDER BY id')]
            finally:
                conn.close()
            device_ids = {d['id'] for d in devices.list_devices()}
            _cache = []
            for row in rows:
                if row['device_id'] is not None and row['device_id'] not in device_ids:
                    continue   # zone van een verwijderde sensor
                points = json.loads(row['points'])
                temps, hums = [p[0] for p in points], [p[1] for p in points]
                _cache.append({**row, 'points': points, 'enabled': bool(row['enabled']),
                               'temp_min': min(temps), 'temp_max': max(temps), 'rh_min': min(hums), 'rh_max': max(hums)})
        return [dict(z) for z in _cache]


def effective(device_id):
    """Ingeschakelde zones die voor deze sensor gelden (voor alle sensoren + alleen deze sensor)."""
    return [z for z in load() if z['enabled'] and z['device_id'] in (None, device_id)]


def contains(zone, temperature, humidity):
    """Ligt (temperatuur, RV) in de zone? Ray casting over de veelhoek."""
    inside = False
    points = zone['points']
    for (t1, h1), (t2, h2) in zip(points, points[1:] + points[:1]):
        if (h1 > humidity) != (h2 > humidity) and temperature < t1 + (humidity - h1) * (t2 - t1) / (h2 - h1):
            inside = not inside
    return inside


def fill_color(name, alpha=0.15):
    """Doorzichtige vulkleur van een zonekleur."""
    hex_color = COLORS[name]
    return f'rgba({int(hex_color[1:3], 16)}, {int(hex_color[3:5], 16)}, {int(hex_color[5:7], 16)}, {alpha})'


def visible(device_id):
    """Zones voor een diagram: van één sensor (incl. alle-sensoren-zones) of, zonder keuze, de algemene zones."""
    if device_id:
        return effective(device_id)
    return [z for z in load() if z['enabled'] and z['device_id'] is None]


def clearly(zone, temperature, humidity, margin_temp, margin_humidity, inside):
    """Ligt het punt binnen (inside=True) of buiten de zone, met minstens de marge tot de rand?

    Voor herstel na een zone-alarm: zonder marge meldt een sensor die op de rand hangt steeds opnieuw alarm
    en herstel. Getoetst op het punt zelf en vier punten op marge-afstand.
    """
    probes = [(temperature, humidity), (temperature - margin_temp, humidity), (temperature + margin_temp, humidity),
              (temperature, humidity - margin_humidity), (temperature, humidity + margin_humidity)]
    return all(contains(zone, t, h) == inside for t, h in probes)
