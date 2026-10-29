# Customer Follow-Up Call System (Demo)

Tracks what each customer bought, how much they paid, and when. Once a purchase is
**90 days old** it's cleared for a follow-up call, and the system automatically emails
each technician their allotment of calls with a deadline, a rundown of what the
customer bought, the performance markers to check, and satisfaction questions.

Pure Python 3.10+, standard library only. Nothing to install.

## Demo walkthrough

```bash
python main.py init-demo --today 2026-10-29     # fictional customers, purchases, techs
python main.py run --dry-run --today 2026-10-29 # preview the allocation
python main.py run --today 2026-10-29           # allocate + write emails to ./outbox
python main.py run --today 2026-10-29           # run again: nothing is double-assigned

# Techs log outcomes
python main.py complete 1 --score 5 --notes "Very happy, bills down" --today 2026-11-02
python main.py complete 3 --unreachable --today 2026-11-04

# Fast-forward: new purchases have cleared, unfinished calls are now overdue
python main.py run --today 2026-11-10
python main.py status --today 2026-11-10
```

Open any `outbox/*.html` in a browser to see the email, or `*.eml` in Outlook / Apple Mail.

## How allocation works

1. **Cleared:** `purchase_date + 90 days <= today`.
2. **One call per customer:** if a customer has several cleared purchases they're
   combined into one call.
3. **Oldest first, balanced:** each call goes to the active tech with the lightest
   open workload who still has room in this run's allotment (`max_calls_per_run`,
   set per tech).
4. **Deadline:** `today + 7 days`.
5. **Carry-over:** anything beyond everyone's allotment stays queued for the next run.
6. **Overdue reminders:** unfinished calls past their deadline are listed at the top
   of the tech's next email.

All of these numbers live in `config.py`.

## Files

| File | Purpose |
|---|---|
| `main.py` | Command line: `init-demo`, `run`, `status`, `complete` |
| `config.py` | Business rules (90 days, 7-day deadline, allotments), email settings |
| `db.py` | Schema and every SQL query (the only file that touches the database) |
| `allocator.py` | 90-day eligibility and tech assignment |
| `emailer.py` | Builds the HTML + plain-text email; outbox or SMTP delivery |
| `catalog.py` | Demo products and per-category performance markers |
| `seed_demo.py` | Fictional demo data (all addresses @example.com) |
| `test_allocator.py` | `python -m unittest -v` |

## Database tables

`customers`, `products`, `purchases` (customer, SKU, quantity, unit price, purchase date),
`performance_markers` (checklist per product category), `technicians`,
`follow_up_calls` (assignment, deadline, status, satisfaction 1–5, notes),
`call_items` (which purchases a call covers; a purchase can only ever be in one call),
`email_log`.

## Moving to production (after agreement)

- **Database:** point `db.py` at the client's database (e.g. `pyodbc` for SQL Server,
  `psycopg` for PostgreSQL) and map their customer/purchase tables onto the queries in
  `eligible_unallocated` and `get_calls`. The follow-up tables can live alongside theirs.
- **Email:** set `FOLLOWUP_EMAIL_MODE=smtp` plus `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
  `SMTP_PASSWORD`, `FOLLOWUP_SENDER` as environment variables.
- **Automation:** schedule `python main.py run` daily, e.g. cron `0 7 * * 1-5` or
  Windows Task Scheduler.
- **First run:** `MAX_PURCHASE_AGE_DAYS` (180) stops years of old purchases from
  flooding techs on day one.
- **Outcome capture:** the `complete` command is a stand-in; a small web form or a
  CRM integration would replace it.
