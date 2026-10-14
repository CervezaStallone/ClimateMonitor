"""Tests voor instellingen en beveiliging. Uitvoeren: python test_app.py (ook in CI)."""
import os
import sys
import tempfile
import time
import traceback

# Tijdelijke database en .env-waarden, vóór het importeren van de modules
_tmp = tempfile.mkdtemp()
os.environ['DATABASE_FILE'] = os.path.join(_tmp, 'test.db')
os.environ['TIMEZONE'] = 'Europe/Madrid'
os.environ['DATA_RETENTION_DAYS'] = 'veel'      # ongeldig -> standaardwaarde
os.environ['DEBUG_LOGGING'] = 'True'
os.environ['APP_HOST'] = '127.0.0.1'            # wordt bewust niet overgenomen
os.environ['MODBUS_PORT'] = '/dev/ttyTEST0'
os.environ['MODBUS_SLAVE_ID'] = '7'
os.environ['MODBUS_PARITY'] = 'X'               # ongeldig -> standaardwaarde

import queue  # noqa: E402
import sqlite3  # noqa: E402
from datetime import datetime  # noqa: E402

import minimalmodbus  # noqa: E402
import serial  # noqa: E402
from flask import Flask  # noqa: E402

import alerts  # noqa: E402
import auth  # noqa: E402
import database  # noqa: E402
import devices  # noqa: E402
import modbus_reader  # noqa: E402
import settings  # noqa: E402
from translations import TRANSLATIONS  # noqa: E402

TRANSLATIONS_NL = TRANSLATIONS['nl']


def fresh_settings():
    """Lege database en cache, zoals een eerste start."""
    if os.path.exists(settings.DB_FILE):
        os.remove(settings.DB_FILE)
    settings._cache.clear()
    settings.load()
    devices._status.clear()
    alerts._rules_cache = None
    alerts._state.clear()
    alerts._offline.clear()
    alerts._first_seen.clear()
    while not alerts._outbox.empty():
        alerts._outbox.get_nowait()


def make_client():
    app = Flask(__name__)
    auth.init_app(app)
    app.add_url_rule('/', 'index', lambda: 'dashboard')
    app.add_url_rule('/_dash-update-component', 'dash', lambda: 'data', methods=['POST'])
    auth._failures.clear()
    auth._sessions.clear()
    return app.test_client()


# --- settings -------------------------------------------------------------

def test_migration_from_env():
    fresh_settings()
    assert settings.get('timezone') == 'Europe/Madrid'
    assert settings.get('data_retention_days') == 0
    assert settings.get('debug_logging') is True
    assert settings.get('app_host') == '0.0.0.0'
    assert settings.get('default_language') == 'en'
    assert len(settings.get('secret_key')) == 64


def test_stored_values_win_over_env():
    fresh_settings()
    assert settings.save({'timezone': 'Asia/Tokyo'}) == {}
    settings._cache.clear()
    settings.load()
    assert settings.get('timezone') == 'Asia/Tokyo'


def test_validation():
    fresh_settings()
    assert settings.save({'timezone': 'Mars/Base'}) == {'timezone': 'err_timezone'}
    assert settings.save({'data_retention_days': -1}) == {'data_retention_days': 'err_range'}
    assert settings.save({'data_retention_days': '1.5'}) == {'data_retention_days': 'err_type'}
    assert settings.save({'app_port': None}) == {'app_port': 'err_required'}
    assert settings.save({'default_language': 'xx'}) == {'default_language': 'err_choice'}
    assert settings.save({'app_host': 'bad host!'}) == {'app_host': 'err_host'}
    assert settings.save({'admin_password_hash': 'x'}) == {'admin_password_hash': 'err_unknown'}
    assert settings.save({'app_host': 'sensor-01.local', 'app_port': '8080', 'default_language': 'ES'}) == {}
    assert settings.get('app_port') == 8080 and settings.get('default_language') == 'es'
    assert settings.save({'debug_logging': []}) == {} and settings.get('debug_logging') is False
    assert settings.save({'debug_logging': ['on']}) == {} and settings.get('debug_logging') is True


def test_save_is_all_or_nothing():
    fresh_settings()
    errors = settings.save({'timezone': 'Asia/Tokyo', 'app_port': 99999})
    assert errors == {'app_port': 'err_range'}
    assert settings.get('timezone') == 'Europe/Madrid'
    settings._cache.clear()
    settings.load()
    assert settings.get('timezone') == 'Europe/Madrid'


def test_public_values_hide_secrets():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    public = settings.public_values()
    assert 'admin_password_hash' not in public and 'secret_key' not in public


def test_reset_password_keeps_other_settings():
    fresh_settings()
    settings.save({'timezone': 'Asia/Tokyo'})
    auth.set_password('geheim123', 'geheim123')
    settings.delete_internal('admin_password_hash')
    settings._cache.clear()
    settings.load()
    assert not auth.has_password()
    assert settings.get('timezone') == 'Asia/Tokyo'


# --- auth -----------------------------------------------------------------

def test_password_rules():
    fresh_settings()
    assert auth.set_password('kort', 'kort') == 'err_password_short'
    assert auth.set_password('geheim123', 'geheim124') == 'err_password_mismatch'
    assert auth.set_password('geheim123', 'geheim123') is None
    assert 'geheim123' not in settings.get('admin_password_hash')
    assert auth.change_password('fout', 'nieuw12345', 'nieuw12345') == 'err_password_wrong'
    assert auth.change_password('geheim123', 'nieuw12345', 'nieuw12345') is None


def test_setup_then_login_flow():
    fresh_settings()
    client = make_client()
    assert client.get('/login').status_code == 302          # nog geen wachtwoord -> /setup
    r = client.post('/setup', data={'password': 'geheim123', 'repeat': 'geheim123', 'next': '/?tab=settings'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/?tab=settings')
    assert client.get('/setup').status_code == 302          # setup kan maar één keer
    client.get('/logout')
    assert client.post('/login', data={'password': 'fout'}).status_code == 401
    r = client.post('/login', data={'password': 'geheim123', 'next': '/\t/evil.example'})
    assert r.status_code == 302 and r.headers['Location'] == '/'   # geen open redirect


def test_login_throttling():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    client = make_client()
    for _ in range(auth.MAX_FAILURES):
        assert client.post('/login', data={'password': 'fout'}).status_code == 401
    assert client.post('/login', data={'password': 'geheim123'}).status_code == 429


def test_guard_settings_mode_keeps_dashboard_public():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    client = make_client()
    assert client.get('/').status_code == 200
    assert client.post('/_dash-update-component').status_code == 200


def test_guard_app_mode_requires_login():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    settings.save({'auth_mode': 'app'})
    client = make_client()
    r = client.get('/')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    assert client.post('/_dash-update-component').status_code == 401
    client.post('/login', data={'password': 'geheim123'})
    assert client.get('/').status_code == 200
    assert client.post('/_dash-update-component').status_code == 200


def test_session_expires():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    settings.save({'auth_mode': 'app', 'session_timeout_minutes': 5})
    client = make_client()
    client.post('/login', data={'password': 'geheim123'})
    for entry in auth._sessions.values():
        entry['last_seen'] = time.time() - 6 * 60   # server-side, de client kan dit niet verlengen
    assert client.get('/').status_code == 302


def test_logout_revokes_copied_cookie():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    settings.save({'auth_mode': 'app'})
    client = make_client()
    client.post('/login', data={'password': 'geheim123'})
    with client.session_transaction() as sess:
        stolen = dict(sess)
    client.get('/logout')
    with client.session_transaction() as sess:
        sess.update(stolen)
    assert client.get('/').status_code == 302


def test_password_change_revokes_other_sessions():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    settings.save({'auth_mode': 'app'})
    client, other = make_client(), None
    app = client.application
    other = app.test_client()
    client.post('/login', data={'password': 'geheim123'})
    other.post('/login', data={'password': 'geheim123'})
    with app.test_request_context():
        from flask import session
        with client.session_transaction() as sess:
            session['sid'] = sess['sid']
        assert auth.change_password('geheim123', 'nieuw12345', 'nieuw12345') is None
    assert client.get('/').status_code == 200
    assert other.get('/').status_code == 302


def test_reset_password_revokes_sessions():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    settings.save({'auth_mode': 'app'})
    client = make_client()
    client.post('/login', data={'password': 'geheim123'})
    settings.delete_internal('admin_password_hash')
    auth.set_password('anders1234', 'anders1234')        # nieuw wachtwoord via /setup
    assert client.get('/').status_code == 302


def test_global_cap_blocks_new_clients_but_not_trusted_browser():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    admin = make_client()
    admin.post('/login', data={'password': 'geheim123'})   # eerder ingelogd: vertrouwde browser
    admin.get('/logout')
    now = time.time()
    for i in range(auth.MAX_FAILURES_GLOBAL):              # aanval vanaf veel adressen
        auth._failures[f'10.0.{i // 250}.{i % 250}'] = [now]
    attacker = admin.application.test_client()
    assert attacker.post('/login', data={'password': 'geheim123'}).status_code == 429   # nieuwe browser: geblokkeerd
    assert admin.post('/login', data={'password': 'geheim123'}).status_code == 302     # vertrouwde browser: ok
    forged = admin.application.test_client()
    forged.set_cookie(auth.TRUSTED_COOKIE, 'vervalst')
    assert forged.post('/login', data={'password': 'geheim123'}).status_code == 429


def test_stolen_trusted_cookie_is_limited_across_addresses():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    admin = make_client()
    admin.post('/login', data={'password': 'geheim123'})
    stolen = admin.get_cookie(auth.TRUSTED_COOKIE).value
    now = time.time()
    for i in range(auth.MAX_FAILURES_GLOBAL):
        auth._failures[f'10.0.{i // 250}.{i % 250}'] = [now]
    codes = []
    for i in range(auth.MAX_FAILURES + 2):                  # elke poging vanaf een ander adres
        attacker = admin.application.test_client()
        attacker.set_cookie(auth.TRUSTED_COOKIE, stolen)
        codes.append(attacker.post('/login', data={'password': 'fout'},
                                   environ_base={'REMOTE_ADDR': f'198.51.100.{i}'}).status_code)
    assert codes[:auth.MAX_FAILURES] == [401] * auth.MAX_FAILURES and set(codes[auth.MAX_FAILURES:]) == {429}


def test_trusted_cookie_invalid_after_password_change():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    admin = make_client()
    admin.post('/login', data={'password': 'geheim123'})
    auth.set_password('nieuw12345', 'nieuw12345')
    with admin.application.test_request_context(headers={'Cookie': f"{auth.TRUSTED_COOKIE}={admin.get_cookie(auth.TRUSTED_COOKIE).value}"}):
        assert auth._trusted_browser_id() is None


def test_login_racing_password_change_is_not_upgraded():
    fresh_settings()
    auth.set_password('geheim123', 'geheim123')
    settings.save({'auth_mode': 'app'})
    client = make_client()
    old_hash = settings.get('admin_password_hash')
    auth.set_password('nieuw12345', 'nieuw12345')          # wijziging tussen controle en sessiestart
    with client.application.test_request_context():
        auth._start_session(old_hash)
        from flask import session
        assert not auth.is_logged_in()
        assert session.get('sid') not in auth._sessions


def test_no_open_redirect():
    for target in ['//evil.example', '/\\evil.example', '/\t/evil.example', 'https://evil.example', 'javascript:alert(1)',
                   '/\n/evil.example', ' /x']:
        assert auth._safe_next(target) == '/', target
    assert auth._safe_next('/?tab=settings') == '/?tab=settings'


def test_ipv6_clients_grouped_per_64():
    assert auth._client_key('2001:db8::1') == auth._client_key('2001:db8::ffff:1234')
    assert auth._client_key('2001:db8:0:1::1') != auth._client_key('2001:db8::1')
    assert auth._client_key('::ffff:192.0.2.7') == '192.0.2.7'


# --- bussen en devices ------------------------------------------------------

def bus(name='Bus 1', port='/dev/ttyUSB0', **extra):
    return {'name': name, 'port': port, 'baudrate': 9600, 'bytesize': 8, 'parity': 'N', 'stopbits': 1,
            'timeout': 0.5, 'enabled': True, **extra}


def device(name='Sensor 1', bus_name='Bus 1', slave_id=1, **extra):
    return {'name': name, 'bus': bus_name, 'slave_id': slave_id, 'function_code': 4, 'register_temp': 1,
            'register_humidity': 2, 'scale_temp': 0.1, 'scale_humidity': 0.1, 'enabled': True, **extra}


def test_devices_migration_from_env():
    fresh_settings()
    devices.init_devices()
    buses, devs = devices.load_config()
    assert len(buses) == 1 and buses[0]['port'] == '/dev/ttyTEST0' and buses[0]['parity'] == 'N'
    assert len(devs) == 1 and devs[0]['slave_id'] == 7 and devs[0]['name'] == 'Sensor 1' and devs[0]['bus'] == 'Bus 1'
    devices.init_devices()                                   # tweede start: niets dubbel
    assert len(devices.load_config()[1]) == 1


def test_devices_validation():
    fresh_settings()
    ok = devices.save_config([bus(), bus('Bus 2', '/dev/ttyUSB1')],
                             [device(), device('Sensor 2', slave_id=2), device('Sensor 3', 'Bus 2', slave_id=1)])
    assert ok == {}                                          # zelfde slave id op andere bus mag
    errors = devices.save_config([bus(), bus('bus 1', '/dev/ttyUSB0', baudrate=1234)],
                                 [device(), device('SENSOR 1', slave_id=1), device('X', 'Bus 9'), device('Y', slave_id=300)])
    assert errors['buses'] == {1: {'name': 'err_duplicate', 'port': 'err_duplicate', 'baudrate': 'err_choice'}}
    assert errors['devices'][1] == {'name': 'err_duplicate', 'slave_id': 'err_duplicate'}
    assert errors['devices'][2] == {'bus': 'err_bus_unknown'}
    assert errors['devices'][3] == {'slave_id': 'err_range'}
    assert len(devices.load_config()[1]) == 3                # niets opgeslagen bij fouten
    assert devices.save_config([bus()], [device(scale_temp=0)])['devices'][0] == {'scale_temp': 'err_range'}
    assert devices.save_config([bus()], [device(name='')])['devices'][0] == {'name': 'err_required'}


def test_devices_ids_stable_on_rename_and_swap():
    fresh_settings()
    devices.save_config([bus()], [device('A', slave_id=1), device('B', slave_id=2)])
    buses, devs = devices.load_config()
    a, b = devs
    # Namen en slave ids omwisselen, bus hernoemen: ids blijven, geen UNIQUE fout
    assert devices.save_config([{**buses[0], 'name': 'Hal'}],
                               [{**a, 'name': 'B', 'slave_id': 2, 'bus': 'Hal'},
                                {**b, 'name': 'A', 'slave_id': 1, 'bus': 'Hal'}]) == {}
    after = {d['id']: d for d in devices.load_config()[1]}
    assert after[a['id']]['name'] == 'B' and after[b['id']]['name'] == 'A' and after[a['id']]['bus'] == 'Hal'
    version = devices.version()
    assert devices.save_config(devices.load_config()[0], [after[a['id']]]) == {}   # B verwijderd
    assert [d['id'] for d in devices.load_config()[1]] == [a['id']] and devices.version() == version + 1


def test_measurement_tables_get_device_column():
    fresh_settings()
    conn = sqlite3.connect(settings.DB_FILE)
    conn.execute('CREATE TABLE measurements_20250101 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL, '
                 'temperature REAL NOT NULL, humidity REAL NOT NULL, dewpoint REAL, absolute_humidity REAL)')
    conn.execute('INSERT INTO measurements_20250101 (timestamp, temperature, humidity) VALUES (1735725600, 20.5, 50)')
    conn.commit()
    conn.close()
    database.init_database()
    conn = sqlite3.connect(settings.DB_FILE)
    assert conn.execute('SELECT device_id FROM measurements_20250101').fetchone() == (1,)
    conn.execute('INSERT INTO measurements_20250101 (timestamp, temperature, humidity, device_id) VALUES (1735725601, 9, 9, 2)')
    query, _ = database.build_union_query(conn.cursor(), ['timestamp', 'temperature'], device_id=2)
    assert conn.execute(query).fetchall() == [(1735725601, 9.0)]
    conn.close()


class FakeInstrument:
    """Sensor met signed 16-bit registers; raise = geen antwoord."""

    def __init__(self, registers=None, fail=False):
        self.registers, self.fail = registers or {}, fail
        self.serial = type('S', (), {'close': lambda self: None})()

    def read_register(self, register, decimals, functioncode, signed=False):
        assert signed and decimals == 0
        if self.fail:
            raise minimalmodbus.NoResponseError('No communication with the instrument (no answer)')
        return self.registers[register]


def test_poller_reads_signed_scaled_values_and_isolates_failures():
    fresh_settings()
    q = queue.Queue()
    dev_ok = {**device('Koelcel'), 'id': 1}
    dev_bad = {**device('Kapot', slave_id=2), 'id': 2}
    dev_range = {**device('Raar', slave_id=3), 'id': 3}
    poller = modbus_reader.BusPoller({**bus(), 'id': 1}, [dev_bad, dev_ok, dev_range], q)
    poller.poll(FakeInstrument(fail=True), dev_bad)
    poller.poll(FakeInstrument({1: -55, 2: 873}), dev_ok)          # -5.5 °C, 87.3 %
    poller.poll(FakeInstrument({1: 2000, 2: 500}), dev_range)       # 200 °C: buiten bereik
    row = q.get_nowait()
    assert row[1:3] == (-5.5, 87.3) and row[5] == 1 and q.empty()
    assert devices.status(1)['temperature'] == -5.5 and devices.status(1)['error'] is None
    assert 'no answer' in devices.status(2)['error'] and 'out of range' in devices.status(3)['error']


def test_poller_survives_missing_interface():
    fresh_settings()
    calls = []

    def missing_port(bus_cfg, dev):
        calls.append(1)
        raise serial.SerialException('could not open port /dev/ttyUSB9')
    poller = modbus_reader.BusPoller({**bus(), 'id': 1}, [{**device(), 'id': 1}], queue.Queue(), missing_port)
    poller.start()
    time.sleep(1.5)
    poller.stop()
    poller.join(timeout=3)
    assert not poller.is_alive() and len(calls) >= 2           # opnieuw geprobeerd, thread niet gecrasht
    assert 'could not open port' in devices.status(1)['error']


def test_writer_stores_device_and_splits_days():
    fresh_settings()
    database.init_database()
    writer = modbus_reader.Writer(queue.Queue())
    day1, day2 = int(datetime(2026, 10, 13, 23, 59, 59).timestamp()), int(datetime(2026, 10, 14, 0, 0, 1).timestamp())
    writer.buffer = [(day1, 20.0, 50.0, 10.0, 8.6, 3), (day2, 21.0, 51.0, 11.2, 9.1, 4)]
    conn = sqlite3.connect(settings.DB_FILE)
    writer.flush(conn)
    assert writer.buffer == []
    assert conn.execute('SELECT device_id FROM measurements_20261013').fetchall() == [(3,)]
    assert conn.execute('SELECT device_id FROM measurements_20261014').fetchall() == [(4,)]
    conn.close()


def test_settings_callbacks_require_login():
    """Settings callbacks geven zonder login geen configuratie, poorten of status terug."""
    import dash
    import settings_ui
    fresh_settings()
    devices.init_devices()
    auth.set_password('geheim123', 'geheim123')
    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    auth.init_app(app.server)
    settings_ui.register_settings_callbacks(app)
    callbacks = {}
    for entry in app.callback_map.values():
        fn = getattr(entry['callback'], '__wrapped__', None)
        if fn:
            callbacks[fn.__name__] = fn
    rows = [bus()]
    with app.server.test_request_context():
        assert callbacks['add_bus'](1, rows) is dash.no_update
        assert callbacks['add_device'](1, [], rows) is dash.no_update
        assert callbacks['update_bus_choices'](rows, {}) is dash.no_update
        assert callbacks['refresh_device_status'](3, 'settings', 'nl') is dash.no_update
        assert all(v is dash.no_update for v in callbacks['show_modbus_errors'](1, rows, [], 'nl', []))
        errors, status, _ = callbacks['save_settings'](1, [], 'nl', rows, [], [])
        assert errors is dash.no_update and status == TRANSLATIONS_NL['settings_locked']
        assert callbacks['change_password'](1, 'x', 'y', 'y', 'nl')[0] == TRANSLATIONS_NL['settings_locked']
        assert 'admin' not in str(callbacks['show_settings']('settings', 'nl'))   # alleen het inlogscherm
        assert callbacks['add_rule'](1, []) is dash.no_update
        assert callbacks['send_test'](1, 0, [], 'nl') == TRANSLATIONS_NL['settings_locked']
        assert callbacks['refresh_alert_log'](5, 'settings', 'nl') is dash.no_update
    assert set(callbacks) >= {'add_bus', 'add_device', 'update_bus_choices', 'refresh_device_status',
                              'show_modbus_errors', 'save_settings', 'change_password', 'show_settings',
                              'add_rule', 'send_test', 'refresh_alert_log'}


# --- meldingen -----------------------------------------------------------------

TOKEN = '123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw1'


def outbox_texts():
    texts = []
    while not alerts._outbox.empty():
        texts.append(alerts._outbox.get_nowait()['text'])
    return texts


def setup_alerts(rules):
    fresh_settings()
    devices.save_config([bus()], [device('Koelcel'), device('Kas', slave_id=2)])
    assert settings.save({'telegram_enabled': True, 'telegram_bot_token': TOKEN, 'telegram_chat_id': '-1001234',
                          'alert_delay_seconds': 60, 'default_language': 'nl'}) == {}
    assert alerts.save_rules(rules) == {}
    return {d['name']: d for d in devices.load_config()[1]}


def test_notification_settings_secrets_and_required_fields():
    fresh_settings()
    assert settings.save({'telegram_enabled': True}) == {'telegram_bot_token': 'err_required', 'telegram_chat_id': 'err_required'}
    assert settings.save({'telegram_bot_token': 'geen-token'}) == {'telegram_bot_token': 'err_telegram_token'}
    assert settings.save({'smtp_to': 'a@b.nl, fout'}) == {'smtp_to': 'err_email'}
    assert settings.save({'telegram_enabled': True, 'telegram_bot_token': TOKEN, 'telegram_chat_id': '@mijnkanaal'}) == {}
    assert settings.public_values()['telegram_bot_token'] is True          # alleen "ingesteld", nooit de waarde
    assert settings.save({'telegram_bot_token': ''}) == {}                  # leeg = houden
    assert settings.get('telegram_bot_token') == TOKEN
    assert settings.merged({'telegram_bot_token': '', 'telegram_chat_id': '42'})['telegram_bot_token'] == TOKEN


def test_rule_validation_and_override():
    names = setup_alerts([{'scope': 0, 'metric': 'humidity', 'max_value': 70, 'enabled': 'true'}])
    kas = names['Kas']['id']
    assert alerts.validate_rules([{'scope': 0, 'metric': 'humidity'}])[1] == {0: {'min_value': 'err_rule_empty'}}
    assert alerts.validate_rules([{'scope': 0, 'metric': 'humidity', 'min_value': 9, 'max_value': 5}])[1] \
        == {0: {'max_value': 'err_min_max'}}
    assert alerts.validate_rules([{'scope': 99, 'metric': 'humidity', 'max_value': 5}])[1] == {0: {'scope': 'err_choice'}}
    assert alerts.validate_rules([{'scope': 0, 'metric': 'humidity', 'max_value': 5}] * 2)[1] == {1: {'metric': 'err_duplicate'}}
    assert alerts.save_rules([{'scope': 0, 'metric': 'humidity', 'max_value': 70, 'enabled': 'true'},
                              {'scope': kas, 'metric': 'humidity', 'max_value': 90, 'enabled': 'true'}]) == {}
    assert alerts.effective_rules(kas)['humidity']['max_value'] == 90
    assert alerts.effective_rules(names['Koelcel']['id'])['humidity']['max_value'] == 70


def test_alarm_delay_single_alert_and_recovery():
    names = setup_alerts([{'scope': 0, 'metric': 'temperature', 'max_value': 8, 'enabled': 'true'}])
    cel = names['Koelcel']
    alerts.evaluate(cel, {'temperature': 9.0}, now=1000)
    alerts.evaluate(cel, {'temperature': 7.0}, now=1030)     # kort boven grens: geen melding
    alerts.evaluate(cel, {'temperature': 9.0}, now=1040)
    alerts.evaluate(cel, {'temperature': 9.5}, now=1080)     # nog geen 60 s
    assert outbox_texts() == []
    alerts.evaluate(cel, {'temperature': 9.6}, now=1100)     # 60 s aanhoudend: alarm
    alerts.evaluate(cel, {'temperature': 10.0}, now=1200)    # geen herhaling
    alerts.evaluate(cel, {'temperature': 7.8}, now=1300)     # binnen grens maar niet voorbij hysterese (0.5)
    texts = outbox_texts()
    assert len(texts) == 1 and 'Koelcel' in texts[0] and '9.6' in texts[0] and 'maximum van 8.0' in texts[0]
    alerts.evaluate(cel, {'temperature': 7.4}, now=1400)     # hersteld
    texts = outbox_texts()
    assert len(texts) == 1 and 'weer normaal' in texts[0]


def test_recovery_message_can_be_disabled_and_low_limit():
    names = setup_alerts([{'scope': 0, 'metric': 'humidity', 'min_value': 30, 'enabled': 'true'}])
    settings.save({'alert_notify_recovery': [], 'alert_delay_seconds': 0})
    kas = names['Kas']
    alerts.evaluate(kas, {'humidity': 25.0}, now=1)
    assert 'minimum van 30.0' in outbox_texts()[0]
    alerts.evaluate(kas, {'humidity': 40.0}, now=2)
    assert outbox_texts() == []


def test_offline_and_online_messages():
    names = setup_alerts([])
    settings.save({'alert_offline_minutes': 5})
    cel = names['Koelcel']
    devices.report_ok(cel['id'], 5.0, 80.0)
    devices.report_ok(names['Kas']['id'], 20.0, 60.0)
    devices._status[cel['id']]['ok_at'] = time.time() - 6 * 60
    alerts.check_offline()
    alerts.check_offline()                                   # niet dubbel
    texts = outbox_texts()
    assert len(texts) == 1 and 'Koelcel' in texts[0] and 'geen meetwaarden' in texts[0]
    alerts.evaluate(cel, {'temperature': 5.0})
    assert 'weer online' in outbox_texts()[0]


def test_new_sensor_without_readings_gets_full_offline_period():
    names = setup_alerts([])
    settings.save({'alert_offline_minutes': 5})
    alerts._first_seen.clear()
    alerts.check_offline(now=10_000)                         # net toegevoegd, nog geen meting
    alerts.check_offline(now=10_000 + 4 * 60)
    assert outbox_texts() == []
    alerts.check_offline(now=10_000 + 5 * 60)
    assert sorted(t.split(':')[0][2:] for t in outbox_texts()) == sorted(names)


def test_send_channels_hide_secrets():
    fresh_settings()
    config = settings.merged({'telegram_bot_token': TOKEN, 'telegram_chat_id': '42', 'smtp_host': 'mail.example.com',
                              'smtp_from': 'a@example.com', 'smtp_to': 'b@example.com, c@example.com',
                              'smtp_username': 'user', 'smtp_password': 'Geheim!pw'})
    original_post, original_smtp = alerts.requests.post, alerts.smtplib.SMTP
    sent = {}

    def failing_post(url, **kwargs):
        raise alerts.requests.ConnectionError(f'Max retries exceeded with url: {url}')

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent['server'] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, context):
            sent['tls'] = True

        def login(self, user, password):
            raise alerts.smtplib.SMTPAuthenticationError(535, f'bad credentials for {user}/{password}')

    try:
        alerts.requests.post, alerts.smtplib.SMTP = failing_post, FakeSMTP
        error = alerts.send_now('telegram', 'x', config)
        assert TOKEN not in error and '***' in error
        error = alerts.send_now('email', 'x', config)
        assert 'Geheim!pw' not in error and sent == {'server': ('mail.example.com', 587), 'tls': True}
    finally:
        alerts.requests.post, alerts.smtplib.SMTP = original_post, original_smtp


def test_notifier_retries_failed_messages():
    setup_alerts([])
    notifier = alerts.Notifier()
    original = alerts.CHANNELS['telegram']
    try:
        alerts.CHANNELS['telegram'] = lambda text, config: (_ for _ in ()).throw(RuntimeError('Bad Gateway'))
        notifier.deliver({'channel': 'telegram', 'text': 'hallo', 'attempt': 0, 'next_try': 0})
        assert alerts.log[0]['ok'] is False and alerts.log[0]['error'] == 'Bad Gateway'
        assert len(notifier.waiting) == 1 and notifier.waiting[0]['next_try'] > time.time()
        alerts.CHANNELS['telegram'] = lambda text, config: None
        notifier.deliver(notifier.waiting.pop())
        assert alerts.log[0]['ok'] is True and alerts.log[0]['attempt'] == 2
    finally:
        alerts.CHANNELS['telegram'] = original


if __name__ == '__main__':
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith('test_') and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"✓ {name}")
        except Exception:
            failed += 1
            print(f"✗ {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} tests geslaagd")
    sys.exit(1 if failed else 0)
