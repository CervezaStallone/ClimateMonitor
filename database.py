import sqlite3
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Laad environment variabelen
load_dotenv()

# Database configuratie
DB_FILE = os.getenv('DATABASE_FILE', 'src/modbus_sensor_data.db')
DATA_RETENTION_DAYS = int(os.getenv('DATA_RETENTION_DAYS', '0'))  # 0 = oneindig, anders aantal dagen
DEBUG_LOGGING = os.getenv('DEBUG_LOGGING', 'False').lower() == 'true'

if DATA_RETENTION_DAYS < 0:
    print(f"Waarschuwing: DATA_RETENTION_DAYS kan niet negatief zijn ({DATA_RETENTION_DAYS}), gebruik 0 voor oneindig")
    DATA_RETENTION_DAYS = 0


def get_table_name(date=None):
    """Genereer tabel naam voor specifieke datum (table-per-day partitioning)"""
    if date is None:
        date = datetime.now()
    return f"measurements_{date.strftime('%Y%m%d')}"


def ensure_table_exists(cursor, table_name):
    """Maak tabel aan als deze nog niet bestaat"""
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            temperature REAL NOT NULL,
            humidity REAL NOT NULL,
            dewpoint REAL,
            absolute_humidity REAL
        )
    ''')
    cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_timestamp ON {table_name}(timestamp)')


def get_all_measurement_tables(cursor):
    """Haal alle measurements tabellen op (gesorteerd op datum)"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'measurements_%' ORDER BY name")
    return [row[0] for row in cursor.fetchall()]


def get_tables_for_timerange(cursor, start_timestamp=None, end_timestamp=None):
    """Bepaal welke tabellen relevant zijn voor een tijdsbereik"""
    all_tables = get_all_measurement_tables(cursor)
    
    if start_timestamp is None and end_timestamp is None:
        return all_tables
    
    relevant_tables = []
    for table_name in all_tables:
        try:
            date_str = table_name.replace('measurements_', '')
            table_date = datetime.strptime(date_str, '%Y%m%d')
            table_start = int(table_date.timestamp())
            table_end = int((table_date + timedelta(days=1)).timestamp())
            
            # Check of tabel overlapt met gevraagde tijdsbereik
            if start_timestamp and table_end < start_timestamp:
                continue
            if end_timestamp and table_start > end_timestamp:
                continue
            
            relevant_tables.append(table_name)
        except ValueError:
            continue
    
    return relevant_tables if relevant_tables else all_tables


def build_union_query(cursor, columns, start_timestamp=None, end_timestamp=None, order_by='timestamp'):
    """Bouw UNION ALL query over relevante tabellen"""
    tables = get_tables_for_timerange(cursor, start_timestamp, end_timestamp)
    
    if not tables:
        if DEBUG_LOGGING:
            print("⚠️ build_union_query: Geen tabellen gevonden voor tijdsbereik")
        return None, None
    
    if DEBUG_LOGGING:
        print(f"🔍 build_union_query: Relevante tabellen: {tables}")
        if start_timestamp:
            print(f"   → Start timestamp: {start_timestamp} ({datetime.fromtimestamp(start_timestamp)})")
        if end_timestamp:
            print(f"   → End timestamp: {end_timestamp} ({datetime.fromtimestamp(end_timestamp)})")
    
    # Bouw SELECT queries voor elke tabel
    column_list = ', '.join(columns)
    queries = []
    
    for table in tables:
        if start_timestamp or end_timestamp:
            where_clauses = []
            if start_timestamp:
                where_clauses.append(f'timestamp >= {start_timestamp}')
            if end_timestamp:
                where_clauses.append(f'timestamp <= {end_timestamp}')
            where_clause = ' AND '.join(where_clauses)
            queries.append(f'SELECT {column_list} FROM {table} WHERE {where_clause}')
        else:
            queries.append(f'SELECT {column_list} FROM {table}')
    
    # Combineer met UNION ALL en sorteer
    full_query = ' UNION ALL '.join(queries)
    if order_by:
        full_query = f'SELECT * FROM ({full_query}) ORDER BY {order_by}'
    
    return full_query, len(tables)


def init_database():
    """Initialiseer database met partitioned table systeem"""
    try:
        # Zorg dat de src directory bestaat
        db_dir = os.path.dirname(DB_FILE)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        conn = sqlite3.connect(DB_FILE, timeout=30)
        cursor = conn.cursor()
        
        # Optimalisatie: WAL mode voor betere concurrent read/write performance
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.execute('PRAGMA temp_store=MEMORY')
        cursor.execute('PRAGMA wal_autocheckpoint=1000')
        
        # Maak tabel voor vandaag aan
        today_table = get_table_name()
        ensure_table_exists(cursor, today_table)
        
        conn.commit()
        conn.close()
        print(f"Database geïnitialiseerd: {DB_FILE} (WAL mode, partitioned)")
        print(f"Actieve tabel: {today_table}")
        if DATA_RETENTION_DAYS > 0:
            print(f"Data retentie actief: {DATA_RETENTION_DAYS} dagen")
        else:
            print("Data retentie: oneindig (alle data wordt bewaard)")
    except Exception as e:
        print(f"FOUT: Kan database niet initialiseren: {e}")
        print("Controleer schrijfrechten en of het bestand niet corrupt is.")
        raise


def cleanup_old_data():
    """Verwijder oude data op basis van retention policy (DROP oude tabellen)"""
    if DATA_RETENTION_DAYS == 0:
        return  # Geen cleanup als retentie oneindig is
    
    try:
        cutoff_date = datetime.now() - timedelta(days=DATA_RETENTION_DAYS)
        conn = sqlite3.connect(DB_FILE, timeout=30)
        cursor = conn.cursor()
        
        # Haal alle measurement tabellen op
        all_tables = get_all_measurement_tables(cursor)
        dropped_count = 0
        
        for table_name in all_tables:
            # Parse datum uit tabel naam (measurements_YYYYMMDD)
            try:
                date_str = table_name.replace('measurements_', '')
                table_date = datetime.strptime(date_str, '%Y%m%d')
                
                # Drop tabel als ouder dan retention period
                if table_date < cutoff_date:
                    cursor.execute(f'DROP TABLE IF EXISTS {table_name}')
                    dropped_count += 1
                    print(f"✓ Tabel {table_name} verwijderd (ouder dan {DATA_RETENTION_DAYS} dagen)")
            except ValueError:
                # Ongeldige tabel naam, skip
                continue
        
        if dropped_count > 0:
            conn.commit()
            # VACUUM om ruimte vrij te geven
            cursor.execute('VACUUM')
            print(f"Data cleanup voltooid: {dropped_count} tabel(len) verwijderd")
        
        conn.close()
    except Exception as e:
        print(f"Waarschuwing: Data cleanup gefaald: {e}")
