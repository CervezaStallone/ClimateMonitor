"""Settings tab: formulier opgebouwd uit settings.SCHEMA, opslaan, wachtwoord wijzigen."""
from urllib.parse import quote
from zoneinfo import available_timezones

from dash import ALL, Input, Output, State, callback_context, dcc, html, no_update

import auth
import settings
from translations import LANGUAGE_NAMES, TRANSLATIONS

SECTIONS = ['regional', 'data', 'server', 'security']

_TIMEZONES = sorted(available_timezones())

LABEL_STYLE = {'fontWeight': 'bold', 'color': '#2c3e50', 'display': 'block', 'marginBottom': '6px'}
INPUT_STYLE = {'width': '100%', 'padding': '8px', 'borderRadius': '8px', 'border': '1px solid #bdc3c7',
               'boxSizing': 'border-box'}
BUTTON_STYLE = {'padding': '12px 30px', 'background': '#27ae60', 'color': 'white', 'border': 'none',
                'borderRadius': '8px', 'cursor': 'pointer', 'fontWeight': 'bold', 'fontSize': '16px'}
LINK_BUTTON_STYLE = {**BUTTON_STYLE, 'textDecoration': 'none', 'display': 'inline-block',
                     'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'}


def _t(lang):
    return TRANSLATIONS.get(lang) or TRANSLATIONS['en']


def _options(key, t):
    if key == 'default_language':
        return [{'label': LANGUAGE_NAMES[code], 'value': code} for code in settings.LANGUAGES]
    if key == 'timezone':
        return _TIMEZONES
    return [{'label': t[f'opt_{key}_{choice}'], 'value': choice} for choice in settings.SCHEMA[key]['choices']]


def _field(key, value, t):
    spec = settings.SCHEMA[key]
    field_id = {'type': 'setting', 'key': key}
    if spec['type'] is bool:
        control = dcc.Checklist(id=field_id, options=[{'label': ' ' + t['lbl_enabled'], 'value': 'on'}],
                                value=['on'] if value else [])
    elif 'choices' in spec or spec.get('check') == 'timezone':
        control = dcc.Dropdown(id=field_id, options=_options(key, t), value=value, clearable=False)
    elif spec['type'] is int:
        control = dcc.Input(id=field_id, type='number', value=value, min=spec.get('min'), max=spec.get('max'),
                            step=1, style=INPUT_STYLE)
    else:
        control = dcc.Input(id=field_id, type='text', value=value, style=INPUT_STYLE)

    label = [t[f'lbl_{key}']]
    if spec.get('restart'):
        label.append(html.Span(t['badge_restart'], style={
            'marginLeft': '8px', 'fontSize': '12px', 'background': '#f39c12', 'color': 'white',
            'padding': '2px 8px', 'borderRadius': '10px'}))
    hint_key = f'hint_{key}'
    return html.Div([
        html.Label(label, style=LABEL_STYLE),
        control,
        html.Div(t[hint_key], style={'fontSize': '12px', 'color': '#7f8c8d', 'marginTop': '4px'}) if hint_key in t else None,
        html.Div(id={'type': 'setting-error', 'key': key},
                 style={'color': '#c0392b', 'fontWeight': 'bold', 'marginTop': '4px'}),
    ], style={'marginBottom': '18px'})


def _section(name, values, t):
    keys = [k for k, spec in settings.SCHEMA.items() if spec['section'] == name]
    extra = []
    if name == 'data':
        extra.append(html.Div([
            html.Label(t['lbl_database_file'], style=LABEL_STYLE),
            dcc.Input(type='text', value=settings.DB_FILE, disabled=True, style={**INPUT_STYLE, 'background': '#ecf0f1'}),
            html.Div(t['hint_database_file'], style={'fontSize': '12px', 'color': '#7f8c8d', 'marginTop': '4px'}),
        ], style={'marginBottom': '18px'}))
    return html.Div([
        html.H3(t[f'section_{name}'], style={'color': '#34495e', 'borderBottom': '2px solid #ecf0f1',
                                             'paddingBottom': '8px'}),
        *[_field(k, values[k], t) for k in keys],
        *extra,
    ], style={'marginBottom': '25px'})


def _password_form(t):
    pw_style = {**INPUT_STYLE, 'marginBottom': '10px'}
    return html.Div([
        html.H3(t['lbl_change_password'], style={'color': '#34495e', 'borderBottom': '2px solid #ecf0f1',
                                                 'paddingBottom': '8px'}),
        html.Label(t['lbl_current_password'], style=LABEL_STYLE),
        dcc.Input(id='pw-current', type='password', autoComplete='current-password', style=pw_style),
        html.Label(t['lbl_new_password'], style=LABEL_STYLE),
        dcc.Input(id='pw-new', type='password', autoComplete='new-password', style=pw_style),
        html.Label(t['lbl_repeat_password'], style=LABEL_STYLE),
        dcc.Input(id='pw-repeat', type='password', autoComplete='new-password', style=pw_style),
        html.Button(t['btn_change_password'], id='pw-change', n_clicks=0, style=BUTTON_STYLE),
        html.Div(id='pw-status', style={'marginTop': '10px', 'fontWeight': 'bold'}),
    ])


def _locked(t, lang):
    target = '/setup' if not auth.has_password() else '/login'
    message = t['setup_prompt'] if target == '/setup' else t['settings_locked']
    button = t['btn_setup'] if target == '/setup' else t['btn_go_login']
    href = f"{target}?lang={lang}&next={quote('/?tab=settings')}"
    return html.Div([
        html.H2(f"⚙️ {t['tab_settings']}", style={'color': '#2c3e50'}),
        html.P(message, style={'color': '#34495e'}),
        html.A(button, href=href, style=LINK_BUTTON_STYLE),
    ], style={'textAlign': 'center', 'padding': '30px'})


def render_settings(lang):
    t = _t(lang)
    if not auth.is_logged_in():
        return _locked(t, lang)
    values = settings.public_values()
    return html.Div([
        html.Div([
            html.H2(f"⚙️ {t['tab_settings']}", style={'color': '#2c3e50', 'display': 'inline-block', 'margin': '0'}),
            html.A(t['btn_logout'], href='/logout', style={'float': 'right', 'color': '#c0392b', 'fontWeight': 'bold'}),
        ], style={'marginBottom': '20px'}),
        *[_section(name, values, t) for name in SECTIONS],
        html.Button(t['btn_save'], id='settings-save', n_clicks=0, style=BUTTON_STYLE),
        html.Div(id='settings-status', style={'marginTop': '10px', 'fontWeight': 'bold'}),
        html.Hr(style={'border': '1px solid #ecf0f1', 'margin': '30px 0'}),
        _password_form(t),
    ], style={'maxWidth': '700px'})


def register_settings_callbacks(app):

    @app.callback(
        Output('main-tabs', 'value'),
        Input('url', 'search')
    )
    def select_tab_from_url(search):
        return 'settings' if search and 'tab=settings' in search else no_update

    @app.callback(
        Output('settings-content', 'children'),
        [Input('main-tabs', 'value'),
         Input('selected-language', 'data')]
    )
    def show_settings(tab, lang):
        if tab != 'settings':
            return no_update
        return render_settings(lang)

    @app.callback(
        [Output({'type': 'setting-error', 'key': ALL}, 'children'),
         Output('settings-status', 'children'),
         Output('settings-status', 'style')],
        Input('settings-save', 'n_clicks'),
        [State({'type': 'setting', 'key': ALL}, 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def save_settings(n_clicks, values, lang):
        t = _t(lang)
        keys = [item['id']['key'] for item in callback_context.states_list[0]]
        ok_style = {'marginTop': '10px', 'fontWeight': 'bold', 'color': '#27ae60'}
        bad_style = {'marginTop': '10px', 'fontWeight': 'bold', 'color': '#c0392b'}
        if not auth.is_logged_in():
            return [''] * len(keys), t['settings_locked'], bad_style

        submitted = dict(zip(keys, values))
        before = settings.public_values()
        errors = settings.save(submitted)
        field_errors = [t.get(errors[k], errors[k]) if k in errors else '' for k in keys]
        if errors:
            return field_errors, t['msg_save_failed'], bad_style

        restart_changed = any(settings.SCHEMA[k].get('restart') and settings.get(k) != before[k] for k in keys)
        message = t['msg_saved_restart'] if restart_changed else t['msg_saved']
        return field_errors, message, ok_style

    @app.callback(
        [Output('pw-status', 'children'),
         Output('pw-status', 'style'),
         Output('pw-current', 'value'),
         Output('pw-new', 'value'),
         Output('pw-repeat', 'value')],
        Input('pw-change', 'n_clicks'),
        [State('pw-current', 'value'),
         State('pw-new', 'value'),
         State('pw-repeat', 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def change_password(n_clicks, current, new, repeat, lang):
        t = _t(lang)
        if not auth.is_logged_in():
            return t['settings_locked'], {'color': '#c0392b', 'marginTop': '10px', 'fontWeight': 'bold'}, '', '', ''
        error = auth.change_password(current, new, repeat)
        if error:
            return t[error], {'color': '#c0392b', 'marginTop': '10px', 'fontWeight': 'bold'}, '', '', ''
        return t['msg_password_changed'], {'color': '#27ae60', 'marginTop': '10px', 'fontWeight': 'bold'}, '', '', ''
