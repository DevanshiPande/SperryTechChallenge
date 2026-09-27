"""Sperry's answer key: the 10 starter projects must produce exactly these 6 overlaps."""
from pathlib import Path

from engine.overlaps import cross_utility_overlaps
from pipeline.starter import starter_projects

XLSX = Path(__file__).resolve().parents[1] / "data" / "raw" / "Projects_Overlaps.xlsx"

EXPECTED = {
    ("DESC_2", "GPC_1"): (4.09, 3074),
    ("DESC_3", "GPC_2"): (5.65, 152),
    ("DESC_3", "GPC_3"): (7.55, 517),
    ("DESC_1", "GPC_1"): (8.01, 3074),
    ("DESC_5", "GPC_2"): (14.34, 365),
    ("DESC_5", "GPC_3"): (14.81, 730),
}


def _overlaps():
    return cross_utility_overlaps(starter_projects(XLSX))


def test_exactly_the_six_sperry_overlaps():
    got = {(o["project_a"], o["project_b"]): (o["center_distance_mi"], o["time_gap_days"]) for o in _overlaps()}
    assert got == EXPECTED


def test_shared_thurmond_is_a_crossing():
    o = next(o for o in _overlaps() if (o["project_a"], o["project_b"]) == ("DESC_2", "GPC_1"))
    assert o["shared_endpoint"] is True
    assert o["tier"] == "crossing"


def test_ids_labels_and_ranks():
    ovs = _overlaps()
    assert sorted(o["rank"] for o in ovs) == list(range(1, 7))
    o = next(o for o in ovs if o["project_a"] == "DESC_3" and o["project_b"] == "GPC_2")
    assert o["id"] == "OVL_DESC_3__GPC_2"
    assert o["label"] == "Jasper–Okatie ↔ McIntosh–Purrysburg"
    assert all(o["kind"] == "cross_utility" for o in ovs)


def test_centers_follow_sperry_rule():
    ps = {p["id"]: p for p in starter_projects(XLSX)}
    assert ps["DESC_2"]["center"] == {"lat": 33.660127, "lon": -82.195931}  # one endpoint = that point
    assert ps["DESC_3"]["center"] == {"lat": round((32.35912 + 32.333758) / 2, 6), "lon": round((-81.1246 + -81.032495) / 2, 6)}
