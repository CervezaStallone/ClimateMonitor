import minimalmodbus
import time
import math
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from database import (
    DB_FILE, 
    DATA_RETENTION_DAYS, 
    get_table_name, 
    ensure_table_exists, 
    cleanup_old_data
)

# Laad environment variabelen
load_dotenv()

# Modbus configuratie uit environment met validatie
try:
    MODBUS_PORT = os.getenv('MODBUS_PORT', 'COM11')
    MODBUS_SLAVE_ID = int(os.getenv('MODBUS_SLAVE_ID', '1'))
    MODBUS_BAUDRATE = int(os.getenv('MODBUS_BAUDRATE', '9600'))
    MODBUS_BYTESIZE = int(os.getenv('MODBUS_BYTESIZE', '8'))
    MODBUS_PARITY = os.getenv('MODBUS_PARITY', 'N')
    MODBUS_STOPBITS = int(os.getenv('MODBUS_STOPBITS', '1'))
    MODBUS_TIMEOUT = int(os.getenv('MODBUS_TIMEOUT', '1'))
    MODBUS_FUNCTION_CODE = int(os.getenv('MODBUS_FUNCTION_CODE', '4'))
    MODBUS_REGISTER_TEMP = int(os.getenv('MODBUS_REGISTER_TEMP', '1'))
    MODBUS_REGISTER_HUMIDITY = int(os.getenv('MODBUS_REGISTER_HUMIDITY', '2'))
    
    # Valideer configuratie
    if MODBUS_SLAVE_ID < 1 or MODBUS_SLAVE_ID > 247:
        raise ValueError(f"MODBUS_SLAVE_ID moet tussen 1-247 zijn, kreeg: {MODBUS_SLAVE_ID}")
    if MODBUS_BAUDRATE not in [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]:
        print(f"Waarschuwing: Ongebruikelijke baudrate: {MODBUS_BAUDRATE}")
    if MODBUS_PARITY not in ['N', 'E', 'O']:
        raise ValueError(f"MODBUS_PARITY moet N, E of O zijn, kreeg: {MODBUS_PARITY}")
    if MODBUS_TIMEOUT < 0:
        raise ValueError(f"MODBUS_TIMEOUT moet positief zijn, kreeg: {MODBUS_TIMEOUT}")
except ValueError as e:
    print(f"FOUT in .env configuratie: {e}")
    raise

# Configuratie van Modbus RTU apparaat
# Mapping voor parity settings
PARITY_MAP = {
    'N': minimalmodbus.serial.PARITY_NONE,
    'E': minimalmodbus.serial.PARITY_EVEN,
    'O': minimalmodbus.serial.PARITY_ODD
}

# Global instrument variable - initialized lazily to avoid serial port access during import
instrument = None


def _initialize_instrument():
    """Initialize Modbus instrument - called only when needed, not during module import"""
    global instrument
    if instrument is None:
        instrument = minimalmodbus.Instrument(MODBUS_PORT, MODBUS_SLAVE_ID)
        instrument.serial.baudrate = MODBUS_BAUDRATE
        instrument.serial.bytesize = MODBUS_BYTESIZE
        instrument.serial.parity = PARITY_MAP.get(MODBUS_PARITY, minimalmodbus.serial.PARITY_NONE)
        instrument.serial.stopbits = MODBUS_STOPBITS
        instrument.serial.timeout = MODBUS_TIMEOUT
    return instrument


def read_modbus_data():
    """Thread functie om Modbus data te lezen en op te slaan"""
    print(f"→ Modbus thread actief - verbinding maken met {MODBUS_PORT}...")
    
    # Initialize instrument now (not during import)
    _initialize_instrument()
    
    last_cleanup = datetime.now()
    current_table = get_table_name()
    
    # Optimalisatie: Hergebruik database connectie en batch inserts
    conn = sqlite3.connect(DB_FILE, timeout=30)
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')
    
    print(f"✓ Database connectie OK - schrijven naar tabel: {current_table}")
    
    # Buffer voor batch inserts (30 metingen = 30 seconden)
    # Optimalisatie: minder schrijfoperaties = langere levensduur database/storage
    measurement_buffer = []
    BATCH_SIZE = 30
    last_commit_time = time.time()
    COMMIT_INTERVAL = 30  # seconds
    
    while True:
        try:
            # Voer cleanup uit elke 24 uur
            if DATA_RETENTION_DAYS > 0 and (datetime.now() - last_cleanup).total_seconds() >= 86400:
                cleanup_old_data()
                last_cleanup = datetime.now()
            
            register_temp = instrument.read_register(MODBUS_REGISTER_TEMP, 0, MODBUS_FUNCTION_CODE)
            register_humidity = instrument.read_register(MODBUS_REGISTER_HUMIDITY, 0, MODBUS_FUNCTION_CODE)
            
            temperature = register_temp / 10
            humidity = register_humidity / 10
            
            # Valideer sensor data
            if not (-50 <= temperature <= 100):
                print(f"Waarschuwing: Ongeldige temperatuur {temperature}°C - meting overgeslagen")
                time.sleep(1)
                continue
            
            if not (0 <= humidity <= 100):
                print(f"Waarschuwing: Ongeldige luchtvochtigheid {humidity}% - meting overgeslagen")
                time.sleep(1)
                continue
            
            # Bereken dauwpunt
            dewpoint = temperature - ((100 - humidity) / 5.0)
            
            # Bereken absolute vochtigheid (g/m³)
            # Formule: AH = (6.112 × e^((17.67 × T)/(T+243.5)) × RH × 2.1674) / (273.15+T)
            absolute_humidity = (6.112 * math.exp((17.67 * temperature) / (temperature + 243.5)) * humidity * 2.1674) / (273.15 + temperature)
            
            # Bereken Humidex
            # Formule: Humidex = T + 0.5555 × (e - 10)
            # waarbij e = 6.11 × e^(5417.7530 × (1/273.16 - 1/(273.15+Td)))
            # en Td = dauwpunt in Kelvin
            dewpoint_kelvin = dewpoint + 273.15
            e = 6.11 * math.exp(5417.7530 * ((1/273.16) - (1/dewpoint_kelvin)))
            humidex = temperature + 0.5555 * (e - 10)
            
            # Opslaan in buffer (integer timestamp voor performance)
            timestamp = datetime.now()
            timestamp_int = int(timestamp.timestamp())
            measurement_buffer.append((timestamp_int, temperature, humidity, dewpoint, absolute_humidity))
            
            print(f"{timestamp.strftime('%H:%M:%S')} - Temperature: {temperature:.1f}°C, Humidity: {humidity:.1f}%, Dewpoint: {dewpoint:.1f}°C, Absolute Humidity: {absolute_humidity:.1f}g/m³")
            
            # Check of we een nieuwe dag zijn (table switch)
            new_table = get_table_name()
            if new_table != current_table:
                # Flush buffer naar oude tabel
                if measurement_buffer:
                    cursor.execute('BEGIN')
                    cursor.executemany(
                        f'INSERT INTO {current_table} (timestamp, temperature, humidity, dewpoint, absolute_humidity) VALUES (?, ?, ?, ?, ?)',
                        measurement_buffer
                    )
                    conn.commit()
                    print(f"✓ {len(measurement_buffer)} metingen opgeslagen in {current_table} (dag wissel)")
                    measurement_buffer.clear()
                
                # Maak nieuwe tabel aan en switch
                ensure_table_exists(cursor, new_table)
                conn.commit()
                current_table = new_table
                print(f"→ Nieuwe dag: nu schrijven naar {current_table}")
            
            # Batch commit: als buffer vol is OF tijd verstreken
            current_time = time.time()
            if len(measurement_buffer) >= BATCH_SIZE or (current_time - last_commit_time) >= COMMIT_INTERVAL:
                if measurement_buffer:
                    cursor.execute('BEGIN')
                    cursor.executemany(
                        f'INSERT INTO {current_table} (timestamp, temperature, humidity, dewpoint, absolute_humidity) VALUES (?, ?, ?, ?, ?)',
                        measurement_buffer
                    )
                    conn.commit()
                    print(f"✓ {len(measurement_buffer)} metingen opgeslagen in {current_table} (batch commit)")
                    measurement_buffer.clear()
                    last_commit_time = current_time
            
            time.sleep(1)
        except Exception as e:
            print(f"Modbus fout: {e}")
            # Bij fout: probeer buffer alsnog op te slaan
            if measurement_buffer:
                try:
                    cursor.executemany(
                        f'INSERT INTO {current_table} (timestamp, temperature, humidity, dewpoint, absolute_humidity) VALUES (?, ?, ?, ?, ?)',
                        measurement_buffer
                    )
                    conn.commit()
                    measurement_buffer.clear()
                except:
                    pass
            time.sleep(5)


def start_modbus_thread():
    """Start Modbus reader thread als daemon"""
    import threading
    
    # Test eerst of minimalmodbus werkt
    try:
        print(f"→ Start Modbus thread (poort: {MODBUS_PORT}, slave: {MODBUS_SLAVE_ID})")
        modbus_thread = threading.Thread(target=read_modbus_data, daemon=True)
        modbus_thread.start()
        print("✓ Modbus reader thread gestart")
        return modbus_thread
    except Exception as e:
        print(f"✗ FOUT bij starten Modbus thread: {e}")
        print(f"   Type: {type(e).__name__}")
        print("   Zorg dat je de app start met de virtual environment!")
        print("   Gebruik: .venv\\Scripts\\python.exe app.py")
        raise
