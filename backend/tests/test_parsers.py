"""DESC + GPC parser counts and spot checks (needs poppler pdftotext or the cached data/text/*.txt)."""
from collections import Counter
from functools import lru_cache

import pytest

from pipeline import parse_desc, parse_gpc


def _available(mod):
    if mod.TEXT.exists():
        return True
    try:
        from pipeline.pdftext import pdftotext_bin
        pdftotext_bin()
        return True
    except RuntimeError:
        return False


@lru_cache(maxsize=1)
def desc():
    return parse_desc.parse()


@lru_cache(maxsize=1)
def gpc():
    return parse_gpc.parse()


needs_desc = pytest.mark.skipif(not _available(parse_desc), reason="no pdftotext / cached text")
needs_gpc = pytest.mark.skipif(not _available(parse_gpc), reason="no pdftotext / cached text")


@needs_desc
def test_desc_counts():
    rows = desc()
    assert len(rows) == 44
    assert Counter(r["status"] for r in rows) == {"In Progress": 27, "Planned": 17}


@needs_desc
def test_desc_project_1():
    p = desc()[0]
    assert p["title"].startswith("Queensboro - Ft Johnson 115 kV")
    assert p["project_ref"] == "6807 B"
    assert p["in_service_date"] == "2023-12-31"
    assert p["cost"]["previous"] == 4604301 and p["cost"]["2024"] == 800000 and p["cost"]["total"] == 5404301


@needs_desc
def test_desc_project_2():
    p = desc()[1]
    assert p["project_ref"] == "0167C-D"
    assert p["in_service_date"] == "2027-12-31"
    assert p["cost"]["total"] == 5300000


def test_desc_date_formats():
    assert parse_desc.parse_date("12/31/23") == "2023-12-31"
    assert parse_desc.parse_date("10/1/2025") == "2025-10-01"
    assert parse_desc.parse_date("06/01/24") == "2024-06-01"
    assert parse_desc.parse_date("soon") is None


@needs_gpc
def test_gpc_counts():
    rows, details = gpc()
    assert len(rows) == 208
    assert Counter(r["sponsor"] for r in rows) == {"GPC": 122, "GTC": 54, "MEAG": 14, "SAV": 16, "DU": 2}
    assert len(details) == 208
    assert {r["teams"] for r in rows} == set(details)


@needs_gpc
def test_gpc_spot_checks():
    rows = {r["teams"]: r for r in gpc()[0]}
    r = rows["20277"]
    assert r["name"] == "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS"
    assert r["need_date"] == "2026-06-01" and r["start_date"] == "2024-01-01"
    assert r["included"] is True
    r = rows["11821"]
    assert r["name"] == "JESUP - LUDOWICI PRIMARY 115KV REBUILD"
    assert r["zone"] == 218 and r["need_date"] == "2025-06-01"


@needs_gpc
def test_gpc_sponsor_filter():
    rows = gpc()[0]
    assert all(r["included"] == (r["sponsor"] in {"GPC", "SAV"}) for r in rows)
