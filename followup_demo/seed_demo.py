"""
Builds a fresh demo database with fictional customers, purchases, and techs.

All names are invented and every email address uses example.com, so nothing
here can reach a real person even if SMTP mode is switched on by mistake.
"""
import random
from datetime import date, timedelta
from pathlib import Path

from catalog import PERFORMANCE_MARKERS, PRODUCTS
from db import Database

FIRST = ["Maya", "Jordan", "Priya", "Marcus", "Elena", "Tyrone", "Hannah", "Diego",
         "Grace", "Omar", "Leah", "Carter", "Nina", "Andre", "Sofia", "Wesley",
         "Imani", "Lucas", "Rachel", "Darnell", "Chloe", "Victor", "Aisha", "Ben"]
LAST = ["Holloway", "Brennan", "Okafor", "Lindqvist", "Ramirez", "Castellano",
        "Whitaker", "Nguyen", "Pemberton", "Abernathy", "Delgado", "Fairbanks",
        "Kowalski", "Sutherland", "Mbeki", "Thornton", "Yamada", "Rourke"]
CITIES = [("Raleigh", "NC"), ("Durham", "NC"), ("Cary", "NC"), ("Wake Forest", "NC"),
          ("Apex", "NC"), ("Chapel Hill", "NC"), ("Garner", "NC"), ("Holly Springs", "NC")]

TECHS = [
    ("Sam Patel", "sam.patel@example.com", 6),
    ("Renee Calloway", "renee.calloway@example.com", 6),
    ("Luis Ortega", "luis.ortega@example.com", 5),
    ("Kim Asante", "kim.asante@example.com", 5),
]


def build_demo_db(path: Path, today: date, n_customers: int = 32,
                  n_purchases: int = 64, seed: int = 7) -> None:
    """Create (or overwrite) the demo database relative to `today`."""
    rng = random.Random(seed)
    path = Path(path)
    if path.exists():
        path.unlink()

    db = Database(path)
    db.init_schema()
    conn = db.conn

    conn.executemany(
        "INSERT INTO products (sku, name, category, description) VALUES (?, ?, ?, ?)",
        [(sku, name, cat, desc) for sku, name, cat, _price, desc in PRODUCTS])

    conn.executemany(
        "INSERT INTO performance_markers (category, marker, sort_order) VALUES (?, ?, ?)",
        [(cat, m, i) for cat, markers in PERFORMANCE_MARKERS.items()
         for i, m in enumerate(markers)])

    conn.executemany(
        "INSERT INTO technicians (name, email, max_calls_per_run) VALUES (?, ?, ?)",
        TECHS)

    used = set()
    customers = []
    while len(customers) < n_customers:
        first, last = rng.choice(FIRST), rng.choice(LAST)
        if (first, last) in used:
            continue
        used.add((first, last))
        city, state = rng.choice(CITIES)
        email = f"{first}.{last}@example.com".lower()
        phone = f"(919) 555-01{rng.randint(0, 99):02d}"  # 555-01xx is reserved for fiction
        customers.append((first, last, email, phone, city, state))
    conn.executemany(
        "INSERT INTO customers (first_name, last_name, email, phone, city, state) "
        "VALUES (?, ?, ?, ?, ?, ?)", customers)

    purchases = []
    for _ in range(n_purchases):
        customer_id = rng.randint(1, n_customers)
        sku, _name, _cat, base_price, _desc = rng.choice(PRODUCTS)
        price = round(base_price * rng.uniform(0.92, 1.10), 2)
        days_ago = rng.randint(1, 170)
        purchases.append((customer_id, sku, 1, price,
                          (today - timedelta(days=days_ago)).isoformat()))
    # Make sure the demo shows the 90-day boundary clearly:
    # one purchase exactly 90 days old (eligible today) and one at 89 (not yet).
    purchases.append((1, "SH-TSTAT-WIFI", 1, 319.99, (today - timedelta(days=90)).isoformat()))
    purchases.append((2, "WT-RO-5", 1, 649.00, (today - timedelta(days=89)).isoformat()))

    conn.executemany(
        "INSERT INTO purchases (customer_id, sku, quantity, unit_price, purchase_date) "
        "VALUES (?, ?, ?, ?, ?)", purchases)
    conn.commit()
    db.close()
