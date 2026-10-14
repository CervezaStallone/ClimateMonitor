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

from flask import Flask  # noqa: E402

import auth  # noqa: E402
import settings  # noqa: E402


def fresh_settings():
    """Lege database en cache, zoals een eerste start."""
    if os.path.exists(settings.DB_FILE):
        os.remove(settings.DB_FILE)
    settings._cache.clear()
    settings.load()


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


def test_no_open_redirect():
    for target in ['//evil.example', '/\\evil.example', '/\t/evil.example', 'https://evil.example', 'javascript:alert(1)',
                   '/\n/evil.example', ' /x']:
        assert auth._safe_next(target) == '/', target
    assert auth._safe_next('/?tab=settings') == '/?tab=settings'


def test_ipv6_clients_grouped_per_64():
    assert auth._client_key('2001:db8::1') == auth._client_key('2001:db8::ffff:1234')
    assert auth._client_key('2001:db8:0:1::1') != auth._client_key('2001:db8::1')
    assert auth._client_key('::ffff:192.0.2.7') == '192.0.2.7'


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
