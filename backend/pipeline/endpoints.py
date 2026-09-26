"""Turn a project title into endpoint names, voltage, project type, work-type label and short name."""
import re

VOLT_RE = re.compile(r"(\d{2,3})\s*-?\s*kV", re.I)
VOLT_PAIR_RE = re.compile(r"(\d{2,3})\s*[-/]\s*[\d.]+\s*kV", re.I)  # 230-115kV, 500/230KV -> first number
VOLT_TOKEN_RE = re.compile(r"\d{2,3}(?:\s*[-/]\s*[\d.]+)?\s*-?\s*kV", re.I)
# Spec work words, plus equipment words from the GPC list (relay, modernization, ...) that are never endpoints.
WORK_RE = re.compile(r"\b(Rebuild|Construct|Reconductor|Reactors?|Tap|Fold-in|Upgrade|Line|Tie|Sub(?:station)?|"
                     r"Autobanks?|Breaker|Switch|Relay|Modernization|Installation|Statcom|Capacitor|Equipment|"
                     r"Improvements?|Replacement|Removal|Protective|Bank|Transformer|Strategic|Area)\b:?", re.I)
PREFIX_RE = re.compile(r"^([A-Z]{2,5}):\s*")
DASH_PREFIX_RE = re.compile(r"^(CC|GRID)\s+-\s+")  # customer-connection / grid-program labels, not endpoints
MULTI_SEP_RE = re.compile(r"\s&\s|\s/\s|(?<!\d)/(?!\d)|,")
SPLIT_RE = re.compile(r"\s+[-–]\s+|\s*–\s*|(?<=[A-Za-z0-9)])-(?=[A-Za-z0-9])|(?<=[A-Za-z])-\s+|\s+-(?=[A-Za-z])")
TRAILING_SUB_RE = re.compile(r"\s+(Sub|Substation)\.?$", re.I)


def voltage_kv(name):
    vals = [int(v) for v in VOLT_RE.findall(name or "")] + [int(v) for v in VOLT_PAIR_RE.findall(name or "")]
    return max(vals) if vals else None


def _clean(part):
    part = re.sub(r"\s+", " ", part).strip(" :;,.-–")
    part = TRAILING_SUB_RE.sub("", part)
    return part.strip(" :;,.-–")


def split_endpoints(name):
    """Returns {endpoints, voltage_kv, region_prefix, flags, needs_fallback}."""
    flags = []
    text = re.sub(r"\s+", " ", (name or "")).strip()
    prefix = None
    m = PREFIX_RE.match(text)
    if m:
        prefix = m.group(1)
        text = text[m.end():]
    m = DASH_PREFIX_RE.match(text)
    if m:
        text = text[m.end():]

    # Several lines or sites in one project: keep the first segment. Separators after the first colon
    # describe the work ("Sub: #1 & #2 Autobanks"), not more sites.
    head = text.split(":", 1)[0]
    sep = MULTI_SEP_RE.search(head)
    if sep:
        rest = text[sep.end():]
        if VOLT_TOKEN_RE.search(rest) or SPLIT_RE.search(rest):
            flags.append("MULTI_SEGMENT")
            text = text[:sep.start()]

    # Endpoint text ends at the first voltage token, work word, or colon.
    cuts = [len(text)]
    for rx in (VOLT_TOKEN_RE, WORK_RE):
        mm = rx.search(text)
        if mm:
            cuts.append(mm.start())
    if ":" in text:
        cuts.append(text.index(":"))
    ep_text = text[:min(cuts)]

    parts = [_clean(p) for p in SPLIT_RE.split(ep_text)]
    parts = [p for p in parts if p]
    return {
        "endpoints": parts if 1 <= len(parts) <= 2 else [],
        "voltage_kv": voltage_kv(name),
        "region_prefix": prefix,
        "flags": flags,
        "needs_fallback": not (1 <= len(parts) <= 2),
    }


def _norm_ws(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def validate_fallback(name, endpoint_names):
    """Gemini fallback output is accepted only if each endpoint is a substring of the title."""
    title = _norm_ws(name)
    names = [n for n in endpoint_names if n]
    return bool(names) and len(names) <= 2 and all(_norm_ws(n) in title for n in names)


def project_type(endpoints):
    return "line" if len(endpoints) == 2 else "substation"


def work_type_label(name, ptype):
    n = name or ""
    rules = [
        (r"construct", "New transmission line" if ptype == "line" else "New substation"),
        (r"reactor", "Equipment upgrade (reactors)"),
        (r"reconductor", "Line reconductor"),
        (r"rebuild|rebld", "Line rebuild" if ptype == "line" else "Substation rebuild"),
        (r"\btap\b", "New tap"),
        (r"fold-in", "Line fold-in"),
        (r"breaker|switch", "Equipment replacement"),
    ]
    for rx, label in rules:
        if re.search(rx, n, re.I):
            return label
    return "Transmission project"


SHORT_DROP_RE = re.compile(r"\(.*?\)|#\s*\d+|\b(primary|pri|dam|sub|substation)\b", re.I)


def _title_word(w):
    if not w:
        return w
    if len(w) <= 3 and w.isupper() and not w.isalpha():
        return w
    low = w.lower()
    if low.startswith("mc") and len(w) > 2:
        return "Mc" + low[2:].capitalize()
    return low.capitalize()


def pretty_name(endpoint_name):
    s = SHORT_DROP_RE.sub(" ", endpoint_name or "")
    s = re.sub(r"\s+", " ", s).strip(" -–")
    if not s:
        s = (endpoint_name or "").strip()
    if s.isupper() or s.islower():
        s = " ".join(_title_word(w) for w in s.split())
    return s


def short_name(endpoints, fallback_name=None):
    names = [pretty_name(e) for e in endpoints if e]
    if names:
        return "–".join(names)
    return re.sub(r"\s+", " ", fallback_name or "").strip()[:40]
