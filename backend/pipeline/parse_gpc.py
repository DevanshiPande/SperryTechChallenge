"""Parse Georgia Power's 2025 IRP Volume 3 (2024 GA ITS Ten-Year Plan): Table 2 project list + project detail pages,
joined on TEAMS number."""
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from pipeline.pdftext import pdf_to_text

BACKEND = Path(__file__).resolve().parents[1]
PDF = BACKEND / "data" / "raw" / "gpc_irp_vol3.pdf"
TEXT = BACKEND / "data" / "text" / "gpc.txt"
REVIEW_CSV = BACKEND / "data" / "review" / "parsed_gpc.csv"

# Sponsors counted as Georgia Power. SAV = Georgia Power's Savannah-area work. GTC/MEAG/DU are other entities
# (open question for Sperry, see OPEN_QUESTIONS.md).
GPC_SPONSORS_INCLUDED = {"GPC", "SAV"}

TABLE_TITLE = "Table 2 Georgia ITS 10 Year Plan Project List"
ROW_RE = re.compile(r"^\s+(2\d{2})\s+(20\d{2})\s+(\d{4,5})\s+(.+?)\s+(\d{1,2}/\d{1,2}/\d{4})\s+([A-Z]+)\s+REDACTED")
TEAMS_RE = re.compile(r"Teams\s*#\s*(\d+)")
NEED_START_RE = re.compile(r"Need Date\s+(\S+)\s+Start Date\s+(\S+)")
HEADER_MARKERS = ["Ten-Year Plan (", "Page ", "PUBLIC DISCLOSURE", "CRITICAL ENERGY INFRASTRUCTURE", "CFR Sec",
                  "Marketing Function", "contents shall be handled", "notification. This document", "Table 2", "TEAMS",
                  "Estimated Cost", "Zone", "Sponsor", "Number",
                  # Detail pages wrap the CEII banner differently; these are its trailing fragments.
                  "policy, should not be disclosed", "be aware that disclosure"]


def is_header(line):
    s = line.strip()
    return any(m in line for m in HEADER_MARKERS) or s == "employees."


def _ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def iso_date(s):
    try:
        return datetime.strptime(s.strip(), "%m/%d/%Y").date().isoformat()
    except (ValueError, AttributeError):
        return None


def parse_table(text):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if TABLE_TITLE in l and not l.startswith(TABLE_TITLE + " below"))
    first_detail = next((i for i, l in enumerate(lines) if TEAMS_RE.search(l)), len(lines))
    rows, cur = [], None
    for l in lines[start + 1:first_detail]:
        m = ROW_RE.match(l)
        if m:
            cur = {"zone": int(m.group(1)), "year": int(m.group(2)), "teams": m.group(3), "table_name": _ws(m.group(4)),
                   "table_need_date": iso_date(m.group(5)), "sponsor": m.group(6)}
            rows.append(cur)
            continue
        if cur is None:
            continue
        if not l.strip() or is_header(l):
            cur = None  # a blank line or page header ends the name wrap
            continue
        cur["table_name"] = _ws(cur["table_name"] + " " + l.strip())
    return rows


def parse_details(text):
    pages_before = [0]
    for ch in text:
        if ch == "\f":
            pages_before.append(pages_before[-1] + 1)
    lines = text.splitlines(keepends=True)
    out = {}
    pos = 0
    offsets = []
    for l in lines:
        offsets.append(pos)
        pos += len(l)
    plain = [l.rstrip("\r\n") for l in lines]
    for i, l in enumerate(plain):
        m = TEAMS_RE.search(l)
        if not m or l.strip().startswith("TEAMS"):
            continue
        teams = m.group(1)
        # Title: up to 2 non-empty, non-header lines directly above.
        title_lines, j = [], i - 1
        while j >= 0 and not plain[j].strip():
            j -= 1
        while j >= 0 and plain[j].strip() and not is_header(plain[j]) and len(title_lines) < 2:
            title_lines.insert(0, plain[j].strip())
            j -= 1
        need = start = None
        for k in range(i + 1, min(i + 6, len(plain))):
            mm = NEED_START_RE.search(plain[k])
            if mm:
                need, start = iso_date(mm.group(1)), iso_date(mm.group(2))
                break
        desc = []
        try:
            d0 = next(k for k in range(i, min(i + 15, len(plain))) if plain[k].strip() == "Description")
            for k in range(d0 + 1, len(plain)):
                if plain[k].strip().startswith("Supporting Statement") or TEAMS_RE.search(plain[k]):
                    break
                if not is_header(plain[k]):
                    desc.append(plain[k])
        except StopIteration:
            pass
        page = text.count("\f", 0, offsets[i]) + 1
        out[teams] = {"teams": teams, "detail_title": _ws(" ".join(title_lines)), "need_date": need,
                      "start_date": start, "description": _ws(" ".join(desc)), "page": page}
    return out


def parse(text=None):
    text = text if text is not None else pdf_to_text(PDF, TEXT)
    table = parse_table(text)
    details = parse_details(text)
    out = []
    for r in table:
        d = details.get(r["teams"], {})
        flags = []
        need = d.get("need_date") or r["table_need_date"]
        if d.get("need_date") and r["table_need_date"] and d["need_date"] != r["table_need_date"]:
            flags.append("DATE_MISMATCH")
        if need is None:
            flags.append("DATE_PARSE_FAILED")
        out.append({
            "id": f"GPC_{r['teams']}",
            "teams": r["teams"],
            "zone": r["zone"],
            "year": r["year"],
            "sponsor": r["sponsor"],
            "included": r["sponsor"] in GPC_SPONSORS_INCLUDED,
            "name": d.get("detail_title") or r["table_name"],
            "table_name": r["table_name"],
            "detail_title": d.get("detail_title"),
            "table_need_date": r["table_need_date"],
            "need_date": need,
            "start_date": d.get("start_date"),
            "in_service_date": need,
            "description": d.get("description"),
            "page": d.get("page"),
            "has_detail": bool(d),
            "flags": flags,
        })
    return out, details


def write_review(rows, path=REVIEW_CSV):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["id", "teams", "zone", "year", "sponsor", "included", "name", "table_name", "detail_title",
            "table_need_date", "need_date", "start_date", "page", "has_detail", "flags", "description"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({**{k: r.get(k) for k in cols}, "flags": ";".join(r["flags"])})


if __name__ == "__main__":
    rows, details = parse()
    write_review(rows)
    print(json.dumps({"table_rows": len(rows), "detail_pages": len(details),
                      "sponsors": Counter(r["sponsor"] for r in rows),
                      "included": sum(r["included"] for r in rows),
                      "missing_detail": [r["teams"] for r in rows if not r["has_detail"]],
                      "date_mismatch": [r["teams"] for r in rows if "DATE_MISMATCH" in r["flags"]]}, indent=1))
