"""Small helpers shared by services."""
import secrets
import string
from datetime import date

from services.errors import bad_request

_ALPHABET = string.ascii_uppercase + string.digits


def new_id(prefix, n=6):
    return f"{prefix}_{''.join(secrets.choice(_ALPHABET) for _ in range(n))}"


def parse_iso(value, field):
    """'YYYY-MM-DD' -> ISO string, else BAD_REQUEST."""
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        raise bad_request(f"{field} must be a date in YYYY-MM-DD format")


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def date_label(start, end):
    """'Jun 3–10, 2027' / 'Jun 28 – Jul 3, 2027' / 'Dec 20, 2026 – Jan 5, 2027'."""
    if not start and not end:
        return None
    if not end or start == end:
        d = date.fromisoformat(start or end)
        return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if a.year == b.year and a.month == b.month:
        return f"{MONTHS[a.month - 1]} {a.day}–{b.day}, {a.year}"
    if a.year == b.year:
        return f"{MONTHS[a.month - 1]} {a.day} – {MONTHS[b.month - 1]} {b.day}, {a.year}"
    return f"{MONTHS[a.month - 1]} {a.day}, {a.year} – {MONTHS[b.month - 1]} {b.day}, {b.year}"


def money(x):
    return f"${x:,.0f}" if float(x).is_integer() else f"${x:,.2f}"


def text_match(hay_parts, q):
    hay = " ".join(str(h) for h in hay_parts if h).lower()
    return all(w in hay for w in (q or "").lower().split())


def parse_near(near):
    """'32.08,-81.09' -> {lat, lon}"""
    try:
        lat, lon = [float(x) for x in str(near).split(",")]
        return {"lat": lat, "lon": lon}
    except (ValueError, TypeError):
        raise bad_request("near must be 'lat,lon'")
