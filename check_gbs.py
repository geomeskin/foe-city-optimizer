from city_loader import load_city
from city_optimizer import is_premier

for label, path in [
    ("CTHG",  r"Exports\CTHG_CityExport_20260502_2215.json"),
    ("PMTHS", r"Exports\PMTHS_CityExport_20260502_2216.json"),
]:
    city = load_city(path)
    gbs = [b for b in city["buildings"] if b["type"] == "greatbuilding"]
    print(f"=== {label} Great Buildings ({len(gbs)}) ===")
    for b in sorted(gbs, key=lambda b: -b["tiles"]):
        req = "road" if b["road_req"] else "NO-ROAD"
        prem = " PREMIER" if is_premier(b) else ""
        print(f"  {b['tiles']:3d}t  {b['width']}x{b['length']}  [{req}]{prem}  {b['name']}")
    print()
