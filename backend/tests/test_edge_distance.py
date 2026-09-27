"""Matching by edge distance (closest points) instead of Sperry's center distance."""
import json
from pathlib import Path

from engine import geo
from engine.overlaps import THRESHOLD_MI, build_overlap

DATA = Path(__file__).resolve().parents[1] / "data"


def _line(name, lat1, lon1, lat2, lon2):
    return {"id": name, "name": name, "utility": "DESC", "state": "SC", "project_type": "line",
            "endpoints": [{"name": "a", "lat": lat1, "lon": lon1}, {"name": "b", "lat": lat2, "lon": lon2}],
            "center": geo.center_of([{"lat": lat1, "lon": lon1}, {"lat": lat2, "lon": lon2}])}


def test_built_pairs_use_edge_distance_and_keep_sperry_pairs():
    ovs = [o for o in json.loads((DATA / "overlaps.json").read_text(encoding="utf-8"))
           if o.get("kind", "cross_utility") == "cross_utility"]
    assert all(min(o["closest_distance_mi"], o["center_distance_mi"]) < THRESHOLD_MI for o in ovs)
    assert all(o["closest_distance_mi"] <= o["center_distance_mi"] + 0.1 for o in ovs)  # projection rounding only
    sperry = [o for o in ovs if o["within_sperry_rule"]]
    assert len(sperry) == sum(o["center_distance_mi"] < THRESHOLD_MI for o in ovs)
    assert len(ovs) > len(sperry)  # edge distance only adds pairs


def test_long_lines_match_when_edges_are_close_even_if_centers_are_not():
    # Two 40-mile east-west lines, end to end with a 10-mile gap: centers ~50 mi apart, edges ~10 mi apart.
    a = _line("A", 32.0, -81.9, 32.0, -81.25)
    b = {**_line("B", 32.0, -81.09, 32.0, -80.44), "utility": "GPC"}
    o = build_overlap(a, b, "cross_utility")
    assert o is not None and o["center_distance_mi"] >= THRESHOLD_MI and not o["within_sperry_rule"]
    assert 8 < o["closest_distance_mi"] < 12


def test_rank_accepts_overlaps_saved_before_edge_matching():
    from engine.overlaps import rank
    old = {"id": "OVL_old", "score": 50, "center_distance_mi": 9.0}
    new = {"id": "OVL_new", "score": 50, "center_distance_mi": 12.0, "closest_distance_mi": 3.0}
    assert [o["id"] for o in rank([old, new])] == ["OVL_new", "OVL_old"]
