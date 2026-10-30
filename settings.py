"""Instellingen opgeslagen in de database, bewerkbaar via de Settings tab.

.env levert alleen de startwaarden: bij de eerste start worden ontbrekende instellingen
overgenomen uit .env (of de standaardwaarde). Daarna is de database leidend.

Wachtwoord vergeten: python settings.py reset-password
"""
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# Bootstrap: nodig voordat instellingen gelezen kunnen worden, blijft dus in .env
DB_FILE = os.getenv('DATABASE_FILE', 'src/modbus_sensor_data.db')

LANGUAGES = ['nl', 'en', 'de', 'fr', 'es']

# key -> type, default, .env naam, sectie, validatie (choices / min / max / check), restart nodig
SCHEMA = {
    'dashboard_view': {'type': str, 'default': 'board', 'section': 'display', 'choices': ['board', 'meters']},
    'dashboard_theme': {'type': str, 'default': 'dark', 'section': 'display', 'choices': ['dark', 'light']},
    'show_comfort': {'type': bool, 'default': True, 'section': 'display'},
    'show_mollier': {'type': bool, 'default': True, 'section': 'display'},
    'poll_interval_seconds': {'type': int, 'default': 1, 'section': 'modbus', 'min': 1, 'max': 3600},
    'data_retention_days': {'type': int, 'default': 0, 'env': 'DATA_RETENTION_DAYS', 'section': 'data',
                            'min': 0, 'max': 3650},
    'debug_logging': {'type': bool, 'default': False, 'env': 'DEBUG_LOGGING', 'section': 'data'},
    'timezone': {'type': str, 'default': 'Europe/Amsterdam', 'env': 'TIMEZONE', 'section': 'regional',
                 'check': 'timezone'},
    'default_language': {'type': str, 'default': 'en', 'env': 'DEFAULT_LANGUAGE', 'section': 'regional',
                         'choices': LANGUAGES},
    # Geen .env migratie: oudere versies negeerden APP_HOST/APP_PORT en luisterden altijd op 0.0.0.0:8050
    'app_host': {'type': str, 'default': '0.0.0.0', 'section': 'server', 'check': 'host', 'restart': True},
    'app_port': {'type': int, 'default': 8050, 'section': 'server', 'min': 1, 'max': 65535, 'restart': True},
    'auth_mode': {'type': str, 'default': 'settings', 'section': 'security', 'choices': ['settings', 'app']},
    'session_timeout_minutes': {'type': int, 'default': 60, 'section': 'security', 'min': 5, 'max': 1440},
    # Notificaties (secret = nooit naar de browser, leeg laten = huidige waarde houden)
    'telegram_enabled': {'type': bool, 'default': False, 'section': 'notify'},
    'telegram_bot_token': {'type': str, 'default': '', 'section': 'notify', 'secret': True, 'optional': True,
                           'check': 'telegram_token'},
    'telegram_chat_id': {'type': str, 'default': '', 'section': 'notify', 'optional': True, 'check': 'chat_id'},
    'smtp_enabled': {'type': bool, 'default': False, 'section': 'notify'},
    'smtp_host': {'type': str, 'default': '', 'section': 'notify', 'optional': True, 'check': 'host'},
    'smtp_port': {'type': int, 'default': 587, 'section': 'notify', 'min': 1, 'max': 65535},
    'smtp_security': {'type': str, 'default': 'starttls', 'section': 'notify', 'choices': ['starttls', 'ssl', 'none']},
    'smtp_username': {'type': str, 'default': '', 'section': 'notify', 'optional': True},
    'smtp_password': {'type': str, 'default': '', 'section': 'notify', 'secret': True, 'optional': True},
    'smtp_from': {'type': str, 'default': '', 'section': 'notify', 'optional': True, 'check': 'email_list'},
    'smtp_to': {'type': str, 'default': '', 'section': 'notify', 'optional': True, 'check': 'email_list'},
    'alert_delay_seconds': {'type': int, 'default': 60, 'section': 'alerts', 'min': 0, 'max': 3600},
    'alert_hysteresis_temp': {'type': float, 'default': 0.5, 'section': 'alerts', 'min': 0, 'max': 20},
    'alert_hysteresis_humidity': {'type': float, 'default': 2.0, 'section': 'alerts', 'min': 0, 'max': 50},
    'alert_notify_recovery': {'type': bool, 'default': True, 'section': 'alerts'},
    'alert_offline_minutes': {'type': int, 'default': 10, 'section': 'alerts', 'min': 0, 'max': 1440},
    # MQTT
    'mqtt_enabled': {'type': bool, 'default': False, 'section': 'mqtt'},
    'mqtt_host': {'type': str, 'default': '', 'section': 'mqtt', 'optional': True, 'check': 'host'},
    'mqtt_port': {'type': int, 'default': 1883, 'section': 'mqtt', 'min': 1, 'max': 65535},
    'mqtt_tls': {'type': bool, 'default': False, 'section': 'mqtt'},
    'mqtt_username': {'type': str, 'default': '', 'section': 'mqtt', 'optional': True},
    'mqtt_password': {'type': str, 'default': '', 'section': 'mqtt', 'secret': True, 'optional': True},
    'mqtt_client_id': {'type': str, 'default': '', 'section': 'mqtt', 'optional': True, 'check': 'client_id'},
    'mqtt_topic_prefix': {'type': str, 'default': 'xy-md02', 'section': 'mqtt', 'check': 'topic'},
    'mqtt_publish_interval_seconds': {'type': int, 'default': 10, 'section': 'mqtt', 'min': 1, 'max': 3600},
    'mqtt_qos': {'type': int, 'default': 0, 'section': 'mqtt', 'choices': [0, 1]},
    'mqtt_retain': {'type': bool, 'default': True, 'section': 'mqtt'},
}

# Een opgeslagen secret gaat alleen naar dezelfde bestemming. Wijzigt een van deze velden, dan moet
# het secret opnieuw ingevuld worden (anders kan het naar een andere server gestuurd worden).
SECRET_BOUND_TO = {
    'smtp_password': ['smtp_host', 'smtp_port', 'smtp_username', 'smtp_security'],   # ook geen downgrade naar onversleuteld
    'mqtt_password': ['mqtt_host', 'mqtt_port', 'mqtt_username', 'mqtt_tls'],
}

# Als een kanaal aan staat moeten deze velden ingevuld zijn
REQUIRED_WHEN = {
    'telegram_enabled': ['telegram_bot_token', 'telegram_chat_id'],
    'smtp_enabled': ['smtp_host', 'smtp_from', 'smtp_to'],
    'mqtt_enabled': ['mqtt_host'],
}

# Interne waarden: nooit naar de browser
INTERNAL_KEYS = ('admin_password_hash', 'secret_key')

_EMAIL_RE = re.compile(r'^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$')
_TELEGRAM_TOKEN_RE = re.compile(r'^\d{5,}:[A-Za-z0-9_-]{30,}$')
_CHAT_ID_RE = re.compile(r'^(-?\d{1,20}|@[A-Za-z][A-Za-z0-9_]{4,})$')
_TOPIC_RE = re.compile(r'^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$')
_CLIENT_ID_RE = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
_HOSTNAME_RE = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*$')

_cache = {}
_lock = threading.Lock()


def _connect():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER)')
    return conn


def coerce(key, raw):
    """Zet ruwe invoer (formulier of .env) om naar het type uit het schema. ValueError bij ongeldig."""
    kind = SCHEMA[key]['type']
    if kind is bool:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, list):  # dcc.Checklist
            return bool(raw)
        if str(raw).strip().lower() in ('true', '1', 'yes', 'on'):
            return True
        if str(raw).strip().lower() in ('false', '0', 'no', 'off', ''):
            return False
        raise ValueError(raw)
    if raw is None or str(raw).strip() == '':
        if SCHEMA[key].get('optional'):
            return ''
        raise ValueError(raw)
    if kind is float:
        return float(str(raw).replace(',', '.'))
    if kind is int:
        value = float(raw)
        if value != int(value):
            raise ValueError(raw)
        return int(value)
    value = str(raw).strip()
    return value.lower() if key == 'default_language' else value


def validate(key, value):
    """Geef een foutcode terug (vertaalbaar via translations.py) of None als de waarde geldig is."""
    spec = SCHEMA[key]
    if value == '' and spec.get('optional'):
        return None
    if 'choices' in spec and value not in spec['choices']:
        return 'err_choice'
    if 'min' in spec and not (spec['min'] <= value <= spec['max']):
        return 'err_range'
    if spec.get('check') == 'timezone':
        try:
            ZoneInfo(value)
        except Exception:
            return 'err_timezone'
    if spec.get('check') == 'email_list':
        if not all(_EMAIL_RE.match(a.strip()) for a in value.split(',')):
            return 'err_email'
    if spec.get('check') == 'telegram_token' and not _TELEGRAM_TOKEN_RE.match(value):
        return 'err_telegram_token'
    if spec.get('check') == 'chat_id' and not _CHAT_ID_RE.match(value):
        return 'err_chat_id'
    if spec.get('check') == 'topic' and (len(value) > 100 or not _TOPIC_RE.match(value)):
        return 'err_topic'
    if spec.get('check') == 'client_id' and not _CLIENT_ID_RE.match(value):
        return 'err_client_id'
    if spec.get('check') == 'host':
        try:
            ipaddress.ip_address(value)
        except ValueError:
            if len(value) > 253 or not _HOSTNAME_RE.match(value):
                return 'err_host'
    return None


def _initial_value(key):
    """Startwaarde voor een nieuwe installatie of upgrade: .env indien geldig, anders default."""
    spec = SCHEMA[key]
    raw = os.getenv(spec['env']) if 'env' in spec else None
    if raw is not None:
        try:
            value = coerce(key, raw)
            if validate(key, value) is None:
                return value
        except ValueError:
            pass
        print(f"Waarschuwing: ongeldige waarde in .env voor {spec['env']}={raw!r}, standaardwaarde gebruikt")
    return spec['default']


def load():
    """Lees alle instellingen in de cache; vul ontbrekende aan vanuit .env/default (migratie)."""
    with _lock:
        conn = _connect()
        try:
            stored = {k: json.loads(v) for k, v in conn.execute('SELECT key, value FROM settings')}
            missing = {k: _initial_value(k) for k in SCHEMA if k not in stored}
            if 'secret_key' not in stored:
                missing['secret_key'] = secrets.token_hex(32)
            if missing:
                now = int(time.time())
                conn.executemany('INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
                                 [(k, json.dumps(v), now) for k, v in missing.items()])
                conn.commit()
            _cache.clear()
            _cache.update(stored)
            _cache.update(missing)
        finally:
            conn.close()


def get(key):
    if not _cache:
        load()
    if key in SCHEMA:
        return _cache.get(key, SCHEMA[key]['default'])
    return _cache.get(key)


def public_values():
    """Alle bewerkbare instellingen, zonder interne/geheime waarden (secrets alleen of ze ingesteld zijn)."""
    return {k: bool(get(k)) if SCHEMA[k].get('secret') else get(k) for k in SCHEMA}


def _secret_destination_changed(secret, values):
    """True als een veld waaraan het opgeslagen secret gebonden is een andere waarde krijgt."""
    for field in SECRET_BOUND_TO.get(secret, []):
        if field in values:
            try:
                if coerce(field, values[field]) != get(field):
                    return True
            except (ValueError, TypeError):
                return True
    return False


def merged(values):
    """Opgeslagen instellingen met (ongevalideerde) formulierwaarden erover (voor de testknoppen).

    Een leeg secret = opgeslagen waarde, maar alleen als de bestemming niet gewijzigd is.
    """
    result = {k: get(k) for k in SCHEMA}
    for key, raw in values.items():
        if key in SCHEMA and not (SCHEMA[key].get('secret') and (raw is None or str(raw) == '')):
            try:
                result[key] = coerce(key, raw)
            except (ValueError, TypeError):
                pass
    for secret in SECRET_BOUND_TO:
        if not values.get(secret) and _secret_destination_changed(secret, values):
            result[secret] = ''
    return result


def save(values):
    """Valideer en sla instellingen op. Alles of niets: bij een fout wordt niets opgeslagen.

    Geeft {key: foutcode} terug; leeg dict = opgeslagen.
    """
    clean, errors = {}, {}
    for key, raw in values.items():
        if key not in SCHEMA:
            errors[key] = 'err_unknown'
            continue
        if SCHEMA[key].get('secret') and (raw is None or str(raw) == ''):
            continue  # write-only veld leeg gelaten: huidige waarde houden
        try:
            value = coerce(key, raw)
        except (ValueError, TypeError):
            errors[key] = 'err_required' if raw is None or str(raw).strip() == '' else 'err_type'
            continue
        error = validate(key, value)
        if error:
            errors[key] = error
        else:
            clean[key] = value
    if not errors:
        for secret in SECRET_BOUND_TO:
            if secret not in clean and get(secret) and _secret_destination_changed(secret, values):
                errors[secret] = 'err_secret_reenter'
    if not errors:
        result = {k: get(k) for k in SCHEMA}
        result.update(clean)
        for switch, fields in REQUIRED_WHEN.items():
            if result[switch]:
                for field in fields:
                    if result[field] == '':
                        errors[field] = 'err_required'
    if errors:
        return errors
    _write(clean)
    return {}


def set_internal(key, value):
    assert key in INTERNAL_KEYS
    _write({key: value})


def delete_internal(key):
    assert key in INTERNAL_KEYS
    with _lock:
        conn = _connect()
        try:
            conn.execute('DELETE FROM settings WHERE key = ?', (key,))
            conn.commit()
        finally:
            conn.close()
        _cache.pop(key, None)


def _write(values):
    if not _cache:
        load()
    with _lock:
        conn = _connect()
        try:
            now = int(time.time())
            conn.executemany('INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
                             [(k, json.dumps(v), now) for k, v in values.items()])
            conn.commit()
        finally:
            conn.close()
        _cache.update(values)


if __name__ == '__main__':
    if sys.argv[1:] == ['reset-password']:
        load()
        delete_internal('admin_password_hash')
        print("✓ Admin wachtwoord verwijderd. Open de Settings tab om een nieuw wachtwoord in te stellen.")
    else:
        print("Gebruik: python settings.py reset-password")
        sys.exit(1)
