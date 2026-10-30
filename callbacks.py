import sqlite3
import math
import pandas as pd
from datetime import datetime, timedelta
from dash import callback_context, html, no_update, Input, Output, State
import plotly.graph_objects as go

import alerts
import devices
import layout
import settings
from translations import TRANSLATIONS
from database import get_all_measurement_tables, build_union_query, DB_FILE
from psychrometric import add_device_points, create_psychrometric_chart, create_psychrometric_chart_historical

# Categorisch palet per sensor (vaste volgorde, gevalideerd op kleurenblindheid en contrast).
# Sensor 9 en verder krijgen een neutrale kleur; status-kleuren worden nooit voor sensoren gebruikt.
SERIES = {
    'light': ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
    'dark': ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
}
NEUTRAL_SERIES = {'light': '#9a9e97', 'dark': '#5e646b'}
THEMES = {
    'dark': dict(text='#e6e8e3', muted='#a2a9a2', grid='#2e343a', axis='#4a525a', paper='#24292e', plot='#1f2428',
                 hover='#2c3238', ok='#0ca30c', warn='#fab219', alarm='#e5534b', offline='#7d838a'),
    'light': dict(text='#1b1f23', muted='#555c55', grid='#e4e5df', axis='#a9ada5', paper='#f7f7f3', plot='#fbfbf8',
                  hover='#eceee8', ok='#0b8a0b', warn='#c98500', alarm='#d03b3b', offline='#7d838a'),
}
FONT = 'system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, sans-serif'
METRIC_UNITS = {'temperature': '°C', 'humidity': '%', 'dewpoint': '°C', 'absolute_humidity': 'g/m³', 'comfort': ''}
METRIC_KEYS = {'temperature': 'temperature', 'humidity': 'humidity', 'dewpoint': 'dewpoint',
               'absolute_humidity': 'abs_humidity', 'comfort': 'comfort'}


def theme_mode():
    mode = settings.get('dashboard_theme')
    return mode if mode in THEMES else 'dark'


def device_colors(mode):
    """{device_id: kleur}; kleur volgt de sensor (vaste volgorde op id), niet de filter."""
    palette = SERIES[mode]
    return {d['id']: palette[i] if i < len(palette) else NEUTRAL_SERIES[mode]
            for i, d in enumerate(devices.list_devices())}


def style_figure(fig, mode, height=None):
    k = THEMES[mode]
    fig.update_layout(
        paper_bgcolor=k['paper'], plot_bgcolor=k['plot'], font=dict(family=FONT, color=k['text'], size=12),
        margin=dict(l=56, r=20, t=16, b=40), hovermode='x unified',
        hoverlabel=dict(bgcolor=k['paper'], bordercolor=k['axis'], font=dict(color=k['text'], family=FONT)),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0, font=dict(color=k['text']), bgcolor='rgba(0,0,0,0)'),
        uirevision='constant',
    )
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(gridcolor=k['grid'], linecolor=k['axis'], zerolinecolor=k['grid'], tickfont=dict(color=k['muted']))
    fig.update_yaxes(gridcolor=k['grid'], linecolor=k['axis'], zerolinecolor=k['grid'], tickfont=dict(color=k['muted']),
                     title_font=dict(color=k['muted']))
    return fig


def bucket_seconds(time_range_minutes):
    """Middelingsinterval voor de grafiek: max ~1000-2000 punten per sensor."""
    for limit, seconds in ((60, 1), (360, 60), (1440, 300), (10080, 900), (43200, 3600), (129600, 10800), (259200, 21600)):
        if time_range_minutes <= limit:
            return seconds
    return 86400


def graph_data(time_range_minutes, device_id=None):
    """Metingen per sensor, al gemiddeld per interval in SQLite.

    Nooit alle ruwe metingen naar pandas: bij 1 s polling en meerdere sensoren duurde dat langer dan
    het verversinterval van de grafiek, waardoor elke update verviel en de grafiek leeg bleef.
    Geeft (DataFrame met kolom n = aantal metingen per punt, interval in seconden).
    """
    conn = sqlite3.connect(DB_FILE)
    try:
        cursor = conn.cursor()
        start = None
        if time_range_minutes == -1:  # Alle data: interval op basis van de oudste dagtabel
            tables = get_all_measurement_tables(cursor)
            oldest = datetime.strptime(tables[0].replace('measurements_', ''), '%Y%m%d') if tables else datetime.now()
            bucket = bucket_seconds((datetime.now() - oldest).total_seconds() / 60)
        else:
            start = int((datetime.now() - timedelta(minutes=time_range_minutes)).timestamp())
            bucket = bucket_seconds(time_range_minutes)
        columns = ['timestamp', 'temperature', 'humidity', 'dewpoint', 'absolute_humidity', 'device_id']
        query, _ = build_union_query(cursor, columns, start_timestamp=start, device_id=device_id, order_by=None)
        if not query:
            return pd.DataFrame(columns=columns + ['n']), bucket
        query = (f'SELECT timestamp / {bucket} * {bucket} AS timestamp, AVG(temperature) AS temperature, '
                 f'AVG(humidity) AS humidity, AVG(dewpoint) AS dewpoint, AVG(absolute_humidity) AS absolute_humidity, '
                 f'device_id, COUNT(*) AS n FROM ({query}) GROUP BY device_id, timestamp / {bucket} ORDER BY timestamp')
        return pd.read_sql_query(query, conn), bucket
    finally:
        conn.close()


def humidex_score(temp, hum):
    """Comfort score 0-6 op basis van Humidex (Environment Canada schaal)"""
    if pd.isna(temp) or pd.isna(hum):
        return None
    dewpoint_kelvin = temp - ((100 - hum) / 5.0) + 273.15
    e = 6.11 * math.exp(5417.7530 * ((1/273.16) - (1/dewpoint_kelvin)))
    humidex = temp + 0.5555 * (e - 10)
    for limit, score in ((20, 0), (27, 4), (30, 5), (35, 6), (40, 3), (46, 2), (54, 1)):
        if humidex < limit:
            return score
    return 0


def metric_figure(df, names, colors, metric, t, mode):
    """Eén grootheid, één lijn per sensor (of één sensor), in de kleuren van het thema."""
    fig = go.Figure()
    unit = METRIC_UNITS[metric]
    for device_id, name in names.items():
        group = df[df['device_id'] == device_id]
        if group.empty:
            continue
        if metric == 'comfort':
            values = [humidex_score(tmp, hum) for tmp, hum in zip(group['temperature'], group['humidity'])]
        else:
            values = group[metric]
        fig.add_trace(go.Scatter(
            x=group['timestamp'], y=values, mode='lines', name=name, line=dict(color=colors.get(device_id), width=2),
            hovertemplate=f'<b>{name}</b>: %{{y:.1f}} {unit}<extra></extra>' if metric != 'comfort'
            else f'<b>{name}</b>: %{{y}}<extra></extra>'))
    style_figure(fig, mode)
    fig.update_layout(showlegend=len(fig.data) > 1)
    title = t[METRIC_KEYS[metric]] + (f' ({unit})' if unit else '')
    fig.update_yaxes(title_text=title)
    if metric == 'humidity':
        fig.update_yaxes(range=[0, 100])
    if metric == 'comfort':
        fig.update_yaxes(range=[-0.5, 6.5], tickmode='linear', tick0=0, dtick=1)
    return fig


def theme_mollier(fig, mode, point_color=None):
    """Mollier diagram in de stijl van het thema: gedempte RV-lijnen, comfortzone, punten in sensorkleur."""
    k = THEMES[mode]
    for trace in fig.data:
        if getattr(trace, 'fill', None) == 'toself':
            trace.fillcolor = 'rgba(12, 163, 12, 0.14)'
            trace.line.color = k['ok']
        elif trace.mode == 'markers+text':
            trace.marker.line.color = k['plot']
            trace.textfont.family = FONT
            if point_color and trace.marker.color in ('#e74c3c',):
                trace.marker.color = point_color
                trace.textfont.color = k['text']
        elif trace.line is not None and trace.line.dash == 'dash':
            trace.line.color = k['axis']
        else:
            trace.line.color = k['muted']
    style_figure(fig, mode, height=520)
    fig.update_layout(title=None, hovermode='closest', margin=dict(l=60, r=20, t=30, b=50),
                      legend=dict(bordercolor=k['grid'], borderwidth=1))
    return fig


def sparkline_svg(values, color, width=120, height=28):
    """Kleine trendlijn als SVG data-URI (geen extra grafiek-componenten per rij)."""
    values = [v for v in values if v is not None and not pd.isna(v)]
    if len(values) < 2:
        return None
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = width / (len(values) - 1)
    points = ' '.join(f'{i * step:.1f},{height - 3 - (v - lo) / span * (height - 6):.1f}' for i, v in enumerate(values))
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
           f"<polyline points='{points}' fill='none' stroke='{color}' stroke-width='1.5' stroke-linejoin='round'/></svg>")
    return 'data:image/svg+xml;utf8,' + svg.replace('#', '%23')


_spark_cache = {'at': 0, 'data': {}}


def sparkline_data():
    """Temperatuur van de laatste 24 uur per sensor (kwartiergemiddelden), 60 s gecachet."""
    now = datetime.now().timestamp()
    if now - _spark_cache['at'] < 60:
        return _spark_cache['data']
    data = {}
    conn = sqlite3.connect(DB_FILE)
    try:
        query, _ = build_union_query(conn.cursor(), ['timestamp', 'temperature', 'device_id'], start_timestamp=int(now - 86400),
                                     order_by=None)
        if query:
            for device_id, temp in conn.execute(f'SELECT device_id, AVG(temperature) FROM ({query}) '
                                                f'GROUP BY device_id, timestamp / 900 ORDER BY device_id, timestamp / 900'):
                data.setdefault(int(device_id), []).append(temp)
    finally:
        conn.close()
    _spark_cache.update(at=now, data=data)
    return data


def latest_per_device():
    """Laatste meting per device uit de twee meest recente dagtabellen: {device_id: (ts, temp, rh, dauwpunt, abs)}"""
    conn = sqlite3.connect(DB_FILE)
    try:
        latest = {}
        for table in get_all_measurement_tables(conn.cursor())[-2:]:
            for device_id, ts, temp, hum, dew, ah in conn.execute(
                    f'SELECT device_id, MAX(timestamp), temperature, humidity, dewpoint, absolute_humidity '
                    f'FROM {table} GROUP BY device_id'):
                latest[device_id] = (ts, temp, hum, dew, ah)
        return latest
    finally:
        conn.close()


def register_callbacks(app):
    """Registreer alle callbacks aan de Dash app"""
    
    @app.callback(
        [Output('selected-language', 'data'),
         Output('brand', 'children'),
         Output('main-tabs', 'options'),
         Output('view-toggle', 'options'),
         Output('metric-tabs', 'options'),
         Output('time-range-dropdown', 'options'),
         Output('label-psychrometric-chart', 'children'),
         Output('label-time-position', 'children')],
        [Input('language-selector', 'value')]
    )
    def update_language(lang):
        """Update alle labels op basis van geselecteerde taal"""
        if lang is None or lang not in TRANSLATIONS:
            lang = 'en'
        t = TRANSLATIONS[lang]
        return (lang, t['app_name'], layout.nav_options(t), layout.view_options(t), layout.metric_options(t),
                layout.range_options(t), t['psychrometric_chart'], t['time_position'])

    @app.callback(
        [Output('page-dashboard', 'style'),
         Output('page-settings', 'style')],
        Input('main-tabs', 'value')
    )
    def show_page(tab):
        if tab == 'settings':
            return {'display': 'none'}, {}
        return {}, {'display': 'none'}

    @app.callback(
        Output('app-root', 'className'),
        Input('main-tabs', 'value'),
        prevent_initial_call=True
    )
    def apply_theme(tab):
        """Thema uit Settings direct toepassen (ook na opslaan)"""
        return f'theme-{theme_mode()}'

    @app.callback(
        [Output('live-graph', 'figure'),
         Output('data-count', 'children'),
         Output('graph-relayout-data', 'data')],
        [Input('graph-update', 'n_intervals'),
         Input('time-range-dropdown', 'value'),
         Input('live-graph', 'relayoutData'),
         Input('selected-language', 'data'),
         Input('device-selector', 'value'),
         Input('metric-tabs', 'value')],
        [State('graph-relayout-data', 'data'),
         State('main-tabs', 'value')]
    )
    def update_graph(n, time_range_minutes, relayout_data, lang, device_sel, metric, stored_relayout, tab):
        """Grafiek van één grootheid: één lijn per sensor of alleen de gekozen sensor"""
        metric = metric or 'temperature'
        time_range_minutes = time_range_minutes or 1440
        if callback_context.triggered_id == 'graph-update':
            # Lange bereiken middelen over minuten of meer: elke seconde opnieuw tekenen heeft geen zin
            if tab == 'settings' or n % min(bucket_seconds(time_range_minutes), 30):
                return no_update, no_update, no_update
        t = TRANSLATIONS.get(lang) or TRANSLATIONS['en']
        mode = theme_mode()
        if relayout_data and isinstance(relayout_data, dict) and any(key.startswith(('xaxis', 'yaxis')) for key in relayout_data):
            stored_relayout = relayout_data

        device_filter = int(device_sel) if device_sel else None
        df, _ = graph_data(time_range_minutes, device_filter)
        names = {d['id']: d['name'] for d in devices.list_devices() if not device_filter or d['id'] == device_filter}
        count_text = f"{int(df['n'].sum())} {t['measurements']} · {t[METRIC_KEYS[metric]]}"
        if df.empty:
            fig = style_figure(go.Figure(), mode)
            fig.add_annotation(text=t['no_data'], showarrow=False, font=dict(color=THEMES[mode]['muted'], size=14),
                               xref='paper', yref='paper', x=0.5, y=0.5)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
            return fig, count_text, stored_relayout
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert(settings.get('timezone')).dt.tz_localize(None)
        fig = metric_figure(df, names, device_colors(mode), metric, t, mode)
        return fig, count_text, stored_relayout

    # Callback voor psychrometric chart
    @app.callback(
        Output('psychrometric-chart', 'figure'),
        [Input('graph-update', 'n_intervals'),
         Input('selected-language', 'data'),
         Input('device-selector', 'value')]
    )
    def update_psychrometric_chart(n, lang, device_sel):
        """Update psychrometrisch diagram met actuele meetwaarden (alle devices of één device)"""
        if not settings.get('show_mollier'):
            return no_update
        if lang is None:
            lang = 'nl'
        
        mode = theme_mode()
        colors = device_colors(mode)
        latest = latest_per_device()
        chosen = [d for d in devices.list_devices() if d['id'] in latest and (not device_sel or d['id'] == device_sel)]
        points = [(d['name'], latest[d['id']][1], latest[d['id']][2], colors.get(d['id'])) for d in chosen]
        fig = theme_mollier(add_device_points(create_psychrometric_chart(None, None, lang), points), mode)
        coldest = min((p[1] for p in points if p[1] is not None), default=0)
        if coldest < 0:
            fig.update_xaxes(range=[coldest - 3, 40])  # punten onder 0 °C zichtbaar houden
        return fig
    
    # Callback voor modal open/close
    @app.callback(
        Output('range-modal', 'style'),
        [Input('open-range-modal-btn', 'n_clicks'),
         Input('close-range-modal-btn', 'n_clicks'),
         Input('apply-custom-range-btn', 'n_clicks')],
        [State('range-modal', 'style')],
        prevent_initial_call=True
    )
    def toggle_modal(open_clicks, close_clicks, apply_clicks, current_style):
        """Toggle modal visibility"""
        ctx = callback_context
        if not ctx.triggered:
            return current_style
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        if button_id == 'open-range-modal-btn':
            return {
                'display': 'block',
                'position': 'fixed',
                'zIndex': '1000',
                'left': '0',
                'top': '0',
                'width': '100%',
                'height': '100%',
                'background': 'rgba(0,0,0,0.5)',
                'overflow': 'auto'
            }
        else:  # close of apply
            return {'display': 'none'}
    
    # Callback voor preset buttons en custom range - sluit ook modal
    @app.callback(
        [Output('selected-range-value', 'data'),
         Output('range-modal', 'style', allow_duplicate=True)],
        [Input('preset-5min', 'n_clicks'),
         Input('preset-10min', 'n_clicks'),
         Input('preset-30min', 'n_clicks'),
         Input('preset-1hour', 'n_clicks'),
         Input('preset-2hours', 'n_clicks'),
         Input('preset-6hours', 'n_clicks'),
         Input('preset-12hours', 'n_clicks'),
         Input('preset-24hours', 'n_clicks'),
         Input('preset-2days', 'n_clicks'),
         Input('preset-week', 'n_clicks'),
         Input('preset-month', 'n_clicks'),
         Input('apply-custom-range-btn', 'n_clicks')],
        [State('custom-start-date', 'date'),
         State('custom-start-hour', 'value'),
         State('custom-start-minute', 'value'),
         State('custom-end-date', 'date'),
         State('custom-end-hour', 'value'),
         State('custom-end-minute', 'value')],
        prevent_initial_call=True
    )
    def handle_range_selection(btn5, btn10, btn30, btn1h, btn2h, btn6h, btn12h, btn24h, btn2d, btnw, btnm, btncustom,
                               start_date, start_hour, start_minute, end_date, end_hour, end_minute):
        """Handle preset button clicks en custom range"""
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # Modal style om te sluiten
        modal_closed = {'display': 'none'}
        
        # Preset button mapping
        preset_map = {
            'preset-5min': 5,
            'preset-10min': 10,
            'preset-30min': 30,
            'preset-1hour': 60,
            'preset-2hours': 120,
            'preset-6hours': 360,
            'preset-12hours': 720,
            'preset-24hours': 1440,
            'preset-2days': 2880,
            'preset-week': 10080,
            'preset-month': 43200
        }
        
        if button_id in preset_map:
            return {'type': 'preset', 'minutes': preset_map[button_id]}, modal_closed
        
        elif button_id == 'apply-custom-range-btn':
            if start_date and end_date:
                # Valideer tijden
                start_hour = start_hour if start_hour is not None else 0
                start_minute = start_minute if start_minute is not None else 0
                end_hour = end_hour if end_hour is not None else 23
                end_minute = end_minute if end_minute is not None else 59
                
                return {
                    'type': 'custom',
                    'start_date': start_date,
                    'start_hour': start_hour,
                    'start_minute': start_minute,
                    'end_date': end_date,
                    'end_hour': end_hour,
                    'end_minute': end_minute
                }, modal_closed
        
        return no_update, no_update
    
    # Callback voor ophalen historische data bij range selectie
    @app.callback(
        [Output('historical-data-store', 'data'),
         Output('historical-time-slider', 'min'),
         Output('historical-time-slider', 'max'),
         Output('historical-time-slider', 'value'),
         Output('historical-time-slider', 'marks'),
         Output('slider-container', 'style')],
        [Input('selected-range-value', 'data'),
         Input('selected-language', 'data')],
        State('device-selector', 'value')
    )
    def load_historical_data(range_value, lang, device_sel):
        """Laad historische data voor geselecteerde periode (preset of custom)"""
        if lang is None:
            lang = 'nl'
        
        t = TRANSLATIONS[lang]
        
        # Als geen range geselecteerd, verberg slider
        if range_value is None:
            return None, 0, 100, 0, {}, {'display': 'none'}
        
        try:
            # Bepaal start en eind tijden op basis van type
            if range_value.get('type') == 'preset':
                # Preset: gebruik minuten
                minutes = range_value['minutes']
                end_dt = datetime.now()
                start_dt = end_dt - timedelta(minutes=minutes)
            
            elif range_value.get('type') == 'custom':
                # Custom: gebruik specifieke datums en tijden
                start_date = pd.to_datetime(range_value['start_date'])
                start_dt = start_date.replace(
                    hour=range_value['start_hour'],
                    minute=range_value['start_minute'],
                    second=0
                )
                
                end_date = pd.to_datetime(range_value['end_date'])
                end_dt = end_date.replace(
                    hour=range_value['end_hour'],
                    minute=range_value['end_minute'],
                    second=59
                )
            else:
                return None, 0, 100, 0, {}, {'display': 'none'}
            
            # Haal data op uit database
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            start_timestamp = int(start_dt.timestamp())
            end_timestamp = int(end_dt.timestamp())
            
            columns = ['timestamp', 'temperature', 'humidity']
            query, table_count = build_union_query(cursor, columns, start_timestamp, end_timestamp,
                                                   device_id=int(device_sel) if device_sel else None)
            
            if query:
                df = pd.read_sql_query(query, conn)
            else:
                df = pd.DataFrame(columns=columns)
            
            conn.close()
            
            if df.empty:
                return None, 0, 100, 0, {}, {'display': 'none'}
            
            # Converteer integer timestamps naar datetime objecten (lokale tijd)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert(settings.get('timezone')).dt.tz_localize(None)
            
            # Bepaal tijdsverschil in minuten
            time_diff_minutes = (end_dt - start_dt).total_seconds() / 60
            
            # Als range > 1 minuut, sample per minuut (anders per seconde)
            if time_diff_minutes > 1:
                # Resample naar 1 minuut intervals (gebruik mean voor aggregatie)
                df = df.set_index('timestamp').resample('1min').mean().reset_index()
                df = df.dropna()  # Verwijder lege minuten
            
            if df.empty:
                return None, 0, 100, 0, {}, {'display': 'none'}
            
            n_points = len(df)
            
            # Maak slider marks met intelligente tijd labels
            if time_diff_minutes <= 60:  # <= 1 uur: toon HH:MM
                label_format = '%H:%M'
                mark_count = min(10, n_points)
            elif time_diff_minutes <= 1440:  # <= 1 dag: toon HH:MM
                label_format = '%H:%M'
                mark_count = min(12, n_points)
            elif time_diff_minutes <= 10080:  # <= 1 week: toon DD-MM HH:MM
                label_format = '%d-%m %H:%M'
                mark_count = min(10, n_points)
            else:  # > 1 week: toon DD-MM
                label_format = '%d-%m'
                mark_count = min(10, n_points)
            
            # Bereken mark indices
            if n_points <= mark_count:
                mark_indices = list(range(n_points))
            else:
                mark_indices = [int(i * (n_points - 1) / (mark_count - 1)) for i in range(mark_count)]
            
            marks = {}
            for idx in mark_indices:
                if idx < n_points:
                    marks[idx] = df['timestamp'].iloc[idx].strftime(label_format)
            
            # Sla data op in store (converteer naar dict voor JSON serialization)
            data_dict = {
                'timestamps': df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist(),
                'temperatures': df['temperature'].tolist(),
                'humidities': df['humidity'].tolist(),
                'sampling_mode': 'minute' if time_diff_minutes > 1 else 'second'
            }
            
            return data_dict, 0, n_points - 1, 0, marks, {'display': 'block'}
            
        except Exception as e:
            print(f"Fout bij laden historische data: {e}")
            return None, 0, 100, 0, {}, {'display': 'none'}
    
    # Callback voor het updaten van timestamp display en psychrometric chart bij slider beweging
    @app.callback(
        [Output('slider-timestamp-display', 'children'),
         Output('psychrometric-chart', 'figure', allow_duplicate=True)],
        [Input('historical-time-slider', 'value'),
         Input('historical-time-slider', 'drag_value'),
         Input('selected-language', 'data')],
        [State('historical-data-store', 'data')],
        prevent_initial_call=True
    )
    def update_historical_view(slider_value, drag_value, lang, stored_data):
        """Update psychrometric chart met historische data punt - live tijdens slepen"""
        # Gebruik drag_value tijdens het slepen, anders value
        current_value = drag_value if drag_value is not None else slider_value
        if lang is None:
            lang = 'nl'
        
        t = TRANSLATIONS[lang]
        
        # Check of er data is
        if stored_data is None or current_value is None:
            return t['no_data_in_range'], theme_mollier(create_psychrometric_chart(None, None, lang), theme_mode())
        
        try:
            # Haal data op uit store
            timestamps = stored_data['timestamps']
            temperatures = stored_data['temperatures']
            humidities = stored_data['humidities']
            
            # Valideer slider waarde
            if current_value < 0 or current_value >= len(timestamps):
                return t['no_data_in_range'], theme_mollier(create_psychrometric_chart(None, None, lang), theme_mode())
            
            # Haal geselecteerd datapunt op
            selected_timestamp = timestamps[current_value]
            selected_temp = temperatures[current_value]
            selected_humidity = humidities[current_value]
            
            # Format timestamp voor display
            dt = pd.to_datetime(selected_timestamp)
            timestamp_display = dt.strftime('%d-%m-%Y %H:%M:%S')
            
            # Creëer aangepast psychrometric chart met historisch punt
            fig = theme_mollier(create_psychrometric_chart_historical(selected_temp, selected_humidity, lang, t['historical_condition']),
                                theme_mode(), point_color=THEMES[theme_mode()]['text'])
            
            return timestamp_display, fig
            
        except Exception as e:
            print(f"Fout bij updaten historische view: {e}")
            return t['no_data_in_range'], theme_mollier(create_psychrometric_chart(None, None, lang), theme_mode())

    @app.callback(
        Output('device-selector', 'options'),
        [Input('url', 'pathname'),
         Input('selected-language', 'data'),
         Input('main-tabs', 'value')]
    )
    def update_device_options(pathname, lang, tab):
        return layout.device_options(TRANSLATIONS.get(lang) or TRANSLATIONS['en'])

    @app.callback(
        [Output('history-controls', 'style'),
         Output('history-hint', 'children'),
         Output('slider-container', 'style', allow_duplicate=True)],
        Input('device-selector', 'value'),
        State('selected-language', 'data'),
        prevent_initial_call='initial_duplicate'
    )
    def toggle_history_controls(device_sel, lang):
        """Historische replay werkt per device"""
        t = TRANSLATIONS.get(lang) or TRANSLATIONS['en']
        if device_sel:
            return {}, '', no_update
        return {'display': 'none'}, t['hint_select_device_history'], {'display': 'none'}

    def sensor_states(t):
        """Actuele toestand per actieve sensor voor bord, meters en samenvatting."""
        latest = latest_per_device()
        offline_after = max(3 * settings.get('poll_interval_seconds'), 30)
        now = datetime.now().timestamp()
        states = []
        for device in devices.list_devices(enabled_only=True):
            config = next((d for d in devices.load_config()[1] if d['id'] == device['id']), {})
            ts, temp, hum, dew, ah = latest.get(device['id'], (None,) * 5)
            if ts is None:
                status, phases = 'never', {}
            elif now - ts > offline_after:
                status, phases = 'offline', {}
            else:
                status, phases = alerts.device_status(device['id'])
            if status == 'ok':
                label, sub = t['st_ok'], t['ago_seconds'].format(n=int(now - ts))
            elif status in ('alarm', 'warn'):
                metrics = ', '.join(t[METRIC_KEYS[m]] for m in phases)
                label = f"{t['st_' + status]} · {metrics}"
                sub = t['ago_seconds'].format(n=int(now - ts))
            elif status == 'offline':
                label, sub = t['st_offline'], t['last_value'].format(time=datetime.fromtimestamp(ts).strftime('%d-%m %H:%M'))
            else:
                label, sub = t['st_never'], devices.status(device['id']).get('error') or ''
            score = humidex_score(temp, hum) if temp is not None else None
            states.append({
                'id': device['id'], 'name': device['name'], 'status': status, 'phases': phases, 'label': label,
                'sub': sub[:80], 'temp': temp, 'hum': hum, 'dew': dew, 'ah': ah,
                'comfort': t[f'comfort_{score}'] if score is not None else '—',
                'where': f"{config.get('bus', '')} · #{config.get('slave_id', '')}",
            })
        return states

    def value_cell(value, unit, phase=None):
        cls = 'lcd' + (' is-alarm' if phase == 'alarm' else ' is-warn' if phase == 'pending' else '')
        text = '— —' if value is None else f'{value:.1f}'
        return html.Span([text, html.Span(unit, className='u')], className=cls)

    def spark(device_id, color, width=120):
        src = sparkline_svg(sparkline_data().get(device_id, []), color, width=width)
        return html.Img(src=src, className='spark', alt='') if src else None

    def render_board(states, colors, t):
        show_comfort = settings.get('show_comfort')
        head = html.Tr([html.Th('', className='bar'), html.Th(t['hdr_sensor']), html.Th(t['temperature']), html.Th(t['humidity']),
                        html.Th(t['dewpoint'], className='col-wide'), html.Th(t['abs_humidity'], className='col-wide'),
                        html.Th(t['comfort'], className='col-wide') if show_comfort else None,
                        html.Th(t['hdr_trend'], className='col-wide'),
                        html.Th(t['hdr_status'], className='col-status')])
        rows = []
        for s_ in states:
            color = colors.get(s_['id'])
            ph = s_['phases']
            rows.append(html.Tr(className='row' + (' is-offline' if s_['status'] in ('offline', 'never') else ''),
                                style={'--st': f"var(--{ {'never': 'offline'}.get(s_['status'], s_['status'])})"}, children=[
                html.Td(className='bar'),
                html.Td([html.Div([html.Span(className='swatch', style={'--series': color}), s_['name']], className='name'),
                         html.Div(s_['where'], className='where'),
                         html.Span(s_['label'], className=f"st st-{s_['status']} st-inline")]),
                html.Td(value_cell(s_['temp'], '°C', ph.get('temperature'))),
                html.Td(value_cell(s_['hum'], '%', ph.get('humidity'))),
                html.Td(value_cell(s_['dew'], '°C', ph.get('dewpoint')), className='col-wide'),
                html.Td(value_cell(s_['ah'], 'g/m³', ph.get('absolute_humidity')), className='col-wide'),
                html.Td(s_['comfort'], className='comfort col-wide') if show_comfort else None,
                html.Td(spark(s_['id'], color), className='col-wide'),
                html.Td([html.Span(s_['label'], className=f"st st-{s_['status']}"),
                         html.Span(s_['sub'], className='st-sub')], className='col-status'),
            ]))
        return html.Section(className='panel board-wrap', children=html.Table([html.Thead(head), html.Tbody(rows)], className='board'))

    def render_meters(states, colors, t):
        cards = []
        for s_ in states:
            ph = s_['phases']
            cls = lambda m: 'is-alarm' if ph.get(m) == 'alarm' else 'is-warn' if ph.get(m) == 'pending' else ''
            fmt = lambda v: '— —' if v is None else f'{v:.1f}'
            cards.append(html.Div(className='meter' + (' is-offline' if s_['status'] in ('offline', 'never') else ''),
                                  style={'--st': f"var(--{ {'never': 'offline'}.get(s_['status'], s_['status'])})"}, children=[
                html.Div(className='meter-head', children=[
                    html.Div([html.Div([html.Span(className='swatch', style={'--series': colors.get(s_['id'])}), s_['name']], className='name'),
                              html.Div(s_['where'], className='where')]),
                    html.Span(s_['label'], className=f"st st-{s_['status']}"),
                ]),
                html.Div(className='meter-display', children=[
                    html.Div([fmt(s_['temp']), html.Span('°C', className='u')], className='v1 ' + cls('temperature')),
                    html.Div([fmt(s_['hum']), html.Span('% RH', className='u')], className='v2 ' + cls('humidity')),
                ]),
                html.Div(className='meter-stats', children=[
                    html.Span(f"{t['dewpoint']} {fmt(s_['dew'])} °C"),
                    html.Span(f"{fmt(s_['ah'])} g/m³"),
                    html.Span(s_['sub']),
                ]),
                spark(s_['id'], colors.get(s_['id']), width=300),
            ]))
        return html.Div(cards, className='meters')

    @app.callback(
        [Output('device-overview', 'children'),
         Output('status-summary', 'children')],
        [Input('graph-update', 'n_intervals'),
         Input('selected-language', 'data'),
         Input('view-toggle', 'value')],
        State('main-tabs', 'value')
    )
    def update_device_overview(n, lang, view, tab):
        """Bord of meters met actuele waarden en status per sensor, plus samenvatting in de kopbalk"""
        if callback_context.triggered_id == 'graph-update' and (n % 2 or tab == 'settings'):
            return no_update, no_update
        t = TRANSLATIONS.get(lang) or TRANSLATIONS['en']
        states = sensor_states(t)
        colors = device_colors(theme_mode())
        counts = {k: sum(1 for s_ in states if s_['status'] == k) for k in ('alarm', 'warn', 'offline')}
        summary = [t['summary_sensors'].format(n=len(states))]
        if counts['alarm']:
            summary += [' · ', html.Span(t['summary_alarm'].format(n=counts['alarm']), className='n-alarm')]
        if counts['warn']:
            summary += [' · ', html.Span(t['summary_warn'].format(n=counts['warn']), className='n-warn')]
        if counts['offline']:
            summary += [' · ', t['summary_offline'].format(n=counts['offline'])]
        if not states:
            return html.Div(t['no_sensors'], className='panel empty'), summary
        body = render_meters(states, colors, t) if view == 'meters' else render_board(states, colors, t)
        return body, summary

    PRESET_BUTTONS = ['5min', '10min', '30min', '1hour', '2hours', '6hours', '12hours', '24hours', '2days', 'week', 'month']

    @app.callback(
        [Output('open-range-modal-btn', 'children'),
         Output('modal-title', 'children'),
         Output('label-quick-select', 'children'),
         Output('label-specific-period', 'children'),
         Output('label-start-datetime', 'children'),
         Output('label-end-datetime', 'children'),
         Output('apply-custom-range-btn', 'children'),
         Output('custom-start-date', 'placeholder'),
         Output('custom-end-date', 'placeholder'),
         Output('custom-start-hour', 'placeholder'),
         Output('custom-end-hour', 'placeholder')] +
        [Output(f'preset-{key}', 'children') for key in PRESET_BUTTONS],
        Input('selected-language', 'data')
    )
    def update_history_language(lang):
        """Teksten van de historische analyse (knop en keuzevenster) in de gekozen taal"""
        t = TRANSLATIONS.get(lang) or TRANSLATIONS['en']
        return [t['btn_select_range'], t['modal_title'], t['quick_select'], t['specific_period'], t['start_datetime'],
                t['end_datetime'], t['btn_apply'], t['select_date'], t['select_date'], t['hour_placeholder'],
                t['hour_placeholder']] + [t[f'btn_{key}'] for key in PRESET_BUTTONS]
