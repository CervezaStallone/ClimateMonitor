import sqlite3
import math
import pandas as pd
from datetime import datetime, timedelta
from dash import callback_context, html, no_update, Input, Output, State
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import devices
import settings
from translations import TRANSLATIONS
from database import get_all_measurement_tables, build_union_query, DB_FILE
from psychrometric import add_device_points, create_psychrometric_chart, create_psychrometric_chart_historical

DEVICE_COLORS = ['#3498db', '#e74c3c', '#27ae60', '#9b59b6', '#f39c12', '#16a085', '#d35400', '#2c3e50',
                 '#c0392b', '#8e44ad', '#2980b9', '#7f8c8d']
CARDS_STYLE = {'marginBottom': '30px'}


def downsample(df, time_range_minutes):
    """Adaptive downsampling voor betere performance bij lange tijdsbereiken.

    Houdt max ~1000-2000 punten voor snelle rendering. df heeft een 'timestamp' kolom (datetime).
    """
    original_points = len(df)
    if time_range_minutes > 60 or original_points > 5000:  # Meer dan 1 uur OF veel data
        df = df.set_index('timestamp')
        
        if time_range_minutes == -1:  # Alle data: intelligente sampling
            total_days = (df.index.max() - df.index.min()).total_seconds() / 86400
            if total_days > 365:  # > 1 jaar: 1 dag gemiddelde
                df = df.resample('1D').mean()
            elif total_days > 90:  # 3-12 maanden: 6 uur gemiddelde
                df = df.resample('6h').mean()
            elif total_days > 30:  # 1-3 maanden: 2 uur gemiddelde
                df = df.resample('2h').mean()
            else:  # < 1 maand: 1 uur gemiddelde
                df = df.resample('1h').mean()
        elif time_range_minutes <= 360:  # 1-6 uur: 1 minuut
            df = df.resample('1min').mean()
        elif time_range_minutes <= 1440:  # 6-24 uur: 5 minuten
            df = df.resample('5min').mean()
        elif time_range_minutes <= 10080:  # 1-7 dagen: 15 minuten
            df = df.resample('15min').mean()
        elif time_range_minutes <= 43200:  # 1 maand: 1 uur
            df = df.resample('1h').mean()
        elif time_range_minutes <= 129600:  # 3 maanden: 3 uur
            df = df.resample('3h').mean()
        elif time_range_minutes <= 259200:  # 6 maanden: 6 uur
            df = df.resample('6h').mean()
        else:  # > 6 maanden: 1 dag
            df = df.resample('1D').mean()
        
        df = df.dropna().reset_index()
        
        if settings.get('debug_logging'):
            reduction = 100 * (1 - len(df)/original_points)
            print(f"   → Downsampled: {original_points} → {len(df)} punten (-{reduction:.1f}%)")
    return df


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


def combined_figure(df, names, time_range_minutes, t):
    """Eén grafiek per grootheid met een lijn per device."""
    fig = make_subplots(
        rows=5, cols=1,
        subplot_titles=(f'🌡️ {t["temperature"]}', f'💧 {t["humidity"]}', f'💦 {t["dewpoint"]}', f'🌫️ {t["abs_humidity"]}', f'😊 {t["comfort"]}'),
        vertical_spacing=0.08
    )
    metrics = [('temperature', '°C', '.1f'), ('humidity', '%', '.1f'), ('dewpoint', '°C', '.1f'),
               ('absolute_humidity', 'g/m³', '.1f'), ('comfort_score', '', '')]
    for index, (device_id, name) in enumerate(names.items()):
        group = df[df['device_id'] == device_id].drop(columns='device_id')
        if group.empty:
            continue
        group = downsample(group, time_range_minutes)
        group['comfort_score'] = [humidex_score(tmp, hum) for tmp, hum in zip(group['temperature'], group['humidity'])]
        color = DEVICE_COLORS[index % len(DEVICE_COLORS)]
        for row, (column, unit, fmt) in enumerate(metrics, start=1):
            fig.add_trace(go.Scatter(
                x=group['timestamp'], y=group[column], mode='lines', name=name, legendgroup=str(device_id),
                showlegend=row == 1, line=dict(color=color, width=2.5),
                hovertemplate=f'<b>{name}</b>: %{{y:{fmt}}}{unit}<extra></extra>'
            ), row=row, col=1)
    for row, title in enumerate([f"{t['temperature']} (°C)", f"{t['humidity']} (%)", f"{t['dewpoint']} (°C)",
                                 f"{t['abs_humidity']} (g/m³)", t['score']], start=1):
        fig.update_yaxes(title_text=title, row=row, col=1, showgrid=True, gridcolor='rgba(0,0,0,0.05)')
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    fig.update_yaxes(range=[-0.5, 6.5], tickmode='linear', tick0=0, dtick=1, row=5, col=1)
    fig.update_xaxes(title_text=t['time'], row=5, col=1, showgrid=True, gridcolor='rgba(0,0,0,0.05)')
    fig.update_layout(
        height=1100,
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.03, xanchor='center', x=0.5),
        hovermode='x unified',
        plot_bgcolor='rgba(0,0,0,0.02)',
        paper_bgcolor='white',
        margin=dict(l=60, r=30, t=80, b=40),
        uirevision='constant'
    )
    return fig


def latest_per_device():
    """Laatste meting per device uit de twee meest recente dagtabellen: {device_id: (ts, temp, rh, dauwpunt)}"""
    conn = sqlite3.connect(DB_FILE)
    try:
        latest = {}
        for table in get_all_measurement_tables(conn.cursor())[-2:]:
            for device_id, ts, temp, hum, dew in conn.execute(
                    f'SELECT device_id, MAX(timestamp), temperature, humidity, dewpoint FROM {table} GROUP BY device_id'):
                latest[device_id] = (ts, temp, hum, dew)
        return latest
    finally:
        conn.close()


def register_callbacks(app):
    """Registreer alle callbacks aan de Dash app"""
    
    @app.callback(
        [Output('selected-language', 'data'),
         Output('page-title', 'children'),
         Output('label-temperature', 'children'),
         Output('label-humidity', 'children'),
         Output('label-dewpoint', 'children'),
         Output('label-abs-humidity', 'children'),
         Output('label-comfort', 'children'),
         Output('label-score', 'children'),
         Output('label-time-period', 'children'),
         Output('label-database', 'children'),
         Output('tooltip-content', 'children'),
         Output('time-range-dropdown', 'options'),
         Output('label-psychrometric-chart', 'children'),
         Output('label-time-position', 'children'),
         Output('tab-dashboard', 'label'),
         Output('tab-settings', 'label'),
         Output('label-device', 'children')],
        [Input('language-selector', 'value')]
    )
    def update_language(lang):
        """Update alle labels op basis van geselecteerde taal"""
        try:
            print(f"🌐 Language changed to: {lang}")  # Debug
            if lang is None or lang not in TRANSLATIONS:
                lang = 'en'
                print(f"⚠️ Invalid language, defaulting to: {lang}")
            t = TRANSLATIONS[lang]
        except Exception as e:
            print(f"❌ Error in update_language: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to English
            lang = 'en'
            t = TRANSLATIONS[lang]
        
        # Tooltip content met vertalingen
        tooltip_content = html.Div([
            html.Strong(f"{t['score_explanation']}:"),
            html.Br(),
            f"0 = {t['comfort_0']}",
            html.Br(),
            f"1 = {t['comfort_1']}",
            html.Br(),
            f"2 = {t['comfort_2']}",
            html.Br(),
            f"3 = {t['comfort_3']}",
            html.Br(),
            f"4 = {t['comfort_4']}",
            html.Br(),
            f"5 = {t['comfort_5']}",
            html.Br(),
            f"6 = {t['comfort_6']}"
        ])
        
        # Dropdown opties met vertalingen
        dropdown_options = [
            {'label': t['last_1min'], 'value': 1},
            {'label': t['last_5min'], 'value': 5},
            {'label': t['last_15min'], 'value': 15},
            {'label': t['last_30min'], 'value': 30},
            {'label': t['last_1hour'], 'value': 60},
            {'label': t['last_6hours'], 'value': 360},
            {'label': t['last_12hours'], 'value': 720},
            {'label': t['last_24hours'], 'value': 1440},
            {'label': t['last_7days'], 'value': 10080},
            {'label': t['last_14days'], 'value': 20160},
            {'label': t['last_1month'], 'value': 43200},
            {'label': t['last_3months'], 'value': 129600},
            {'label': t['last_6months'], 'value': 259200},
            {'label': t['all_data'], 'value': -1}
        ]
        
        return (
            lang,
            t['title'],
            t['temperature'],
            t['humidity'],
            t['dewpoint'],
            t['abs_humidity'],
            t['comfort'],
            t['score'] + ': ',
            t['time_period'],
            t['database'],
            tooltip_content,
            dropdown_options,
            f"📐 {t['psychrometric_chart']}",
            t['time_position'],
            t['tab_dashboard'],
            t['tab_settings'],
            t['lbl_device_select']
        )
    
    @app.callback(
        [Output('live-graph', 'figure'),
         Output('data-count', 'children'),
         Output('current-temp', 'children'),
         Output('current-humidity', 'children'),
         Output('current-dewpoint', 'children'),
         Output('current-abs-humidity', 'children'),
         Output('comfort-level', 'children'),
         Output('comfort-score', 'children'),
         Output('comfort-icon', 'children'),
         Output('graph-relayout-data', 'data'),
         Output('current-cards', 'style')],
        [Input('graph-update', 'n_intervals'),
         Input('time-range-dropdown', 'value'),
         Input('live-graph', 'relayoutData'),
         Input('selected-language', 'data'),
         Input('device-selector', 'value')],
        [State('graph-relayout-data', 'data')]
    )
    def update_graph(n, time_range_minutes, relayout_data, lang, device_sel, stored_relayout):
        """Update grafieken en metingen op basis van tijdsbereik"""
        if lang is None:
            lang = 'nl'
        
        t = TRANSLATIONS[lang]
        
        def get_comfort_level(temp, humidity):
            """Bepaal comfort level op basis van Humidex"""
            # Bereken Humidex
            # Eerst dauwpunt berekenen
            dewpoint = temp - ((100 - humidity) / 5.0)
            dewpoint_kelvin = dewpoint + 273.15
            
            # Dampdrukverzadiging bij dauwpunt
            e = 6.11 * math.exp(5417.7530 * ((1/273.16) - (1/dewpoint_kelvin)))
            
            # Humidex formule
            humidex = temp + 0.5555 * (e - 10)
            
            # Comfort classificatie op basis van Humidex ranges
            # Bron: Environment Canada Humidex schaal
            if humidex < 20:
                return t['comfort_0'], 0, "🥶", humidex  # Te koud
            elif humidex < 27:
                return t['comfort_4'], 4, "🙂", humidex  # Comfortabel koel
            elif humidex < 30:
                return t['comfort_5'], 5, "😊", humidex  # Comfortabel
            elif humidex < 35:
                return t['comfort_6'], 6, "✨", humidex  # Optimaal comfortabel
            elif humidex < 40:
                return t['comfort_3'], 3, "😓", humidex  # Enig ongemak
            elif humidex < 46:
                return t['comfort_2'], 2, "😟", humidex  # Veel ongemak, vermijd fysieke inspanning
            elif humidex < 54:
                return t['comfort_1'], 1, "🔥", humidex  # Gevaarlijk - hittekrampen mogelijk
            else:
                return t['comfort_0'], 0, "⚠️", humidex  # Heatstroke dreigend
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Haal totaal aantal metingen op (som over alle tabellen)
        tables = get_all_measurement_tables(cursor)
        total_count = 0
        for table in tables:
            result = cursor.execute(f'SELECT COUNT(*) FROM {table}').fetchone()
            total_count += result[0] if result else 0
        
        # Bepaal tijdsfilter en bouw query (0 = alle devices gecombineerd)
        combined = not device_sel
        device_filter = None if combined else int(device_sel)
        columns = ['timestamp', 'temperature', 'humidity', 'dewpoint', 'absolute_humidity'] + (['device_id'] if combined else [])
        
        if time_range_minutes == -1:
            # Alle data
            query, table_count = build_union_query(cursor, columns, device_id=device_filter)
            if settings.get('debug_logging'):
                print(f"📊 Query voor ALLE data - aantal tabellen: {table_count}")
        else:
            # Filter op tijdsbereik
            cutoff_time = datetime.now() - timedelta(minutes=time_range_minutes)
            cutoff_timestamp = int(cutoff_time.timestamp())
            if settings.get('debug_logging'):
                print(f"📊 Query voor laatste {time_range_minutes} minuten (vanaf {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')})")
            query, table_count = build_union_query(cursor, columns, start_timestamp=cutoff_timestamp, device_id=device_filter)
            if settings.get('debug_logging'):
                print(f"   → Aantal relevante tabellen: {table_count}")
        
        if query:
            df = pd.read_sql_query(query, conn)
            if settings.get('debug_logging'):
                print(f"   → Opgehaalde datapunten: {len(df)}")
        else:
            df = pd.DataFrame(columns=columns)
            if settings.get('debug_logging'):
                print("   ⚠️ Geen query gegenereerd (geen relevante tabellen)")
        
        conn.close()
        
        # Update stored relayout data als er nieuwe zoom/pan data is
        if relayout_data and isinstance(relayout_data, dict) and any(key.startswith(('xaxis', 'yaxis')) for key in relayout_data.keys()):
            stored_relayout = relayout_data
        
        cards_style = {**CARDS_STYLE, 'display': 'none'} if combined else CARDS_STYLE
        if df.empty:
            return go.Figure(), f"{total_count} {t['measurements']}", "-- °C", "-- %", "-- °C", "-- g/m³", t['no_data'], "--", "❓", stored_relayout, cards_style
        
        # Converteer integer timestamps naar datetime objecten (lokale tijd)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert(settings.get('timezone')).dt.tz_localize(None)
        
        if combined:
            names = {d['id']: d['name'] for d in devices.list_devices()}
            fig = combined_figure(df, names, time_range_minutes, t)
            return fig, f"📊 {total_count} {t['measurements']}", "-- °C", "-- %", "-- °C", "-- g/m³", "", "--", "", stored_relayout, cards_style
        
        df = downsample(df, time_range_minutes)
        
        df['timestamp_formatted'] = df['timestamp'].dt.strftime('%d-%m-%Y %H:%M:%S')
        
        # Haal laatste waarden op
        latest_temp = df['temperature'].iloc[-1]
        latest_humidity = df['humidity'].iloc[-1]
        latest_dewpoint = df['dewpoint'].iloc[-1] if 'dewpoint' in df.columns else latest_temp - ((100 - latest_humidity) / 5.0)
        
        # Bereken absolute humidity als die niet in database zit
        if 'absolute_humidity' in df.columns:
            latest_abs_humidity = df['absolute_humidity'].iloc[-1]
        else:
            latest_abs_humidity = (6.112 * math.exp((17.67 * latest_temp) / (latest_temp + 243.5)) * latest_humidity * 2.1674) / (273.15 + latest_temp)
        
        # Bereken comfort score voor elk datapunt
        comfort_debug_counter = [0]  # Mutable counter voor closure
        
        def calculate_comfort_score(temp, hum):
            """Bereken comfort score op basis van Humidex"""
            try:
                # Check voor NaN waarden
                if pd.isna(temp) or pd.isna(hum):
                    return None
                
                dewpoint = temp - ((100 - hum) / 5.0)
                dewpoint_kelvin = dewpoint + 273.15
                e = 6.11 * math.exp(5417.7530 * ((1/273.16) - (1/dewpoint_kelvin)))
                humidex = temp + 0.5555 * (e - 10)
                
                if humidex < 20:
                    score = 0
                elif humidex < 27:
                    score = 4
                elif humidex < 30:
                    score = 5
                elif humidex < 35:
                    score = 6
                elif humidex < 40:
                    score = 3
                elif humidex < 46:
                    score = 2
                elif humidex < 54:
                    score = 1
                else:
                    score = 0
                
                # Debug output alleen voor eerste 5 punten
                if settings.get('debug_logging') and comfort_debug_counter[0] < 5:
                    print(f"   Debug comfort #{comfort_debug_counter[0]+1}: T={temp:.1f}°C, RH={hum:.1f}%, Humidex={humidex:.1f}, Score={score}")
                    comfort_debug_counter[0] += 1
                
                return score
            except Exception as e:
                if settings.get('debug_logging'):
                    print(f"   Error calculating comfort score: {e}")
                return None
        
        # Bereken comfort scores voor alle datapunten
        df['comfort_score'] = df.apply(lambda row: calculate_comfort_score(row['temperature'], row['humidity']), axis=1)
        
        # Maak subplots
        fig = make_subplots(
            rows=5, cols=1,
            subplot_titles=(f'🌡️ {t["temperature"]}', f'💧 {t["humidity"]}', f'💦 {t["dewpoint"]}', f'🌫️ {t["abs_humidity"]}', f'😊 {t["comfort"]}'),
            vertical_spacing=0.08
        )
        
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'], 
                y=df['temperature'],
                mode='lines',
                name=t['temperature'],
                line=dict(color='#3498db', width=2.5),
                fill='tozeroy',
                fillcolor='rgba(52, 152, 219, 0.1)',
                hovertemplate='<b>%{y:.1f}°C</b><br>%{customdata}<extra></extra>',
                customdata=df['timestamp_formatted']
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'], 
                y=df['humidity'], 
                mode='lines',
                name=t['humidity'],
                line=dict(color='#e74c3c', width=2.5),
                fill='tozeroy',
                fillcolor='rgba(231, 76, 60, 0.1)',
                hovertemplate='<b>%{y:.1f}%</b><br>%{customdata}<extra></extra>',
                customdata=df['timestamp_formatted']
            ),
            row=2, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'], 
                y=df['dewpoint'] if 'dewpoint' in df.columns else df['temperature'] - ((100 - df['humidity']) / 5.0), 
                mode='lines',
                name=t['dewpoint'],
                line=dict(color='#9b59b6', width=2.5),
                fill='tozeroy',
                fillcolor='rgba(155, 89, 182, 0.1)',
                hovertemplate='<b>%{y:.1f}°C</b><br>%{customdata}<extra></extra>',
                customdata=df['timestamp_formatted']
            ),
            row=3, col=1
        )
        
        # Bereken absolute humidity voor grafiek als niet aanwezig
        if 'absolute_humidity' in df.columns:
            abs_hum_data = df['absolute_humidity']
        else:
            # Correcte formule voor absolute vochtigheid
            abs_hum_data = (6.112 * df['temperature'].apply(lambda temp: math.exp((17.67 * temp) / (temp + 243.5))) * df['humidity'] * 2.1674) / (273.15 + df['temperature'])
        
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'], 
                y=abs_hum_data,
                mode='lines',
                name=t['abs_humidity'],
                line=dict(color='#16a085', width=2.5),
                fill='tozeroy',
                fillcolor='rgba(22, 160, 133, 0.1)',
                hovertemplate='<b>%{y:.1f}g/m³</b><br>%{customdata}<extra></extra>',
                customdata=df['timestamp_formatted']
            ),
            row=4, col=1
        )
        
        # Comfort score grafiek met kleurcodering
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'], 
                y=df['comfort_score'], 
                mode='lines',
                name=t['comfort'],
                line=dict(color='#f39c12', width=2.5),
                fill='tozeroy',
                fillcolor='rgba(243, 156, 18, 0.1)',
                hovertemplate='<b>Score: %{y}</b><br>%{customdata}<extra></extra>',
                customdata=df['timestamp_formatted']
            ),
            row=5, col=1
        )
        
        # Bereken dynamische Y-axis ranges met padding
        temp_min, temp_max = df['temperature'].min(), df['temperature'].max()
        temp_range = [max(0, temp_min - 5), temp_max + 5]
        
        hum_range = [0, 100]  # Humidity blijft altijd 0-100%
        
        dewpoint_data = df['dewpoint'] if 'dewpoint' in df.columns else df['temperature'] - ((100 - df['humidity']) / 5.0)
        dew_min, dew_max = dewpoint_data.min(), dewpoint_data.max()
        dew_range = [max(0, dew_min - 5), dew_max + 5]
        
        abs_min, abs_max = abs_hum_data.min(), abs_hum_data.max()
        abs_range = [max(0, abs_min - 2), abs_max + 2]
        
        fig.update_xaxes(
            title_text=t['time'], 
            row=5, col=1,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)'
        )
        fig.update_yaxes(
            title_text=f"{t['temperature']} (°C)", 
            row=1, col=1,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            range=temp_range
        )
        fig.update_yaxes(
            title_text=f"{t['humidity']} (%)", 
            row=2, col=1,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            range=hum_range
        )
        fig.update_yaxes(
            title_text=f"{t['dewpoint']} (°C)", 
            row=3, col=1,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            range=dew_range
        )
        fig.update_yaxes(
            title_text=f"{t['abs_humidity']} (g/m³)", 
            row=4, col=1,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            range=abs_range
        )
        fig.update_yaxes(
            title_text=t['score'], 
            row=5, col=1,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.05)',
            range=[-0.5, 6.5],
            tickmode='linear',
            tick0=0,
            dtick=1
        )
        
        fig.update_layout(
            height=1100,
            showlegend=False,
            hovermode='x unified',
            plot_bgcolor='rgba(0,0,0,0.02)',
            paper_bgcolor='white',
            margin=dict(l=60, r=30, t=50, b=40),
            hoverlabel=dict(
                bgcolor="white",
                font_size=14,
                font_family="Arial, sans-serif",
                font_color="#2c3e50",
                bordercolor="#2c3e50",
                align="left"
            ),
            uirevision='constant'  # Behoud UI state (zoom/pan) tussen updates
        )
        
        # Bepaal comfort level (retourneert nu ook humidex)
        comfort_text, comfort_score, comfort_icon, humidex = get_comfort_level(latest_temp, latest_humidity)
        
        return fig, f"📊 {total_count} {t['measurements']}", f"{latest_temp:.1f} °C", f"{latest_humidity:.1f} %", f"{latest_dewpoint:.1f} °C", f"{latest_abs_humidity:.1f} g/m³", comfort_text, str(comfort_score), comfort_icon, stored_relayout, cards_style
    
    # Callback voor psychrometric chart
    @app.callback(
        Output('psychrometric-chart', 'figure'),
        [Input('graph-update', 'n_intervals'),
         Input('selected-language', 'data'),
         Input('device-selector', 'value')]
    )
    def update_psychrometric_chart(n, lang, device_sel):
        """Update psychrometrisch diagram met actuele meetwaarden (alle devices of één device)"""
        if lang is None:
            lang = 'nl'
        
        if not device_sel:
            latest = latest_per_device()
            points = [(d['name'], latest[d['id']][1], latest[d['id']][2], DEVICE_COLORS[i % len(DEVICE_COLORS)])
                      for i, d in enumerate(devices.list_devices()) if d['id'] in latest]
            return add_device_points(create_psychrometric_chart(None, None, lang), points)
        
        # Haal laatste meting op uit database
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            # Zoek in meest recente tabel (laatste in lijst)
            tables = get_all_measurement_tables(cursor)
            if tables:
                latest_table = tables[-1]  # Laatste tabel (meest recente datum)
                query = f'SELECT temperature, humidity FROM {latest_table} WHERE device_id = {int(device_sel)} ORDER BY timestamp DESC LIMIT 1'
                df = pd.read_sql_query(query, conn)
            else:
                df = pd.DataFrame(columns=['temperature', 'humidity'])
            
            conn.close()
            
            if not df.empty:
                current_temp = df['temperature'].iloc[0]
                current_rh = df['humidity'].iloc[0]
                return create_psychrometric_chart(current_temp, current_rh, lang)
            else:
                # Geen data beschikbaar - toon leeg diagram
                return create_psychrometric_chart(None, None, lang)
        except Exception as e:
            print(f"Fout bij updaten psychrometric chart: {e}")
            return create_psychrometric_chart(None, None, lang)
    
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
            return t['no_data_in_range'], create_psychrometric_chart(None, None, lang)
        
        try:
            # Haal data op uit store
            timestamps = stored_data['timestamps']
            temperatures = stored_data['temperatures']
            humidities = stored_data['humidities']
            
            # Valideer slider waarde
            if current_value < 0 or current_value >= len(timestamps):
                return t['no_data_in_range'], create_psychrometric_chart(None, None, lang)
            
            # Haal geselecteerd datapunt op
            selected_timestamp = timestamps[current_value]
            selected_temp = temperatures[current_value]
            selected_humidity = humidities[current_value]
            
            # Format timestamp voor display
            dt = pd.to_datetime(selected_timestamp)
            timestamp_display = f"📅 {dt.strftime('%d-%m-%Y %H:%M:%S')}"
            
            # Creëer aangepast psychrometric chart met historisch punt
            fig = create_psychrometric_chart_historical(selected_temp, selected_humidity, lang, t['historical_condition'])
            
            return timestamp_display, fig
            
        except Exception as e:
            print(f"Fout bij updaten historische view: {e}")
            return t['no_data_in_range'], create_psychrometric_chart(None, None, lang)

    @app.callback(
        Output('device-selector', 'options'),
        [Input('url', 'pathname'),
         Input('selected-language', 'data'),
         Input('main-tabs', 'value')]
    )
    def update_device_options(pathname, lang, tab):
        """Keuzelijst: alle devices gecombineerd + elk device"""
        t = TRANSLATIONS.get(lang) or TRANSLATIONS['en']
        return [{'label': t['opt_all_devices'], 'value': 0}] + [
            {'label': f"#{d['id']} {d['name']}", 'value': d['id']} for d in devices.list_devices()]

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
            return {'textAlign': 'center', 'marginBottom': '20px'}, '', no_update
        return {'display': 'none'}, t['hint_select_device_history'], {'display': 'none'}

    @app.callback(
        Output('device-overview', 'children'),
        [Input('graph-update', 'n_intervals'),
         Input('selected-language', 'data'),
         Input('device-selector', 'value')]
    )
    def update_device_overview(n, lang, device_sel):
        """Kaart per device met actuele waarden en online/offline status"""
        if n and n % 2 and callback_context.triggered_id == 'graph-update':
            return no_update
        t = TRANSLATIONS.get(lang) or TRANSLATIONS['en']
        latest = latest_per_device()
        offline_after = max(3 * settings.get('poll_interval_seconds'), 30)
        now = datetime.now().timestamp()
        cards = []
        for index, device in enumerate(devices.list_devices(enabled_only=True)):
            ts, temp, hum, dew = latest.get(device['id'], (None, None, None, None))
            online = ts is not None and now - ts <= offline_after
            error = devices.status(device['id']).get('error')
            color = DEVICE_COLORS[index % len(DEVICE_COLORS)]
            if ts is None:
                state = t['status_never']
            elif online:
                state = f"🟢 {t['online']}"
            else:
                state = f"🔴 {t['offline']} · {t['last_value'].format(time=datetime.fromtimestamp(ts).strftime('%d-%m %H:%M'))}"
            cards.append(html.Div([
                html.Div(device['name'], style={'fontWeight': 'bold', 'color': color, 'fontSize': '16px'}),
                html.Div(f"#{device['id']}", style={'fontSize': '11px', 'color': '#95a5a6'}),
                html.Div(f"🌡️ {temp:.1f} °C   💧 {hum:.1f} %   💦 {dew:.1f} °C" if ts is not None else "--",
                         style={'fontSize': '15px', 'margin': '6px 0', 'color': '#2c3e50', 'whiteSpace': 'pre'}),
                html.Div(state, style={'fontSize': '12px', 'color': '#27ae60' if online else '#c0392b'}),
                html.Div(error, style={'fontSize': '11px', 'color': '#c0392b'}) if error and not online else None,
            ], style={
                'display': 'inline-block', 'verticalAlign': 'top', 'minWidth': '220px', 'margin': '0 12px 12px 0',
                'padding': '12px 16px', 'background': 'white', 'borderRadius': '12px',
                'boxShadow': '0 4px 6px rgba(0,0,0,0.1)', 'borderLeft': f'5px solid {color}',
                'outline': f'2px solid {color}' if device_sel == device['id'] else 'none'
            }))
        return cards

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
