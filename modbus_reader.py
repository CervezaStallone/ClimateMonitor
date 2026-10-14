"""Modbus RTU uitlezen van meerdere bussen (RS-485 interfaces) met elk meerdere slaves.

- Supervisor: start per actieve bus een BusPoller en herstart alleen bussen waarvan de
  configuratie in Settings is gewijzigd (of waarvan de thread onverwacht gestopt is).
- BusPoller: leest de devices op één bus na elkaar (RS-485 is half duplex). Bussen lopen
  parallel, dus een trage of ontbrekende interface houdt de andere bussen niet op.
- Writer: schrijft alle metingen in batches naar de database (minder schrijfacties = langere
  levensduur van SD-kaart/flash).
"""
import math
import queue
import sqlite3
import threading
import time
from datetime import datetime

import minimalmodbus
import serial

import alerts
import devices
import mqtt_publisher
import settings
from database import DB_FILE, cleanup_old_data, ensure_table_exists, get_table_name

PARITY_MAP = {
    'N': minimalmodbus.serial.PARITY_NONE,
    'E': minimalmodbus.serial.PARITY_EVEN,
    'O': minimalmodbus.serial.PARITY_ODD
}

# Geldige meetbereiken (buiten bereik = meting overgeslagen)
TEMP_RANGE = (-50, 100)
HUMIDITY_RANGE = (0, 100)

BATCH_SIZE = 30          # metingen per database commit
COMMIT_INTERVAL = 30     # seconden, maximaal tussen commits
MAX_BUFFER = 10000       # bij langdurige databasefouten: oudste metingen vervallen
MAX_BACKOFF = 60         # seconden tussen pogingen om een ontbrekende interface te openen
SUPERVISOR_INTERVAL = 2  # seconden


def derived_values(temperature, humidity):
    """Bereken dauwpunt (°C) en absolute vochtigheid (g/m³)."""
    dewpoint = temperature - ((100 - humidity) / 5.0)
    # Formule: AH = (6.112 × e^((17.67 × T)/(T+243.5)) × RH × 2.1674) / (273.15+T)
    absolute_humidity = (6.112 * math.exp((17.67 * temperature) / (temperature + 243.5)) * humidity * 2.1674) / (273.15 + temperature)
    return dewpoint, absolute_humidity


def read_device(instrument, device):
    """Lees temperatuur en luchtvochtigheid (signed registers × schaal)."""
    raw_temp = instrument.read_register(device['register_temp'], 0, device['function_code'], signed=True)
    raw_humidity = instrument.read_register(device['register_humidity'], 0, device['function_code'], signed=True)
    return round(raw_temp * device['scale_temp'], 3), round(raw_humidity * device['scale_humidity'], 3)


def open_instrument(bus, device):
    """Maak een Modbus instrument; slaves op dezelfde poort delen de seriële verbinding."""
    instrument = minimalmodbus.Instrument(bus['port'], device['slave_id'])
    instrument.serial.baudrate = bus['baudrate']
    instrument.serial.bytesize = bus['bytesize']
    instrument.serial.parity = PARITY_MAP.get(bus['parity'], minimalmodbus.serial.PARITY_NONE)
    instrument.serial.stopbits = bus['stopbits']
    instrument.serial.timeout = bus['timeout']
    if not instrument.serial.is_open:
        instrument.serial.open()
    return instrument


class Writer(threading.Thread):
    """Schrijft metingen (timestamp, temp, rh, dauwpunt, abs. vochtigheid, device_id) in batches."""

    def __init__(self, measurements):
        super().__init__(daemon=True, name='modbus-writer')
        self.measurements = measurements
        self.buffer = []
        self.last_commit = time.time()
        self.last_cleanup = time.time()

    def run(self):
        conn = sqlite3.connect(DB_FILE, timeout=30)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        while True:
            try:
                self.buffer.append(self.measurements.get(timeout=1))
            except queue.Empty:
                pass
            if len(self.buffer) >= BATCH_SIZE or (self.buffer and time.time() - self.last_commit >= COMMIT_INTERVAL):
                self.flush(conn)
            # Retentie: elke 24 uur oude dagtabellen verwijderen
            if settings.get('data_retention_days') > 0 and time.time() - self.last_cleanup >= 86400:
                cleanup_old_data()
                self.last_cleanup = time.time()

    def flush(self, conn):
        """Schrijf de buffer weg, per dagtabel (dag wissel binnen een batch gaat zo vanzelf goed)."""
        try:
            per_table = {}
            for row in self.buffer:
                per_table.setdefault(get_table_name(datetime.fromtimestamp(row[0])), []).append(row)
            conn.execute('BEGIN')
            for table, rows in per_table.items():
                ensure_table_exists(conn.cursor(), table)
                conn.executemany(
                    f'INSERT INTO {table} (timestamp, temperature, humidity, dewpoint, absolute_humidity, device_id) '
                    'VALUES (?, ?, ?, ?, ?, ?)', rows)
            conn.commit()
            if settings.get('debug_logging'):
                print(f"✓ {len(self.buffer)} metingen opgeslagen")
            self.buffer.clear()
        except Exception as e:
            conn.rollback()
            print(f"Database fout, metingen blijven in buffer ({len(self.buffer)}): {e}")
            del self.buffer[:-MAX_BUFFER]
        self.last_commit = time.time()


class BusPoller(threading.Thread):
    """Leest alle actieve devices op één bus, opnieuw verbinden met back-off bij fouten."""

    def __init__(self, bus, bus_devices, measurements, instrument_factory=open_instrument):
        super().__init__(daemon=True, name=f"modbus-bus-{bus['id']}")
        self.bus = bus
        self.devices = bus_devices
        self.measurements = measurements
        self.instrument_factory = instrument_factory
        self.stop_event = threading.Event()
        self.last_errors = {}

    def stop(self):
        self.stop_event.set()

    def run(self):
        backoff = 1
        while not self.stop_event.is_set():
            instruments = {}
            try:
                instruments = {d['id']: self.instrument_factory(self.bus, d) for d in self.devices}
                print(f"✓ {self.bus['name']} verbonden ({self.bus['port']}, {len(self.devices)} device(s))")
                backoff = 1
                while not self.stop_event.is_set():
                    started = time.time()
                    for device in self.devices:
                        if self.stop_event.is_set():
                            break
                        self.poll(instruments[device['id']], device)
                    interval = settings.get('poll_interval_seconds')
                    self.stop_event.wait(max(0, interval - (time.time() - started)))
            except (serial.SerialException, OSError) as e:
                # Interface ontbreekt of is losgekoppeld: alle devices op deze bus melden, later opnieuw
                for device in self.devices:
                    self.report_error(device, e)
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
            finally:
                for instrument in instruments.values():
                    try:
                        instrument.serial.close()
                    except Exception:
                        pass

    def poll(self, instrument, device):
        """Lees één device. Device fouten (geen antwoord) raken andere devices niet."""
        try:
            temperature, humidity = read_device(instrument, device)
        except minimalmodbus.ModbusException as e:
            # Device fout (geen/ongeldig antwoord). Let op: subklasse van OSError, dus vóór OSError afvangen
            self.report_error(device, e)
            return
        except (serial.SerialException, OSError):
            raise  # interface weg: hele bus opnieuw verbinden
        except Exception as e:
            self.report_error(device, e)
            return
        if not (TEMP_RANGE[0] <= temperature <= TEMP_RANGE[1]) or not (HUMIDITY_RANGE[0] <= humidity <= HUMIDITY_RANGE[1]):
            self.report_error(device, f"out of range: {temperature} °C, {humidity} %")
            return
        dewpoint, absolute_humidity = derived_values(temperature, humidity)
        self.measurements.put((int(time.time()), temperature, humidity, dewpoint, absolute_humidity, device['id']))
        devices.report_ok(device['id'], temperature, humidity)
        values = {'temperature': temperature, 'humidity': humidity, 'dewpoint': dewpoint,
                  'absolute_humidity': absolute_humidity}
        alerts.evaluate(device, values)
        mqtt_publisher.store(device, values)
        self.last_errors.pop(device['id'], None)
        if settings.get('debug_logging'):
            print(f"{datetime.now().strftime('%H:%M:%S')} - {device['name']}: {temperature:.1f}°C, {humidity:.1f}%")

    def report_error(self, device, error):
        devices.report_error(device['id'], error)
        message = str(error)
        if self.last_errors.get(device['id']) != message:  # zelfde fout niet elke seconde loggen
            print(f"✗ {self.bus['name']} / {device['name']}: {message}")
            self.last_errors[device['id']] = message


class Supervisor(threading.Thread):
    """Houdt per actieve bus een BusPoller in de lucht volgens de configuratie in Settings."""

    def __init__(self, measurements, instrument_factory=open_instrument):
        super().__init__(daemon=True, name='modbus-supervisor')
        self.measurements = measurements
        self.instrument_factory = instrument_factory
        self.pollers = {}   # bus_id -> (configuratie, BusPoller)

    def desired(self):
        buses, all_devices = devices.load_config()
        result = {}
        for bus in buses:
            bus_devices = [d for d in all_devices if d['bus_id'] == bus['id'] and d['enabled']]
            if bus['enabled'] and bus_devices:
                result[bus['id']] = (bus, bus_devices)
        return result

    def sync(self):
        wanted = self.desired()
        for bus_id, (config, poller) in list(self.pollers.items()):
            if wanted.get(bus_id) != config or not poller.is_alive():
                poller.stop()
                poller.join(timeout=config[0]['timeout'] * 2 * len(config[1]) + 2)
                del self.pollers[bus_id]
        for bus_id, config in wanted.items():
            if bus_id not in self.pollers:
                poller = BusPoller(config[0], config[1], self.measurements, self.instrument_factory)
                poller.start()
                self.pollers[bus_id] = (config, poller)

    def run(self):
        seen_version = None
        while True:
            try:
                dead = any(not poller.is_alive() for _, poller in self.pollers.values())
                if devices.version() != seen_version or dead:
                    seen_version = devices.version()
                    self.sync()
            except Exception as e:
                print(f"Modbus supervisor fout: {e}")
            time.sleep(SUPERVISOR_INTERVAL)


def start_modbus_thread():
    """Start de database schrijver en de Modbus supervisor (beide daemon threads)."""
    measurements = queue.Queue()
    Writer(measurements).start()
    supervisor = Supervisor(measurements)
    supervisor.start()
    print("✓ Modbus reader gestart (één thread per bus)")
    return supervisor
