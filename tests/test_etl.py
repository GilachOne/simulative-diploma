import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import validate, canonical, integer

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2023, 1, 1)
        self.row = dict(client_id=1, gender='F', purchase_datetime='2023-01-01',
            purchase_time_as_seconds_from_midnight=12, product_id=2, quantity=3,
            price_per_item=10, discount_per_item=2, total_price=24)

    def test_correct_amount(self):
        self.assertEqual(validate(self.row, self.day)[-1], Decimal('24'))

    def test_zero_quantity_quarantined(self):
        self.row.update(quantity=0, total_price=0)
        with self.assertRaises(ValueError): validate(self.row, self.day)

    def test_wrong_amount(self):
        self.row['total_price'] = 30
        with self.assertRaises(ValueError): validate(self.row, self.day)

    def test_wrong_day(self):
        self.row['purchase_datetime'] = '2023-01-02'
        with self.assertRaises(ValueError): validate(self.row, self.day)

    def test_missing_date_not_imputed(self):
        self.row['purchase_datetime'] = None
        with self.assertRaises(TypeError): validate(self.row, self.day)

    def test_invalid_discount(self):
        self.row.update(discount_per_item=11, total_price=0)
        with self.assertRaises(ValueError): validate(self.row, self.day)

    def test_nonfinite_money(self):
        self.row['price_per_item'] = float('nan')
        with self.assertRaises(ValueError): validate(self.row, self.day)

    def test_time_boundary(self):
        self.row['purchase_time_as_seconds_from_midnight'] = 86400
        with self.assertRaises(ValueError): validate(self.row, self.day)

    def test_boolean_is_not_integer(self):
        with self.assertRaises(ValueError): integer(True, 'quantity')

    def test_dictionary_order_does_not_change_hash_input(self):
        self.assertEqual(canonical(self.row), canonical(dict(reversed(list(self.row.items())))))

if __name__ == '__main__':
    unittest.main()
