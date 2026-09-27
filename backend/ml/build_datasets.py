"""
Build ML training datasets from the two public filings.
  gpc_duration.csv : Georgia Power projects with real Start Date and Need Date  -> target: duration_months
  desc_cost.csv    : Dominion projects with real budgets                         -> target: total_cost_usd
Input: pdftotext -layout output of both PDFs.
"""
import re, sys, csv
from datetime import datetime

GPC_TXT, DESC_TXT = sys.argv[1], sys.argv[2]
NOISE = ("Ten-Year Plan (", "Page ", "PUBLIC DISCLOSURE", "CRITICAL ENERGY", "CFR Sec", "Marketing Function",
         "contents shall be handled", "notification. This document", "should be aware", "non-public transmission",
         "be aware that disclosure", "employees.")

def clean(l): return re.sub(r"\s+", " ", l).strip()
def is_noise(l): return any(n in l for n in NOISE)

def voltage(text):
    text = re.sub(r"(\d{2})O(\s*kv)", r"\g<1>0\2", text, flags=re.I)          # filing typo "23O KV" -> 230
    v = []
    for a, b in re.findall(r"(\d{2,3})(?:\s*[-/]\s*(\d{2,3}))?\s*kv", text, re.I):   # also 230-115kV, 230/115KV
        v += [int(x) for x in (a, b) if x and 34 <= int(x) <= 765]
    return max(v) if v else None

def miles(text):
    m = re.findall(r"(\d+(?:\.\d+)?)\s*(?:miles|mile|mi\b)", text, re.I)
    vals = [float(x) for x in m if 0 < float(x) < 300]
    return round(sum(vals), 2) if vals else None

WORK_RULES = [  # checked in order, on the title first, then the description
    (r"relay", "relay_protection"),
    (r"statcom|\bsvc\b|static var|capacitor|reactor", "reactive_equipment"),
    (r"reconductor", "reconductor"),
    (r"rebuild", "rebuild"),
    (r"breaker|switch", "breaker_switch"),
    (r"transformer|autobank", "transformer"),
    (r"new substation|substation:?\s*construct|construct.*substation", "new_substation"),
    (r"construct|\bnew\b", "new_line"),
    (r"\btap\b|fold-in|fold in", "tap"),
    (r"upgrade|moderniz|uprate", "upgrade"),
]
def work_type(title, desc):
    for text in (title, desc):
        for pat, lab in WORK_RULES:
            if re.search(pat, text or "", re.I):
                return lab
    return "other"

def project_type(title):
    core = re.split(r"\d{2,3}\s*-?\s*kv", re.sub(r"^[A-Z]{2,5}:\s*", "", title), flags=re.I)[0]
    return "line" if re.search(r"\s[-–]\s|[a-z]-[a-z]", core, re.I) else "substation"

# ---------- Georgia Power ----------
g = open(GPC_TXT, encoding="utf-8", errors="ignore").read().splitlines()
table = {}
row_re = re.compile(r"^\s+(2\d{2})\s+(20\d{2})\s+(\d{4,5})\s+(.+?)\s+(\d{1,2}/\d{1,2}/\d{4})\s+([A-Z]+)\s+REDACTED")
for l in g:
    m = row_re.match(l)
    if m: table[m.group(3)] = {"zone": int(m.group(1)), "sponsor": m.group(6)}

rows = []
for i, l in enumerate(g):
    m = re.search(r"Teams #\s*(\d+)", l)
    if not m: continue
    teams = m.group(1)
    # title: nearest non-empty, non-noise lines above
    title_lines, j = [], i - 1
    while j >= 0 and len(title_lines) < 2:
        s = clean(g[j])
        if s and not is_noise(s): title_lines.insert(0, s)
        elif title_lines: break
        j -= 1
    title = " ".join(title_lines)
    need = start = None
    for k in range(i + 1, min(i + 6, len(g))):
        d = re.search(r"Need Date\s+(\d{1,2}/\d{1,2}/\d{4})\s+Start Date\s+(\d{1,2}/\d{1,2}/\d{4})", g[k])
        if d: need, start = d.group(1), d.group(2); break
    desc, k = [], i + 1
    while k < len(g) and "Description" not in g[k] and k < i + 12: k += 1
    k += 1
    while k < len(g) and "Supporting Statement" not in g[k] and k < i + 60:
        s = clean(g[k])
        if s and not is_noise(s): desc.append(s)
        k += 1
    desc = " ".join(desc)
    if not (need and start): continue
    dn, ds = datetime.strptime(need, "%m/%d/%Y"), datetime.strptime(start, "%m/%d/%Y")
    dur = round((dn - ds).days / 30.44, 1)
    t = table.get(teams, {})
    rows.append({"teams": teams, "title": title, "zone": t.get("zone"), "sponsor": t.get("sponsor"),
                 "voltage_kv": voltage(title) or voltage(desc), "project_type": project_type(title),
                 "work_type": work_type(title, desc), "line_miles": miles(desc),
                 "start_date": ds.date().isoformat(), "need_date": dn.date().isoformat(),
                 "start_year": ds.year, "duration_months": dur, "description": desc[:400]})

with open("gpc_duration.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("GPC rows:", len(rows))

# ---------- Dominion ----------
d = open(DESC_TXT, encoding="utf-8", errors="ignore").read()
blocks = re.split(r"Project \d+ of 44", d)[1:] if "Project 1 of 44" in d else []
# the "Project N of 44" marker sits at the top of each page; the block content follows it
parts = re.split(r"(Project \d+ of 44)", d)
drows = []
for idx in range(1, len(parts), 2):
    n = int(re.search(r"\d+", parts[idx]).group())
    b = parts[idx + 1] if idx + 1 < len(parts) else ""
    L = [clean(x) for x in b.splitlines()]
    def after(label):
        for q, x in enumerate(L):
            if x.startswith(label):
                for y in L[q + 1:]:
                    if y: return y
        return None
    def between(a, bb):
        out, on = [], False
        for x in L:
            if x.startswith(a): on = True; continue
            if on and x.startswith(bb): break
            if on and x: out.append(x)
        return " ".join(out)
    title = between("5 Year Budget", "Project ID")
    desc = between("Project Description", "Project Need")
    isd = after("Planned In-Service Date")
    cost_line = None
    for q, x in enumerate(L):
        if x.startswith("Previous"):
            for y in L[q + 1:]:
                if y.count("$") >= 7: cost_line = y; break
            break
    if not cost_line: continue
    vals = [int(v.replace(",", "")) for v in re.findall(r"\$([\d,]+)", cost_line)]
    if len(vals) != 7: continue
    try:
        fmt = "%m/%d/%y" if re.match(r"^\d{1,2}/\d{1,2}/\d{2}$", isd or "") else "%m/%d/%Y"
        isd_iso = datetime.strptime(isd, fmt).date().isoformat()
    except Exception:
        isd_iso = None
    spend_years = [y for y, v in zip([2024, 2025, 2026, 2027, 2028], vals[1:6]) if v > 0]
    drows.append({"project_no": n, "title": title, "voltage_kv": voltage(title) or voltage(desc),
                  "project_type": project_type(title), "work_type": work_type(title, desc),
                  "line_miles": miles(desc), "status": after("Project Status"), "in_service_date": isd_iso,
                  "spend_previous": vals[0], "spend_years": len(spend_years) + (1 if vals[0] > 0 else 0),
                  "total_cost_usd": vals[6], "description": desc[:400]})
with open("desc_cost.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(drows[0].keys())); w.writeheader(); w.writerows(drows)
print("DESC rows:", len(drows))
