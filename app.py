from dash import Dash
from waitress import serve
import logging

# Import modules
import auth
import devices
import settings
from database import init_database, cleanup_old_data
from modbus_reader import start_modbus_thread
from layout import create_layout, HTML_TEMPLATE
from callbacks import register_callbacks
from settings_ui import register_settings_callbacks

# Zet Waitress logging op ERROR niveau (onderdruk warnings)
logging.getLogger('waitress').setLevel(logging.ERROR)

# Initialiseer database
print("=== XY-MD02 WebApp Startup ===")
settings.load()
init_database()
devices.init_devices()

# Voer cleanup uit (indien retention policy actief)
if settings.get('data_retention_days') > 0:
    cleanup_old_data()

# Start Modbus thread
modbus_thread = start_modbus_thread()

# Dash app initialisatie
print("→ Initialiseren Dash applicatie...")
app = Dash(__name__, title="XY-MD02 Temperature & Humidity Monitor", suppress_callback_exceptions=True)
server = app.server
auth.init_app(server)
app.index_string = HTML_TEMPLATE
print("✓ Dash applicatie geïnitialiseerd")

# Layout instellen
print("→ Layout configureren...")
app.layout = create_layout  # functie: standaardtaal per page load uit Settings
print("✓ Layout geconfigureerd")

# Callbacks registreren
print("→ Callbacks registreren...")
register_callbacks(app)
register_settings_callbacks(app)
print("✓ Callbacks geregistreerd")

# Main entry point
FALLBACK_HOST, FALLBACK_PORT = '0.0.0.0', 8050


def run_server(host, port):
    # Gebruik Waitress production server (cross-platform)
    # Verhoog threads en channel_timeout voor Dash's frequente callbacks
    print(f"→ Waitress WSGI server starten op {host}:{port}...")
    print(f"✓ Server actief - Open browser op: http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}")
    print("Druk CTRL+C om te stoppen\n")
    serve(
        server, 
        host=host, 
        port=port, 
        threads=8,                    # Meer threads voor concurrent requests
        channel_timeout=60,           # Timeout voor idle connections
        cleanup_interval=10,          # Cleanup interval voor oude connections
        asyncore_use_poll=True        # Betere performance op Windows
    )


if __name__ == '__main__':
    print("\n=== Server wordt gestart ===")
    host, port = settings.get('app_host'), settings.get('app_port')
    try:
        try:
            run_server(host, port)
        except OSError as e:
            # Een verkeerd adres/poort in Settings mag een remote apparaat niet onbereikbaar maken
            if (host, port) == (FALLBACK_HOST, FALLBACK_PORT):
                raise
            print(f"✗ Kan niet luisteren op {host}:{port} ({e}) - terugval naar {FALLBACK_HOST}:{FALLBACK_PORT}")
            run_server(FALLBACK_HOST, FALLBACK_PORT)
    except KeyboardInterrupt:
        print("\n\n=== Server gestopt ===")
