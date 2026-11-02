"""Settings tab: formulier opgebouwd uit settings.SCHEMA, Modbus bussen/devices, opslaan, wachtwoord wijzigen."""
import json
import time
from urllib.parse import quote
from zoneinfo import available_timezones

from dash import ALL, Input, Output, State, callback_context, dcc, html, no_update

import alerts
import auth
import devices
import layout
import modbus_reader
import mqtt_publisher
import settings
import zones
from translations import LANGUAGE_NAMES, TRANSLATIONS

SECTIONS = ['display', 'modbus', 'notify', 'alerts', 'wood', 'mqtt', 'regional', 'data', 'server', 'security']

# Bussen, sensoren en grenswaarden: één regel gewone formuliervelden per item (geen DataTable: daar verplaatsen
# de pijltjestoetsen de cel in plaats van de cursor en zijn de keuzelijsten in cellen onbetrouwbaar)
BUS_COLUMNS = ['name', 'port', 'baudrate', 'bytesize', 'parity', 'stopbits', 'timeout', 'enabled']
DEVICE_COLUMNS = ['name', 'bus', 'slave_id', 'function_code', 'register_temp', 'register_humidity', 'data_type',
                  'byte_order', 'scale_temp', 'scale_humidity', 'offset_temp', 'offset_humidity', 'enabled']
BYTE_ORDER_LABELS = {'ABCD': 'ABCD · big endian', 'DCBA': 'DCBA · little endian', 'BADC': 'BADC · byte swap',
                     'CDAB': 'CDAB · word swap'}
RULE_COLUMNS = ['scope', 'metric', 'level', 'min_value', 'max_value', 'enabled']
ZONE_COLUMNS = ['name', 'scope', 'mode', 'level', 'color', 'temp_min', 'temp_max', 'rh_min', 'rh_max', 'enabled']
RECT_FIELDS = ['temp_min', 'temp_max', 'rh_min', 'rh_max']
TABLE_COLUMNS = {'buses': BUS_COLUMNS, 'devices': DEVICE_COLUMNS, 'rules': RULE_COLUMNS, 'zones': ZONE_COLUMNS}
HIDDEN_FIELDS = {'zones': ['shape', 'points']}   # meegestuurd zonder zichtbaar veld (getekende vorm)
WIDE_FIELDS = {'name', 'port', 'bus', 'scope', 'metric', 'byte_order', 'mode'}   # twee kolommen breed

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


def table_rows(table):
    """Opgeslagen bussen, sensoren, grenswaarden of zones als formulierregels (aan/uit als 'true'/'false')."""
    if table == 'zones':
        return [{'id': z['id'], 'scope': z['device_id'] or 0, 'name': z['name'], 'mode': z['mode'], 'level': z['level'],
                 'color': z['color'], 'shape': z['shape'], 'points': json.dumps(z['points']),
                 **{f: z[f] for f in RECT_FIELDS}, 'enabled': 'true' if z['enabled'] else 'false'} for z in zones.load()]
    if table == 'rules':
        return [{'id': None, 'scope': r['device_id'] or 0, 'metric': r['metric'], 'level': r['level'],
                 'min_value': r['min_value'], 'max_value': r['max_value'], 'enabled': 'true' if r['enabled'] else 'false'}
                for r in alerts.load_rules()]
    buses, device_rows = devices.load_config()
    return [{**{c: ('true' if r[c] else 'false') if isinstance(r.get(c), bool) else r.get(c) for c in TABLE_COLUMNS[table]},
             'id': r['id']} for r in (buses if table == 'buses' else device_rows)]


def collect(states):
    """Formulierwaarden (callback_context.states_list) terug naar regels, in schermvolgorde."""
    rows = {}
    for item in states:
        rows.setdefault(item['id']['row'], {})[item['id']['field']] = item.get('value')
    result = []
    for index in sorted(rows):
        row = rows[index]
        if 'enabled' in row:
            row['enabled'] = 'true' if row['enabled'] else 'false'   # vinkje: ['on'] of []
        row['id'] = row.get('id') or None
        result.append(row)
    return result


def _choices(table, field, t, bus_names):
    """Keuzes voor een veld, None = vrij invoerveld."""
    plain = {'baudrate': devices.BAUDRATES, 'bytesize': [7, 8], 'parity': ['N', 'E', 'O'], 'stopbits': [1, 2]}
    if table == 'buses' and field in plain:
        return [{'label': str(v), 'value': v} for v in plain[field]]
    if field == 'bus':
        return [{'label': n, 'value': n} for n in bus_names]
    if field == 'data_type':
        return [{'label': v, 'value': v} for v in devices.DEVICE_FIELDS['data_type']['choices']]
    if field == 'byte_order':
        return [{'label': BYTE_ORDER_LABELS[v], 'value': v} for v in devices.DEVICE_FIELDS['byte_order']['choices']]
    if field == 'function_code':
        return [{'label': t[f'opt_function_code_{v}'], 'value': v} for v in (4, 3)]
    if field == 'scope':
        return [{'label': t['opt_all_devices'], 'value': 0}] + [
            {'label': f"#{d['id']} {d['name']}", 'value': d['id']} for d in devices.list_devices()]
    if field == 'metric':
        return [{'label': t[alerts.METRICS[m][0]], 'value': m} for m in alerts.METRICS]
    if field == 'level':
        return [{'label': t[f'opt_level_{v}'], 'value': v} for v in alerts.LEVELS]
    if field == 'mode':
        return [{'label': t[f'opt_mode_{v}'], 'value': v} for v in zones.MODES]
    if field == 'color':
        return [{'label': html.Span([html.Span(className='swatch', style={'--series': hex_color}), t[f'opt_color_{v}']],
                                    className='color-option'), 'value': v} for v, hex_color in zones.COLORS.items()]
    return None


def _control(table, index, field, value, t, bus_names):
    field_id = {'type': 'cfg', 'table': table, 'row': index, 'field': field}
    options = _choices(table, field, t, bus_names)
    if field == 'enabled':
        return dcc.Checklist(id=field_id, options=[{'label': ' ' + t['lbl_enabled'], 'value': 'on'}],
                             value=['on'] if str(value).lower() in ('true', '1') else [], className='cfg-switch')
    if options is not None:
        return dcc.Dropdown(id=field_id, options=options, value=value, clearable=False, searchable=False)
    if field in ('name', 'port'):
        # Poort: vrij tekstveld met de gevonden adapters als suggesties (datalist)
        return dcc.Input(id=field_id, type='text', value=value, className='input', autoComplete='off', spellCheck=False,
                         list='port-options' if field == 'port' else None)
    return dcc.Input(id=field_id, type='number', value=value, step='any', className='input')


def row_form(table, rows, t, bus_names=None):
    """Formulierregels voor bussen, sensoren of grenswaarden."""
    if bus_names is None:
        bus_names = [b['name'] for b in devices.load_config()[0]]
    items = []
    for index, row in enumerate(rows):
        cells = [dcc.Input(id={'type': 'cfg', 'table': table, 'row': index, 'field': field}, type='hidden',
                           value=row.get(field)) for field in ['id'] + HIDDEN_FIELDS.get(table, [])]
        for field in TABLE_COLUMNS[table]:
            cell_id = {'type': 'cfg-cell', 'table': table, 'row': index, 'field': field}
            if row.get('shape') == 'polygon' and field in RECT_FIELDS:
                if field == RECT_FIELDS[0]:   # getekende vorm: één vak in plaats van vier min/max-velden
                    cells.append(html.Div(id=cell_id, className='cfg-cell wide', children=[
                        html.Span(t['col_shape'], className='cfg-label'),
                        html.Span(t['zone_free_shape'], className='cfg-static')]))
                continue
            control = _control(table, index, field, row.get(field), t, bus_names)
            # Label om het veld heen (koppeling zonder id); het vinkje heeft al een eigen label
            wrapper = html.Div if field == 'enabled' else html.Label
            cells.append(wrapper(id=cell_id, className=_cell_class(field), children=[
                html.Span(t[f'col_{field}'], className='cfg-label'), control]))
        cells.append(html.Button(t['btn_remove'], id={'type': 'cfg-remove', 'table': table, 'row': index}, n_clicks=0,
                                 className='btn btn-link cfg-remove'))
        items.append(html.Div(cells, className='cfg-row'))
    return items or [html.Div(t['cfg_empty'], className='cfg-empty')]


def _fields(table):
    """Pattern-matching id van alle velden (incl. verborgen id) van één formulier."""
    return {'type': 'cfg', 'table': table, 'row': ALL, 'field': ALL}


def _cell_class(field, invalid=False):
    return 'cfg-cell' + (' wide' if field in WIDE_FIELDS else '') + (' is-invalid' if invalid else '')


def _new_row(table, rows, bus_names):
    """Nieuwe regel met handige standaardwaarden (vrije poort, vrij slave adres)."""
    if table == 'buses':
        used = {r.get('port') for r in rows}
        port = next((p for p in devices.available_ports() if p not in used), '')
        return {'id': None, 'name': f'Bus {len(rows) + 1}', 'port': port, 'baudrate': 9600, 'bytesize': 8,
                'parity': 'N', 'stopbits': 1, 'timeout': 1.0, 'enabled': 'true'}
    if table == 'devices':
        bus_name = next((n for n in bus_names if n), '')
        used = {r.get('slave_id') for r in rows if r.get('bus') == bus_name}
        return {'id': None, 'name': f'Sensor {len(rows) + 1}', 'bus': bus_name,
                'slave_id': next(i for i in range(1, 248) if i not in used), 'function_code': 4, 'register_temp': 1,
                'register_humidity': 2, 'data_type': 'int16', 'byte_order': 'ABCD', 'scale_temp': 0.1,
                'scale_humidity': 0.1, 'offset_temp': 0, 'offset_humidity': 0, 'enabled': 'true'}
    if table == 'zones':
        return {'id': None, 'scope': 0, 'name': f'Zone {len(rows) + 1}', 'mode': 'keep_inside', 'level': 'warning',
                'color': 'green', 'shape': 'rect', 'points': None, 'temp_min': 18, 'temp_max': 24, 'rh_min': 40,
                'rh_max': 60, 'enabled': 'true'}
    return {'id': None, 'scope': 0, 'metric': 'temperature', 'level': 'alarm', 'min_value': None, 'max_value': None,
            'enabled': 'true'}


def _modbus_section(t):
    ports = devices.available_ports()
    return [
        html.Datalist(id='port-options', children=[html.Option(value=p) for p in ports]),
        html.H4(t['table_buses']),
        html.Div(id='buses-form', className='cfg-list', children=row_form('buses', table_rows('buses'), t)),
        html.Div(t['hint_ports'].format(ports=', '.join(ports)) if ports else t['hint_no_ports'], className='field-hint'),
        html.Button(t['btn_add_bus'], id='add-bus', n_clicks=0, className='btn btn-small'),
        html.H4(t['table_devices']),
        html.Div(t['hint_registers'], className='field-hint'),
        html.Div(id='devices-form', className='cfg-list', children=row_form('devices', table_rows('devices'), t)),
        html.Button(t['btn_add_device'], id='add-device', n_clicks=0, className='btn btn-small'),
        html.Div(id='modbus-errors', className='field-error'),
        html.H4(t['lbl_device_status']),
        html.Div(id='device-status', children=device_status_list(t)),
        html.H4(t['lbl_scan']),
        html.Div(t['hint_scan'], className='field-hint'),
        html.Div(className='draw-actions', children=[
            dcc.Dropdown(id='scan-bus-select', options=[b['name'] for b in devices.load_config()[0]],
                         value=next((b['name'] for b in devices.load_config()[0]), None), clearable=False,
                         searchable=False, style={'minWidth': '200px'}),
            html.Button(t['btn_scan'], id='scan-bus-btn', n_clicks=0, className='btn btn-small'),
        ]),
        dcc.Loading(html.Div(id='scan-result', className='status-list'), type='dot'),
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


def _alerts_section(t):
    return [
        html.H4(t['table_rules']),
        html.Div(t['hint_rules'], className='field-hint'),
        html.Div(id='rules-form', className='cfg-list', children=row_form('rules', table_rows('rules'), t)),
        html.Button(t['btn_add_rule'], id='add-rule', n_clicks=0, className='btn btn-small'),
        html.Div(id='rule-errors', className='field-error'),
        html.H4(t['table_zones']),
        html.Div(t['hint_zones'], className='field-hint'),
        html.Div(id='zones-form', className='cfg-list', children=row_form('zones', table_rows('zones'), t)),
        html.Button(t['btn_add_zone'], id='add-zone', n_clicks=0, className='btn btn-small'),
        html.Div(id='zone-errors', className='field-error'),
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
        [Output('main-tabs', 'value'),
         Output('url', 'search')],
        [Input('url', 'search'),
         Input('main-tabs', 'value')]
    )
    def sync_tab_url(search, tab):
        """Tab en adresbalk gelijk houden: ?tab=settings alleen zolang Settings open is (F5 blijft op de tab)."""
        if callback_context.triggered_id == 'main-tabs':
            wanted = '?tab=settings' if tab == 'settings' else ''
            return no_update, wanted if (search or '') != wanted else no_update
        return ('settings' if search and 'tab=settings' in search else no_update), no_update

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
         State(_fields('buses'), 'value'),
         State(_fields('devices'), 'value'),
         State(_fields('rules'), 'value'),
         State(_fields('zones'), 'value')],
        prevent_initial_call=True
    )
    def save_settings(n_clicks, values, lang, bus_values, device_values, rule_values, zone_values):
        t = _t(lang)
        ok_style = {'marginTop': '10px', 'fontWeight': 'bold', 'color': 'var(--ok)'}
        bad_style = {'marginTop': '10px', 'fontWeight': 'bold', 'color': 'var(--alarm)'}
        if not auth.is_logged_in():
            return no_update, t['settings_locked'], bad_style
        keys = [item['id']['key'] for item in callback_context.states_list[0]]
        bus_rows, device_rows, rule_rows, zone_rows = (collect(callback_context.states_list[i]) for i in (2, 3, 4, 5))

        # Eerst de Modbus configuratie, grenswaarden en zones valideren, zodat bij een fout niets wordt opgeslagen
        _, _, modbus_errors = devices.validate_config(bus_rows or [], device_rows or [])
        _, rule_errors = alerts.validate_rules(rule_rows or [])
        _, zone_errors = zones.validate(zone_rows or [])
        if modbus_errors or rule_errors or zone_errors:
            return [''] * len(keys), t['msg_save_failed'], bad_style

        submitted = dict(zip(keys, values))
        before = settings.public_values()
        errors = settings.save(submitted)
        field_errors = [t.get(errors[k], errors[k]) if k in errors else '' for k in keys]
        if errors:
            return field_errors, t['msg_save_failed'], bad_style
        devices.save_config(bus_rows or [], device_rows or [])
        zones.save(zone_rows or [])
        alerts.save_rules(rule_rows or [])

        restart_changed = any(settings.SCHEMA[k].get('restart') and settings.get(k) != before[k] for k in keys)
        message = t['msg_saved_restart'] if restart_changed else t['msg_saved']
        return field_errors, message, ok_style

    @app.callback(
        [Output('modbus-errors', 'children'),
         Output('rule-errors', 'children'),
         Output('zone-errors', 'children'),
         Output('buses-form', 'children', allow_duplicate=True),
         Output('devices-form', 'children', allow_duplicate=True),
         Output('rules-form', 'children', allow_duplicate=True),
         Output('zones-form', 'children', allow_duplicate=True),
         Output({'type': 'cfg-cell', 'table': ALL, 'row': ALL, 'field': ALL}, 'className')],
        Input('settings-status', 'children'),   # na save_settings: anders kan het herladen vóór het opslaan lopen
        [State(_fields('buses'), 'value'),
         State(_fields('devices'), 'value'),
         State(_fields('rules'), 'value'),
         State(_fields('zones'), 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def show_modbus_errors(status, bus_values, device_values, rule_values, zone_values, lang):
        """Markeer foute velden; na succesvol opslaan de formulieren herladen (nieuwe regels krijgen een id)."""
        t = _t(lang)
        if not auth.is_logged_in():
            return (no_update,) * 8
        bus_rows, device_rows, rule_rows, zone_rows = (collect(callback_context.states_list[i]) for i in (0, 1, 2, 3))
        _, _, errors = devices.validate_config(bus_rows, device_rows)
        _, rule_errors = alerts.validate_rules(rule_rows)
        _, zone_errors = zones.validate(zone_rows)
        if rule_errors:
            errors = {**errors, 'rules': rule_errors}
        if zone_errors:
            errors = {**errors, 'zones': zone_errors}
        messages = {'modbus': [], 'rules': [], 'zones': []}
        for table in ('buses', 'devices', 'rules', 'zones'):
            for row, fields in errors.get(table, {}).items():
                for field, code in fields.items():
                    messages[table if table in ('rules', 'zones') else 'modbus'].append(html.Li(t['row_error'].format(
                        table=t[f'table_{table}'], row=row + 1, field=t[f'col_{field}'], error=t.get(code, code))))
        cells = callback_context.outputs_list[-1]
        classes = [_cell_class(c['id']['field'], c['id']['field'] in errors.get(c['id']['table'], {}).get(c['id']['row'], {}))
                   for c in cells]
        modbus_text = html.Ul(messages['modbus']) if messages['modbus'] else ''
        rules_text = html.Ul(messages['rules']) if messages['rules'] else ''
        zones_text = html.Ul(messages['zones']) if messages['zones'] else ''
        if errors or status not in (t['msg_saved'], t['msg_saved_restart']):
            return modbus_text, rules_text, zones_text, no_update, no_update, no_update, no_update, classes
        return ('', '', '', row_form('buses', table_rows('buses'), t), row_form('devices', table_rows('devices'), t),
                row_form('rules', table_rows('rules'), t), row_form('zones', table_rows('zones'), t), classes)

    def edit_rows(table, t, bus_names):
        """Regel toevoegen of verwijderen; de rest van het formulier houdt de (nog niet opgeslagen) invoer."""
        rows = collect(callback_context.states_list[0])
        trigger = callback_context.triggered_id
        if isinstance(trigger, dict):
            if not callback_context.triggered[0].get('value'):
                return no_update   # nieuw getekende verwijderknop, geen klik
            rows.pop(trigger['row'])
        else:
            rows.append(_new_row(table, rows, bus_names))
        return row_form(table, rows, t, bus_names)

    @app.callback(
        Output('buses-form', 'children'),
        [Input('add-bus', 'n_clicks'),
         Input({'type': 'cfg-remove', 'table': 'buses', 'row': ALL}, 'n_clicks')],
        [State(_fields('buses'), 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def edit_buses(n_clicks, remove_clicks, values, lang):
        if not auth.is_logged_in():
            return no_update
        return edit_rows('buses', _t(lang), bus_names=[])

    @app.callback(
        Output('devices-form', 'children'),
        [Input('add-device', 'n_clicks'),
         Input({'type': 'cfg-remove', 'table': 'devices', 'row': ALL}, 'n_clicks')],
        [State(_fields('devices'), 'value'),
         State({'type': 'cfg', 'table': 'buses', 'row': ALL, 'field': 'name'}, 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def edit_devices(n_clicks, remove_clicks, values, bus_names, lang):
        if not auth.is_logged_in():
            return no_update
        return edit_rows('devices', _t(lang), bus_names=[n for n in bus_names if n])

    @app.callback(
        Output('rules-form', 'children'),
        [Input('add-rule', 'n_clicks'),
         Input({'type': 'cfg-remove', 'table': 'rules', 'row': ALL}, 'n_clicks')],
        [State(_fields('rules'), 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def edit_rules(n_clicks, remove_clicks, values, lang):
        if not auth.is_logged_in():
            return no_update
        return edit_rows('rules', _t(lang), bus_names=[])

    @app.callback(
        Output('zones-form', 'children'),
        [Input('add-zone', 'n_clicks'),
         Input({'type': 'cfg-remove', 'table': 'zones', 'row': ALL}, 'n_clicks')],
        [State(_fields('zones'), 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def edit_zones(n_clicks, remove_clicks, values, lang):
        if not auth.is_logged_in():
            return no_update
        return edit_rows('zones', _t(lang), bus_names=[])

    @app.callback(
        Output({'type': 'cfg', 'table': 'devices', 'row': ALL, 'field': 'bus'}, 'options'),
        Input({'type': 'cfg', 'table': 'buses', 'row': ALL, 'field': 'name'}, 'value'),
        prevent_initial_call=True
    )
    def update_bus_choices(names):
        """Buskeuze bij de sensoren volgt de (nog niet opgeslagen) bussen."""
        if not auth.is_logged_in():
            return no_update
        options = [{'label': n, 'value': n} for n in names if n]
        return [options] * len(callback_context.outputs_list)

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
        Output('scan-result', 'children'),
        Input('scan-bus-btn', 'n_clicks'),
        [State('scan-bus-select', 'value'),
         State('selected-language', 'data')],
        prevent_initial_call=True
    )
    def scan_bus_now(n_clicks, bus_name, lang):
        """Welke slaves antwoorden op een opgeslagen bus (alleen ingelogd: opent de seriële poort)."""
        t = _t(lang)
        if not auth.is_logged_in():
            return t['settings_locked']
        bus = next((b for b in devices.load_config()[0] if b['name'] == bus_name), None)
        if bus is None:
            return no_update
        try:
            found = modbus_reader.scan_bus(bus, range(1, 31))
        except Exception as e:   # interface weg of in gebruik door een ander programma
            return html.Span(t['scan_failed'].format(error=e), style={'color': 'var(--alarm)'})
        if not found:
            return t['scan_none']
        return html.Ul([html.Li(t['scan_found_error'].format(slave=f['slave_id'], error=f['error']) if 'error' in f
                                else t['scan_found'].format(slave=f['slave_id'], temperature=f'{f["temperature"]:.1f}',
                                                            humidity=f'{f["humidity"]:.1f}')) for f in found])

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
         Output('view-toggle', 'value'),
         Output('metric-tabs', 'options', allow_duplicate=True),
         Output('metric-tabs', 'value'),
         Output('mollier-panel', 'style'),
         Output('wood-panel', 'style')],
        Input('settings-status', 'children'),
        [State('selected-language', 'data'),
         State('metric-tabs', 'value')],
        prevent_initial_call=True
    )
    def apply_saved_display(status, lang, metric):
        """Na opslaan thema, weergave, comfort, Mollier en houtvocht direct toepassen"""
        options = layout.metric_options(_t(lang))
        if metric not in [o['value'] for o in options]:
            metric = 'temperature'
        return (f'theme-{layout.current_theme()}', settings.get('dashboard_view'), options, metric,
                layout.mollier_style(), layout.wood_style())

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
