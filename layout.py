from dash import dcc, html

import settings
from translations import LANGUAGE_NAMES, TRANSLATIONS

# Design tokens per thema (CSS variabelen) en componentstijlen. Alles lokaal: geen externe fonts of CDN's.
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            .theme-dark, .theme-dark .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table {
                --bg: #1b1f23; --panel: #24292e; --panel-2: #1f2428; --line: #343a41; --line-strong: #4a525a;
                --text: #e6e8e3; --muted: #a2a9a2; --cell: #141a17; --digit: #d4ecc9;
                --accent: #6aa8e8; --accent-ink: #0f1a26; --hover: #2c3238;
                --ok: #0ca30c; --warn: #fab219; --alarm: #e5534b; --offline: #7d838a;
                --alarm-cell: #3a1d1b; --warn-cell: #33291a;
                color-scheme: dark;
            }
            .theme-light, .theme-light .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table {
                --bg: #e8e9e4; --panel: #f7f7f3; --panel-2: #fbfbf8; --line: #cdd0c9; --line-strong: #a9ada5;
                --text: #1b1f23; --muted: #555c55; --cell: #dde5d6; --digit: #1e2a1b;
                --accent: #1f5fa8; --accent-ink: #ffffff; --hover: #eceee8;
                --ok: #0b8a0b; --warn: #c98500; --alarm: #d03b3b; --offline: #7d838a;
                --alarm-cell: #f6dcd9; --warn-cell: #f6ead0;
                color-scheme: light;
            }
            /* De DataTable zet eigen --accent/--hover/--muted op zijn tabel (roze focus, witte opties): thema-tokens
               hierboven daarom ook op die tabel. */
            :root { --sans: system-ui, -apple-system, "Segoe UI", Roboto, Ubuntu, Cantarell, "Noto Sans", sans-serif;
                    --mono: ui-monospace, "DejaVu Sans Mono", "Cascadia Mono", Menlo, Consolas, monospace; }
            html, body { margin: 0; }
            body { font-family: var(--sans); }
            #app-root { min-height: 100vh; background: var(--bg); color: var(--text); font-size: 14px; }
            #app-root ::selection { background: var(--accent); color: var(--accent-ink); }
            #app-root * { box-sizing: border-box; scrollbar-color: var(--line-strong) transparent; }
            #app-root :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
            .d { font-family: var(--mono); font-variant-numeric: tabular-nums; }

            /* Header */
            .topbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
                      padding: 10px 24px; background: var(--panel); border-bottom: 1px solid var(--line); }
            .topbar-left, .topbar-right { display: flex; align-items: center; gap: 22px; flex-wrap: wrap; }
            .brand { font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: 13px; }
            .summary { font-family: var(--mono); font-size: 12px; color: var(--muted); letter-spacing: .04em; }
            .summary .n-alarm { color: var(--alarm); } .summary .n-warn { color: var(--warn); }
            .nav { display: flex; gap: 18px; }
            .nav input, .seg input, .tabs input { position: absolute; opacity: 0; pointer-events: none; }
            .nav label { cursor: pointer; padding: 6px 0; color: var(--muted); border-bottom: 2px solid transparent; }
            .nav label:has(input:checked) { color: var(--text); border-bottom-color: var(--accent); }
            .nav label:hover, .tabs label:hover { color: var(--text); }
            .nav label:has(input:focus-visible), .seg label:has(input:focus-visible), .tabs label:has(input:focus-visible) {
                outline: 2px solid var(--accent); outline-offset: 2px; }
            .seg { display: inline-flex; border: 1px solid var(--line); }
            .seg label { cursor: pointer; padding: 5px 12px; font-size: 13px; color: var(--muted); }
            .seg label + label { border-left: 1px solid var(--line); }
            .seg label:has(input:checked) { background: var(--hover); color: var(--text); }
            .lang { width: 76px; }

            /* Pagina */
            .page { padding: 18px 24px 40px; display: grid; gap: 16px; max-width: 1600px; margin: 0 auto; }
            .page > * { min-width: 0; }
            .panel { background: var(--panel); border: 1px solid var(--line); }
            .panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
                          border-bottom: 1px solid var(--line); padding: 0 12px; min-height: 44px; }
            .panel-title { font-size: 12px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); padding: 12px 4px; }
            .panel-body { padding: 12px 14px; }
            .panel-foot { padding: 0 16px 12px; font-size: 12px; color: var(--muted); }
            .tabs { display: flex; flex-wrap: wrap; }
            .tabs label { cursor: pointer; padding: 12px 14px 10px; color: var(--muted); border-bottom: 2px solid transparent; }
            .tabs label:has(input:checked) { color: var(--text); border-bottom-color: var(--accent); }
            .controls { display: flex; gap: 10px; align-items: center; padding: 6px 0; }
            .controls > div:first-child { width: 230px; } .controls > div:last-child { width: 210px; }
            .st.st-inline { display: none; margin-top: 4px; }

            /* Status */
            .st { display: inline-flex; align-items: center; gap: 7px; font-family: var(--mono); font-size: 12px; white-space: nowrap; }
            .st::before { content: ""; width: 9px; height: 9px; border-radius: 50%; background: var(--st); flex: none; }
            .st-ok { --st: var(--ok); } .st-warn { --st: var(--warn); } .st-alarm { --st: var(--alarm); }
            .st-offline, .st-never { --st: var(--offline); }
            .st-sub { display: block; color: var(--muted); font-family: var(--mono); font-size: 11px; margin: 2px 0 0 16px; }

            /* Waardecellen (LCD) */
            .lcd { display: inline-block; background: var(--cell); color: var(--digit); font-family: var(--mono);
                    font-variant-numeric: tabular-nums; padding: 6px 10px; min-width: 108px; text-align: right;
                    font-size: 24px; line-height: 1.15; border: 1px solid transparent; white-space: nowrap; }
            .lcd .u { font-size: 12px; color: var(--muted); margin-left: 5px; }
            .lcd.is-alarm { background: var(--alarm-cell); border-color: var(--alarm); }
            .lcd.is-warn { background: var(--warn-cell); border-color: var(--warn); }
            .is-offline { opacity: .5; }

            /* Bord */
            .board-wrap { overflow-x: auto; }
            .board { width: 100%; border-collapse: collapse; }
            .board th { text-align: left; font-weight: 600; font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
                        color: var(--muted); padding: 10px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
            .board td { padding: 8px 12px; border-bottom: 1px solid var(--line); vertical-align: middle; }
            .board tr:last-child td { border-bottom: 0; }
            .board .bar { width: 4px; min-width: 4px; max-width: 4px; padding: 0; }
            .board td.bar { background: var(--st); }
            .board .name { font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 8px; }
            .board .where { font-family: var(--mono); font-size: 11px; color: var(--muted); margin-top: 2px; }
            .swatch { width: 12px; height: 3px; background: var(--series); flex: none; }
            .board .comfort { color: var(--muted); font-size: 13px; }
            .board tr.row:hover td:not(.bar) { background: var(--hover); }
            .spark { display: block; }

            /* Meters */
            .meters { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
            .meter { background: var(--panel); border: 1px solid var(--line); border-top: 3px solid var(--st); padding: 14px 16px; }
            .meter-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
            .meter .name { font-weight: 600; display: flex; align-items: center; gap: 8px; }
            .meter .where { font-family: var(--mono); font-size: 11px; color: var(--muted); margin-top: 2px; }
            .meter-display { background: var(--cell); margin-top: 12px; padding: 12px 14px; display: grid; gap: 6px; }
            .meter-display .v1, .meter-display .v2 { font-family: var(--mono); font-variant-numeric: tabular-nums; color: var(--digit); line-height: 1.1; }
            .meter-display .v1 { font-size: 46px; } .meter-display .v2 { font-size: 28px; }
            .meter-display .u { font-size: 13px; color: var(--muted); margin-left: 6px; }
            .meter-display .is-alarm { color: var(--alarm); } .meter-display .is-warn { color: var(--warn); }
            .meter-stats { display: flex; justify-content: space-between; gap: 8px; margin-top: 10px; font-family: var(--mono); font-size: 12px; color: var(--muted); }
            .meter .spark { margin-top: 8px; width: 100%; }
            .empty { padding: 28px; color: var(--muted); }

            /* Mollier + historie */
            .history-bar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 0 16px 14px; }
            .hint { color: var(--muted); font-size: 13px; }
            .slider-box { padding: 4px 16px 18px; }
            .slider-time { font-family: var(--mono); font-size: 15px; margin-bottom: 8px; }

            /* Knoppen en velden */
            .btn { font: inherit; font-size: 14px; font-weight: 600; padding: 8px 16px; border: 1px solid var(--line-strong);
                   background: var(--panel); color: var(--text); cursor: pointer; text-decoration: none; display: inline-block; }
            .btn:hover { background: var(--hover); }
            .btn-primary { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
            .btn-primary:hover { background: var(--accent); filter: brightness(1.08); }
            .btn-small { padding: 5px 12px; font-size: 13px; }
            .btn-link { background: none; border: 0; color: var(--muted); padding: 4px 6px; font-weight: 400; }
            .btn-link:hover { color: var(--text); background: none; }
            .field input, .time-row input, .settings > div > input, input.input {
                font: inherit; color: var(--text); background: var(--panel-2); border: 1px solid var(--line-strong); padding: 7px 9px; border-radius: 0; }
            #app-root input::placeholder { color: var(--muted); }
            #app-root input[type=checkbox] { accent-color: var(--accent); width: 16px; height: 16px; vertical-align: middle; }
            .Select-control { background: var(--panel-2) !important; border: 1px solid var(--line-strong) !important; border-radius: 0 !important; }
            .Select-value-label, .Select-input > input { color: var(--text) !important; }
            .Select-placeholder { color: var(--muted) !important; }
            .Select-menu-outer { background: var(--panel) !important; border: 1px solid var(--line-strong) !important; border-radius: 0 !important; z-index: 30 !important; }
            .Select-option, .VirtualizedSelectOption { background: var(--panel) !important; color: var(--text) !important; }
            .Select-option.is-focused, .VirtualizedSelectFocusedOption { background: var(--hover) !important; }
            .Select-option.is-selected, .VirtualizedSelectSelectedOption { color: var(--accent) !important; font-weight: 600; }
            .Select-menu { background: var(--panel) !important; }
            .Select-arrow { border-top-color: var(--muted) !important; }
            .is-focused:not(.is-open) > .Select-control { box-shadow: 0 0 0 2px var(--accent) !important; }

            /* Slider en datumkiezer */
            .rc-slider-rail { background: var(--line) !important; }
            .rc-slider-track { background: var(--accent) !important; }
            .rc-slider-handle { border-color: var(--accent) !important; background: var(--panel) !important; }
            .rc-slider-handle, .rc-slider-handle:focus, .rc-slider-handle:active { box-shadow: none !important; }
            .rc-slider-handle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
            .rc-slider-mark-text { color: var(--muted) !important; }
            .SingleDatePickerInput, .DateInput, .DateInput_input { background: var(--panel-2) !important; color: var(--text) !important; }
            .SingleDatePickerInput__withBorder { border: 1px solid var(--line-strong) !important; border-radius: 0 !important; }

            /* Keuzevenster */
            .modal-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, .55); z-index: 50; overflow: auto; }
            .modal { position: relative; background: var(--panel); border: 1px solid var(--line); max-width: 600px; margin: 40px auto; padding: 24px; }
            .modal h3 { margin: 0 0 8px; font-size: 18px; }
            .modal h4 { margin: 20px 0 10px; font-size: 12px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
            .modal-close { position: absolute; top: 14px; right: 16px; font-size: 18px; }
            .presets { display: flex; flex-wrap: wrap; gap: 8px; }
            .time-row { display: flex; align-items: center; gap: 6px; margin: 8px 0 14px; }
            .time-row input { width: 72px; }
            .field-label { display: block; font-weight: 600; margin-bottom: 6px; }

            /* Settings */
            .settings { max-width: 1000px; padding: 20px 24px 0; }
            .settings h2 { margin: 0; font-size: 20px; }
            .settings h3 { font-size: 12px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: var(--muted);
                           margin: 30px 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
            .settings h4 { margin: 18px 0 6px; font-size: 14px; }
            .field { margin-bottom: 16px; max-width: 520px; }
            .field input[type=text], .field input[type=number], .field input[type=password] { width: 100%; }
            .field-hint { font-size: 12px; color: var(--muted); margin-top: 4px; white-space: pre-line; }
            .field-error { color: var(--alarm); font-weight: 600; margin-top: 4px; }
            .badge { margin-left: 8px; font-size: 11px; font-weight: 600; padding: 1px 7px; border: 1px solid var(--warn); color: var(--warn); }
            .msg { margin-top: 10px; font-weight: 600; }
            .msg-ok { color: var(--ok); font-weight: 600; margin-top: 10px; }
            .msg-err { color: var(--alarm); font-weight: 600; margin-top: 10px; }
            .locked { text-align: center; padding: 40px 20px; }
            .settings-head { display: flex; justify-content: space-between; align-items: center; }
            .settings-actions { position: sticky; bottom: 0; background: var(--panel); border-top: 1px solid var(--line);
                                padding: 12px 0; margin-top: 24px; display: flex; align-items: center; gap: 16px; }
            .status-list { margin: 0; padding-left: 18px; font-size: 13px; }
            .status-list li { margin: 3px 0; }
            .table-actions { margin: 8px 0 4px; }
            .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner input { color: var(--text) !important; background: var(--panel-2) !important; }
            .dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td.focused { background: var(--hover) !important; }
            .dash-table-container .dash-delete-cell, .dash-table-container .dash-select-cell { background: var(--panel) !important; color: var(--muted) !important; }

            .site-footer { text-align: center; padding: 8px 16px 28px; font-size: 12px; color: var(--muted); }
            .site-footer a { color: var(--muted); text-underline-offset: 3px; }
            .site-footer a:hover { color: var(--text); }

            @media (max-width: 720px) {
                .topbar { padding: 10px 14px; gap: 10px; }
                .topbar-left, .topbar-right { gap: 14px; }
                .page { padding: 12px 10px 30px; }
                .summary { width: 100%; order: 3; }
                .board .col-wide { display: none; }
                .lcd { min-width: 0; font-size: 18px; padding: 5px 7px; }
                .meter-display .v1 { font-size: 38px; }
                .panel-head { padding: 0 6px; }
                .controls { width: 100%; } .controls > div:first-child, .controls > div:last-child { width: auto; flex: 1; min-width: 0; }
                .board .col-status { display: none; } .st.st-inline { display: inline-flex; }
                .tabs label { padding: 10px 9px 8px; }
                .settings { padding: 14px; }
                .settings .dash-spreadsheet-container { overflow-x: auto; }
                /* Scrollende tabel knipt een open keuzelijst af: zolang die open is ruimte eronder maken */
                .settings .dash-spreadsheet-container:has(.Select.is-open) { padding-bottom: 210px; }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

METRICS = ['temperature', 'humidity', 'dewpoint', 'absolute_humidity', 'comfort']
METRIC_LABEL_KEYS = {'temperature': 'temperature', 'humidity': 'humidity', 'dewpoint': 'dewpoint',
                     'absolute_humidity': 'abs_humidity', 'comfort': 'comfort'}
TIME_RANGES = [('last_1min', 1), ('last_5min', 5), ('last_15min', 15), ('last_30min', 30), ('last_1hour', 60),
               ('last_6hours', 360), ('last_12hours', 720), ('last_24hours', 1440), ('last_7days', 10080),
               ('last_14days', 20160), ('last_1month', 43200), ('last_3months', 129600),
               ('last_6months', 259200), ('all_data', -1)]
PRESETS = ['5min', '10min', '30min', '1hour', '2hours', '6hours', '12hours', '24hours', '2days', 'week', 'month']


def nav_options(t):
    return [{'label': t['tab_dashboard'], 'value': 'dashboard'}, {'label': t['tab_settings'], 'value': 'settings'}]


def view_options(t):
    return [{'label': t['view_board'], 'value': 'board'}, {'label': t['view_meters'], 'value': 'meters'}]


def metric_options(t):
    return [{'label': t[METRIC_LABEL_KEYS[m]], 'value': m} for m in METRICS
            if m != 'comfort' or settings.get('show_comfort')]


def mollier_style():
    return {} if settings.get('show_mollier') else {'display': 'none'}


def range_options(t):
    return [{'label': t[key], 'value': value} for key, value in TIME_RANGES]


def create_layout():
    """Creëert de hoofdlayout (per page load: taal, thema en weergave uit Settings)"""
    lang = settings.get('default_language')
    t = TRANSLATIONS[lang]
    return html.Div(id='app-root', className=f"theme-{settings.get('dashboard_theme')}", children=[
        dcc.Location(id='url', refresh=False),
        dcc.Store(id='selected-language', data=lang),
        dcc.Store(id='graph-relayout-data', data={}),
        dcc.Store(id='historical-data-store'),
        dcc.Store(id='selected-range-method', data='preset'),
        dcc.Store(id='selected-range-value'),
        dcc.Interval(id='graph-update', interval=1000, n_intervals=0),

        html.Header(className='topbar', children=[
            html.Div(className='topbar-left', children=[
                html.Span(id='brand', className='brand', children=t['app_name']),
                dcc.RadioItems(id='main-tabs', className='nav', options=nav_options(t), value='dashboard'),
            ]),
            html.Div(className='topbar-right', children=[
                html.Span(id='status-summary', className='summary'),
                dcc.RadioItems(id='view-toggle', className='seg', options=view_options(t),
                               value=settings.get('dashboard_view')),
                dcc.Dropdown(id='language-selector', className='lang', clearable=False, searchable=False,
                             options=[{'label': LANGUAGE_NAMES[code], 'value': code} for code in LANGUAGE_NAMES],
                             value=lang),
            ]),
        ]),

        html.Main(id='page-dashboard', className='page', children=[
            html.Div(id='device-overview'),

            html.Section(className='panel', children=[
                html.Div(className='panel-head', children=[
                    dcc.RadioItems(id='metric-tabs', className='tabs', options=metric_options(t), value='temperature'),
                    html.Div(className='controls', children=[
                        dcc.Dropdown(id='device-selector', className='ctl-device', value=0, clearable=False),
                        dcc.Dropdown(id='time-range-dropdown', className='ctl-range', options=range_options(t),
                                     value=1440, clearable=False, searchable=False),
                    ]),
                ]),
                html.Div(className='panel-body', children=dcc.Graph(
                    id='live-graph', config={'displaylogo': False, 'displayModeBar': False}, style={'height': '380px'})),
                html.Div(id='data-count', className='panel-foot'),
            ]),

            html.Section(id='mollier-panel', className='panel', style=mollier_style(), children=[
                html.Div(className='panel-head', children=[
                    html.Span(id='label-psychrometric-chart', className='panel-title', children=t['psychrometric_chart']),
                ]),
                html.Div(className='panel-body', children=dcc.Graph(
                    id='psychrometric-chart', config={'displaylogo': False, 'displayModeBar': False})),
                html.Div(className='history-bar', children=[
                    html.Div(id='history-controls', children=html.Button(
                        t['btn_select_range'], id='open-range-modal-btn', n_clicks=0, className='btn')),
                    html.Span(id='history-hint', className='hint'),
                ]),
                html.Div(id='slider-container', className='slider-box', style={'display': 'none'}, children=[
                    html.Label(id='label-time-position', className='field-label', children=t['time_position']),
                    html.Div(id='slider-timestamp-display', className='slider-time'),
                    dcc.Slider(id='historical-time-slider', min=0, max=100, step=1, value=0, marks={},
                               tooltip={'placement': 'bottom', 'always_visible': False}),
                ]),
            ]),

            # Keuzevenster voor de historische periode
            html.Div(id='range-modal', className='modal-backdrop', style={'display': 'none'}, children=[
                html.Div(className='modal', role='dialog', children=[
                    html.H3(id='modal-title', children=t['modal_title']),
                    html.Button('✕', id='close-range-modal-btn', n_clicks=0, className='btn btn-link modal-close',
                                title=t['btn_close']),
                    html.H4(id='label-quick-select', children=t['quick_select']),
                    html.Div(className='presets', children=[
                        html.Button(t[f'btn_{key}'], id=f'preset-{key}', n_clicks=0, className='btn btn-small')
                        for key in PRESETS]),
                    html.H4(id='label-specific-period', children=t['specific_period']),
                    html.Label(id='label-start-datetime', className='field-label', children=t['start_datetime']),
                    dcc.DatePickerSingle(id='custom-start-date', display_format='DD-MM-YYYY', placeholder=t['select_date']),
                    html.Div(className='time-row', children=[
                        dcc.Input(id='custom-start-hour', type='number', min=0, max=23, value=0, placeholder=t['hour_placeholder']),
                        html.Span(':'),
                        dcc.Input(id='custom-start-minute', type='number', min=0, max=59, value=0, placeholder='MM'),
                    ]),
                    html.Label(id='label-end-datetime', className='field-label', children=t['end_datetime']),
                    dcc.DatePickerSingle(id='custom-end-date', display_format='DD-MM-YYYY', placeholder=t['select_date']),
                    html.Div(className='time-row', children=[
                        dcc.Input(id='custom-end-hour', type='number', min=0, max=23, value=23, placeholder=t['hour_placeholder']),
                        html.Span(':'),
                        dcc.Input(id='custom-end-minute', type='number', min=0, max=59, value=59, placeholder='MM'),
                    ]),
                    html.Button(t['btn_apply'], id='apply-custom-range-btn', n_clicks=0, className='btn btn-primary'),
                ]),
            ]),
        ]),

        html.Main(id='page-settings', className='page', style={'display': 'none'}, children=[
            html.Div(id='settings-content', className='panel settings'),
        ]),

        html.Footer(className='site-footer', children=[
            'Made by ', html.A('BRDC', href='https://brdc.nl', target='_blank', rel='noopener'),
        ]),
    ])
