"""Grenswaarden bewaken en meldingen versturen via Telegram en/of e-mail (SMTP).

- Regels: per grootheid een minimum en/of maximum, voor alle sensoren of één sensor.
  Een regel voor een sensor vervangt de globale regel voor dezelfde grootheid.
- Alarm pas na 'alert_delay_seconds' aanhoudende overschrijding; herstel pas binnen de
  grens min hysterese. Eén melding per alarm, optioneel een herstelmelding.
- Offline melding als een sensor 'alert_offline_minutes' geen geldige meting levert.
- Versturen gebeurt in een eigen thread met retries, zodat het uitlezen nooit vertraagt.
"""
import collections
import os
import queue
import smtplib
import sqlite3
import ssl
import threading
import time
from datetime import datetime
from email.message import EmailMessage

import requests

import devices
import settings
from settings import DB_FILE
from translations import TRANSLATIONS

METRICS = {  # grootheid -> (vertaalsleutel, eenheid, hysterese instelling)
    'temperature': ('temperature', '°C', 'alert_hysteresis_temp'),
    'humidity': ('humidity', '%', 'alert_hysteresis_humidity'),
    'dewpoint': ('dewpoint', '°C', 'alert_hysteresis_temp'),
    'absolute_humidity': ('abs_humidity', 'g/m³', 'alert_hysteresis_humidity'),
}

MAX_RETRY_DELAY = 3600
SEND_TIMEOUT = 15

_lock = threading.Lock()
_rules_cache = None           # [regel dicts], None = opnieuw laden
_state = {}                   # (device_id, metric) -> {'phase', 'since', 'kind', 'limit'}
_offline = set()              # device ids waarvoor een offline melding is verstuurd
_first_seen = {}              # device id -> eerste keer gezien door de offline controle (nieuwe sensoren)
_outbox = queue.Queue()
log = collections.deque(maxlen=20)   # laatste meldingen: {'time', 'channel', 'text', 'ok', 'error'}


# --- regels ------------------------------------------------------------------

def _connect():
    db_dir = os.path.dirname(DB_FILE)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute('''CREATE TABLE IF NOT EXISTS alert_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT, device_id INTEGER, metric TEXT NOT NULL,
        min_value REAL, max_value REAL, enabled INTEGER NOT NULL)''')
    return conn


def _number(raw):
    """Leeg = None, anders float. ValueError bij ongeldige invoer."""
    if raw is None or str(raw).strip() == '':
        return None
    return float(str(raw).replace(',', '.'))


def validate_rules(rows):
    """Valideer regels uit de UI. Geeft (schone regels, {rij: {veld: foutcode}})."""
    device_ids = {d['id'] for d in devices.list_devices()}
    clean, errors, seen = [], {}, set()
    for index, row in enumerate(rows):
        row_errors = {}
        try:
            scope = int(row.get('scope') or 0)
        except (TypeError, ValueError):
            scope = -1
        if scope != 0 and scope not in device_ids:
            row_errors['scope'] = 'err_choice'
        metric = row.get('metric')
        if metric not in METRICS:
            row_errors['metric'] = 'err_choice'
        values = {}
        for field in ('min_value', 'max_value'):
            try:
                values[field] = _number(row.get(field))
            except (TypeError, ValueError):
                row_errors[field] = 'err_type'
        if not row_errors:
            if values['min_value'] is None and values['max_value'] is None:
                row_errors['min_value'] = 'err_rule_empty'
            elif values['min_value'] is not None and values['max_value'] is not None \
                    and values['min_value'] >= values['max_value']:
                row_errors['max_value'] = 'err_min_max'
            elif (scope, metric) in seen:
                row_errors['metric'] = 'err_duplicate'
            seen.add((scope, metric))
        if row_errors:
            errors[index] = row_errors
        clean.append({'device_id': scope or None, 'metric': metric, **values,
                      'enabled': str(row.get('enabled', 'true')).lower() in ('true', '1')})
    return clean, errors


def save_rules(rows):
    """Sla regels op (alles of niets). Geeft fouten terug; leeg dict = opgeslagen."""
    global _rules_cache
    clean, errors = validate_rules(rows)
    if errors:
        return errors
    with _lock:
        conn = _connect()
        try:
            conn.execute('BEGIN')
            conn.execute('DELETE FROM alert_rules')
            conn.executemany('INSERT INTO alert_rules (device_id, metric, min_value, max_value, enabled) VALUES (?, ?, ?, ?, ?)',
                             [(r['device_id'], r['metric'], r['min_value'], r['max_value'], int(r['enabled'])) for r in clean])
            conn.commit()
        finally:
            conn.close()
        _rules_cache = None
        _state.clear()   # nieuwe grenzen: opnieuw beoordelen
    return {}


def load_rules():
    """Alle regels; regels van verwijderde sensoren worden genegeerd."""
    global _rules_cache
    with _lock:
        if _rules_cache is None:
            conn = _connect()
            conn.row_factory = sqlite3.Row
            try:
                rows = [dict(r) for r in conn.execute('SELECT * FROM alert_rules ORDER BY id')]
            finally:
                conn.close()
            device_ids = {d['id'] for d in devices.list_devices()}
            _rules_cache = [{**r, 'enabled': bool(r['enabled'])} for r in rows
                            if r['device_id'] is None or r['device_id'] in device_ids]
        return list(_rules_cache)


def effective_rules(device_id):
    """{grootheid: regel} voor één sensor: sensorregel vervangt globale regel."""
    rules = {}
    for rule in load_rules():
        if rule['enabled'] and rule['device_id'] is None:
            rules.setdefault(rule['metric'], rule)
    for rule in load_rules():
        if rule['device_id'] == device_id:
            if rule['enabled']:
                rules[rule['metric']] = rule
            else:
                rules.pop(rule['metric'], None)   # uitgeschakelde sensorregel = globale regel uit voor deze sensor
    return rules


# --- bewaking ------------------------------------------------------------------

def _t():
    return TRANSLATIONS.get(settings.get('default_language')) or TRANSLATIONS['en']


def _now_text(ts=None):
    return datetime.fromtimestamp(ts or time.time()).strftime('%d-%m-%Y %H:%M')


def evaluate(device, values, now=None):
    """Beoordeel een nieuwe meting. values: {grootheid: waarde}. Mag nooit een uitzondering gooien."""
    try:
        now = now or time.time()
        _check_online(device, now)
        delay = settings.get('alert_delay_seconds')
        for metric, rule in effective_rules(device['id']).items():
            if metric in values:
                _evaluate_metric(device, metric, values[metric], rule, delay, now)
    except Exception as e:
        print(f"Alarm evaluatie fout ({device.get('name')}): {e}")


def _evaluate_metric(device, metric, value, rule, delay, now):
    key = (device['id'], metric)
    state = _state.setdefault(key, {'phase': 'normal'})
    hysteresis = settings.get(METRICS[metric][2])
    if rule['max_value'] is not None and value > rule['max_value']:
        breach = ('high', rule['max_value'])
    elif rule['min_value'] is not None and value < rule['min_value']:
        breach = ('low', rule['min_value'])
    else:
        breach = None

    if state['phase'] == 'alarm':
        limit, kind = state['limit'], state['kind']
        recovered = value <= limit - hysteresis if kind == 'high' else value >= limit + hysteresis
        if recovered and breach is None:
            _state[key] = {'phase': 'normal'}
            if settings.get('alert_notify_recovery'):
                _notify('alert_recovered', device, metric, value, limit)
        return
    if breach is None:
        _state[key] = {'phase': 'normal'}
        return
    if state['phase'] != 'pending' or state['kind'] != breach[0]:
        _state[key] = state = {'phase': 'pending', 'since': now, 'kind': breach[0], 'limit': breach[1]}
    if now - state['since'] >= delay:
        _state[key] = {'phase': 'alarm', 'kind': breach[0], 'limit': breach[1]}
        _notify('alert_high' if breach[0] == 'high' else 'alert_low', device, metric, value, breach[1])


def _notify(template, device, metric, value, limit):
    t = _t()
    name_key, unit, _ = METRICS[metric]
    send(t[template].format(device=device['name'], metric=t[name_key], value=f'{value:.1f}', limit=f'{limit:.1f}',
                            unit=unit, time=_now_text()))


def _check_online(device, now):
    if device['id'] in _offline:
        _offline.discard(device['id'])
        if settings.get('alert_offline_minutes'):
            send(_t()['alert_online'].format(device=device['name'], time=_now_text(now)))


def check_offline(now=None):
    """Meld sensoren die te lang geen geldige meting hebben (periodiek aangeroepen)."""
    minutes = settings.get('alert_offline_minutes')
    if not minutes:
        return
    now = now or time.time()
    for device in devices.list_devices(enabled_only=True):
        # Nog nooit gemeten (net toegevoegd of net gestart): tellen vanaf het moment dat we de sensor zien
        last = devices.status(device['id']).get('ok_at') or _first_seen.setdefault(device['id'], now)
        if now - last >= minutes * 60 and device['id'] not in _offline:
            _offline.add(device['id'])
            send(_t()['alert_offline'].format(device=device['name'], time=_now_text(last)))


# --- versturen -------------------------------------------------------------------

def _hide_secrets(text, config):
    """Tokens/wachtwoorden nooit in logs of UI (requests foutmeldingen bevatten de URL met token)."""
    for key in ('telegram_bot_token', 'smtp_password'):
        if config.get(key):
            text = text.replace(config[key], '***')
    return text


def send_telegram(text, config):
    response = requests.post(f"https://api.telegram.org/bot{config['telegram_bot_token']}/sendMessage",
                             json={'chat_id': config['telegram_chat_id'], 'text': text}, timeout=SEND_TIMEOUT)
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not response.ok or not body.get('ok'):
        raise RuntimeError(body.get('description') or f'HTTP {response.status_code}')


def send_email(text, config):
    message = EmailMessage()
    message['Subject'] = f"XY-MD02: {text.splitlines()[0][:100]}"
    message['From'] = config['smtp_from']
    message['To'] = config['smtp_to']
    message.set_content(text)
    context = ssl.create_default_context()
    if config['smtp_security'] == 'ssl':
        server = smtplib.SMTP_SSL(config['smtp_host'], config['smtp_port'], timeout=SEND_TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(config['smtp_host'], config['smtp_port'], timeout=SEND_TIMEOUT)
    with server:
        if config['smtp_security'] == 'starttls':
            server.starttls(context=context)
        if config['smtp_username']:
            server.login(config['smtp_username'], config['smtp_password'])
        server.send_message(message)


CHANNELS = {'telegram': send_telegram, 'email': send_email}


def send_now(channel, text, config):
    """Verstuur direct (testknop). Geeft None of een foutmelding (zonder secrets)."""
    try:
        CHANNELS[channel](text, config)
        return None
    except Exception as e:
        return _hide_secrets(str(e) or type(e).__name__, config)


def send(text):
    """Zet een melding klaar voor alle ingeschakelde kanalen."""
    for channel, enabled in (('telegram', 'telegram_enabled'), ('email', 'smtp_enabled')):
        if settings.get(enabled):
            _outbox.put({'channel': channel, 'text': text, 'attempt': 0, 'next_try': 0})


class Notifier(threading.Thread):
    """Verstuurt meldingen met retries (exponentieel, max 1 uur) en controleert offline sensoren."""

    def __init__(self):
        super().__init__(daemon=True, name='notifier')
        self.waiting = []

    def run(self):
        last_offline_check = 0
        while True:
            try:
                self.waiting.append(_outbox.get(timeout=5))
            except queue.Empty:
                pass
            now = time.time()
            if now - last_offline_check >= 30:
                check_offline(now)
                last_offline_check = now
            due = [m for m in self.waiting if m['next_try'] <= now]
            self.waiting = [m for m in self.waiting if m['next_try'] > now]
            for item in due:
                self.deliver(item)

    def deliver(self, item):
        config = {k: settings.get(k) for k in settings.SCHEMA}
        error = send_now(item['channel'], item['text'], config)
        log.appendleft({'time': time.time(), 'channel': item['channel'], 'text': item['text'], 'ok': error is None,
                        'error': error, 'attempt': item['attempt'] + 1})
        if error:
            # Geen foutdetails in de console/journal: die kunnen gegevens van de server bevatten;
            # de (opgeschoonde) foutmelding staat in het meldingslog in Settings
            print(f"✗ Melding via {item['channel']} mislukt (poging {item['attempt'] + 1}), zie Settings > Meldingen")
            item['attempt'] += 1
            item['next_try'] = time.time() + min(30 * 2 ** (item['attempt'] - 1), MAX_RETRY_DELAY)
            self.waiting.append(item)


def start():
    notifier = Notifier()
    notifier.start()
    return notifier
