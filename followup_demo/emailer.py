"""
Builds and delivers the call-allotment email each tech receives.

Every email has a plain-text part and an HTML part. In "outbox" mode the email
is saved as an .eml (opens in Outlook/Apple Mail) plus an .html preview; in
"smtp" mode it is sent for real.
"""
import re
import smtplib
from datetime import date
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from pathlib import Path

import config
from db import Call, Database, Technician


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _day(d: date) -> str:
    return d.strftime("%a, %b %d, %Y").replace(" 0", " ")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_subject(new_calls: list[Call], overdue: list[Call]) -> str:
    parts = []
    if new_calls:
        due = min(c.due_date for c in new_calls)
        parts.append(f"{len(new_calls)} follow-up call{'s' if len(new_calls) != 1 else ''} "
                     f"due by {due.strftime('%b %d').replace(' 0', ' ')}")
    if overdue:
        parts.append(f"{len(overdue)} overdue")
    return f"[{config.COMPANY_NAME}] " + " · ".join(parts)


# ---------------------------------------------------------------- plain text

def build_text(tech: Technician, new_calls: list[Call], overdue: list[Call],
               markers: dict[str, list[str]], today: date) -> str:
    first = tech.name.split()[0]
    lines = [f"Hi {first},", ""]
    if new_calls:
        due = min(c.due_date for c in new_calls)
        lines += [f"You have {len(new_calls)} new customer follow-up call(s). "
                  f"Please complete them by {_day(due)}.", ""]
    if overdue:
        lines += [f"You also have {len(overdue)} overdue call(s), listed at the end.", ""]

    for i, call in enumerate(new_calls, 1):
        c = call.customer
        lines += ["=" * 64,
                  f"CALL {i} of {len(new_calls)}  ·  Call ID #{call.call_id}  ·  due {_day(call.due_date)}",
                  "=" * 64,
                  f"Customer: {c.full_name}",
                  f"Phone:    {c.phone}",
                  f"Email:    {c.email}",
                  f"Location: {c.city}, {c.state}", "",
                  "What they bought:"]
        for it in call.items:
            lines.append(f"  - {it.product_name} ({it.sku}) x{it.quantity}  "
                         f"{_money(it.total)}  purchased {_day(it.purchase_date)} "
                         f"({it.days_owned(today)} days ago)")
        lines += ["", "Performance markers to check:"]
        for cat in call.categories:
            lines.append(f"  [{cat}]")
            lines += [f"    [ ] {m}" for m in markers.get(cat, [])]
        lines += ["", "Satisfaction:"]
        lines += [f"    [ ] {q}" for q in config.SATISFACTION_QUESTIONS]
        lines.append("")

    if overdue:
        lines += ["-" * 64, "OVERDUE - please complete as soon as possible:"]
        for call in overdue:
            lines.append(f"  #{call.call_id}  {call.customer.full_name}  {call.customer.phone}  "
                         f"(was due {_day(call.due_date)})")
        lines.append("")

    lines += ["Record each outcome with its Call ID in the follow-up system.",
              "", f"— {config.COMPANY_NAME} Customer Care"]
    return "\n".join(lines)


# ---------------------------------------------------------------------- HTML

INK, MUTED, LINE, ACCENT, BG, WARN = "#1f2933", "#5f6b7a", "#e3e7ec", "#1d5c8f", "#f5f7fa", "#b4462b"


def _call_card(i: int, n: int, call: Call, markers: dict[str, list[str]], today: date) -> str:
    c = call.customer
    item_rows = "".join(
        f"""<tr>
              <td style="padding:8px 10px;border-top:1px solid {LINE};">
                <strong>{escape(it.product_name)}</strong><br>
                <span style="color:{MUTED};font-size:12px;">{escape(it.sku)} · {escape(it.description)}</span>
              </td>
              <td style="padding:8px 10px;border-top:1px solid {LINE};white-space:nowrap;">{_day(it.purchase_date)}<br>
                <span style="color:{MUTED};font-size:12px;">{it.days_owned(today)} days ago</span></td>
              <td style="padding:8px 10px;border-top:1px solid {LINE};text-align:right;white-space:nowrap;">
                {_money(it.total)}{f'<br><span style="color:{MUTED};font-size:12px;">x{it.quantity}</span>' if it.quantity > 1 else ''}</td>
            </tr>""" for it in call.items)

    marker_blocks = "".join(
        f"""<p style="margin:12px 0 4px;font-size:12px;font-weight:bold;color:{ACCENT};
                      text-transform:uppercase;letter-spacing:.04em;">{escape(cat)}</p>
            {''.join(f'<p style="margin:3px 0;">&#9744;&nbsp; {escape(m)}</p>' for m in markers.get(cat, []))}"""
        for cat in call.categories)

    satisfaction = "".join(
        f'<p style="margin:3px 0;">&#9744;&nbsp; {escape(q)}</p>' for q in config.SATISFACTION_QUESTIONS)

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid {LINE};border-radius:8px;margin:0 0 20px;background:#fff;">
      <tr><td style="padding:14px 16px;border-bottom:1px solid {LINE};background:{BG};border-radius:8px 8px 0 0;">
        <span style="font-size:12px;color:{MUTED};">Call {i} of {n} · Call ID #{call.call_id} · due {_day(call.due_date)}</span><br>
        <span style="font-size:18px;font-weight:bold;">{escape(c.full_name)}</span><br>
        <a href="tel:{escape(re.sub(r'[^0-9+]', '', c.phone))}" style="color:{ACCENT};">{escape(c.phone)}</a>
        &nbsp;·&nbsp; <span style="color:{MUTED};">{escape(c.email)}</span>
        &nbsp;·&nbsp; <span style="color:{MUTED};">{escape(c.city)}, {escape(c.state)}</span>
      </td></tr>
      <tr><td style="padding:12px 16px 4px;">
        <p style="margin:0 0 6px;font-weight:bold;">What they bought</p>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;">
          <tr style="color:{MUTED};font-size:12px;text-align:left;">
            <th style="padding:4px 10px;font-weight:normal;">Product</th>
            <th style="padding:4px 10px;font-weight:normal;">Purchased</th>
            <th style="padding:4px 10px;font-weight:normal;text-align:right;">Paid</th>
          </tr>
          {item_rows}
        </table>
      </td></tr>
      <tr><td style="padding:8px 16px 4px;">
        <p style="margin:8px 0 0;font-weight:bold;">Performance markers to check</p>
        {marker_blocks}
      </td></tr>
      <tr><td style="padding:8px 16px 16px;">
        <p style="margin:12px 0 4px;font-weight:bold;">Satisfaction</p>
        {satisfaction}
      </td></tr>
    </table>"""


def build_html(tech: Technician, new_calls: list[Call], overdue: list[Call],
               markers: dict[str, list[str]], today: date) -> str:
    first = escape(tech.name.split()[0])
    due = min((c.due_date for c in new_calls), default=None)

    stats = []
    if new_calls:
        stats.append((str(len(new_calls)), "new call" if len(new_calls) == 1 else "new calls", INK))
        stats.append((due.strftime("%b %d").replace(" 0", " "), "deadline", ACCENT))
    stats.append((str(len(overdue)), "overdue", WARN if overdue else MUTED))
    stat_cells = "".join(
        f"""<td style="padding:12px;text-align:center;border:1px solid {LINE};border-radius:8px;background:#fff;">
              <div style="font-size:22px;font-weight:bold;color:{color};">{escape(val)}</div>
              <div style="font-size:12px;color:{MUTED};">{label}</div></td>
            <td width="8"></td>""" for val, label, color in stats)

    intro = (f"You have <strong>{len(new_calls)}</strong> customer follow-up call"
             f"{'s' if len(new_calls) != 1 else ''} to make. Each customer below is at least "
             f"{config.ELIGIBILITY_DAYS} days past their purchase. Please complete every call by "
             f"<strong>{_day(due)}</strong>.") if new_calls else \
            "No new calls this run, but you have overdue calls that still need to go out."

    cards = "".join(_call_card(i, len(new_calls), c, markers, today)
                    for i, c in enumerate(new_calls, 1))

    overdue_html = ""
    if overdue:
        rows = "".join(
            f"""<tr><td style="padding:6px 10px;border-top:1px solid {LINE};">#{c.call_id}</td>
                <td style="padding:6px 10px;border-top:1px solid {LINE};">{escape(c.customer.full_name)}</td>
                <td style="padding:6px 10px;border-top:1px solid {LINE};">{escape(c.customer.phone)}</td>
                <td style="padding:6px 10px;border-top:1px solid {LINE};color:{WARN};">was due {_day(c.due_date)}</td></tr>"""
            for c in overdue)
        overdue_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="border:1px solid {WARN};border-radius:8px;margin:0 0 20px;background:#fff;font-size:14px;">
          <tr><td colspan="4" style="padding:12px 10px;font-weight:bold;color:{WARN};">
            Overdue — please complete as soon as possible</td></tr>
          {rows}
        </table>"""

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(build_subject(new_calls, overdue))}</title></head>
<body style="margin:0;padding:0;background:{BG};font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:{INK};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};">
<tr><td align="center" style="padding:24px 12px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:680px;">
    <tr><td style="padding:0 0 16px;">
      <div style="font-size:13px;color:{MUTED};letter-spacing:.04em;text-transform:uppercase;">
        {escape(config.COMPANY_NAME)} · Customer follow-ups</div>
      <h1 style="margin:6px 0 8px;font-size:24px;">Hi {first}, here are your calls</h1>
      <p style="margin:0;line-height:1.5;">{intro}</p>
    </td></tr>
    <tr><td style="padding:0 0 20px;">
      <table role="presentation" cellpadding="0" cellspacing="0"><tr>{stat_cells}</tr></table>
    </td></tr>
    <tr><td>{overdue_html}{cards}</td></tr>
    <tr><td style="padding:4px 0 0;font-size:13px;color:{MUTED};line-height:1.5;">
      Record each outcome (satisfaction score 1–5 and notes) with its Call ID in the follow-up system.
      Assigned {_day(today)}.
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""


# ------------------------------------------------------------------ delivery

def build_message(tech: Technician, new_calls: list[Call], overdue: list[Call],
                  markers: dict[str, list[str]], today: date) -> tuple[EmailMessage, str]:
    msg = EmailMessage()
    msg["Subject"] = build_subject(new_calls, overdue)
    msg["From"] = f"{config.COMPANY_NAME} <{config.SENDER_ADDRESS}>"
    msg["To"] = f"{tech.name} <{tech.email}>"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=config.SENDER_ADDRESS.split("@")[-1])
    msg.set_content(build_text(tech, new_calls, overdue, markers, today))
    html = build_html(tech, new_calls, overdue, markers, today)
    msg.add_alternative(html, subtype="html")
    return msg, html


def _unique_path(folder: Path, stem: str, suffix: str) -> Path:
    path, n = folder / f"{stem}{suffix}", 2
    while path.exists():
        path, n = folder / f"{stem}-{n}{suffix}", n + 1
    return path


def deliver(msg: EmailMessage, html: str, tech: Technician, today: date) -> tuple[str, str]:
    """Returns (delivery_mode, location)."""
    if config.EMAIL_MODE == "smtp":
        if not config.SMTP_HOST:
            raise RuntimeError("EMAIL_MODE is 'smtp' but SMTP_HOST is not set.")
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            if config.SMTP_USE_TLS:
                smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
        return "smtp", tech.email

    config.OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    eml = _unique_path(config.OUTBOX_DIR, f"{today.isoformat()}_{_slug(tech.name)}", ".eml")
    eml.write_bytes(bytes(msg))
    eml.with_suffix(".html").write_text(html, encoding="utf-8")
    return "outbox", str(eml)


def send_assignments(db: Database, calls_by_tech: dict[int, list[int]], today: date,
                     *, include_overdue: bool = True) -> list[dict]:
    """Email every tech who has new calls and/or overdue calls."""
    sent = []
    marker_cache: dict[str, list[str]] = {}

    for tech in db.active_techs():
        new_calls = db.get_calls(calls_by_tech.get(tech.tech_id, []))
        overdue = (db.get_calls(tech_id=tech.tech_id, status="assigned", due_before=today)
                   if include_overdue else [])
        if not new_calls and not overdue:
            continue

        for call in new_calls:
            for cat in call.categories:
                if cat not in marker_cache:
                    marker_cache[cat] = db.markers_for(cat)

        msg, html = build_message(tech, new_calls, overdue, marker_cache, today)
        mode, location = deliver(msg, html, tech, today)
        db.log_email(tech.tech_id, today, msg["Subject"], len(new_calls), len(overdue),
                     mode, location)
        sent.append({"tech": tech.name, "email": tech.email, "new": len(new_calls),
                     "overdue": len(overdue), "delivery": mode, "location": location})
    db.conn.commit()
    return sent
