from dash import dcc, html

import settings
from translations import LANGUAGE_NAMES, TRANSLATIONS

# Custom HTML template met CSS
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            .tooltip-container {
                position: relative;
                cursor: help;
            }
            .tooltip-container .tooltip-text {
                visibility: hidden;
                width: 280px;
                background-color: #2c3e50;
                color: #fff;
                text-align: left;
                border-radius: 8px;
                padding: 12px;
                position: absolute;
                z-index: 1000;
                top: 110%;
                left: 50%;
                margin-left: -140px;
                opacity: 0;
                transition: opacity 0.3s;
                font-size: 13px;
                line-height: 1.6;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }
            .tooltip-container .tooltip-text::after {
                content: "";
                position: absolute;
                bottom: 100%;
                left: 50%;
                margin-left: -8px;
                border-width: 8px;
                border-style: solid;
                border-color: transparent transparent #2c3e50 transparent;
            }
            .tooltip-container:hover .tooltip-text {
                visibility: visible;
                opacity: 1;
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

def create_layout():
    """Creëert de hoofdlayout van de applicatie (per page load, zodat de standaardtaal uit Settings komt)"""
    DEFAULT_LANGUAGE = settings.get('default_language')
    t = TRANSLATIONS[DEFAULT_LANGUAGE]
    return html.Div([
        dcc.Location(id='url', refresh=False),
        # Store voor geselecteerde taal (standaardtaal uit Settings)
        dcc.Store(id='selected-language', data=DEFAULT_LANGUAGE),
        # Store voor grafiek zoom/relayout state
        dcc.Store(id='graph-relayout-data', data={}),
        
        # Header met taalkeuze
        html.Div([
            html.Div([
                html.Div([
                    dcc.Dropdown(
                        id='language-selector',
                        options=[{'label': LANGUAGE_NAMES[lang], 'value': lang} for lang in LANGUAGE_NAMES.keys()],
                        value=DEFAULT_LANGUAGE,
                        clearable=False,
                        style={
                            'width': '80px',
                            'fontSize': '14px',
                            'fontWeight': 'bold'
                        }
                    )
                ], style={'display': 'inline-block', 'width': '10%', 'textAlign': 'left', 'verticalAlign': 'middle'}),
                html.H1(id='page-title', children=t['title'], style={
                    'textAlign': 'center',
                    'color': '#2c3e50',
                    'marginBottom': '0px',
                    'fontFamily': 'Arial, sans-serif',
                    'display': 'inline-block',
                    'width': '90%'
                })
            ])
        ], style={
            'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            'padding': '20px',
            'borderRadius': '10px',
            'marginBottom': '20px',
            'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'
        }),
        
        dcc.Tabs(id='main-tabs', value='dashboard', children=[
        dcc.Tab(id='tab-dashboard', label=t['tab_dashboard'], value='dashboard', children=[
        # Device keuze: alle devices (gecombineerd) of één device
        html.Div([
            html.Label(id='label-device', children=t['lbl_device_select'], style={
                'fontSize': '16px', 'fontWeight': 'bold', 'color': '#2c3e50', 'marginRight': '15px'
            }),
            dcc.Dropdown(id='device-selector', value=0, clearable=False,
                         style={'width': '350px', 'display': 'inline-block', 'verticalAlign': 'middle'})
        ], style={
            'margin': '20px 0',
            'padding': '15px 20px',
            'background': 'white',
            'borderRadius': '15px',
            'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'
        }),
        
        # Overzicht per device (status en actuele waarden)
        html.Div(id='device-overview', style={'marginBottom': '20px'}),
        
        # Huidige waarden - alle 5 cards in een rij (alleen bij één geselecteerd device)
        html.Div(id='current-cards', children=[
            # Temperatuur
            html.Div([
                html.Div([
                    html.Div("🌡️", style={'fontSize': '35px', 'marginBottom': '8px'}),
                    html.Div(id='label-temperature', children=t['temperature'], style={'fontSize': '14px', 'color': '#7f8c8d', 'marginBottom': '5px'}),
                    html.Div(id='current-temp', style={
                        'fontSize': '28px',
                        'fontWeight': 'bold',
                        'color': '#3498db'
                    })
                ], style={
                    'background': 'white',
                    'padding': '20px',
                    'borderRadius': '15px',
                    'boxShadow': '0 4px 6px rgba(0,0,0,0.1)',
                    'textAlign': 'center',
                    'border': '2px solid #3498db',
                    'height': '140px'
                })
            ], style={'width': '19%', 'display': 'inline-block', 'marginRight': '1%'}),
            
            # Luchtvochtigheid
            html.Div([
                html.Div([
                    html.Div("💧", style={'fontSize': '35px', 'marginBottom': '8px'}),
                    html.Div(id='label-humidity', children=t['humidity'], style={'fontSize': '14px', 'color': '#7f8c8d', 'marginBottom': '5px'}),
                    html.Div(id='current-humidity', style={
                        'fontSize': '28px',
                        'fontWeight': 'bold',
                        'color': '#e74c3c'
                    })
                ], style={
                    'background': 'white',
                    'padding': '20px',
                    'borderRadius': '15px',
                    'boxShadow': '0 4px 6px rgba(0,0,0,0.1)',
                    'textAlign': 'center',
                    'border': '2px solid #e74c3c',
                    'height': '140px'
                })
            ], style={'width': '19%', 'display': 'inline-block', 'marginRight': '1%'}),
            
            # Dauwpunt
            html.Div([
                html.Div([
                    html.Div("💦", style={'fontSize': '35px', 'marginBottom': '8px'}),
                    html.Div(id='label-dewpoint', children=t['dewpoint'], style={'fontSize': '14px', 'color': '#7f8c8d', 'marginBottom': '5px'}),
                    html.Div(id='current-dewpoint', style={
                        'fontSize': '28px',
                        'fontWeight': 'bold',
                        'color': '#9b59b6'
                    })
                ], style={
                    'background': 'white',
                    'padding': '20px',
                    'borderRadius': '15px',
                    'boxShadow': '0 4px 6px rgba(0,0,0,0.1)',
                    'textAlign': 'center',
                    'border': '2px solid #9b59b6',
                    'height': '140px'
                })
            ], style={'width': '19%', 'display': 'inline-block', 'marginRight': '1%'}),
            
            # Absolute Vochtigheid
            html.Div([
                html.Div([
                    html.Div("🌫️", style={'fontSize': '35px', 'marginBottom': '8px'}),
                    html.Div(id='label-abs-humidity', children=t['abs_humidity'], style={'fontSize': '14px', 'color': '#7f8c8d', 'marginBottom': '5px'}),
                    html.Div(id='current-abs-humidity', style={
                        'fontSize': '28px',
                        'fontWeight': 'bold',
                        'color': '#16a085'
                    })
                ], style={
                    'background': 'white',
                    'padding': '20px',
                    'borderRadius': '15px',
                    'boxShadow': '0 4px 6px rgba(0,0,0,0.1)',
                    'textAlign': 'center',
                    'border': '2px solid #16a085',
                    'height': '140px'
                })
            ], style={'width': '19%', 'display': 'inline-block', 'marginRight': '1%'}),
            
            # Behagelijkheid
            html.Div([
                html.Div([
                    html.Div("☀️", id='comfort-icon', style={'fontSize': '35px', 'marginBottom': '8px'}),
                    html.Div(id='label-comfort', children=t['comfort'], style={'fontSize': '14px', 'color': '#7f8c8d', 'marginBottom': '5px'}),
                    html.Div(id='comfort-level', style={
                        'fontSize': '14px',
                        'fontWeight': 'bold',
                        'color': '#2c3e50',
                        'lineHeight': '1.2',
                        'marginBottom': '5px'
                    }),
                    html.Div([
                        html.Span(id='label-score', children=t['score'] + ': ', style={'fontSize': '14px', 'color': '#7f8c8d'}),
                        html.Span(id='comfort-score', style={'fontSize': '20px', 'fontWeight': 'bold', 'color': '#2c3e50'})
                    ]),
                    html.Div(id='tooltip-content', children=[
                        TRANSLATIONS[DEFAULT_LANGUAGE]['score_explanation'] + ":",
                        html.Br(),
                        f"0 = {TRANSLATIONS[DEFAULT_LANGUAGE]['comfort_0']}",
                        html.Br(),
                        f"1 = {TRANSLATIONS[DEFAULT_LANGUAGE]['comfort_1']}",
                        html.Br(),
                        f"2 = {TRANSLATIONS[DEFAULT_LANGUAGE]['comfort_2']}",
                        html.Br(),
                        f"3 = {TRANSLATIONS[DEFAULT_LANGUAGE]['comfort_3']}",
                        html.Br(),
                        f"4 = {TRANSLATIONS[DEFAULT_LANGUAGE]['comfort_4']}",
                        html.Br(),
                        f"5 = {TRANSLATIONS[DEFAULT_LANGUAGE]['comfort_5']}",
                        html.Br(),
                        f"6 = {TRANSLATIONS[DEFAULT_LANGUAGE]['comfort_6']}"
                    ], className='tooltip-text')
                ], className='tooltip-container', style={
                    'background': 'white',
                    'padding': '20px',
                    'borderRadius': '15px',
                    'boxShadow': '0 4px 6px rgba(0,0,0,0.1)',
                    'textAlign': 'center',
                    'border': '2px solid #f39c12',
                    'height': '140px',
                    'display': 'flex',
                    'flexDirection': 'column',
                    'justifyContent': 'center',
                    'position': 'relative'
                })
            ], style={'width': '19%', 'display': 'inline-block', 'verticalAlign': 'top'})
        ], style={'marginBottom': '30px'}),
        
        # Grafiek
        html.Div([
            dcc.Graph(id='live-graph', style={'borderRadius': '10px'})
        ], style={
            'background': 'white',
            'padding': '20px',
            'borderRadius': '15px',
            'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'
        }),
        
        # Update interval
        dcc.Interval(
            id='graph-update',
            interval=1000,
            n_intervals=0
        ),
        
        # Controls
        html.Div([
            html.Div([
                html.Label(id='label-time-period', children=t['time_period'], style={
                    'fontSize': '16px',
                    'fontWeight': 'bold',
                    'color': '#2c3e50',
                    'marginBottom': '10px',
                    'display': 'block'
                }),
                dcc.Dropdown(
                    id='time-range-dropdown',
                    options=[{'label': t[key], 'value': value} for key, value in [
                        ('last_1min', 1), ('last_5min', 5), ('last_15min', 15), ('last_30min', 30), ('last_1hour', 60),
                        ('last_6hours', 360), ('last_12hours', 720), ('last_24hours', 1440), ('last_7days', 10080),
                        ('last_14days', 20160), ('last_1month', 43200), ('last_3months', 129600),
                        ('last_6months', 259200), ('all_data', -1)]],
                    value=5,
                    clearable=False,
                    style={'borderRadius': '8px'}
                )
            ], style={'width': '48%', 'display': 'inline-block'}),
            
            html.Div([
                html.Label(id='label-database', children=t['database'], style={
                    'fontSize': '16px',
                    'fontWeight': 'bold',
                    'color': '#2c3e50',
                    'marginBottom': '10px',
                    'display': 'block'
                }),
                html.Div(id='data-count', style={
                    'fontSize': '24px',
                    'fontWeight': 'bold',
                    'color': '#27ae60'
                })
            ], style={'width': '48%', 'display': 'inline-block', 'float': 'right', 'textAlign': 'right'})
        ], style={
            'marginTop': '30px',
            'padding': '20px',
            'background': 'white',
            'borderRadius': '15px',
            'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'
        }),
        
        # Psychrometric Chart (Mollier Diagram) met historische replay
        html.Div([
            html.H3(id='label-psychrometric-chart', children=f"📐 {t['psychrometric_chart']}", style={
                'color': '#2c3e50',
                'marginBottom': '20px',
                'fontFamily': 'Arial Black'
            }),
            
            dcc.Graph(
                id='psychrometric-chart',
                config={'displayModeBar': True, 'displaylogo': False}
            ),
            
            # Knop om bereik te kiezen (alleen bij één geselecteerd device)
            html.Div(id='history-hint', style={'textAlign': 'center', 'color': '#7f8c8d', 'marginTop': '20px'}),
            html.Div(id='history-controls', children=[
                html.Button(
                    id='open-range-modal-btn',
                    children=t['btn_select_range'],
                    n_clicks=0,
                    style={
                        'padding': '12px 30px',
                        'fontSize': '16px',
                        'fontWeight': 'bold',
                        'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        'color': 'white',
                        'border': 'none',
                        'borderRadius': '12px',
                        'cursor': 'pointer',
                        'boxShadow': '0 4px 15px rgba(102, 126, 234, 0.4)',
                        'transition': 'all 0.3s ease',
                        'marginTop': '20px'
                    }
                )
            ], style={'textAlign': 'center', 'marginBottom': '20px'}),
            
            # Slider voor historische data
            html.Div([
                html.Label(id='label-time-position', children=t['time_position'], style={
                    'fontSize': '16px',
                    'fontWeight': 'bold',
                    'color': '#2c3e50',
                    'marginBottom': '10px',
                    'display': 'block'
                }),
                html.Div(id='slider-timestamp-display', style={
                    'fontSize': '20px',
                    'fontWeight': 'bold',
                    'color': '#3498db',
                    'marginBottom': '15px',
                    'textAlign': 'center',
                    'padding': '10px',
                    'background': '#ecf0f1',
                    'borderRadius': '8px'
                }),
                dcc.Slider(
                    id='historical-time-slider',
                    min=0,
                    max=100,
                    step=1,
                    value=0,
                    marks={},
                    tooltip={'placement': 'bottom', 'always_visible': False}
                )
            ], id='slider-container', style={'display': 'none', 'marginTop': '20px'}),
            
            # Modal met presets en custom range
            html.Div([
                html.Div([
                    html.Div([
                        html.H3(id='modal-title', children=t['modal_title'], style={'marginTop': '0', 'color': '#2c3e50', 'marginBottom': '20px'}),
                        html.Button('✕', id='close-range-modal-btn', n_clicks=0, style={
                            'position': 'absolute',
                            'top': '15px',
                            'right': '15px',
                            'background': 'transparent',
                            'border': 'none',
                            'fontSize': '24px',
                            'cursor': 'pointer',
                            'color': '#7f8c8d'
                        }),
                        html.Div([
                            # Preset buttons in modal
                            html.H4(id='label-quick-select', children=t['quick_select'], style={'color': '#34495e', 'marginBottom': '15px'}),
                            html.Div([
                                html.Button(t['btn_5min'], id='preset-5min', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                                html.Button(t['btn_10min'], id='preset-10min', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                                html.Button(t['btn_30min'], id='preset-30min', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                                html.Button(t['btn_1hour'], id='preset-1hour', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                                html.Button(t['btn_2hours'], id='preset-2hours', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                                html.Button(t['btn_6hours'], id='preset-6hours', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                            ], style={'marginBottom': '10px', 'textAlign': 'center'}),
                            html.Div([
                                html.Button(t['btn_12hours'], id='preset-12hours', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                                html.Button(t['btn_24hours'], id='preset-24hours', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                                html.Button(t['btn_2days'], id='preset-2days', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                                html.Button(t['btn_week'], id='preset-week', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                                html.Button(t['btn_month'], id='preset-month', n_clicks=0, style={'margin': '5px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': '2px solid #3498db', 'background': 'white', 'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                            ], style={'marginBottom': '30px', 'textAlign': 'center'}),
                            
                            # Divider
                            html.Hr(style={'border': '1px solid #ecf0f1', 'margin': '20px 0'}),
                            
                            # Custom date/time picker
                            html.H4(id='label-specific-period', children=t['specific_period'], style={'color': '#34495e', 'marginBottom': '15px'}),
                            html.Label(id='label-start-datetime', children=t['start_datetime'], style={'fontWeight': 'bold', 'marginBottom': '10px', 'display': 'block'}),
                            dcc.DatePickerSingle(
                                id='custom-start-date',
                                display_format='DD-MM-YYYY',
                                placeholder=t['select_date'],
                                style={'marginBottom': '10px'}
                            ),
                            html.Div([
                                dcc.Input(id='custom-start-hour', type='number', min=0, max=23, value=0, placeholder=t['hour_placeholder'], style={'width': '70px', 'marginRight': '5px', 'padding': '8px', 'borderRadius': '5px', 'border': '1px solid #bdc3c7'}),
                                html.Span(':', style={'marginRight': '5px', 'fontWeight': 'bold'}),
                                dcc.Input(id='custom-start-minute', type='number', min=0, max=59, value=0, placeholder='MM', style={'width': '70px', 'padding': '8px', 'borderRadius': '5px', 'border': '1px solid #bdc3c7'})
                            ], style={'marginBottom': '20px'}),
                            
                            html.Label(id='label-end-datetime', children=t['end_datetime'], style={'fontWeight': 'bold', 'marginBottom': '10px', 'display': 'block'}),
                            dcc.DatePickerSingle(
                                id='custom-end-date',
                                display_format='DD-MM-YYYY',
                                placeholder=t['select_date'],
                                style={'marginBottom': '10px'}
                            ),
                            html.Div([
                                dcc.Input(id='custom-end-hour', type='number', min=0, max=23, value=23, placeholder=t['hour_placeholder'], style={'width': '70px', 'marginRight': '5px', 'padding': '8px', 'borderRadius': '5px', 'border': '1px solid #bdc3c7'}),
                                html.Span(':', style={'marginRight': '5px', 'fontWeight': 'bold'}),
                                dcc.Input(id='custom-end-minute', type='number', min=0, max=59, value=59, placeholder='MM', style={'width': '70px', 'padding': '8px', 'borderRadius': '5px', 'border': '1px solid #bdc3c7'})
                            ], style={'marginBottom': '20px'}),
                            
                            html.Button(t['btn_apply'], id='apply-custom-range-btn', n_clicks=0, style={
                                'width': '100%',
                                'padding': '12px',
                                'background': '#27ae60',
                                'color': 'white',
                                'border': 'none',
                                'borderRadius': '8px',
                                'cursor': 'pointer',
                                'fontWeight': 'bold',
                                'fontSize': '16px'
                            })
                        ], style={'padding': '25px'})
                    ], style={
                        'position': 'relative',
                        'background': 'white',
                        'borderRadius': '15px',
                        'maxWidth': '600px',
                        'maxHeight': '90vh',
                        'overflow': 'auto',
                        'margin': '30px auto',
                        'boxShadow': '0 10px 40px rgba(0,0,0,0.3)'
                    })
                ], id='range-modal', style={
                    'display': 'none',
                    'position': 'fixed',
                    'zIndex': '1000',
                    'left': '0',
                    'top': '0',
                    'width': '100%',
                    'height': '100%',
                    'background': 'rgba(0,0,0,0.5)',
                    'overflow': 'auto'
                })
            ])
        ], style={
            'marginTop': '30px',
            'padding': '30px',
            'background': 'white',
            'borderRadius': '15px',
            'boxShadow': '0 4px 6px rgba(0,0,0,0.1)',
            'marginBottom': '50px'
        }),
        
        ]),
        dcc.Tab(id='tab-settings', label=t['tab_settings'], value='settings', children=[
            html.Div(id='settings-content', style={
                'marginTop': '20px',
                'padding': '30px',
                'background': 'white',
                'borderRadius': '15px',
                'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'
            })
        ])
        ]),
        
        # Store voor historische data
        dcc.Store(id='historical-data-store'),
        dcc.Store(id='selected-range-method', data='preset'),  # 'preset' of 'custom'
        dcc.Store(id='selected-range-value')  # Opslaan van minutes (preset) of dates (custom)
    ], style={
        'maxWidth': '1400px',
        'margin': '0 auto',
        'padding': '20px',
        'background': '#ecf0f1',
        'fontFamily': 'Arial, sans-serif'
    })
