"""Periodiek rapport (PDF): houtvocht per sensor per dag en een tabel met min/max per sensor."""
import io
import math
import sqlite3
import textwrap
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
from matplotlib.figure import Figure   # zonder pyplot: geen GUI backend, veilig in threads

import alerts
import devices
import settings
import wood
from database import build_union_query
from translations import TRANSLATIONS

# Kleurgrenzen houtvocht (%): boven de grens krijgt de waarde deze kleur
LEVELS = ((20, 'red'), (18, 'orange'), (16, 'yellow'))
COLORS = {'normal': ('#1a7f37', '#dcf5e3'), 'yellow': ('#a87800', '#fff3c4'),   # (tekst, achtergrond)
          'orange': ('#c2410c', '#ffe1cc'), 'red': ('#c62828', '#fbd5d5')}
MUTED = '#6b6b6b'
RETRY_SECONDS = 3600   # na een mislukte verzending
_next_try = 0


def level(value):
    """'normal' tot en met 16 %, daarboven geel, oranje (> 18 %) en rood (> 20 %)."""
    return next((name for limit, name in LEVELS if value > limit), 'normal')


def period(kind, now, current=False):
    """(begin, einde) van de vorige volledige week (maandag-maandag) of maand in de tijdzone van now;
    current=True: de lopende week of maand tot nu."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == 'week':
        end = midnight - timedelta(days=midnight.weekday())
        return (end, now) if current else (end - timedelta(days=7), end)
    end = midnight.replace(day=1)
    return (end, now) if current else ((end - timedelta(days=1)).replace(day=1), end)


def _query(sql, columns, start_ts, end_ts):
    """sql met {q} = alle metingen van start_ts tot (niet tot en met) end_ts over de dagtabellen."""
    conn = sqlite3.connect(settings.DB_FILE, timeout=30)
    try:
        query, _ = build_union_query(conn.cursor(), columns, start_timestamp=start_ts, end_timestamp=end_ts - 1,
                                     order_by=None)
        return conn.execute(sql.format(q=query)).fetchall() if query else []
    finally:
        conn.close()


def _wood(hourly, hours):
    """[(uur, temp, rv)] -> [(uur, houtvocht)], vertraagd met de reactietijd zoals de alarmen (wood.update)."""
    series, smooth, last = [], None, None
    for hour, temp, hum in hourly:
        live = float(wood.value(temp, hum))
        if smooth is None or not hours:
            smooth = live
        else:
            smooth += (live - smooth) * (1 - math.exp(-(hour - last) / hours))
        series.append((hour, smooth))
        last = hour
    return series


def collect(start, end):
    """Per sensor met metingen in [start, end): naam, min/max van temperatuur, RV en houtvocht, en het
    houtvocht per dag [(datum, gemiddelde)]. Houtvocht uit uurgemiddelden; de reactietijd vóór start telt mee."""
    start_ts, end_ts = int(start.timestamp()), int(end.timestamp())
    columns = ['device_id', 'timestamp', 'temperature', 'humidity']
    rows = {r[0]: r[1:] for r in _query(
        'SELECT device_id, MIN(temperature), MAX(temperature), MIN(humidity), MAX(humidity) FROM ({q}) GROUP BY device_id',
        columns, start_ts, end_ts)}
    hours = settings.get('wood_response_hours')
    hourly = {}
    for device_id, hour, temp, hum in _query(
            'SELECT device_id, timestamp / 3600 AS h, AVG(temperature), AVG(humidity) FROM ({q}) '
            'GROUP BY device_id, h ORDER BY h', columns, start_ts - hours * 3600, end_ts):
        hourly.setdefault(device_id, []).append((hour, temp, hum))
    result = []
    for d in devices.list_devices():
        if d['id'] not in rows:
            continue
        values = [(h, v) for h, v in _wood(hourly[d['id']], hours) if h * 3600 >= start_ts]
        days = {}
        for hour, value in values:
            days.setdefault(datetime.fromtimestamp(hour * 3600, start.tzinfo).date(), []).append(value)
        temp_min, temp_max, hum_min, hum_max = rows[d['id']]
        result.append({'name': d['name'], 'temp_min': temp_min, 'temp_max': temp_max, 'hum_min': hum_min,
                       'hum_max': hum_max, 'wood_min': min(v for _, v in values), 'wood_max': max(v for _, v in values),
                       'days': [(day, sum(v) / len(v)) for day, v in sorted(days.items())]})
    return result


def _dates(start, end):
    """Begin- en einddatum voor de tekst (end is exclusief)."""
    return start.strftime('%d-%m-%Y'), (end - timedelta(seconds=1)).strftime('%d-%m-%Y')


def build_pdf(start, end, lang):
    """A4 PDF: titel, uitleg, houtvocht per sensor per dag, tabel met min/max en de kleurgrenzen."""
    from callbacks import SERIES   # hier pas: callbacks laadt settings_ui, dat dit module laadt
    t = TRANSLATIONS[lang]
    sensors = collect(start, end)
    fig = Figure(figsize=(8.27, 11.69))   # A4
    fig.text(0.5, 0.95, t['report_title'], ha='center', fontsize=18)
    fig.text(0.5, 0.925, t['report_period'].format(start=_dates(start, end)[0], end=_dates(start, end)[1]),
             ha='center', fontsize=10, color=MUTED)
    fig.text(0.1, 0.9, textwrap.fill(t['report_intro'], 92), va='top', fontsize=10)

    ax = fig.add_axes((0.1, 0.6, 0.85, 0.22))
    palette = SERIES['light']
    for i, sensor in enumerate(sensors):
        days, values = zip(*sensor['days'])
        ax.plot(days, values, marker='o', markersize=3, linewidth=1.5, label=sensor['name'],
                color=palette[i % len(palette)])
    for limit, name in LEVELS:
        ax.axhline(limit, color=COLORS[name][0], linewidth=0.8, linestyle='--', alpha=0.6)
    ax.set_title(t['report_chart'], fontsize=9, loc='left', color=MUTED)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    if sensors:
        first, last = min(s['days'][0][0] for s in sensors), max(s['days'][-1][0] for s in sensors)
        ax.set_xlim(first - timedelta(hours=12), last + timedelta(hours=12))
    ax.tick_params(labelsize=7)
    ax.grid(axis='y', color='#e5e5e5')
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    if sensors:
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.12), ncol=min(len(sensors), 6), fontsize=8, frameon=False)
    else:
        ax.text(0.5, 0.5, t['report_no_data'], ha='center', transform=ax.transAxes)

    fig.text(0.1, 0.5, t['report_table'], fontsize=11)
    columns = ['sensor', 'temp_min', 'temp_max', 'hum_min', 'hum_max', 'wood_min', 'wood_max']
    if sensors:
        height = min(0.035 * (len(sensors) + 1), 0.3)
        tax = fig.add_axes((0.1, 0.48 - height, 0.85, height))
        tax.axis('off')
        cells = [[s['name']] + [f"{s[c]:.1f}" for c in columns[1:]] for s in sensors]
        table = tax.table(cellText=cells, colLabels=[t[f'report_col_{c}'] for c in columns], loc='upper center',
                          cellLoc='right', colLoc='right', bbox=(0, 0, 1, 1),
                          colWidths=[0.16, 0.115, 0.115, 0.115, 0.115, 0.19, 0.19])
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        for (row, col), cell in table.get_celld().items():
            cell.set_edgecolor('#e5e5e5')
            cell.visible_edges = 'B'
            if row == 0:
                cell.get_text().set_fontweight('bold')
                cell.set_fontsize(7)
            elif columns[col] in ('wood_min', 'wood_max') and level(sensors[row - 1][columns[col]]) != 'normal':
                cell.get_text().set_color(COLORS[level(sensors[row - 1][columns[col]])][0])
                cell.get_text().set_fontweight('bold')
            if col == 0:
                cell.get_text().set_horizontalalignment('left')
        bottom = 0.48 - height
    else:
        bottom = 0.48

    fig.text(0.1, bottom - 0.04, t['report_levels'], fontsize=10, fontweight='bold')
    bounds = [None, *[limit for limit, _ in reversed(LEVELS)]]   # None, 16, 18, 20
    for i, name in enumerate(('normal', 'yellow', 'orange', 'red')):
        low, high = bounds[i], bounds[i + 1] if i + 1 < len(bounds) else None
        rule = f'≤ {high} %' if low is None else f'> {low} %' if high is None else \
            f"> {low} % {t['report_and']} ≤ {high} %"
        y = bottom - 0.07 - i * 0.022
        fig.text(0.1, y, f" {t[f'report_level_{name}']} ", fontsize=8, color=COLORS[name][0],
                 bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS[name][1], edgecolor='none'))
        fig.text(0.22, y, rule, fontsize=9)
    fig.text(0.1, 0.03, t['report_generated'].format(time=datetime.now(start.tzinfo).strftime('%d-%m-%Y %H:%M')),
             fontsize=7, color=MUTED)

    buffer = io.BytesIO()
    fig.savefig(buffer, format='pdf', metadata={'Title': t['report_title'], 'Creator': 'Climate Monitor'})
    return buffer.getvalue()


def filename(start, lang):
    return f"{TRANSLATIONS[lang]['report_filename']}-{start:%Y-%m-%d}.pdf"


def check(now=None):
    """Verstuur het rapport over de vorige week/maand zodra die om 07:00 voorbij is (ook later, na
    uitval), één keer per periode; na een fout opnieuw na RETRY_SECONDS. Geeft True als verstuurd."""
    global _next_try
    kind = settings.get('report_period')
    if kind == 'off' or not settings.get('smtp_enabled'):
        return False
    now = now or datetime.now(ZoneInfo(settings.get('timezone')))
    start, end = period(kind, now)
    key = f'{kind}:{start:%Y-%m-%d}'
    if now < end + timedelta(hours=7) or settings.get('report_last_sent') == key or now.timestamp() < _next_try:
        return False
    lang = settings.get('report_language')
    t = TRANSLATIONS[lang]
    first, last = _dates(start, end)
    text = t['report_email_subject'].format(start=first, end=last) + '\n\n' + \
        t['report_email_body'].format(start=first, end=last)
    config = {k: settings.get(k) for k in settings.SCHEMA}
    try:
        alerts.send_email(text, config, (filename(start, lang), build_pdf(start, end, lang)))
        error = None
    except Exception as e:
        error = alerts._hide_secrets(str(e) or type(e).__name__, config)
    alerts.log.appendleft({'time': time.time(), 'channel': 'email', 'text': text.splitlines()[0], 'ok': error is None,
                           'error': error, 'attempt': 1})   # zichtbaar in Settings → Meldingen
    if error:
        _next_try = now.timestamp() + RETRY_SECONDS
        return False
    settings.set_internal('report_last_sent', key)
    return True


def _loop():
    while True:
        try:
            check()
        except Exception as e:   # bv. database bezet: volgende minuut opnieuw
            print(f"Rapport fout: {e}")
        time.sleep(60)


def start():
    thread = threading.Thread(target=_loop, daemon=True, name='report')
    thread.start()
    return thread
