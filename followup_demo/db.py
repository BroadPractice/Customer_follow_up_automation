"""
Data layer.

All SQL lives in this file. For the demo it talks to SQLite; when the client's
real database is connected, swap the connection in `Database.__init__` (and any
dialect-specific SQL below) and the allocator/emailer keep working unchanged.
"""
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id   INTEGER PRIMARY KEY,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    email         TEXT,
    phone         TEXT,
    city          TEXT,
    state         TEXT
);

CREATE TABLE IF NOT EXISTS products (
    sku           TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    description   TEXT
);

CREATE TABLE IF NOT EXISTS performance_markers (
    marker_id     INTEGER PRIMARY KEY,
    category      TEXT NOT NULL,
    marker        TEXT NOT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0
);

-- What they bought, how much it was, and when they bought it.
CREATE TABLE IF NOT EXISTS purchases (
    purchase_id   INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    sku           TEXT    NOT NULL REFERENCES products(sku),
    quantity      INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price    REAL    NOT NULL CHECK (unit_price >= 0),
    purchase_date TEXT    NOT NULL          -- ISO date, YYYY-MM-DD
);
CREATE INDEX IF NOT EXISTS ix_purchases_date ON purchases(purchase_date);

CREATE TABLE IF NOT EXISTS technicians (
    tech_id            INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    email              TEXT NOT NULL UNIQUE,
    active             INTEGER NOT NULL DEFAULT 1,
    max_calls_per_run  INTEGER NOT NULL DEFAULT 6
);

-- One call per customer per allocation; a call can cover several purchases.
CREATE TABLE IF NOT EXISTS follow_up_calls (
    call_id            INTEGER PRIMARY KEY,
    customer_id        INTEGER NOT NULL REFERENCES customers(customer_id),
    tech_id            INTEGER NOT NULL REFERENCES technicians(tech_id),
    assigned_date      TEXT NOT NULL,
    due_date           TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'assigned'
                       CHECK (status IN ('assigned', 'completed', 'unreachable')),
    satisfaction_score INTEGER CHECK (satisfaction_score BETWEEN 1 AND 5),
    notes              TEXT,
    completed_date     TEXT
);
CREATE INDEX IF NOT EXISTS ix_calls_tech_status ON follow_up_calls(tech_id, status);

-- UNIQUE purchase_id guarantees a purchase is never allocated twice.
CREATE TABLE IF NOT EXISTS call_items (
    call_id       INTEGER NOT NULL REFERENCES follow_up_calls(call_id),
    purchase_id   INTEGER NOT NULL UNIQUE REFERENCES purchases(purchase_id),
    PRIMARY KEY (call_id, purchase_id)
);

CREATE TABLE IF NOT EXISTS email_log (
    email_id      INTEGER PRIMARY KEY,
    tech_id       INTEGER NOT NULL REFERENCES technicians(tech_id),
    run_date      TEXT NOT NULL,
    subject       TEXT NOT NULL,
    new_calls     INTEGER NOT NULL,
    overdue_calls INTEGER NOT NULL,
    delivery      TEXT NOT NULL,     -- 'outbox' or 'smtp'
    location      TEXT               -- file path or recipient address
);
"""


@dataclass
class Technician:
    tech_id: int
    name: str
    email: str
    max_calls_per_run: int


@dataclass
class PurchaseItem:
    purchase_id: int
    sku: str
    product_name: str
    category: str
    description: str
    quantity: int
    unit_price: float
    purchase_date: date

    @property
    def total(self) -> float:
        return round(self.quantity * self.unit_price, 2)

    def days_owned(self, today: date) -> int:
        return (today - self.purchase_date).days


@dataclass
class Customer:
    customer_id: int
    first_name: str
    last_name: str
    email: str
    phone: str
    city: str
    state: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass
class Call:
    call_id: int
    tech_id: int
    assigned_date: date
    due_date: date
    status: str
    customer: Customer
    items: list[PurchaseItem] = field(default_factory=list)

    @property
    def categories(self) -> list[str]:
        seen = []
        for item in self.items:
            if item.category not in seen:
                seen.append(item.category)
        return seen


class Database:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self):
        self.conn.close()

    def init_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- reads -------------------------------------------------------------

    def eligible_unallocated(self, cleared_on_or_before: date,
                             not_before: date | None = None) -> list[sqlite3.Row]:
        """Purchases old enough to be called on that aren't in any call yet,
        oldest first."""
        sql = """
            SELECT p.purchase_id, p.customer_id, p.sku, p.quantity, p.unit_price,
                   p.purchase_date
            FROM purchases p
            LEFT JOIN call_items ci ON ci.purchase_id = p.purchase_id
            WHERE ci.purchase_id IS NULL
              AND p.purchase_date <= ?
        """
        params: list = [cleared_on_or_before.isoformat()]
        if not_before is not None:
            sql += " AND p.purchase_date >= ?"
            params.append(not_before.isoformat())
        sql += " ORDER BY p.purchase_date, p.purchase_id"
        return self.conn.execute(sql, params).fetchall()

    def active_techs(self) -> list[Technician]:
        rows = self.conn.execute(
            "SELECT tech_id, name, email, max_calls_per_run FROM technicians "
            "WHERE active = 1 ORDER BY tech_id"
        ).fetchall()
        return [Technician(**dict(r)) for r in rows]

    def open_call_counts(self) -> dict[int, int]:
        rows = self.conn.execute(
            "SELECT tech_id, COUNT(*) AS n FROM follow_up_calls "
            "WHERE status = 'assigned' GROUP BY tech_id"
        ).fetchall()
        return {r["tech_id"]: r["n"] for r in rows}

    def markers_for(self, category: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT marker FROM performance_markers WHERE category = ? "
            "ORDER BY sort_order, marker_id", (category,)
        ).fetchall()
        return [r["marker"] for r in rows]

    def get_calls(self, call_ids: list[int] | None = None, *,
                  tech_id: int | None = None, status: str | None = None,
                  due_before: date | None = None) -> list[Call]:
        """Load calls with their customer and purchased items."""
        clauses, params = [], []
        if call_ids is not None:
            if not call_ids:
                return []
            clauses.append(f"f.call_id IN ({','.join('?' * len(call_ids))})")
            params.extend(call_ids)
        if tech_id is not None:
            clauses.append("f.tech_id = ?")
            params.append(tech_id)
        if status is not None:
            clauses.append("f.status = ?")
            params.append(status)
        if due_before is not None:
            clauses.append("f.due_date < ?")
            params.append(due_before.isoformat())
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        rows = self.conn.execute(f"""
            SELECT f.call_id, f.tech_id, f.assigned_date, f.due_date, f.status,
                   c.customer_id, c.first_name, c.last_name, c.email, c.phone,
                   c.city, c.state,
                   p.purchase_id, p.sku, p.quantity, p.unit_price, p.purchase_date,
                   pr.name AS product_name, pr.category, pr.description
            FROM follow_up_calls f
            JOIN customers  c  ON c.customer_id  = f.customer_id
            JOIN call_items ci ON ci.call_id     = f.call_id
            JOIN purchases  p  ON p.purchase_id  = ci.purchase_id
            JOIN products   pr ON pr.sku         = p.sku
            {where}
            ORDER BY f.due_date, f.call_id, p.purchase_date
        """, params).fetchall()

        calls: dict[int, Call] = {}
        for r in rows:
            call = calls.get(r["call_id"])
            if call is None:
                call = Call(
                    call_id=r["call_id"], tech_id=r["tech_id"],
                    assigned_date=date.fromisoformat(r["assigned_date"]),
                    due_date=date.fromisoformat(r["due_date"]),
                    status=r["status"],
                    customer=Customer(r["customer_id"], r["first_name"], r["last_name"],
                                      r["email"], r["phone"], r["city"], r["state"]),
                )
                calls[r["call_id"]] = call
            call.items.append(PurchaseItem(
                purchase_id=r["purchase_id"], sku=r["sku"],
                product_name=r["product_name"], category=r["category"],
                description=r["description"] or "", quantity=r["quantity"],
                unit_price=r["unit_price"],
                purchase_date=date.fromisoformat(r["purchase_date"]),
            ))
        return list(calls.values())

    def status_summary(self, today: date) -> list[sqlite3.Row]:
        return self.conn.execute("""
            SELECT t.name,
                   SUM(f.status = 'assigned' AND f.due_date >= ?) AS open_on_time,
                   SUM(f.status = 'assigned' AND f.due_date <  ?) AS overdue,
                   SUM(f.status = 'completed')                    AS completed,
                   SUM(f.status = 'unreachable')                  AS unreachable,
                   ROUND(AVG(f.satisfaction_score), 2)            AS avg_satisfaction
            FROM technicians t
            LEFT JOIN follow_up_calls f ON f.tech_id = t.tech_id
            GROUP BY t.tech_id ORDER BY t.tech_id
        """, (today.isoformat(), today.isoformat())).fetchall()

    def queue_counts(self, today: date, eligibility_days: int,
                     not_before: date | None) -> dict[str, int]:
        cutoff = today - timedelta(days=eligibility_days)
        waiting = len(self.eligible_unallocated(cutoff, not_before))
        not_yet = self.conn.execute(
            "SELECT COUNT(*) FROM purchases WHERE purchase_date > ?",
            (cutoff.isoformat(),)).fetchone()[0]
        return {"eligible_unassigned": waiting, "not_yet_eligible": not_yet}

    # ---- writes ------------------------------------------------------------

    def create_call(self, customer_id: int, tech_id: int, assigned: date,
                    due: date, purchase_ids: list[int]) -> int:
        cur = self.conn.execute(
            "INSERT INTO follow_up_calls (customer_id, tech_id, assigned_date, due_date) "
            "VALUES (?, ?, ?, ?)",
            (customer_id, tech_id, assigned.isoformat(), due.isoformat()))
        call_id = cur.lastrowid
        self.conn.executemany(
            "INSERT INTO call_items (call_id, purchase_id) VALUES (?, ?)",
            [(call_id, pid) for pid in purchase_ids])
        return call_id

    def record_outcome(self, call_id: int, status: str, score: int | None,
                       notes: str | None, on: date) -> bool:
        cur = self.conn.execute(
            "UPDATE follow_up_calls SET status = ?, satisfaction_score = ?, "
            "notes = ?, completed_date = ? WHERE call_id = ?",
            (status, score, notes, on.isoformat(), call_id))
        self.conn.commit()
        return cur.rowcount == 1

    def log_email(self, tech_id: int, run_date: date, subject: str, new_calls: int,
                  overdue_calls: int, delivery: str, location: str):
        self.conn.execute(
            "INSERT INTO email_log (tech_id, run_date, subject, new_calls, overdue_calls, "
            "delivery, location) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tech_id, run_date.isoformat(), subject, new_calls, overdue_calls,
             delivery, location))
