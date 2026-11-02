"""Houtvochtevenwicht (EMC): het vochtgehalte waar hout naartoe gaat bij een gegeven temperatuur en RV.

Formule: Hailwood-Horrobin (Simpson 1973), USDA Wood Handbook hoofdstuk 4, versie in °C.
Volgens het handboek bruikbaar voor alle houtsoorten (afwijking per soort ~1-2 %-punt). Daarom
geen tabel met houtsoorten maar één correctie in Settings.
"""
import math
import sqlite3
import threading
import time

import numpy as np
import plotly.graph_objects as go

import settings
from database import build_union_query

_lock = threading.Lock()
_smooth = {}   # device_id -> (tijdstip, vertraagd houtvocht)


def emc(temperature, humidity):
    """EMC in % (vocht t.o.v. droog hout) zonder correctie. Werkt ook op numpy arrays / pandas series."""
    t = temperature
    h = np.clip(humidity, 0, 99.5) / 100   # bij 100 % RV deelt de formule door nul
    w = 349 + 1.29 * t + 0.0135 * t * t
    k = 0.805 + 0.000736 * t - 0.00000273 * t * t
    k1 = 6.27 - 0.00938 * t - 0.000303 * t * t
    k2 = 1.91 + 0.0407 * t - 0.000293 * t * t
    kh = k * h
    return 1800 / w * (kh / (1 - kh) + (k1 * kh + 2 * k1 * k2 * kh * kh) / (1 + k1 * kh + k1 * k2 * kh * kh))


def value(temperature, humidity):
    """EMC met de correctie uit Settings (houtsoort / eigen ijking)."""
    return emc(temperature, humidity) + settings.get('wood_emc_offset')


def _history_value(device_id, hours, now):
    """Houtvocht uit het gemiddelde van de afgelopen reactietijd in de database, None zonder data."""
    conn = sqlite3.connect(settings.DB_FILE, timeout=30)
    try:
        query, _ = build_union_query(conn.cursor(), ['temperature', 'humidity'], start_timestamp=int(now - hours * 3600),
                                     device_id=device_id, order_by=None)
        if not query:
            return None
        temp, hum = conn.execute(f'SELECT AVG(temperature), AVG(humidity) FROM ({query})').fetchone()
        return None if temp is None else float(value(temp, hum))
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def update(device_id, temperature, humidity, now=None):
    """Nieuwe meting: geeft het vertraagde houtvocht.

    Hout volgt de lucht traag (dagen), daarom een exponentieel gemiddelde met de reactietijd uit
    Settings (0 = actuele waarde). Bij de eerste meting na een start beginnen we bij het gemiddelde
    uit de database, zodat een herstart geen vals alarm geeft.
    """
    now = now or time.time()
    live = float(value(temperature, humidity))
    hours = settings.get('wood_response_hours')
    with _lock:
        if not hours:
            _smooth[device_id] = (now, live)
            return live
        if device_id not in _smooth:
            seed = _history_value(device_id, hours, now)
            _smooth[device_id] = (now, live if seed is None else seed)
        last, smooth = _smooth[device_id]
        smooth += (live - smooth) * (1 - math.exp(-max(now - last, 0) / (hours * 3600)))
        _smooth[device_id] = (now, smooth)
        return smooth


def current(device_id):
    """Laatste vertraagde houtvocht van een sensor, None als die nog niet gemeten is."""
    entry = _smooth.get(device_id)
    return entry[1] if entry else None


def iso_line(target, temps):
    """RV (%) waarbij de gecorrigeerde EMC gelijk is aan target, per temperatuur (EMC stijgt met RV)."""
    rh = np.linspace(0, 99.5, 400)
    raw = target - settings.get('wood_emc_offset')
    return np.array([np.interp(raw, emc(t, rh), rh, left=0, right=100) for t in temps])


# --- diagram -------------------------------------------------------------------

def _rgba(hex_color, alpha):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f'rgba({r}, {g}, {b}, {alpha})'


def figure(points, limits, t, k, areas=()):
    """Diagram temperatuur × RV met lijnen van gelijk houtvocht, houtvochtgrenzen, zones en de sensoren.

    points: [(naam, temperatuur, rv, kleur)]; limits: [(min, max, niveau)] in % houtvocht uit de alarmregels;
    areas: zones (zones.py, veelhoek in temperatuur × RV); k: themakleuren (callbacks.THEMES).
    """
    import zones
    seen = [p[1] for p in points if p[1] is not None]
    temps = np.linspace(min([-5] + [x - 3 for x in seen]), max([45] + [x + 3 for x in seen]), 60)
    fig = go.Figure()
    for zone in areas:
        corners = zone['points'] + zone['points'][:1]
        fig.add_trace(go.Scatter(x=[p[0] for p in corners], y=[p[1] for p in corners], mode='lines', fill='toself',
                                 name=zone['name'], fillcolor=zones.fill_color(zone['color']),
                                 line=dict(color=zones.COLORS[zone['color']], width=1.5), hoverinfo='skip'))
    for level in ('warning', 'alarm'):   # alarm als laatste: ligt over de waarschuwing
        color = k['warn'] if level == 'warning' else k['alarm']
        for low, high, zone_level in limits:
            if zone_level != level:
                continue
            for limit, edge, sign in ((high, 100, '≥'), (low, 0, '≤')):
                if limit is None:
                    continue
                fig.add_trace(go.Scatter(
                    x=list(temps) + list(temps[::-1]), y=list(iso_line(limit, temps)) + [edge] * len(temps),
                    fill='toself', mode='lines', fillcolor=_rgba(color, 0.16), line=dict(color=color, width=1.5),
                    name=f"{t['opt_level_' + level]} {sign} {limit:g} %", hoverinfo='skip'))
    for target in range(4, 28, 2):
        line = iso_line(target, temps)
        fig.add_trace(go.Scatter(x=temps, y=line, mode='lines', line=dict(color=k['axis'], width=1),
                                 showlegend=False, hoverinfo='skip'))
        if line[-1] < 96:   # boven 96 % liggen de lijnen te dicht op elkaar voor labels
            fig.add_annotation(x=temps[-1], y=line[-1], text=f'{target} %', showarrow=False, xanchor='left',
                               font=dict(color=k['muted'], size=11))
    for name, temp, rh, color in points:
        if temp is None or rh is None:
            continue
        fig.add_trace(go.Scatter(
            x=[temp], y=[rh], mode='markers+text', name=name, text=[name], textposition='top center',
            marker=dict(size=13, color=color, line=dict(width=2, color=k['plot'])), textfont=dict(color=k['text']),
            hovertemplate=f"<b>{name}</b><br>{temp:.1f} °C · {rh:.0f} %<br>"
                          f"{t['wood_emc']}: {float(value(temp, rh)):.1f} %<extra></extra>"))
    fig.update_xaxes(title_text=f"{t['temperature']} (°C)", range=[temps[0], temps[-1]])
    fig.update_yaxes(title_text=f"{t['humidity']} (%)", range=[0, 100])
    return fig
