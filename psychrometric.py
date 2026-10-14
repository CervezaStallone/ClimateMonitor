import plotly.graph_objects as go
import numpy as np
from translations import TRANSLATIONS


def create_psychrometric_chart(current_temp, current_rh, lang='nl'):
    """Genereer een psychrometrisch (Mollier) diagram met huidige conditie"""
    t = TRANSLATIONS[lang]
    
    # Temperatuur range voor het diagram (0-40°C)
    temp_range = np.linspace(0, 40, 200)
    
    # Creëer figure
    fig = go.Figure()
    
    # Teken verzadigingslijn (100% RH)
    sat_humidity_ratio = []
    for temp in temp_range:
        # Verzadigde dampdrukverzadiging (Pa) - August-Roche-Magnus formule
        pws = 611.2 * np.exp(17.62 * temp / (243.12 + temp))
        # Vochtigheidsratio bij verzadiging (kg water / kg dry air)
        ws = 0.622 * pws / (101325 - pws)
        sat_humidity_ratio.append(ws * 1000)  # Converteer naar g/kg
    
    fig.add_trace(go.Scatter(
        x=temp_range,
        y=sat_humidity_ratio,
        mode='lines',
        name='100% RH',
        line=dict(color='#3498db', width=3),
        showlegend=True
    ))
    
    # Teken RH lijnen (10%, 20%, ..., 90%)
    rh_levels = [10, 20, 30, 40, 50, 60, 70, 80, 90]
    colors = ['#ecf0f1', '#d5dbdb', '#bdc3c7', '#95a5a6', '#7f8c8d', '#5d6d7e', '#34495e', '#2c3e50', '#1c2833']
    
    for rh, color in zip(rh_levels, colors):
        humidity_ratio = []
        for temp in temp_range:
            pws = 611.2 * np.exp(17.62 * temp / (243.12 + temp))
            pw = pws * (rh / 100.0)
            if pw >= 101325:  # Voorkom onmogelijke waarden
                humidity_ratio.append(None)
            else:
                w = 0.622 * pw / (101325 - pw)
                humidity_ratio.append(w * 1000)
        
        fig.add_trace(go.Scatter(
            x=temp_range,
            y=humidity_ratio,
            mode='lines',
            name=f'{rh}% RH',
            line=dict(color=color, width=1, dash='dash'),
            showlegend=False,
            hovertemplate=f'{rh}% RH<br>T: %{{x:.1f}}°C<br>ω: %{{y:.1f}} g/kg<extra></extra>'
        ))
    
    # Comfortzone (typisch 20-26°C en 30-60% RH)
    comfort_temp_range = np.linspace(20, 26, 50)
    
    # Ondergrens comfortzone (30% RH)
    comfort_lower = []
    for temp in comfort_temp_range:
        pws = 611.2 * np.exp(17.62 * temp / (243.12 + temp))
        pw = pws * 0.30
        w = 0.622 * pw / (101325 - pw)
        comfort_lower.append(w * 1000)
    
    # Bovengrens comfortzone (60% RH)
    comfort_upper = []
    for temp in comfort_temp_range:
        pws = 611.2 * np.exp(17.62 * temp / (243.12 + temp))
        pw = pws * 0.60
        w = 0.622 * pw / (101325 - pw)
        comfort_upper.append(w * 1000)
    
    # Vul comfortzone
    fig.add_trace(go.Scatter(
        x=list(comfort_temp_range) + list(comfort_temp_range[::-1]),
        y=comfort_lower + comfort_upper[::-1],
        fill='toself',
        fillcolor='rgba(46, 204, 113, 0.2)',
        line=dict(width=0),
        name=t['comfort_zone'],
        showlegend=True,
        hoverinfo='skip'
    ))
    
    # Bereken huidige vochtigheidsratio
    if current_temp is not None and current_rh is not None:
        pws_current = 611.2 * np.exp(17.62 * current_temp / (243.12 + current_temp))
        pw_current = pws_current * (current_rh / 100.0)
        w_current = 0.622 * pw_current / (101325 - pw_current)
        w_current_g_kg = w_current * 1000
        
        # Markeer huidige conditie
        fig.add_trace(go.Scatter(
            x=[current_temp],
            y=[w_current_g_kg],
            mode='markers+text',
            name=t['current_condition'],
            marker=dict(
                size=15,
                color='#e74c3c',
                symbol='star',
                line=dict(width=2, color='white')
            ),
            text=[f"{current_temp:.1f}°C<br>{current_rh:.0f}%"],
            textposition='top center',
            textfont=dict(size=12, color='#e74c3c', family='Arial Black'),
            showlegend=True,
            hovertemplate=f'{t["current_condition"]}<br>T: {current_temp:.1f}°C<br>RH: {current_rh:.0f}%<br>ω: {w_current_g_kg:.1f} g/kg<extra></extra>'
        ))
    
    # Layout
    fig.update_layout(
        title={
            'text': f"📊 {t['psychrometric_chart']}",
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20, 'color': '#2c3e50', 'family': 'Arial Black'}
        },
        xaxis_title=t['dry_bulb_temp'],
        yaxis_title=t['humidity_ratio_axis'],
        xaxis=dict(
            range=[0, 40],
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)',
            dtick=5
        ),
        yaxis=dict(
            range=[0, 25],
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)',
            dtick=5
        ),
        height=600,
        plot_bgcolor='rgba(255,255,255,1)',
        paper_bgcolor='white',
        hovermode='closest',
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='#2c3e50',
            borderwidth=1
        )
    )
    
    return fig


def create_psychrometric_chart_historical(current_temp, current_rh, lang='nl', label='Historische toestand'):
    """Genereer psychrometrisch diagram met aangepaste label voor historisch punt"""
    t = TRANSLATIONS[lang]
    
    # Temperatuur range voor het diagram (0-40°C)
    temp_range = np.linspace(0, 40, 200)
    
    # Creëer figure
    fig = go.Figure()
    
    # Teken verzadigingslijn (100% RH)
    sat_humidity_ratio = []
    for temp in temp_range:
        pws = 611.2 * np.exp(17.62 * temp / (243.12 + temp))
        ws = 0.622 * pws / (101325 - pws)
        sat_humidity_ratio.append(ws * 1000)
    
    fig.add_trace(go.Scatter(
        x=temp_range,
        y=sat_humidity_ratio,
        mode='lines',
        name='100% RH',
        line=dict(color='#3498db', width=3),
        showlegend=True
    ))
    
    # Teken RH lijnen (10%, 20%, ..., 90%)
    rh_levels = [10, 20, 30, 40, 50, 60, 70, 80, 90]
    colors = ['#ecf0f1', '#d5dbdb', '#bdc3c7', '#95a5a6', '#7f8c8d', '#5d6d7e', '#34495e', '#2c3e50', '#1c2833']
    
    for rh, color in zip(rh_levels, colors):
        humidity_ratio = []
        for temp in temp_range:
            pws = 611.2 * np.exp(17.62 * temp / (243.12 + temp))
            pw = pws * (rh / 100.0)
            if pw >= 101325:
                humidity_ratio.append(None)
            else:
                w = 0.622 * pw / (101325 - pw)
                humidity_ratio.append(w * 1000)
        
        fig.add_trace(go.Scatter(
            x=temp_range,
            y=humidity_ratio,
            mode='lines',
            name=f'{rh}% RH',
            line=dict(color=color, width=1, dash='dash'),
            showlegend=False,
            hovertemplate=f'{rh}% RH<br>T: %{{x:.1f}}°C<br>ω: %{{y:.1f}} g/kg<extra></extra>'
        ))
    
    # Comfortzone (typisch 20-26°C en 30-60% RH)
    comfort_temp_range = np.linspace(20, 26, 50)
    
    comfort_lower = []
    for temp in comfort_temp_range:
        pws = 611.2 * np.exp(17.62 * temp / (243.12 + temp))
        pw = pws * 0.30
        w = 0.622 * pw / (101325 - pw)
        comfort_lower.append(w * 1000)
    
    comfort_upper = []
    for temp in comfort_temp_range:
        pws = 611.2 * np.exp(17.62 * temp / (243.12 + temp))
        pw = pws * 0.60
        w = 0.622 * pw / (101325 - pw)
        comfort_upper.append(w * 1000)
    
    fig.add_trace(go.Scatter(
        x=list(comfort_temp_range) + list(comfort_temp_range[::-1]),
        y=comfort_lower + comfort_upper[::-1],
        fill='toself',
        fillcolor='rgba(46, 204, 113, 0.2)',
        line=dict(width=0),
        name=t['comfort_zone'],
        showlegend=True,
        hoverinfo='skip'
    ))
    
    # Bereken en markeer punt
    if current_temp is not None and current_rh is not None:
        pws_current = 611.2 * np.exp(17.62 * current_temp / (243.12 + current_temp))
        pw_current = pws_current * (current_rh / 100.0)
        w_current = 0.622 * pw_current / (101325 - pw_current)
        w_current_g_kg = w_current * 1000
        
        fig.add_trace(go.Scatter(
            x=[current_temp],
            y=[w_current_g_kg],
            mode='markers+text',
            name=label,
            marker=dict(
                size=15,
                color='#e74c3c',
                symbol='star',
                line=dict(width=2, color='white')
            ),
            text=[f"{current_temp:.1f}°C<br>{current_rh:.0f}%"],
            textposition='top center',
            textfont=dict(size=12, color='#e74c3c', family='Arial Black'),
            showlegend=True,
            hovertemplate=f'{label}<br>T: {current_temp:.1f}°C<br>RH: {current_rh:.0f}%<br>ω: {w_current_g_kg:.1f} g/kg<extra></extra>'
        ))
    
    # Layout
    fig.update_layout(
        title={
            'text': f"📊 {t['psychrometric_chart']}",
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20, 'color': '#2c3e50', 'family': 'Arial Black'}
        },
        xaxis_title=t['dry_bulb_temp'],
        yaxis_title=t['humidity_ratio_axis'],
        xaxis=dict(
            range=[0, 40],
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)',
            dtick=5
        ),
        yaxis=dict(
            range=[0, 25],
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)',
            dtick=5
        ),
        height=600,
        plot_bgcolor='rgba(255,255,255,1)',
        paper_bgcolor='white',
        hovermode='closest',
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='#2c3e50',
            borderwidth=1
        )
    )
    
    return fig


def add_device_points(fig, points):
    """Voeg de huidige toestand van meerdere devices toe aan een Mollier diagram.

    points: [(naam, temperatuur, rv, kleur)]
    """
    for name, temp, rh, color in points:
        pws = 611.2 * np.exp(17.62 * temp / (243.12 + temp))
        pw = pws * (rh / 100.0)
        w_g_kg = 0.622 * pw / (101325 - pw) * 1000
        fig.add_trace(go.Scatter(
            x=[temp],
            y=[w_g_kg],
            mode='markers+text',
            name=name,
            marker=dict(size=14, color=color, symbol='star', line=dict(width=2, color='white')),
            text=[name],
            textposition='top center',
            textfont=dict(size=12, color=color, family='Arial Black'),
            hovertemplate=f'{name}<br>T: {temp:.1f}°C<br>RH: {rh:.0f}%<br>ω: {w_g_kg:.1f} g/kg<extra></extra>'
        ))
    return fig
