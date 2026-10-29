"""Run with:  python -m unittest -v"""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import config
from allocator import allocate
from db import Database

TODAY = date(2026, 10, 29)


class AllocatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")
        self.db.init_schema()
        c = self.db.conn
        c.execute("INSERT INTO products VALUES ('SKU1', 'Widget', 'HVAC', '')")
        c.executemany("INSERT INTO technicians (name, email, max_calls_per_run) VALUES (?, ?, ?)",
                      [("A", "a@example.com", 2), ("B", "b@example.com", 2)])
        for i in range(1, 11):
            c.execute("INSERT INTO customers (first_name, last_name) VALUES (?, ?)", (f"C{i}", "X"))
        c.commit()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def buy(self, customer_id, days_ago):
        self.db.conn.execute(
            "INSERT INTO purchases (customer_id, sku, unit_price, purchase_date) VALUES (?, 'SKU1', 100, ?)",
            (customer_id, (TODAY - timedelta(days=days_ago)).isoformat()))
        self.db.conn.commit()

    def test_90_day_boundary(self):
        self.buy(1, config.ELIGIBILITY_DAYS - 1)   # 89 days: not yet
        self.buy(2, config.ELIGIBILITY_DAYS)       # 90 days: cleared
        r = allocate(self.db, TODAY)
        self.assertEqual(r.total_calls, 1)
        call = self.db.get_calls(sum(r.calls_by_tech.values(), []))[0]
        self.assertEqual(call.customer.customer_id, 2)

    def test_deadline(self):
        self.buy(1, 100)
        r = allocate(self.db, TODAY)
        self.assertEqual(r.due_date, TODAY + timedelta(days=config.CALL_DEADLINE_DAYS))

    def test_never_allocated_twice(self):
        self.buy(1, 100)
        self.assertEqual(allocate(self.db, TODAY).total_calls, 1)
        self.assertEqual(allocate(self.db, TODAY).total_calls, 0)

    def test_same_customer_grouped_into_one_call(self):
        self.buy(1, 120)
        self.buy(1, 95)
        r = allocate(self.db, TODAY)
        self.assertEqual(r.total_calls, 1)
        self.assertEqual(r.purchases_allocated, 2)

    def test_allotment_cap_and_carryover(self):
        for cid in range(1, 7):                    # 6 customers, capacity 2 + 2
            self.buy(cid, 100 + cid)
        r = allocate(self.db, TODAY)
        self.assertEqual(r.total_calls, 4)
        self.assertEqual(sorted(len(v) for v in r.calls_by_tech.values()), [2, 2])
        self.assertEqual(r.customers_left_in_queue, 2)
        self.assertEqual(allocate(self.db, TODAY + timedelta(days=1)).total_calls, 2)

    def test_oldest_first(self):
        self.buy(1, 95)
        self.buy(2, 160)
        r = allocate(self.db, TODAY)
        first_tech_calls = self.db.get_calls(r.calls_by_tech[1])
        self.assertEqual(first_tech_calls[0].customer.customer_id, 2)

    def test_dry_run_writes_nothing(self):
        self.buy(1, 100)
        self.assertEqual(allocate(self.db, TODAY, dry_run=True).total_calls, 1)
        self.assertEqual(allocate(self.db, TODAY).total_calls, 1)


if __name__ == "__main__":
    unittest.main()
