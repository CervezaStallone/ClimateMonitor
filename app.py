from dash import Dash

# Import modules
from database import init_database, cleanup_old_data, DATA_RETENTION_DAYS
from modbus_reader import start_modbus_thread
from layout import create_layout, HTML_TEMPLATE
from callbacks import register_callbacks

# Initialiseer database
print("=== XY-MD02 WebApp Startup ===")
init_database()

# Voer cleanup uit (indien retention policy actief)
if DATA_RETENTION_DAYS > 0:
    cleanup_old_data()

# Start Modbus thread
modbus_thread = start_modbus_thread()

# Dash app initialisatie
app = Dash(__name__, title="XY-MD02 Temperature & Humidity Monitor")
server = app.server
app.index_string = HTML_TEMPLATE

# Layout instellen
app.layout = create_layout()

# Callbacks registreren
register_callbacks(app)

# Main entry point
if __name__ == '__main__':
    print("\n=== Server wordt gestart ===")
    print("Open browser op: http://127.0.0.1:8050")
    print("Druk CTRL+C om te stoppen\n")
    
    try:
        app.run(debug=False, host='0.0.0.0', port=8050)
    except KeyboardInterrupt:
        print("\n\n=== Server gestopt ===")
