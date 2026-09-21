"""API -> immutable daily snapshot -> validated PostgreSQL tables.

No order ID is supplied: rows are purchase lines, not orders.
Local private data and credentials are excluded from Git.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import execute_values, Json

ROOT = Path(__file__).resolve().parent
API = 'http://final-project.simulative.ru/data'
FIRST_DATE = date(2022, 1, 1)

def connect():
    # PostgreSQL can read PGPASSWORD or the user's pgpass file itself.
    return psycopg2.connect(host=os.getenv('PGHOST', '127.0.0.1'),
        port=os.getenv('PGPORT', '55440'), user=os.getenv('PGUSER', 'postgres'),
        dbname=os.getenv('PGDATABASE', 'marketplace_diploma'), connect_timeout=15,
        application_name='simulative_diploma_etl')

def canonical(row):
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def fetch_day(day):
    path = ROOT / 'data/raw' / (str(day) + '.json.gz')
    if path.exists():
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError('Cached response must be a list')
        return data
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(API + '?date=' + str(day),
                headers={'User-Agent': 'SimulativeDiploma/1.0'})
            with urllib.request.urlopen(req, timeout=90) as response:
                raw = response.read()
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError('API response must be a list')
            if any(not isinstance(row,dict) or row.get('purchase_datetime') != str(day) for row in data):
                raise ValueError('API mixed dates: retry complete daily response')
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            with gzip.open(temporary, 'wt', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            temporary.replace(path)
            return data
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            last = exc
            # Do not log URLs with credentials, raw responses or connection strings.
            logging.warning('fetch %s attempt %s failed (%s, status=%s)', day, attempt+1, type(exc).__name__, getattr(exc,'code','n/a'))
            if attempt == 4:
                break
            retry_after = exc.headers.get('Retry-After') if isinstance(exc, urllib.error.HTTPError) else None
            wait = min(120, int(retry_after)) if retry_after and retry_after.isdigit() else min(60,5*2**attempt) + random.random()
            time.sleep(wait)
    raise RuntimeError('API download failed for ' + str(day)) from last

def integer(value, field):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(field + ': expected integer')
    return value

def money(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(field + ': expected number')
    result = Decimal(str(value))
    if not result.is_finite() or result < 0 or result >= Decimal('10000000000000000'):
        raise ValueError(field + ': outside range')
    if result != result.quantize(Decimal('.01')):
        raise ValueError(field + ': sub-cent precision')
    return result

def validate(row, day):
    if not isinstance(row, dict):
        raise ValueError('row must be an object')
    actual_day = date.fromisoformat(row['purchase_datetime'])
    if actual_day != day:
        raise ValueError('date mismatch')
    client = integer(row['client_id'], 'client_id')
    product = integer(row['product_id'], 'product_id')
    qty = integer(row['quantity'], 'quantity')
    second = integer(row['purchase_time_as_seconds_from_midnight'], 'sale_second')
    if not 0 < client < 2**63 or not 0 < product < 2**63:
        raise ValueError('invalid identifier')
    if not 0 < qty < 2**31:
        raise ValueError('nonpositive or oversized quantity')
    if not 0 <= second < 86400:
        raise ValueError('invalid time')
    gender = row['gender']
    if not isinstance(gender, str) or gender not in ('M', 'F'):
        raise ValueError('unknown gender')
    price = money(row['price_per_item'], 'price')
    discount = money(row['discount_per_item'], 'discount')
    total = money(row['total_price'], 'total')
    if discount > price:
        raise ValueError('discount exceeds price')
    if abs(total - (price-discount)*qty) > Decimal('.01'):
        raise ValueError('total mismatch')
    return client, gender, second, product, qty, price, discount, total

def load_day(day):
    connection = connect()
    try:
        with connection:
            with connection.cursor() as cursor:
                # Date-scoped transaction lock also protects the local cached file.
                cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', (1263, day.toordinal()))
                # API shares mutable state across concurrent requests. Serialize ALL dates.
                cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', (1263, 0))
                cursor.execute('SELECT accepted_rows FROM etl_days WHERE sale_date=%s', (day,))
                if cursor.fetchone() is not None:
                    return str(day), 'already_loaded'
                rows = fetch_day(day)
                occurrences = Counter()
                valid, rejected = [], []
                canonical_rows = []
                for index, row in enumerate(rows):
                    serialized = canonical(row)
                    canonical_rows.append(serialized)
                    try:
                        values = validate(row, day)
                    except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
                        rejected.append((day, index, str(exc), Json(row)))
                        continue
                    key = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
                    occurrences[key] += 1
                    valid.append((day, key, occurrences[key], *values))
                # Keep multiplicity: identical source rows may be separate purchases.
                if valid:
                    execute_values(cursor, 'INSERT INTO sales VALUES %s', valid, page_size=1000)
                if rejected:
                    execute_values(cursor, 'INSERT INTO rejected_rows VALUES %s', rejected, page_size=1000)
                digest = hashlib.sha256('\n'.join(sorted(canonical_rows)).encode('utf-8')).hexdigest()
                cursor.execute('INSERT INTO etl_days (sale_date,source_rows,accepted_rows,rejected_rows,snapshot_sha256) VALUES (%s,%s,%s,%s,%s)',
                    (day, len(rows), len(valid), len(rejected), digest))
                return str(day), f'loaded={len(valid)} rejected={len(rejected)}'
    finally:
        connection.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=date.fromisoformat)
    parser.add_argument('--end', type=date.fromisoformat, help='inclusive')
    parser.add_argument('--daily', action='store_true')
    parser.add_argument('--workers', type=int, default=1, choices=[1], help='API requires sequential requests')
    args = parser.parse_args()
    (ROOT / 'logs').mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.StreamHandler(), logging.FileHandler(ROOT/'logs/etl.log', encoding='utf-8')])
    yesterday = datetime.now(ZoneInfo(os.getenv('BUSINESS_TIMEZONE', 'Europe/Moscow'))).date()-timedelta(days=1)
    if args.daily:
        if args.start or args.end:
            parser.error('--daily cannot be combined with a range')
        start = end = yesterday
    else:
        start, end = args.start, args.end or yesterday
        if start is None:
            parser.error('Specify --start or --daily')
    if start < FIRST_DATE or end < start or end > yesterday:
        parser.error('Range must be between 2022-01-01 and yesterday')
    conn = connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute((ROOT/'sql/schema.sql').read_text('utf-8'))
    finally:
        conn.close()
    days = [start+timedelta(days=i) for i in range((end-start).days+1)]
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(load_day, day): day for day in days}
        for future in as_completed(futures):
            day = futures[future]
            try:
                loaded_day, status = future.result()
                logging.info('%s %s', loaded_day, status)
            except Exception as exc:
                logging.error('%s failed (%s)', day, type(exc).__name__)
                failures.append(str(day))
    logging.info('Completed: requested=%s failed=%s', len(days), len(failures))
    return int(bool(failures))

if __name__ == '__main__':
    raise SystemExit(main())
