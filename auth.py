"""Admin wachtwoord, login sessies en toegangsbeveiliging.

auth_mode 'settings': alleen de Settings tab vraagt om login (dashboard is openbaar).
auth_mode 'app':      de hele app vraagt om login.
"""
import ipaddress
import secrets
import threading
import time
from html import escape
from urllib.parse import urlsplit

from flask import Response, has_request_context, redirect, request, session
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import settings
from translations import TRANSLATIONS

MIN_PASSWORD_LENGTH = 8
MAX_FAILURES = 5            # per client (IPv4 adres of IPv6 /64)
MAX_FAILURES_GLOBAL = 50    # daarboven alleen nog pogingen vanaf vertrouwde browsers
BLOCK_SECONDS = 300
TRUSTED_COOKIE = 'xy_trusted'
TRUSTED_DAYS = 90

# ponytail: in-memory per proces (reset bij herstart = iedereen uitgelogd); voldoende voor één Waitress proces
_failures = {}   # client -> [tijdstippen mislukte login]
_sessions = {}   # sid -> {'last_seen': tijd, 'pw': hash op moment van inloggen}
_lock = threading.Lock()

PUBLIC_PATHS = ('/login', '/setup', '/logout')


def has_password():
    return bool(settings.get('admin_password_hash'))


def set_password(password, repeat):
    """Geef een foutcode terug, of None als het wachtwoord is opgeslagen."""
    if len(password or '') < MIN_PASSWORD_LENGTH:
        return 'err_password_short'
    if password != repeat:
        return 'err_password_mismatch'
    settings.set_internal('admin_password_hash', generate_password_hash(password))
    return None


def change_password(current, new, repeat):
    if not check_password_hash(settings.get('admin_password_hash') or '', current or ''):
        return 'err_password_wrong'
    error = set_password(new, repeat)
    if error is None:
        # Andere sessies intrekken, de huidige blijft ingelogd
        sid = session.get('sid') if has_request_context() else None
        with _lock:
            current_session = _sessions.get(sid)
            _sessions.clear()
            if current_session:
                current_session['pw'] = settings.get('admin_password_hash')
                _sessions[sid] = current_session
    return error


def is_logged_in():
    """Sessie is server-side geldig: niet uitgelogd, niet verlopen, wachtwoord sindsdien niet gewijzigd."""
    sid = session.get('sid')
    if not sid:
        return False
    now = time.time()
    with _lock:
        entry = _sessions.get(sid)
        if (entry is None or not has_password() or entry['pw'] != settings.get('admin_password_hash')
                or now - entry['last_seen'] > settings.get('session_timeout_minutes') * 60):
            _sessions.pop(sid, None)
            return False
        entry['last_seen'] = now
    return True


def _start_session(verified_hash):
    """verified_hash: de hash waartegen het wachtwoord net is gecontroleerd (niet opnieuw opvragen:
    als het wachtwoord intussen gewijzigd is, moet deze sessie ongeldig zijn)."""
    sid = secrets.token_urlsafe(32)
    with _lock:
        _sessions.pop(session.get('sid'), None)
        _sessions[sid] = {'last_seen': time.time(), 'pw': verified_hash}
    session.clear()
    session['sid'] = sid


def _client_key(ip):
    """IPv6 per /64 groeperen: één aansluiting heeft er vaak miljarden adressen."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f'{addr}/64', strict=False))
    return str(addr)


def _trusted_serializer():
    return URLSafeTimedSerializer(settings.get('secret_key'), salt='trusted-browser')


def _trusted_browser_id():
    """Id van een browser waarmee eerder succesvol is ingelogd, of None.

    Gesigneerde cookie met een eigen id per browser, gebonden aan de huidige wachtwoord hash
    (na een wachtwoordwijziging ongeldig). Blijft bewaard na uitloggen.
    """
    token = request.cookies.get(TRUSTED_COOKIE)
    if not token:
        return None
    try:
        data = _trusted_serializer().loads(token, max_age=TRUSTED_DAYS * 86400)
    except BadSignature:
        return None
    current = settings.get('admin_password_hash') or ''
    if not isinstance(data, dict) or data.get('pw') != current[-16:]:
        return None
    return data.get('id')


def _blocked_for(client, trusted_id=None):
    """Seconden dat deze client nog geblokkeerd is (0 = niet geblokkeerd).

    Per client (IPv4 / IPv6 /64) en per vertrouwde browser maximaal MAX_FAILURES pogingen. Bij een
    aanval vanaf veel adressen (MAX_FAILURES_GLOBAL over alle clients) mogen alleen vertrouwde browsers
    nog proberen, zodat de beheerder vanaf de eigen browser niet buitengesloten wordt. Een gestolen
    cookie geeft dus hooguit MAX_FAILURES pogingen per BLOCK_SECONDS, ongeacht het aantal adressen.
    """
    now = time.time()
    with _lock:
        for key in list(_failures):
            _failures[key] = [t for t in _failures[key] if now - t < BLOCK_SECONDS]
            if not _failures[key]:
                del _failures[key]
        mine = _failures.get(client, [])
        browser = _failures.get(f'trusted:{trusted_id}', []) if trusted_id else []
        everyone = sorted(t for key, times in _failures.items() if not key.startswith('trusted:') for t in times)
    for own in (mine, browser):
        if len(own) >= MAX_FAILURES:
            return int(BLOCK_SECONDS - (now - own[-MAX_FAILURES])) + 1
    if len(everyone) >= MAX_FAILURES_GLOBAL and not trusted_id:
        return int(BLOCK_SECONDS - (now - everyone[-MAX_FAILURES_GLOBAL])) + 1
    return 0


def _record_failure(client, trusted_id=None):
    with _lock:
        _failures.setdefault(client, []).append(time.time())
        if trusted_id:
            _failures.setdefault(f'trusted:{trusted_id}', []).append(time.time())


def _safe_next(target):
    """Alleen lokale paden als redirect doel (geen open redirect)."""
    if not target or any(ord(c) < 0x21 or c == '\\' for c in target):
        return '/'
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith('/') or target.startswith('//'):
        return '/'
    return target


def _lang():
    lang = request.args.get('lang') or request.form.get('lang') or settings.get('default_language')
    return lang if lang in TRANSLATIONS else 'en'


def _page(t, title, prompt, button, error='', repeat=False, status=200):
    next_url = escape(_safe_next(request.values.get('next')))
    error_html = f'<p class="err">{escape(error)}</p>' if error else ''
    repeat_html = (f'<label>{escape(t["lbl_repeat_password"])}</label>'
                   f'<input type="password" name="repeat" autocomplete="new-password" required>') if repeat else ''
    body = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
body {{ font-family: Arial, sans-serif; background: #ecf0f1; margin: 0; padding: 20px; }}
.box {{ max-width: 380px; margin: 60px auto; background: white; border-radius: 15px; overflow: hidden;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
.head {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; }}
.head h1 {{ margin: 0; font-size: 22px; }}
form {{ padding: 20px; }}
label {{ display: block; font-weight: bold; color: #2c3e50; margin: 12px 0 6px; }}
input {{ width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #bdc3c7; border-radius: 8px; font-size: 16px; }}
button {{ width: 100%; margin-top: 20px; padding: 12px; background: #27ae60; color: white; border: none;
          border-radius: 8px; font-weight: bold; font-size: 16px; cursor: pointer; }}
.err {{ color: #c0392b; font-weight: bold; }}
p {{ color: #34495e; }}
</style></head>
<body><div class="box"><div class="head"><h1>{escape(title)}</h1></div>
<form method="post">
<p>{escape(prompt)}</p>{error_html}
<input type="hidden" name="next" value="{next_url}">
<input type="hidden" name="lang" value="{escape(_lang())}">
<label>{escape(t["lbl_password"])}</label>
<input type="password" name="password" autocomplete="{'new-password' if repeat else 'current-password'}" required autofocus>
{repeat_html}
<button type="submit">{escape(button)}</button>
</form></div></body></html>'''
    return Response(body, status=status, mimetype='text/html')


def _setup():
    if has_password():
        return redirect('/login?next=' + _safe_next(request.values.get('next')))
    t = TRANSLATIONS[_lang()]
    error = ''
    if request.method == 'POST':
        code = set_password(request.form.get('password'), request.form.get('repeat'))
        if code is None:
            _start_session(settings.get('admin_password_hash'))
            return _trust_browser(redirect(_safe_next(request.form.get('next'))))
        error = t[code]
    return _page(t, t['setup_title'], t['setup_prompt'], t['btn_setup'], error, repeat=True)


def _login():
    if not has_password():
        return redirect('/setup?next=' + _safe_next(request.values.get('next')))
    t = TRANSLATIONS[_lang()]
    client = _client_key(request.remote_addr or '?')
    if request.method == 'POST':
        trusted_id = _trusted_browser_id()
        wait = _blocked_for(client, trusted_id)
        if wait:
            return _page(t, t['login_title'], t['login_prompt'], t['btn_login'],
                         t['err_login_blocked'].format(seconds=wait), status=429)
        verified_hash = settings.get('admin_password_hash')
        if check_password_hash(verified_hash, request.form.get('password') or ''):
            with _lock:
                _failures.pop(client, None)
            _start_session(verified_hash)
            return _trust_browser(redirect(_safe_next(request.form.get('next'))))
        _record_failure(client, trusted_id)
        return _page(t, t['login_title'], t['login_prompt'], t['btn_login'], t['err_password_wrong'], status=401)
    return _page(t, t['login_title'], t['login_prompt'], t['btn_login'])


def _trust_browser(response):
    token = _trusted_serializer().dumps({'id': secrets.token_urlsafe(16),
                                         'pw': (settings.get('admin_password_hash') or '')[-16:]})
    response.set_cookie(TRUSTED_COOKIE, token, max_age=TRUSTED_DAYS * 86400, httponly=True, samesite='Lax')
    return response


def _logout():
    with _lock:
        _sessions.pop(session.get('sid'), None)
    session.clear()
    return redirect('/')


def _guard():
    """auth_mode 'app': alles behalve login/setup/logout vereist een sessie."""
    if settings.get('auth_mode') != 'app' or request.path in PUBLIC_PATHS or is_logged_in():
        return None
    if request.path.startswith('/_dash-') or request.path.startswith('/_reload'):
        return Response('Unauthorized', status=401)
    return redirect('/login?next=' + _safe_next(request.full_path.rstrip('?')))


def init_app(server):
    """Koppel sessies, routes en de toegangscontrole aan de Flask server van Dash."""
    server.secret_key = settings.get('secret_key')
    server.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
    server.add_url_rule('/setup', 'setup', _setup, methods=['GET', 'POST'])
    server.add_url_rule('/login', 'login', _login, methods=['GET', 'POST'])
    server.add_url_rule('/logout', 'logout', _logout)
    server.before_request(_guard)
