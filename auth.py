"""Admin wachtwoord, login sessies en toegangsbeveiliging.

auth_mode 'settings': alleen de Settings tab vraagt om login (dashboard is openbaar).
auth_mode 'app':      de hele app vraagt om login.
"""
import time
from html import escape

from flask import Response, redirect, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import settings
from translations import TRANSLATIONS

MIN_PASSWORD_LENGTH = 8
MAX_FAILURES = 5
BLOCK_SECONDS = 300

# ponytail: in-memory per proces, reset bij herstart; voldoende voor één Waitress proces
_failures = {}

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
    return set_password(new, repeat)


def is_logged_in():
    if not session.get('admin') or not has_password():
        return False
    if time.time() - session.get('last_seen', 0) > settings.get('session_timeout_minutes') * 60:
        session.clear()
        return False
    session['last_seen'] = time.time()
    return True


def _start_session():
    session.clear()
    session['admin'] = True
    session['last_seen'] = time.time()


def _blocked_for(ip):
    """Seconden dat dit IP nog geblokkeerd is (0 = niet geblokkeerd)."""
    now = time.time()
    recent = [t for t in _failures.get(ip, []) if now - t < BLOCK_SECONDS]
    _failures[ip] = recent
    if len(recent) >= MAX_FAILURES:
        return int(BLOCK_SECONDS - (now - recent[0])) + 1
    return 0


def _safe_next(target):
    """Alleen lokale paden als redirect doel (geen open redirect)."""
    if not target or not target.startswith('/') or target.startswith('//') or '\\' in target:
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
            _start_session()
            return redirect(_safe_next(request.form.get('next')))
        error = t[code]
    return _page(t, t['setup_title'], t['setup_prompt'], t['btn_setup'], error, repeat=True)


def _login():
    if not has_password():
        return redirect('/setup?next=' + _safe_next(request.values.get('next')))
    t = TRANSLATIONS[_lang()]
    ip = request.remote_addr or '?'
    if request.method == 'POST':
        wait = _blocked_for(ip)
        if wait:
            return _page(t, t['login_title'], t['login_prompt'], t['btn_login'],
                         t['err_login_blocked'].format(seconds=wait), status=429)
        if check_password_hash(settings.get('admin_password_hash'), request.form.get('password') or ''):
            _failures.pop(ip, None)
            _start_session()
            return redirect(_safe_next(request.form.get('next')))
        _failures.setdefault(ip, []).append(time.time())
        return _page(t, t['login_title'], t['login_prompt'], t['btn_login'], t['err_password_wrong'], status=401)
    return _page(t, t['login_title'], t['login_prompt'], t['btn_login'])


def _logout():
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
