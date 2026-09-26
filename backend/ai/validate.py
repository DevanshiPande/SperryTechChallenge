"""Guards on Gemini output: every number and every record ID must come from the facts / tool results."""
import json
import re

NUM_RE = re.compile(r"\d[\d,]*\.?\d*")
LIST_MARKER_RE = re.compile(r"(?m)^\s*\d{1,2}[.)]\s+")
ID_RE = re.compile(r"\b(?:DESC|GPC|USR|OVL|RES|RSV|JOB|APP|CNV|MSG|ACT|CMP|WRK)_[A-Za-z0-9_]+\b")


def _to_float(tok):
    t = tok.replace(",", "").rstrip(".")
    try:
        return float(t)
    except ValueError:
        return None


def numbers_in_text(text):
    out = []
    for m in NUM_RE.finditer(text or ""):
        # Skip digits that are part of an ID like GPC_20277 or DESC_3 (checked by the ID guard instead).
        start = m.start()
        if start > 0 and (text[start - 1] == "_" or text[start - 1].isalpha()):
            continue
        v = _to_float(m.group())
        if v is not None:
            out.append(v)
    return out


def _walk(x, out):
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        out.add(float(x))
    elif isinstance(x, str):
        for v in numbers_in_text(x):
            out.add(v)
        for m in NUM_RE.finditer(x):  # digits inside IDs/names count as known too
            v = _to_float(m.group())
            if v is not None:
                out.add(v)
    elif isinstance(x, dict):
        for k, v in x.items():
            _walk(k, out)
            _walk(v, out)
    elif isinstance(x, (list, tuple, set)):
        for v in x:
            _walk(v, out)


def allowed_numbers(*sources):
    out = set()
    for s in sources:
        _walk(s, out)
    return out


def _matches(v, allowed):
    """A number passes if it equals a fact as-is or rounded to 0, 1 or 2 decimals."""
    return any(v == f or any(round(f, n) == v for n in (0, 1, 2)) for f in allowed)


def number_check(text, facts, extra_allowed=()):
    """Returns the list of numbers in `text` that do not appear in `facts` (empty list = pass)."""
    allowed = allowed_numbers(facts) | {float(x) for x in extra_allowed}
    text = LIST_MARKER_RE.sub("", text or "")  # "1. ..." / "2) ..." at line starts are list markers, not facts
    return [v for v in numbers_in_text(text) if not _matches(v, allowed)]


def id_check(text, allowed_ids):
    """Returns IDs mentioned in `text` that are not in `allowed_ids`."""
    allowed = set(allowed_ids)
    return [i for i in ID_RE.findall(text or "") if i not in allowed]


def ids_in(obj):
    return set(ID_RE.findall(json.dumps(obj, default=str)))
