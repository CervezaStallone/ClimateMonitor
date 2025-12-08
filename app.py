from dash import Dash
from waitress import serve
import logging

# Import modules
from database import init_database, cleanup_old_data, DATA_RETENTION_DAYS
from modbus_reader import start_modbus_thread
from layout import create_layout, HTML_TEMPLATE
from callbacks import register_callbacks

# Zet Waitress logging op ERROR niveau (onderdruk warnings)
logging.getLogger('waitress').setLevel(logging.ERROR)

# Initialiseer database
print("=== XY-MD02 WebApp Startup ===")
init_database()

# Voer cleanup uit (indien retention policy actief)
if DATA_RETENTION_DAYS > 0:
    cleanup_old_data()

# Start Modbus thread
modbus_thread = start_modbus_thread()

# Dash app initialisatie
print("→ Initialiseren Dash applicatie...")
app = Dash(__name__, title="XY-MD02 Temperature & Humidity Monitor")
server = app.server
app.index_string = HTML_TEMPLATE
print("✓ Dash applicatie geïnitialiseerd")

# Layout instellen
print("→ Layout configureren...")
app.layout = create_layout()
print("✓ Layout geconfigureerd")

# Callbacks registreren
print("→ Callbacks registreren...")
register_callbacks(app)
print("✓ Callbacks geregistreerd")

# Main entry point
if __name__ == '__main__':
    print("\n=== Server wordt gestart ===")
    print("→ Waitress WSGI server starten op 0.0.0.0:8050...")
    print("✓ Server actief - Open browser op: http://127.0.0.1:8050")
    print("Druk CTRL+C om te stoppen\n")
    
    try:
        # Gebruik Waitress production server (cross-platform)
        # Verhoog threads en channel_timeout voor Dash's frequente callbacks
        serve(
            server, 
            host='0.0.0.0', 
            port=8050, 
            threads=8,                    # Meer threads voor concurrent requests
            channel_timeout=60,           # Timeout voor idle connections
            cleanup_interval=10,          # Cleanup interval voor oude connections
            asyncore_use_poll=True        # Betere performance op Windows
        )
    except KeyboardInterrupt:
        print("\n\n=== Server gestopt ===")
