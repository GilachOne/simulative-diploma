"""Opt-in integration checks in a temporary schema of the configured database.

Run with DIPLOMA_DB_TESTS=1 and the normal PostgreSQL environment variables.
"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from datetime import date
import uuid
import psycopg2
from psycopg2 import sql

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import etl

@unittest.skipUnless(os.getenv('DIPLOMA_DB_TESTS')=='1','requires a test database connection')
class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.schema='test_diploma_'+uuid.uuid4().hex
        self.base_connect=etl.connect
        with self.base_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
                cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
                cur.execute((etl.ROOT/'sql/schema.sql').read_text('utf-8'))
        conn.close()
        self.day=date(2023,1,1)
        self.row=dict(client_id=1,gender='F',purchase_datetime=str(self.day),
            purchase_time_as_seconds_from_midnight=12,product_id=2,quantity=3,
            price_per_item=10,discount_per_item=2,total_price=24)

    def connect(self):
        conn=self.base_connect()
        with conn.cursor() as cur:
            cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
        conn.commit()
        return conn

    def counts(self):
        conn=self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT (SELECT count(*) FROM sales),(SELECT count(*) FROM rejected_rows),(SELECT count(*) FROM etl_days)')
                return cur.fetchone()
        finally:conn.close()

    def tearDown(self):
        conn=self.base_connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        finally:conn.close()

    def test_replay_preserves_multiplicity_and_quarantine(self):
        bad={**self.row,'quantity':0,'total_price':0}
        with patch.object(etl,'connect',self.connect),patch.object(etl,'fetch_day',return_value=[self.row,self.row,bad]) as fetch:
            etl.load_day(self.day)
            self.assertEqual(etl.load_day(self.day)[1],'already_loaded')
            fetch.assert_called_once()
        self.assertEqual(self.counts(),(2,1,1))

    def test_ledger_failure_rolls_back_sales(self):
        conn=self.connect()
        with conn:
            with conn.cursor() as cur:
                cur.execute('ALTER TABLE etl_days ADD CONSTRAINT force_failure CHECK (source_rows < 2)')
        conn.close()
        with patch.object(etl,'connect',self.connect),patch.object(etl,'fetch_day',return_value=[self.row,self.row]):
            with self.assertRaises(psycopg2.IntegrityError):etl.load_day(self.day)
        self.assertEqual(self.counts(),(0,0,0))
