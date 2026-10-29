"""
Customer follow-up call system: command-line entry point.

    python main.py init-demo              # build a fresh demo database
    python main.py run                    # allocate cleared purchases and email techs
    python main.py run --dry-run          # preview who would get what, change nothing
    python main.py status                 # queue + per-tech progress
    python main.py complete 12 --score 5 --notes "Loves it"
    python main.py complete 13 --unreachable

Every command takes --today YYYY-MM-DD so the demo can "fast-forward" time.
In production, `run` is scheduled daily (cron / Windows Task Scheduler).
"""
import argparse
import sys
from datetime import date

import config
from allocator import allocate, eligibility_cutoff, lookback_floor
from db import Database
from emailer import send_assignments
from seed_demo import build_demo_db


def _date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {s!r}")


def cmd_init_demo(args):
    build_demo_db(config.DB_PATH, args.today)
    db = Database(config.DB_PATH)
    q = db.queue_counts(args.today, config.ELIGIBILITY_DAYS, lookback_floor(args.today))
    n = db.conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
    db.close()
    print(f"Demo database created at {config.DB_PATH}")
    print(f"  {n} purchases · {q['eligible_unassigned']} cleared for calls today · "
          f"{q['not_yet_eligible']} still inside the {config.ELIGIBILITY_DAYS}-day window")


def cmd_run(args):
    db = Database(config.DB_PATH)
    result = allocate(db, args.today, dry_run=args.dry_run)
    techs = {t.tech_id: t for t in db.active_techs()}

    label = "DRY RUN — nothing saved or sent" if args.dry_run else "Allocation run"
    print(f"{label} for {args.today} (purchases on or before "
          f"{eligibility_cutoff(args.today)} are cleared)")
    print(f"  {result.total_calls} calls covering {result.purchases_allocated} purchases, "
          f"due {result.due_date}")
    for tech_id, call_ids in result.calls_by_tech.items():
        print(f"    {techs[tech_id].name:<18} {len(call_ids)} call(s)")
    if result.customers_left_in_queue:
        print(f"  {result.customers_left_in_queue} customer(s) left in queue for the next run "
              f"(allotments full)")

    if not args.dry_run:
        sent = send_assignments(db, result.calls_by_tech, args.today)
        if sent:
            print(f"  Emails ({config.EMAIL_MODE}):")
            for s in sent:
                print(f"    -> {s['tech']:<18} {s['new']} new, {s['overdue']} overdue  "
                      f"[{s['location']}]")
        else:
            print("  No emails needed.")
    db.close()


def cmd_status(args):
    db = Database(config.DB_PATH)
    q = db.queue_counts(args.today, config.ELIGIBILITY_DAYS, lookback_floor(args.today))
    print(f"Status as of {args.today}")
    print(f"  Queue: {q['eligible_unassigned']} cleared & unassigned purchases · "
          f"{q['not_yet_eligible']} not yet at {config.ELIGIBILITY_DAYS} days")
    print(f"\n  {'Tech':<18}{'Open':>6}{'Overdue':>9}{'Done':>6}{'No ans.':>9}{'Avg sat.':>10}")
    for r in db.status_summary(args.today):
        avg = "-" if r["avg_satisfaction"] is None else f"{r['avg_satisfaction']:.2f}"
        print(f"  {r['name']:<18}{r['open_on_time'] or 0:>6}{r['overdue'] or 0:>9}"
              f"{r['completed'] or 0:>6}{r['unreachable'] or 0:>9}{avg:>10}")
    db.close()


def cmd_complete(args):
    if not args.unreachable and args.score is None:
        sys.exit("Give --score 1-5, or --unreachable if the customer couldn't be reached.")
    db = Database(config.DB_PATH)
    status = "unreachable" if args.unreachable else "completed"
    ok = db.record_outcome(args.call_id, status, None if args.unreachable else args.score,
                           args.notes, args.today)
    db.close()
    if not ok:
        sys.exit(f"No call with ID {args.call_id}.")
    print(f"Call #{args.call_id} marked {status}.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Customer follow-up call allocator")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--today", type=_date, default=date.today(),
                        help="override today's date (YYYY-MM-DD) for demos")
        sp.set_defaults(func=fn)
        return sp

    add("init-demo", cmd_init_demo, "create a fresh demo database")
    run = add("run", cmd_run, "allocate cleared purchases and email techs")
    run.add_argument("--dry-run", action="store_true", help="preview without saving or sending")
    add("status", cmd_status, "show queue and per-tech progress")
    comp = add("complete", cmd_complete, "record the outcome of a call")
    comp.add_argument("call_id", type=int)
    comp.add_argument("--score", type=int, choices=range(1, 6), metavar="1-5")
    comp.add_argument("--notes")
    comp.add_argument("--unreachable", action="store_true")

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
