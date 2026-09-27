"""Construction windows and overlap months. Pure functions."""
from datetime import date

from dateutil.relativedelta import relativedelta

DAYS_PER_MONTH = 30.44


def to_date(s):
    if s is None:
        return None
    if isinstance(s, date):
        return s
    return date.fromisoformat(str(s)[:10])


def iso(d):
    return d.isoformat() if d else None


def add_months(s, months):
    return iso(to_date(s) + relativedelta(months=months))


def overlap_months(w1, w2):
    """max(0, min(ends) - max(starts)) days / 30.44, rounded."""
    if not w1 or not w2 or not all(w.get(k) for w in (w1, w2) for k in ("start", "end")):
        return 0
    start = max(to_date(w1["start"]), to_date(w2["start"]))
    end = min(to_date(w1["end"]), to_date(w2["end"]))
    days = (end - start).days
    return round(days / DAYS_PER_MONTH) if days > 0 else 0


def overlap_days(w1, w2):
    start = max(to_date(w1["start"]), to_date(w2["start"]))
    end = min(to_date(w1["end"]), to_date(w2["end"]))
    return (end - start).days


def _finalize(start, end, source):
    flags = []
    if start and end and start > end:
        start = end - relativedelta(months=12)
        flags.append("WINDOW_INVALID")
    return {"start": iso(start), "end": iso(end), "source": source}, flags


def estimated_window(in_service, project_type):
    end = to_date(in_service)
    if end is None:
        return None, []
    months = 24 if project_type == "line" else 18
    return _finalize(end - relativedelta(months=months), end, "estimated")


def gpc_window(start_date, need_date, project_type):
    if start_date and need_date:
        return _finalize(to_date(start_date), to_date(need_date), "gpc_start_date")
    return estimated_window(need_date, project_type)


def desc_window(cost, in_service, project_type):
    """Jan 1 of the first budget year with spend; 2023-01-01 if prior spend exists."""
    end = to_date(in_service)
    if end is None:
        return None, []
    start = None
    if cost:
        by_year = cost.get("by_year", {})
        if (by_year.get("previous") or 0) > 0:
            start = date(2023, 1, 1)
        else:
            for y in ("2024", "2025", "2026", "2027", "2028"):
                if (by_year.get(y) or 0) > 0:
                    start = date(int(y), 1, 1)
                    break
    if start is None:
        return estimated_window(in_service, project_type)
    return _finalize(start, end, "desc_spend_years")
