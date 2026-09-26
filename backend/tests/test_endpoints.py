import pytest

from pipeline.endpoints import short_name, split_endpoints, validate_fallback, work_type_label

CASES = [
    ("Jasper - Okatie 230 kV #2: Construct", ["Jasper", "Okatie"], 230, False),
    ("Okatie-Bluffton 115 kV: Rebuild", ["Okatie", "Bluffton"], 115, False),
    ("Hooks - Thurmond 115 kV Tie: Rebuild", ["Hooks", "Thurmond"], 115, False),
    ("SAV: MCINTOSH - PURRYSBURG 230KV REACTORS", ["MCINTOSH", "PURRYSBURG"], 230, False),
    ("SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD", ["GOSHEN (SAV)", "MCINTOSH"], 115, False),
    ("EVANS PRIMARY - THURMOND DAM (USA) #5 115KV REBUILD", ["EVANS PRIMARY", "THURMOND DAM (USA) #5"], 115, False),
    ("MITCHELL - NORTH TIFTON 230KV RECONDUCTOR", ["MITCHELL", "NORTH TIFTON"], 230, False),
    ("Stevens Creek - Hooks 115 kV / LR Plumb Branch 46 kV Rebuilds", ["Stevens Creek", "Hooks"], 115, True),
    ("Okatie 230-115kV Substation, Jasper – Yemassee 230kV #1 Fold-in", ["Okatie"], 230, True),
]


@pytest.mark.parametrize("name,endpoints,kv,multi", CASES)
def test_split(name, endpoints, kv, multi):
    r = split_endpoints(name)
    assert r["endpoints"] == endpoints
    assert r["voltage_kv"] == kv
    assert ("MULTI_SEGMENT" in r["flags"]) == multi


def test_region_prefix():
    assert split_endpoints("SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD")["region_prefix"] == "SAV"


def test_short_names():
    assert short_name(["Jasper", "Okatie"]) == "Jasper–Okatie"
    assert short_name(["MCINTOSH", "PURRYSBURG"]) == "McIntosh–Purrysburg"
    assert short_name(["GOSHEN (SAV)", "MCINTOSH"]) == "Goshen–McIntosh"
    assert short_name(["EVANS PRIMARY", "THURMOND DAM (USA) #5"]) == "Evans–Thurmond"


def test_work_type_labels():
    assert work_type_label("Jasper - Okatie 230 kV #2: Construct", "line") == "New transmission line"
    assert work_type_label("SAV: MCINTOSH - PURRYSBURG 230KV REACTORS", "line") == "Equipment upgrade (reactors)"
    assert work_type_label("MITCHELL - NORTH TIFTON 230KV RECONDUCTOR", "line") == "Line reconductor"
    assert work_type_label("Okatie-Bluffton 115 kV: Rebuild", "line") == "Line rebuild"


def test_fallback_validation():
    assert validate_fallback("Cameron Jct – Cameron – St Matthews 46 kV Rebuild", ["Cameron Jct", "St Matthews"])
    assert not validate_fallback("Cameron Jct – Cameron – St Matthews 46 kV Rebuild", ["Orangeburg"])
