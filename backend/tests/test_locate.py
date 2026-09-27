"""Locating endpoints with synthetic OSM features. No network."""
from pipeline import locate
from pipeline.fetch_substations import match_project, normalize


def feat(name, lat, lon, operator=None, osm_id="way/1"):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"osm_id": osm_id, "name": name, "operator": operator, "voltage": None, "tags": {}}}


GOSHEN_AUG = feat("Goshen Substation", 33.32, -81.99, "Georgia Power", "way/10")
GOSHEN_SAV = feat("Goshen Substation", 32.25, -81.21, "Georgia Power", "way/11")
MCINTOSH = feat("McIntosh Substation", 32.352116, -81.175112, "Georgia Power", "way/12")
FEATURES = [GOSHEN_AUG, GOSHEN_SAV, MCINTOSH, feat("Airport Substation", 33.95, -81.10, None, "way/13"),
            feat("North Substation", 33.61, -81.09, None, "way/14")]
OVERRIDES = {("DESC", normalize("Okatie Sub")): {"lat": "32.333758", "lon": "-81.032495", "source": "Sperry starter workbook"}}


def test_goshen_sav_hint_picks_savannah():
    r = match_project("SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD", ["GOSHEN (SAV)", "MCINTOSH"], "GPC", FEATURES)
    assert (r[0]["lat"], r[0]["lon"]) == (32.25, -81.21)


def test_goshen_without_hint_uses_sibling_anchor():
    # No SAV prefix, no zone: McIntosh is unique, so Goshen must be the one near it, not Augusta's.
    r = match_project("GOSHEN - MCINTOSH 115KV LINE REBUILD", ["GOSHEN", "MCINTOSH"], "GPC",
                      [GOSHEN_AUG, GOSHEN_SAV, MCINTOSH])
    assert (r[1]["lat"], r[1]["lon"]) == (32.352116, -81.175112)
    assert (r[0]["lat"], r[0]["lon"]) == (32.25, -81.21)
    assert "LOCATED_VIA_SIBLING" in r[0]["flags"]


def test_goshen_zone_219_anchor():
    r = match_project("GOSHEN - KRAFT 115KV", ["GOSHEN"], "GPC", FEATURES, zone=219)
    assert (r[0]["lat"], r[0]["lon"]) == (32.25, -81.21)


def test_ambiguous_name_is_low_and_flagged():
    r = match_project("GOSHEN 115KV BREAKER", ["GOSHEN"], "GPC", [GOSHEN_AUG, GOSHEN_SAV])
    assert r[0]["confidence"] == "low"
    assert "AMBIGUOUS_NAME" in r[0]["flags"]


def test_okatie_override():
    loc = locate.locate_project("DESC_X", "DESC", "Jasper - Okatie 230 kV #2: Construct", FEATURES, overrides=OVERRIDES)
    okatie = loc["endpoints"][1]
    assert (okatie["lat"], okatie["lon"], okatie["confidence"]) == (32.333758, -81.032495, "high")
    assert okatie["source"] == "Sperry starter workbook"


def test_weak_fuzzy_matches_are_rejected():
    loc = locate.locate_project("DESC_Y", "DESC", "Riverport Tap: Construct Tap", FEATURES)
    assert loc["endpoints"][0]["confidence"] == "not_found"
    assert "Airport" in loc["match"][0]["rejected"]
    loc = locate.locate_project("GPC_Y", "GPC", "NORTH SPA 230KV STRATEGIC PROJECT", FEATURES)
    assert loc["endpoints"][0]["lat"] is None


def test_near_border():
    assert locate.near_border(32.35, -81.17)  # McIntosh
    assert not locate.near_border(34.0, -81.03)  # Columbia, SC
