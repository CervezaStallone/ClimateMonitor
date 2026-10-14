"""Meetwaarden per sensor doorgeven aan een MQTT broker.

Topics (prefix instelbaar, standaard 'xy-md02'):
  <prefix>/status                 online / offline (retained, offline via last will)
  <prefix>/<sensor>/state         JSON met alle waarden
  <prefix>/<sensor>/<grootheid>   losse waarde (temperature, humidity, dewpoint, absolute_humidity)

De poller schrijft alleen de laatste waarden in het geheugen; een eigen thread verbindt, verbindt
opnieuw na wijzigingen in Settings of uitval, en publiceert elk interval.
"""
import json
import re
import secrets
import threading
import time
import unicodedata
from datetime import datetime

import paho.mqtt.client as mqtt

import devices
import settings

METRICS = ('temperature', 'humidity', 'dewpoint', 'absolute_humidity')
CONFIG_KEYS = ('mqtt_enabled', 'mqtt_host', 'mqtt_port', 'mqtt_tls', 'mqtt_username', 'mqtt_password',
               'mqtt_client_id', 'mqtt_topic_prefix', 'mqtt_qos', 'mqtt_retain')
CONNECT_TIMEOUT = 10

_lock = threading.Lock()
_latest = {}        # device_id -> {'name', 'values', 'ts', 'published': bool}
status = {'connected': False, 'error': None, 'last_publish': None}


def store(device, values, ts=None):
    """Laatste meting van een sensor bewaren (aangeroepen door de poller, blokkeert nooit)."""
    with _lock:
        _latest[device['id']] = {'name': device['name'], 'values': dict(values), 'ts': ts or time.time(),
                                 'published': False}


def slug(name):
    """'Kas noord' -> 'kas-noord' (veilig als MQTT topic niveau)."""
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-') or 'sensor'


def topic_names(entries):
    """{device_id: topic niveau}; dubbele slugs krijgen het id erachter."""
    names, used = {}, set()
    for device_id in sorted(entries):
        name = slug(entries[device_id]['name'])
        if name in used:
            name = f'{name}-{device_id}'
        used.add(name)
        names[device_id] = name
    return names


def make_client(config):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=config['mqtt_client_id'] or f'xy-md02-{secrets.token_hex(4)}')
    if config['mqtt_username']:
        client.username_pw_set(config['mqtt_username'], config['mqtt_password'] or None)
    if config['mqtt_tls']:
        client.tls_set()   # systeem CA's
    client.will_set(f"{config['mqtt_topic_prefix']}/status", 'offline', qos=1, retain=True)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    return client


def test_connection(config):
    """Probeer te verbinden met de formulierwaarden. Geeft None of een foutmelding."""
    result = {}
    done = threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties):
        result['rc'] = reason_code
        done.set()

    client = make_client(config)
    client.on_connect = on_connect
    try:
        client.connect(config['mqtt_host'], config['mqtt_port'], keepalive=CONNECT_TIMEOUT)
        client.loop_start()
        if not done.wait(CONNECT_TIMEOUT):
            return 'timeout'
        if result['rc'].is_failure:
            return str(result['rc'])
        client.publish(f"{config['mqtt_topic_prefix']}/status", 'online', qos=1, retain=True).wait_for_publish(5)
        return None
    except Exception as e:
        return str(e) or type(e).__name__
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass


class Publisher(threading.Thread):
    """Houdt de verbinding volgens Settings in stand en publiceert de laatste waarden per interval."""

    def __init__(self):
        super().__init__(daemon=True, name='mqtt-publisher')
        self.client = None
        self.active = None
        self.last_publish = 0

    def run(self):
        while True:
            try:
                config = {k: settings.get(k) for k in CONFIG_KEYS}
                if config != self.active:
                    self.reconnect(config)
                if self.client and status['connected'] and \
                        time.time() - self.last_publish >= settings.get('mqtt_publish_interval_seconds'):
                    self.publish(config)
            except Exception as e:
                status['error'] = str(e)
                print(f"MQTT fout: {e}")
            time.sleep(1)

    def reconnect(self, config):
        self.stop_client()
        self.active = config
        if not config['mqtt_enabled'] or not config['mqtt_host']:
            status.update(connected=False, error=None)
            return
        client = make_client(config)
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_connect_fail = self.on_connect_fail
        client.connect_async(config['mqtt_host'], config['mqtt_port'], keepalive=60)
        client.loop_start()   # paho verbindt opnieuw met back-off bij uitval
        self.client = client
        print(f"→ MQTT verbinden met {config['mqtt_host']}:{config['mqtt_port']}")

    def stop_client(self):
        if self.client:
            try:
                self.client.publish(f"{self.active['mqtt_topic_prefix']}/status", 'offline', qos=1, retain=True)
                self.client.disconnect()
            except Exception:
                pass
            self.client.loop_stop()
            self.client = None
        status['connected'] = False

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            status.update(connected=False, error=str(reason_code))
            return
        status.update(connected=True, error=None)
        client.publish(f"{self.active['mqtt_topic_prefix']}/status", 'online', qos=1, retain=True)
        print("✓ MQTT verbonden")

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        status['connected'] = False
        if reason_code.is_failure:
            status['error'] = str(reason_code)

    def on_connect_fail(self, client, userdata):
        status.update(connected=False, error='connection failed')

    def publish(self, config):
        """Publiceer alleen sensoren met een nieuwe meting sinds de vorige keer."""
        prefix, qos, retain = config['mqtt_topic_prefix'], config['mqtt_qos'], config['mqtt_retain']
        current = {d['id'] for d in devices.list_devices(enabled_only=True)}
        with _lock:
            for device_id in set(_latest) - current:   # verwijderde/uitgeschakelde sensoren: topic vrijgeven
                del _latest[device_id]
            entries = {k: dict(v) for k, v in _latest.items()}
            for entry in _latest.values():
                entry['published'] = True
        for device_id, level in topic_names(entries).items():
            entry = entries[device_id]
            if entry['published']:
                continue
            values = {m: round(entry['values'][m], 2) for m in METRICS if m in entry['values']}
            payload = {'device_id': device_id, 'name': entry['name'], **values,
                       'timestamp': datetime.fromtimestamp(entry['ts']).astimezone().isoformat(timespec='seconds')}
            self.client.publish(f'{prefix}/{level}/state', json.dumps(payload), qos=qos, retain=retain)
            for metric, value in values.items():
                self.client.publish(f'{prefix}/{level}/{metric}', str(value), qos=qos, retain=retain)
        self.last_publish = time.time()
        status['last_publish'] = self.last_publish


def start():
    publisher = Publisher()
    publisher.start()
    return publisher
