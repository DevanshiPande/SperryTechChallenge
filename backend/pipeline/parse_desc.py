"""Parse Dominion Energy South Carolina '2024-2028 $2 million and above project descriptions' (one project per page)."""
import csv
import json
import re
from datetime import date
from pathlib import Path

from pipeline.pdftext import pdf_to_text

BACKEND = Path(__file__).resolve().parents[1]
PDF = BACKEND / "data" / "raw" / "desc_projects.pdf"
TEXT = BACKEND / "data" / "text" / "desc.txt"
REVIEW_CSV = BACKEND / "data" / "review" / "parsed_desc.csv"

MARKER_RE = re.compile(r"Project\s+(\d+)\s+of\s+(\d+)")
LABELS = ["Project ID", "Project Description", "Project Need", "Project Status", "Planned In-Service Date",
          "Estimated Project Cost"]
MONEY_RE = re.compile(r"\$[\d,]+")
COST_KEYS = ["previous", "2024", "2025", "2026", "2027", "2028", "total"]


def _ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def parse_date(s):
    """M/D/YY or M/D/YYYY -> YYYY-MM-DD (two-digit years are 20YY); None on failure."""
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\s*", s or "")
    if not m:
        return None
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _section(lines, label):
    """Lines after `label` up to the next known label."""
    try:
        i = next(k for k, l in enumerate(lines) if l.strip() == label)
    except StopIteration:
        return []
    out = []
    for l in lines[i + 1:]:
        if l.strip() in LABELS:
            break
        out.append(l)
    return out


def _first_nonempty(lines):
    return next((l.strip() for l in lines if l.strip()), None)


def parse_cost(lines):
    """Header line starting with 'Previous', then the next line with 7 dollar amounts."""
    try:
        h = next(k for k, l in enumerate(lines) if l.strip().startswith("Previous"))
    except StopIteration:
        return None
    for l in lines[h + 1:]:
        vals = MONEY_RE.findall(l)
        if vals:
            if len(vals) != 7:
                return None
            nums = [int(v.replace("$", "").replace(",", "")) for v in vals]
            return dict(zip(COST_KEYS, nums))
    return None


def parse_block(n, block):
    lines = block.splitlines()
    flags = []
    # Title: non-empty lines between '5 Year Budget' and 'Project ID'.
    try:
        b = next(k for k, l in enumerate(lines) if "5 Year Budget" in l)
        pid = next(k for k, l in enumerate(lines) if l.strip() == "Project ID")
        title = _ws(" ".join(l for l in lines[b + 1:pid] if l.strip()))
    except StopIteration:
        title = None
    date_raw = _first_nonempty(_section(lines, "Planned In-Service Date"))
    isd = parse_date(date_raw)
    if isd is None:
        # Phased projects list several dates ("10/1/2025 (phase 1) and 10/1/2026 (phase 2)"): use the final phase.
        phases = [d for d in (parse_date(x) for x in re.findall(r"\d{1,2}/\d{1,2}/\d{2,4}", date_raw or "")) if d]
        if len(phases) > 1:
            isd = max(phases)
            flags.append("MULTI_PHASE_DATE")
        else:
            flags.append("DATE_PARSE_FAILED")
    cost = parse_cost(_section(lines, "Estimated Project Cost"))
    if cost is None:
        flags.append("COST_PARSE_FAILED")
    return {
        "id": f"DESC_{n}",
        "page": n,
        "title": title,
        "project_ref": _first_nonempty(_section(lines, "Project ID")),
        "description": _ws(" ".join(_section(lines, "Project Description"))),
        "need": _ws(" ".join(_section(lines, "Project Need"))),
        "status": _first_nonempty(_section(lines, "Project Status")),
        "in_service_date_raw": date_raw,
        "in_service_date": isd,
        "cost": cost,
        "flags": flags,
    }


def parse(text=None):
    text = text if text is not None else pdf_to_text(PDF, TEXT)
    marks = list(MARKER_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append(parse_block(int(m.group(1)), text[m.end():end]))
    return out


def write_review(rows, path=REVIEW_CSV):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["id", "page", "project_ref", "title", "status", "in_service_date_raw", "in_service_date"] + \
           [f"cost_{k}" for k in COST_KEYS] + ["flags", "description", "need"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            row = {k: r.get(k) for k in cols if k in r}
            for k in COST_KEYS:
                row[f"cost_{k}"] = (r["cost"] or {}).get(k)
            row["flags"] = ";".join(r["flags"])
            w.writerow(row)


if __name__ == "__main__":
    rows = parse()
    write_review(rows)
    print(json.dumps({"projects": len(rows), "statuses": {s: sum(r["status"] == s for r in rows)
                                                           for s in {r["status"] for r in rows}}}, indent=1))
