"""Settings tab: formulier opgebouwd uit settings.SCHEMA, Modbus bussen/devices, opslaan, wachtwoord wijzigen."""
import time
from urllib.parse import quote
from zoneinfo import available_timezones

from dash import ALL, Input, Output, State, callback_context, dash_table, dcc, html, no_update

import alerts
import auth
import devices
import mqtt_publisher
import settings
from translations import LANGUAGE_NAMES, TRANSLATIONS

SECTIONS = ['display', 'modbus', 'notify', 'alerts', 'mqtt', 'regional', 'data', 'server', 'security']

BUS_COLUMNS = ['name', 'port', 'baudrate', 'bytesize', 'parity', 'stopbits', 'timeout', 'enabled']
DEVICE_COLUMNS = ['id', 'name', 'bus', 'slave_id', 'function_code', 'register_temp', 'register_humidity',
                  'scale_temp', 'scale_humidity', 'enabled']

_TIMEZONES = sorted(available_timezones())



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
    if spec.get('secret'):
        # Write-only: nooit de waarde tonen, alleen of hij ingesteld is; leeg laten = houden
        control = dcc.Input(id=field_id, type='password', value='', autoComplete='new-password',
                            placeholder=t['secret_set'] if value else t['secret_not_set'], className='input')
    elif spec['type'] is bool:
        control = dcc.Checklist(id=field_id, options=[{'label': ' ' + t['lbl_enabled'], 'value': 'on'}],
                                value=['on'] if value else [])
    elif 'choices' in spec or spec.get('check') == 'timezone':
        control = dcc.Dropdown(id=field_id, options=_options(key, t), value=value, clearable=False)
    elif spec['type'] in (int, float):
        control = dcc.Input(id=field_id, type='number', value=value, min=spec.get('min'), max=spec.get('max'),
                            step=1 if spec['type'] is int else 'any', className='input')
    else:
        control = dcc.Input(id=field_id, type='text', value=value, className='input')

    label = [t[f'lbl_{key}']]
    if spec.get('restart'):
        label.append(html.Span(t['badge_restart'], className='badge'))
    hint_key = f'hint_{key}'
    return html.Div([
        html.Label(label, className='field-label'),
        control,
        html.Div(t[hint_key], className='field-hint') if hint_key in t else None,
        html.Div(id={'type': 'setting-error', 'key': key},
                 className='field-error'),
    ], className='field')


def _yes_no(t):
    return [{'label': t['opt_yes'], 'value': 'true'}, {'label': t['opt_no'], 'value': 'false'}]


def _table_rows(rows, columns):
    """Database rijen naar DataTable rijen (bool als 'true'/'false', id blijft mee voor bijwerken)."""
    return [{**{c: ('true' if r[c] else 'false') if isinstance(r.get(c), bool) else r.get(c) for c in columns},
             'id': r.get('id')} for r in rows]


def _bus_table(buses, t):
    choices = {'baudrate': devices.BAUDRATES, 'bytesize': [7, 8], 'parity': ['N', 'E', 'O'], 'stopbits': [1, 2]}
    return dash_table.DataTable(
        id='bus-table',
        columns=[{'id': c, 'name': t[f'col_{c}'], 'presentation': 'dropdown' if c in choices or c == 'enabled' else 'input',
                  'type': 'numeric' if c == 'timeout' else 'any'} for c in BUS_COLUMNS],
        data=_table_rows(buses, BUS_COLUMNS),
        editable=True, row_deletable=True,
        dropdown={**{c: {'options': [{'label': str(v), 'value': v} for v in opts], 'clearable': False}
                     for c, opts in choices.items()},
                  'enabled': {'options': _yes_no(t), 'clearable': False}},
        **TABLE_STYLE)


def _device_table(device_rows, bus_names, t):
    return dash_table.DataTable(
        id='device-table',
        columns=[{'id': c, 'name': t[f'col_{c}'], 'editable': c != 'id',
                  'presentation': 'dropdown' if c in ('bus', 'function_code', 'enabled') else 'input',
                  'type': 'numeric' if c.startswith(('slave', 'register', 'scale')) else 'any'} for c in DEVICE_COLUMNS],
        data=_table_rows(device_rows, DEVICE_COLUMNS),
        editable=True, row_deletable=True,
        dropdown={'bus': {'options': [{'label': n, 'value': n} for n in bus_names], 'clearable': False},
                  'function_code': {'options': [{'label': t['opt_function_code_3'], 'value': 3},
                                                {'label': t['opt_function_code_4'], 'value': 4}], 'clearable': False},
                  'enabled': {'options': _yes_no(t), 'clearable': False}},
        **TABLE_STYLE)


TABLE_STYLE = {
    'style_table': {'overflowX': 'auto', 'marginBottom': '10px'},
    'style_cell': {'fontFamily': 'var(--sans)', 'fontSize': '14px', 'padding': '7px 8px', 'minWidth': '70px',
                   'backgroundColor': 'var(--panel-2)', 'color': 'var(--text)', 'border': '1px solid var(--line)',
                   'textAlign': 'left'},
    'style_header': {'backgroundColor': 'var(--panel)', 'fontWeight': '600', 'color': 'var(--muted)',
                     'border': '1px solid var(--line)', 'fontSize': '12px'},
    'css': [{'selector': '.Select-menu-outer', 'rule': 'display: block !important'}],
}


def _modbus_section(t):
    buses, device_rows = devices.load_config()
    ports = devices.available_ports()
    return [
        html.H4(t['table_buses']),
        _bus_table(buses, t),
        html.Div(t['hint_ports'].format(ports=', '.join(ports)) if ports else t['hint_no_ports'], className='field-hint'),
        html.Button(t['btn_add_bus'], id='add-bus', n_clicks=0, className='btn btn-small'),
        html.H4(t['table_devices']),
        html.Div(t['hint_registers'], className='field-hint'),
        _device_table(device_rows, [b['name'] for b in buses], t),
        html.Button(t['btn_add_device'], id='add-device', n_clicks=0, className='btn btn-small'),
        html.Div(id='modbus-errors', className='field-error'),
        html.H4(t['lbl_device_status']),
        html.Div(id='device-status', children=device_status_list(t)),
    ]


def _notify_section(t):
    return [
        html.Div(t['hint_telegram'], className='field-hint', style={'marginBottom': '10px'}),
        html.Button(t['btn_test_telegram'], id='test-telegram', n_clicks=0, className='btn btn-small'),
        html.Button(t['btn_test_email'], id='test-email', n_clicks=0, className='btn btn-small'),
        html.Div(id='test-status', className='msg'),
    ]


def _mqtt_section(t):
    return [
        html.Div(t['hint_mqtt'], style={'fontSize': '12px', 'color': 'var(--muted)', 'marginBottom': '10px',
                                        'whiteSpace': 'pre-line'}),
        html.Button(t['btn_test_mqtt'], id='test-mqtt', n_clicks=0, className='btn btn-small'),
        html.Div(id='test-mqtt-status', className='msg'),
        html.Div(id='mqtt-status', children=mqtt_status_text(t), style={'marginTop': '10px'}),
    ]


def mqtt_status_text(t):
    state = mqtt_publisher.status
    if not settings.get('mqtt_enabled'):
        return html.Span(t['mqtt_status_disabled'], style={'color': 'var(--muted)'})
    if state['connected']:
        last = state['last_publish']
        text = t['mqtt_status_connected'] + (' · ' + t['mqtt_last_publish'].format(
            time=time.strftime('%H:%M:%S', time.localtime(last))) if last else '')
        return html.Span(text, style={'color': 'var(--ok)', 'fontWeight': 'bold'})
    return html.Span(t['mqtt_status_disconnected'].format(error=state['error'] or '...'),
                     style={'color': 'var(--alarm)', 'fontWeight': 'bold'})


def _rule_rows():
    return [{'scope': r['device_id'] or 0, 'metric': r['metric'], 'min_value': r['min_value'],
             'max_value': r['max_value'], 'enabled': 'true' if r['enabled'] else 'false'} for r in alerts.load_rules()]


def _alerts_section(t):
    scopes = [{'label': t['opt_all_devices'], 'value': 0}] + [
        {'label': f"#{d['id']} {d['name']}", 'value': d['id']} for d in devices.list_devices()]
    metrics = [{'label': t[alerts.METRICS[m][0]], 'value': m} for m in alerts.METRICS]
    return [
        html.H4(t['table_rules']),
        html.Div(t['hint_rules'], className='field-hint'),
        dash_table.DataTable(
            id='alert-rule-table',
            columns=[{'id': 'scope', 'name': t['col_scope'], 'presentation': 'dropdown'},
                     {'id': 'metric', 'name': t['col_metric'], 'presentation': 'dropdown'},
                     {'id': 'min_value', 'name': t['col_min_value'], 'type': 'numeric'},
                     {'id': 'max_value', 'name': t['col_max_value'], 'type': 'numeric'},
                     {'id': 'enabled', 'name': t['col_enabled'], 'presentation': 'dropdown'}],
            data=_rule_rows(), editable=True, row_deletable=True,
            dropdown={'scope': {'options': scopes, 'clearable': False},
                      'metric': {'options': metrics, 'clearable': False},
                      'enabled': {'options': _yes_no(t), 'clearable': False}},
            **TABLE_STYLE),
        html.Button(t['btn_add_rule'], id='add-rule', n_clicks=0, className='btn btn-small'),
        html.H4(t['lbl_alert_log']),
        html.Div(id='alert-log', children=alert_log_list(t)),
    ]


def alert_log_list(t):
    if not alerts.log:
        return html.Div(t['alert_log_empty'], style={'color': 'var(--muted)'})
    channel_names = {'telegram': 'Telegram', 'email': 'E-mail'}
    return html.Ul([html.Li([
        html.Span(time.strftime('%d-%m %H:%M:%S', time.localtime(entry['time'])) + ' · ' + channel_names[entry['channel']] + ': '),
        html.Span(entry['text']),
        html.Span(' ✓' if entry['ok'] else f" ✗ {entry['error']}", style={'color': 'var(--ok)' if entry['ok'] else 'var(--alarm)',
                                                                          'fontWeight': 'bold'}),
    ]) for entry in list(alerts.log)], className='status-list')


def device_status_list(t):
    """Live status per device: laatste waarden of laatste fout."""
    items = []
    now = time.time()
    for dev in devices.load_config()[1]:
        state = devices.status(dev['id'])
        if not dev['enabled']:
            text, color = t['status_disabled'], 'var(--muted)'
        elif state.get('ok_at') and not state.get('error'):
            text = t['status_ok'].format(temp=state['temperature'], hum=state['humidity'], ago=int(now - state['ok_at']))
            color = 'var(--ok)'
        elif state.get('error'):
            text, color = t['status_error'].format(error=state['error']), 'var(--alarm)'
        else:
            text, color = t['status_never'], 'var(--muted)'
        items.append(html.Li([html.Strong(f"#{dev['id']} {dev['name']} ({dev['bus']}, slave {dev['slave_id']}): "),
                              html.Span(text, style={'color': color})]))
    return html.Ul(items, className='status-list')


def _section(name, values, t):
    keys = [k for k, spec in settings.SCHEMA.items() if spec['section'] == name]
    extra = {'modbus': _modbus_section, 'notify': _notify_section, 'alerts': _alerts_section,
             'mqtt': _mqtt_section}.get(name, lambda t: [])(t)
    if name == 'data':
        extra.append(html.Div([
            html.Label(t['lbl_database_file'], className='field-label'),
            dcc.Input(type='text', value=settings.DB_FILE, disabled=True, className='input'),
            html.Div(t['hint_database_file'], className='field-hint'),
        ], className='field'))
    return html.Div([
        html.H3(t[f'section_{name}']),
        *[_field(k, values[k], t) for k in keys],
        *extra,
    ])


def _password_form(t):
    return html.Div([
        html.H3(t['lbl_change_password']),
        html.Label(t['lbl_current_password'], className='field-label'),
        dcc.Input(id='pw-current', type='password', autoComplete='current-password', className='input'),
        html.Label(t['lbl_new_password'], className='field-label'),
        dcc.Input(id='pw-new', type='password', autoComplete='new-password', className='input'),
        html.Label(t['lbl_repeat_password'], className='field-label'),
        dcc.Input(id='pw-repeat', type='password', autoComplete='new-password', className='input'),
        html.Button(t['btn_change_password'], id='pw-change', n_clicks=0, className='btn'),
        html.Div(id='pw-status'),
    ])


def _locked(t, lang):
    target = '/setup' if not auth.has_password() else '/login'
    message = t['setup_prompt'] if target == '/setup' else t['settings_locked']
    button = t['btn_setup'] if target == '/setup' else t['btn_go_login']
    href = f"{target}?lang={lang}&next={quote('/?tab=settings')}"
    return html.Div([
        html.H2(t['tab_settings']),
        html.P(message, className='hint'),
        html.A(button, href=href, className='btn btn-primary'),
    ], className='locked')


def render_settings(lang):
    t = _t(lang)
    if not auth.is_logged_in():
        return _locked(t, lang)
    values = settings.public_values()
    return html.Div([
        html.Div([
            html.H2(t['tab_settings']),
            html.A(t['btn_logout'], href='/logout', className='btn btn-small'),
        ], className='settings-head'),
        *[_section(name, values, t) for name in SECTIONS],
        html.Div(className='settings-actions', children=[
            html.Button(t['btn_save'], id='settings-save', n_clicks=0, className='btn btn-primary'),
            html.Div(id='settings-status'),
        ]),
        _password_form(t),
    ])


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
         State('selected-language', 'data'),
         State('bus-table', 'data'),
         State('device-table', 'data'),
         State('alert-rule-table', 'data')],
        prevent_initial_call=True
    )
    def save_settings(n_clicks, values, lang, bus_rows, device_rows, rule_rows):
        t = _t(lang)
        ok_style = {'marginTop': '10px', 'fontWeight': 'bold', 'color': 'var(--ok)'}
        bad_style = {'marginTop': '10px', 'fontWeight': 'bold', 'color': 'var(--alarm)'}
        if not auth.is_logged_in():
            return no_update, t['settings_locked'], bad_style
        keys = [item['id']['key'] for item in callback_context.states_list[0]]

        # Eerst de Modbus configuratie valideren, zodat bij een fout niets wordt opgeslagen
        _, _, modbus_errors = devices.validate_config(bus_rows or [], device_rows or [])
        _, rule_errors = alerts.validate_rules(rule_rows or [])
        if modbus_errors or rule_errors:
            return [''] * len(keys), t['msg_save_failed'], bad_style

        submitted = dict(zip(keys, values))
        before = settings.public_values()
        errors = settings.save(submitted)
        field_errors = [t.get(errors[k], errors[k]) if k in errors else '' for k in keys]
        if errors:
            return field_errors, t['msg_save_failed'], bad_style
        devices.save_config(bus_rows or [], device_rows or [])
        alerts.save_rules(rule_rows or [])

        restart_changed = any(settings.SCHEMA[k].get('restart') and settings.get(k) != before[k] for k in keys)
        message = t['msg_saved_restart'] if restart_changed else t['msg_saved']
        return field_errors, message, ok_style

    @app.callback(
        [Output('modbus-errors', 'children'),
         Output('bus-table', 'style_data_conditional'),
         Output('device-table', 'style_data_conditional'),
         Output('bus-table', 'data', allow_duplicate=True),
         Output('device-table', 'data', allow_duplicate=True),
         Output('alert-rule-table', 'style_data_conditional'),
         Output('alert-rule-table', 'data', allow_duplicate=True)],
        Input('settings-save', 'n_clicks'),
        [State('bus-table', 'data'),
         State('device-table', 'data'),
         State('selected-language', 'data'),
         State('alert-rule-table', 'data')],
        prevent_initial_call=True
    )
    def show_modbus_errors(n_clicks, bus_rows, device_rows, lang, rule_rows):
        """Markeer foute cellen; na succesvol opslaan de tabellen herladen (nieuwe rijen krijgen een id)."""
        t = _t(lang)
        if not auth.is_logged_in():
            return (no_update,) * 7
        _, _, errors = devices.validate_config(bus_rows or [], device_rows or [])
        _, rule_errors = alerts.validate_rules(rule_rows or [])
        if rule_errors:
            errors = {**errors, 'rules': rule_errors}
        messages, styles = [], {'buses': [], 'devices': [], 'rules': []}
        for table in ('buses', 'devices', 'rules'):
            for row, fields in errors.get(table, {}).items():
                for field, code in fields.items():
                    messages.append(html.Li(t['row_error'].format(table=t[f'table_{table}'], row=row + 1,
                                                                  field=t[f'col_{field}'], error=t.get(code, code))))
                    styles[table].append({'if': {'row_index': row, 'column_id': field},
                                          'backgroundColor': 'var(--alarm-cell)', 'color': 'var(--alarm)'})
        if errors:
            return html.Ul(messages), styles['buses'], styles['devices'], no_update, no_update, styles['rules'], no_update
        buses, device_rows = devices.load_config()
        return '', [], [], _table_rows(buses, BUS_COLUMNS), _table_rows(device_rows, DEVICE_COLUMNS), [], _rule_rows()

    @app.callback(
        Output('bus-table', 'data'),
        Input('add-bus', 'n_clicks'),
        State('bus-table', 'data'),
        prevent_initial_call=True
    )
    def add_bus(n_clicks, rows):
        if not auth.is_logged_in():
            return no_update
        rows = rows or []
        used = {r.get('port') for r in rows}
        port = next((p for p in devices.available_ports() if p not in used), '')
        return rows + [{'id': None, 'name': f'Bus {len(rows) + 1}', 'port': port, 'baudrate': 9600, 'bytesize': 8,
                        'parity': 'N', 'stopbits': 1, 'timeout': 1.0, 'enabled': 'true'}]

    @app.callback(
        Output('device-table', 'data'),
        Input('add-device', 'n_clicks'),
        [State('device-table', 'data'),
         State('bus-table', 'data')],
        prevent_initial_call=True
    )
    def add_device(n_clicks, rows, bus_rows):
        if not auth.is_logged_in():
            return no_update
        rows = rows or []
        bus_name = (bus_rows or [{}])[0].get('name', '')
        used = {r.get('slave_id') for r in rows if r.get('bus') == bus_name}
        slave_id = next(i for i in range(1, 248) if i not in used)
        return rows + [{'id': None, 'name': f'Sensor {len(rows) + 1}', 'bus': bus_name, 'slave_id': slave_id,
                        'function_code': 4, 'register_temp': 1, 'register_humidity': 2, 'scale_temp': 0.1,
                        'scale_humidity': 0.1, 'enabled': 'true'}]

    @app.callback(
        Output('device-table', 'dropdown'),
        Input('bus-table', 'data'),
        State('device-table', 'dropdown'),
        prevent_initial_call=True
    )
    def update_bus_choices(bus_rows, dropdown):
        """Bus keuze in de device tabel volgt de (nog niet opgeslagen) bustabel."""
        if not auth.is_logged_in():
            return no_update
        names = [r['name'] for r in bus_rows or [] if r.get('name')]
        return {**dropdown, 'bus': {'options': [{'label': n, 'value': n} for n in names], 'clearable': False}}

    @app.callback(
        Output('device-status', 'children'),
        Input('graph-update', 'n_intervals'),
        [State('main-tabs', 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def refresh_device_status(n, tab, lang):
        if tab != 'settings' or n % 3 or not auth.is_logged_in():
            return no_update
        return device_status_list(_t(lang))

    @app.callback(
        Output('alert-rule-table', 'data'),
        Input('add-rule', 'n_clicks'),
        State('alert-rule-table', 'data'),
        prevent_initial_call=True
    )
    def add_rule(n_clicks, rows):
        if not auth.is_logged_in():
            return no_update
        return (rows or []) + [{'scope': 0, 'metric': 'temperature', 'min_value': None, 'max_value': None,
                                'enabled': 'true'}]

    @app.callback(
        Output('test-status', 'children'),
        [Input('test-telegram', 'n_clicks'),
         Input('test-email', 'n_clicks')],
        [State({'type': 'setting', 'key': ALL}, 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def send_test(telegram_clicks, email_clicks, values, lang):
        """Testbericht met de waarden in het formulier (ook nog niet opgeslagen)."""
        t = _t(lang)
        if not auth.is_logged_in():
            return t['settings_locked']
        keys = [item['id']['key'] for item in callback_context.states_list[0]]
        config = settings.merged(dict(zip(keys, values)))
        channel = 'telegram' if callback_context.triggered_id == 'test-telegram' else 'email'
        required = settings.REQUIRED_WHEN['telegram_enabled' if channel == 'telegram' else 'smtp_enabled']
        missing = [t[f'lbl_{k}'] for k in required if not config.get(k)]
        if missing:
            return html.Span(t['test_missing'].format(fields=', '.join(missing)), style={'color': 'var(--alarm)'})
        error = alerts.send_now(channel, t['test_message'].format(time=time.strftime('%d-%m-%Y %H:%M')), config)
        if error:
            return html.Span(t['test_failed'].format(error=error), style={'color': 'var(--alarm)'})
        return html.Span(t['test_ok'], style={'color': 'var(--ok)'})

    @app.callback(
        Output('test-mqtt-status', 'children'),
        Input('test-mqtt', 'n_clicks'),
        [State({'type': 'setting', 'key': ALL}, 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def test_mqtt(n_clicks, values, lang):
        """Verbinding testen met de waarden in het formulier (ook nog niet opgeslagen)."""
        t = _t(lang)
        if not auth.is_logged_in():
            return t['settings_locked']
        keys = [item['id']['key'] for item in callback_context.states_list[0]]
        config = settings.merged(dict(zip(keys, values)))
        if not config['mqtt_host']:
            return html.Span(t['test_missing'].format(fields=t['lbl_mqtt_host']), style={'color': 'var(--alarm)'})
        error = mqtt_publisher.test_connection(config)
        if error:
            return html.Span(t['test_failed'].format(error=error), style={'color': 'var(--alarm)'})
        return html.Span(t['test_mqtt_ok'], style={'color': 'var(--ok)'})

    @app.callback(
        Output('mqtt-status', 'children'),
        Input('graph-update', 'n_intervals'),
        [State('main-tabs', 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def refresh_mqtt_status(n, tab, lang):
        if tab != 'settings' or n % 3 or not auth.is_logged_in():
            return no_update
        return mqtt_status_text(_t(lang))

    @app.callback(
        Output('alert-log', 'children'),
        Input('graph-update', 'n_intervals'),
        [State('main-tabs', 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def refresh_alert_log(n, tab, lang):
        if tab != 'settings' or n % 5 or not auth.is_logged_in():
            return no_update
        return alert_log_list(_t(lang))

    @app.callback(
        [Output('app-root', 'className', allow_duplicate=True),
         Output('view-toggle', 'value')],
        Input('settings-status', 'children'),
        prevent_initial_call=True
    )
    def apply_saved_display(status):
        """Na opslaan thema en weergave direct toepassen"""
        return f"theme-{settings.get('dashboard_theme')}", settings.get('dashboard_view')

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
            return t['settings_locked'], {'color': 'var(--alarm)', 'marginTop': '10px', 'fontWeight': 'bold'}, '', '', ''
        error = auth.change_password(current, new, repeat)
        if error:
            return t[error], {'color': 'var(--alarm)', 'marginTop': '10px', 'fontWeight': 'bold'}, '', '', ''
        return t['msg_password_changed'], {'color': 'var(--ok)', 'marginTop': '10px', 'fontWeight': 'bold'}, '', '', ''
