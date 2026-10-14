"""Settings tab: formulier opgebouwd uit settings.SCHEMA, Modbus bussen/devices, opslaan, wachtwoord wijzigen."""
import time
from urllib.parse import quote
from zoneinfo import available_timezones

from dash import ALL, Input, Output, State, callback_context, dash_table, dcc, html, no_update

import auth
import devices
import settings
from translations import LANGUAGE_NAMES, TRANSLATIONS

SECTIONS = ['modbus', 'regional', 'data', 'server', 'security']

BUS_COLUMNS = ['name', 'port', 'baudrate', 'bytesize', 'parity', 'stopbits', 'timeout', 'enabled']
DEVICE_COLUMNS = ['id', 'name', 'bus', 'slave_id', 'function_code', 'register_temp', 'register_humidity',
                  'scale_temp', 'scale_humidity', 'enabled']

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
    'style_cell': {'fontFamily': 'Arial, sans-serif', 'fontSize': '14px', 'padding': '6px', 'minWidth': '70px'},
    'style_header': {'backgroundColor': '#ecf0f1', 'fontWeight': 'bold', 'color': '#2c3e50'},
    'css': [{'selector': '.Select-menu-outer', 'rule': 'display: block !important'}],
}


def _modbus_section(t):
    buses, device_rows = devices.load_config()
    ports = devices.available_ports()
    small = {'fontSize': '12px', 'color': '#7f8c8d', 'marginBottom': '8px'}
    add_style = {**BUTTON_STYLE, 'padding': '6px 14px', 'fontSize': '14px', 'background': '#3498db'}
    return [
        html.H4(t['table_buses'], style={'color': '#2c3e50', 'marginBottom': '6px'}),
        _bus_table(buses, t),
        html.Div(t['hint_ports'].format(ports=', '.join(ports)) if ports else t['hint_no_ports'], style=small),
        html.Button(t['btn_add_bus'], id='add-bus', n_clicks=0, style=add_style),
        html.H4(t['table_devices'], style={'color': '#2c3e50', 'margin': '20px 0 6px'}),
        html.Div(t['hint_registers'], style=small),
        _device_table(device_rows, [b['name'] for b in buses], t),
        html.Button(t['btn_add_device'], id='add-device', n_clicks=0, style=add_style),
        html.Div(id='modbus-errors', style={'color': '#c0392b', 'fontWeight': 'bold', 'marginTop': '10px'}),
        html.H4(t['lbl_device_status'], style={'color': '#2c3e50', 'margin': '20px 0 6px'}),
        html.Div(id='device-status', children=device_status_list(t)),
    ]


def device_status_list(t):
    """Live status per device: laatste waarden of laatste fout."""
    items = []
    now = time.time()
    for dev in devices.load_config()[1]:
        state = devices.status(dev['id'])
        if not dev['enabled']:
            text, color = t['status_disabled'], '#7f8c8d'
        elif state.get('ok_at') and not state.get('error'):
            text = t['status_ok'].format(temp=state['temperature'], hum=state['humidity'], ago=int(now - state['ok_at']))
            color = '#27ae60'
        elif state.get('error'):
            text, color = t['status_error'].format(error=state['error']), '#c0392b'
        else:
            text, color = t['status_never'], '#7f8c8d'
        items.append(html.Li([html.Strong(f"#{dev['id']} {dev['name']} ({dev['bus']}, slave {dev['slave_id']}): "),
                              html.Span(text, style={'color': color})]))
    return html.Ul(items, style={'paddingLeft': '20px', 'margin': '0'})


def _section(name, values, t):
    keys = [k for k, spec in settings.SCHEMA.items() if spec['section'] == name]
    extra = _modbus_section(t) if name == 'modbus' else []
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
         State('selected-language', 'data'),
         State('bus-table', 'data'),
         State('device-table', 'data')],
        prevent_initial_call=True
    )
    def save_settings(n_clicks, values, lang, bus_rows, device_rows):
        t = _t(lang)
        ok_style = {'marginTop': '10px', 'fontWeight': 'bold', 'color': '#27ae60'}
        bad_style = {'marginTop': '10px', 'fontWeight': 'bold', 'color': '#c0392b'}
        if not auth.is_logged_in():
            return no_update, t['settings_locked'], bad_style
        keys = [item['id']['key'] for item in callback_context.states_list[0]]

        # Eerst de Modbus configuratie valideren, zodat bij een fout niets wordt opgeslagen
        _, _, modbus_errors = devices.validate_config(bus_rows or [], device_rows or [])
        if modbus_errors:
            return [''] * len(keys), t['msg_save_failed'], bad_style

        submitted = dict(zip(keys, values))
        before = settings.public_values()
        errors = settings.save(submitted)
        field_errors = [t.get(errors[k], errors[k]) if k in errors else '' for k in keys]
        if errors:
            return field_errors, t['msg_save_failed'], bad_style
        devices.save_config(bus_rows or [], device_rows or [])

        restart_changed = any(settings.SCHEMA[k].get('restart') and settings.get(k) != before[k] for k in keys)
        message = t['msg_saved_restart'] if restart_changed else t['msg_saved']
        return field_errors, message, ok_style

    @app.callback(
        [Output('modbus-errors', 'children'),
         Output('bus-table', 'style_data_conditional'),
         Output('device-table', 'style_data_conditional'),
         Output('bus-table', 'data', allow_duplicate=True),
         Output('device-table', 'data', allow_duplicate=True)],
        Input('settings-save', 'n_clicks'),
        [State('bus-table', 'data'),
         State('device-table', 'data'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def show_modbus_errors(n_clicks, bus_rows, device_rows, lang):
        """Markeer foute cellen; na succesvol opslaan de tabellen herladen (nieuwe rijen krijgen een id)."""
        t = _t(lang)
        if not auth.is_logged_in():
            return no_update, no_update, no_update, no_update, no_update
        _, _, errors = devices.validate_config(bus_rows or [], device_rows or [])
        messages, styles = [], {'buses': [], 'devices': []}
        for table in ('buses', 'devices'):
            for row, fields in errors.get(table, {}).items():
                for field, code in fields.items():
                    messages.append(html.Li(t['row_error'].format(table=t[f'table_{table}'], row=row + 1,
                                                                  field=t[f'col_{field}'], error=t.get(code, code))))
                    styles[table].append({'if': {'row_index': row, 'column_id': field},
                                          'backgroundColor': '#fadbd8', 'color': '#c0392b'})
        if errors:
            return html.Ul(messages), styles['buses'], styles['devices'], no_update, no_update
        buses, device_rows = devices.load_config()
        return '', [], [], _table_rows(buses, BUS_COLUMNS), _table_rows(device_rows, DEVICE_COLUMNS)

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
