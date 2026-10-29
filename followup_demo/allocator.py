"""
Allocation rules.

1. A purchase is cleared for a follow-up call once it is ELIGIBILITY_DAYS old
   (purchase_date + 90 days <= today).
2. Cleared purchases for the same customer are combined into ONE call, so a
   customer who bought two things gets one phone call, not two.
3. Calls go out oldest-first. Each goes to the active tech with the lightest
   open workload who still has room in this run's allotment.
4. Each call gets a deadline of today + CALL_DEADLINE_DAYS.
5. Anything that doesn't fit this run's allotments stays in the queue and is
   picked up first on the next run.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

import config
from db import Database


@dataclass
class AllocationResult:
    run_date: date
    due_date: date
    calls_by_tech: dict[int, list[int]] = field(default_factory=dict)  # tech_id -> call_ids
    purchases_allocated: int = 0
    customers_left_in_queue: int = 0

    @property
    def total_calls(self) -> int:
        return sum(len(v) for v in self.calls_by_tech.values())


def eligibility_cutoff(today: date) -> date:
    """Latest purchase date that is cleared for allocation on `today`."""
    return today - timedelta(days=config.ELIGIBILITY_DAYS)


def lookback_floor(today: date) -> date | None:
    if config.MAX_PURCHASE_AGE_DAYS is None:
        return None
    return today - timedelta(days=config.MAX_PURCHASE_AGE_DAYS)


def allocate(db: Database, today: date, *, dry_run: bool = False) -> AllocationResult:
    due = today + timedelta(days=config.CALL_DEADLINE_DAYS)
    result = AllocationResult(run_date=today, due_date=due)

    rows = db.eligible_unallocated(eligibility_cutoff(today), lookback_floor(today))

    # Group by customer, keeping oldest-purchase-first order.
    groups: dict[int, list[int]] = {}
    for r in rows:
        groups.setdefault(r["customer_id"], []).append(r["purchase_id"])

    techs = db.active_techs()
    if not techs:
        result.customers_left_in_queue = len(groups)
        return result

    open_load = db.open_call_counts()
    load = {t.tech_id: open_load.get(t.tech_id, 0) for t in techs}
    room = {t.tech_id: t.max_calls_per_run for t in techs}

    fake_id = -1  # used for dry runs so nothing is written
    remaining = list(groups.items())
    while remaining:
        available = [t for t in techs if room[t.tech_id] > 0]
        if not available:
            break
        customer_id, purchase_ids = remaining.pop(0)
        tech = min(available, key=lambda t: (load[t.tech_id], t.tech_id))

        if dry_run:
            call_id, fake_id = fake_id, fake_id - 1
        else:
            call_id = db.create_call(customer_id, tech.tech_id, today, due, purchase_ids)

        result.calls_by_tech.setdefault(tech.tech_id, []).append(call_id)
        result.purchases_allocated += len(purchase_ids)
        load[tech.tech_id] += 1
        room[tech.tech_id] -= 1

    result.customers_left_in_queue = len(remaining)
    if not dry_run:
        db.conn.commit()
    return result
