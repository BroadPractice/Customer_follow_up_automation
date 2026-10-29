"""
Central settings for the follow-up call system.

Everything a client is likely to want to tune lives here. SMTP credentials are
read from environment variables so they never get committed to source control.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- Data -------------------------------------------------------------------
# Demo uses a local SQLite file. When the client's real database is connected,
# only db.py needs a new connection/driver; the rest of the app is unchanged.
DB_PATH = Path(os.getenv("FOLLOWUP_DB_PATH", BASE_DIR / "demo_data.db"))

# --- Business rules ---------------------------------------------------------
ELIGIBILITY_DAYS = 90          # purchase is cleared for a follow-up call this many days after purchase
CALL_DEADLINE_DAYS = 7         # techs have this many days from assignment to make the call
DEFAULT_MAX_CALLS_PER_RUN = 6  # default allotment per tech per run (overridable per tech in the DB)

# Ignore purchases older than this when looking for eligible ones. Prevents a
# first run against years of history from flooding techs. Set to None to disable.
MAX_PURCHASE_AGE_DAYS = 180

# --- Email ------------------------------------------------------------------
COMPANY_NAME = "Demo Home Services"
SENDER_ADDRESS = os.getenv("FOLLOWUP_SENDER", "followups@example.com")

# "outbox": write emails to ./outbox as .eml + .html files (safe for demos)
# "smtp":   actually send through the SMTP server below
EMAIL_MODE = os.getenv("FOLLOWUP_EMAIL_MODE", "outbox")
OUTBOX_DIR = BASE_DIR / "outbox"

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

# Asked on every call, regardless of product.
SATISFACTION_QUESTIONS = [
    "Overall, how satisfied are you with the product? (1 = very unsatisfied, 5 = very satisfied)",
    "Has it met the expectations set at the time of purchase?",
    "Would you recommend it (and us) to a friend or neighbor?",
    "Is there anything you need from us right now: service, parts, or a question answered?",
]
