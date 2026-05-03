from city_loader import load_city

keywords = ["honor", "victory", "road to"]

for label, path in [
    ("CTHG",  r"Exports\CTHG_CityExport_20260502_2215.json"),
    ("PMTHS", r"Exports\PMTHS_CityExport_20260502_2216.json"),
]:
    city = load_city(path)
    matches = [b for b in city["buildings"]
               if any(k in b["name"].lower() for k in keywords)]
    if matches:
        print(f"{label}:")
        for b in sorted(matches, key=lambda b: b["name"]):
            print(f"  {b['tiles']:3d}t  {b['width']}x{b['length']}  "
                  f"road_req={b['road_req']}  {b['name']}  [{b['entity_id']}]")
        print()
