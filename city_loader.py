import json
from collections import defaultdict

EXPORT_FILE = "FullCTHG_Export.json"

ERA_ORDER = [
    "StoneAge","BronzeAge","IronAge","EarlyMiddleAge","HighMiddleAge",
    "LateMiddleAge","ColonialAge","IndustrialAge","ProgressiveEra",
    "ModernEra","PostModernEra","ContemporaryEra","TomorrowEra",
    "FutureEra","ArcticFuture","OceanicFuture","VirtualFuture",
    "SpaceAgeMars","SpaceAgeAsteroidBelt","SpaceAgeVenus",
    "SpaceAgeJupiterMoon","SpaceAgeTitan","SpaceAgeSpaceHub",
]

COMBAT_TYPES = frozenset({
    "att_boost_attacker", "def_boost_attacker", "att_def_boost_attacker",
    "att_boost_defender", "def_boost_defender", "att_def_boost_defender",
})

def _era_value(era_map, era):
    for key in ("AllAge", era):
        if key in era_map:
            d = era_map[key]
            return d.get("type"), d.get("value", 0)
    for e in reversed(ERA_ORDER):
        if e in era_map:
            d = era_map[e]
            return d.get("type"), d.get("value", 0)
    return None, 0

def _era_component(entity, era):
    """Return the best-match components sub-dict for a given era."""
    comp = entity.get("components", {})
    return comp.get(era) or comp.get("AllAge") or {}

def compute_boost_scores(entities, era="SpaceAgeSpaceHub"):
    """Return {entity_id: total_combat_boost_pct} for each entity at the given era.
    Reads from abilities.boostHints (T_ buildings) and components[era].boosts (W_ buildings).
    """
    scores = {}
    for eid, entity in entities.items():
        total = 0.0
        # abilities.boostHints — used by T_ expedition/combat buildings
        for ability in entity.get("abilities", []):
            for bh in (ability.get("boostHints") or []):
                btype, val = _era_value(bh.get("boostHintEraMap", {}), era)
                if btype in COMBAT_TYPES and val:
                    total += val
            for bn in (ability.get("bonuses") or []):
                boost = bn.get("boost", {})
                if isinstance(boost, dict):
                    btype, val = _era_value(boost, era)
                    if btype in COMBAT_TYPES and val:
                        total += val
        # components[era].boosts — used by W_ event buildings (skip guild_raids-only boosts)
        era_comp = _era_component(entity, era)
        for b in (era_comp.get("boosts") or {}).get("boosts", []):
            if b.get("type") in COMBAT_TYPES and b.get("targetedFeature") != "guild_raids":
                total += b.get("value", 0)
        if total > 0:
            scores[eid] = total
    return scores


def get_size(entity):
    if "width" in entity and "length" in entity:
        return entity["width"], entity["length"]
    try:
        size = entity["components"]["AllAge"]["placement"]["size"]
        return size["x"], size["y"]
    except (KeyError, TypeError):
        return None, None


def get_road_req(entity):
    # Standard buildings use requirements.street_connection_level
    req = entity.get("requirements", {})
    if isinstance(req, dict) and req.get("street_connection_level", 0):
        return req["street_connection_level"]
    # Event/special buildings use components.AllAge.streetConnectionRequirement
    try:
        return entity["components"]["AllAge"]["streetConnectionRequirement"]["requiredLevel"]
    except (KeyError, TypeError):
        return 0


def load_city(export_file=EXPORT_FILE):
    with open(export_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    entities   = data["CityEntities"]
    city_map   = data["CityMapData"]
    unlock_raw = data["UnlockedAreas"]

    # --- unlocked cell set ---
    unlocked = set()
    for area in unlock_raw:
        ay = area.get("y", 0)   # missing y defaults to 0 (off-grid, filtered later)
        for y in range(ay, ay + area["length"]):
            for x in range(area["x"], area["x"] + area["width"]):
                unlocked.add((x, y))

    # --- separate roads and buildings ---
    buildings = []
    skipped   = []

    for item in city_map.values():
        bx, by  = item["x"], item.get("y", 0)
        btype   = item["type"]
        eid     = item["cityentity_id"]
        inst_id = item["id"]

        if btype == "street":
            continue                       # roads counted separately below
        if (bx, by) not in unlocked:
            skipped.append(eid)
            continue                       # off-grid, ignore

        entity = entities.get(eid)
        if not entity:
            skipped.append(eid)
            continue

        w, l = get_size(entity)
        if w is None:
            skipped.append(eid)
            continue

        buildings.append({
            "inst_id":  inst_id,           # placed-instance ID (unique)
            "entity_id": eid,              # building type ID
            "name":     entity.get("name", eid),
            "type":     btype,
            "width":    w,
            "length":   l,
            "tiles":    w * l,
            "road_req": get_road_req(entity),  # 0=none, 1=standard, 2=2x2
            "x":        bx,
            "y":        by,
        })

    # --- count original road cells ---
    road_cells = set()
    for item in city_map.values():
        if item["type"] == "street":
            e = entities.get(item["cityentity_id"])
            w, l = get_size(e) if e else (1, 1)
            if w is None:
                w, l = 1, 1
            for dy in range(l):
                for dx in range(w):
                    road_cells.add((item["x"] + dx, item["y"] + dy))

    boost_scores = compute_boost_scores(entities)

    return {
        "unlocked":       unlocked,
        "buildings":      buildings,
        "skipped":        skipped,
        "original_roads": len(road_cells),
        "boost_scores":   boost_scores,
        "entities":       entities,
    }


def print_summary(city):
    unlocked  = city["unlocked"]
    buildings = city["buildings"]

    total_tiles = sum(b["tiles"] for b in buildings)
    need_road   = sum(1 for b in buildings if b["road_req"] > 0)

    from collections import Counter
    type_counts = Counter(b["type"] for b in buildings)
    name_counts = Counter(b["name"] for b in buildings)
    dupes       = {name: cnt for name, cnt in name_counts.items() if cnt > 1}

    print(f"Unlocked cells:      {len(unlocked)}")
    print(f"Buildings:           {len(buildings)}")
    print(f"Building cells:      {total_tiles}")
    print(f"Require road:        {need_road}")
    print(f"No road needed:      {len(buildings) - need_road}")
    print(f"Free cells (no roads): {len(unlocked) - total_tiles}")
    print(f"Skipped (off-grid):  {len(city['skipped'])}")
    print()
    print("Building types:")
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")
    print()
    print(f"Duplicate buildings (candidates for clustering): {len(dupes)}")
    for name, cnt in sorted(dupes.items(), key=lambda x: -x[1])[:10]:
        print(f"  {cnt}x  {name}")


if __name__ == "__main__":
    city = load_city()
    print_summary(city)
