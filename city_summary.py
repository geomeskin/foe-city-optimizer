"""
city_summary.py - city overview: ATT/DEF boosts, FP, space efficiency.

Reads boostHints and bonuses from CityEntities — covers ALL building types
including event buildings (W_, A_, T_ prefixes).

Usage:
    py city_summary.py Exports/CTHG_CityExport_20260502_2215.json
    py city_summary.py Exports/PMTHS_CityExport_20260502_2216.json
    py city_summary.py Exports/CTHG_CityExport_20260502_2215.json SpaceAgeTitan

era defaults to SpaceAgeSpaceHub (latest). Override with 2nd arg if needed.
"""
import sys
import json
import os
from collections import defaultdict

_DIR = os.path.dirname(os.path.abspath(__file__))

from city_loader import load_city
from city_optimizer import BUILDING_SETS

export_file = sys.argv[1] if len(sys.argv) > 1 else None
era         = sys.argv[2] if len(sys.argv) > 2 else "SpaceAgeSpaceHub"

city      = load_city(export_file)
buildings = city["buildings"]

with open(export_file, encoding="utf-8") as f:
    raw = json.load(f)
entities = raw.get("CityEntities", {})

stem = os.path.basename(export_file).split("_")[0] if export_file else "City"
W = 66
print(f"\n{'='*W}")
print(f"  CITY SUMMARY — {stem}  (era: {era})")
print(f"{'='*W}")

# ── Era helpers ───────────────────────────────────────────────────────────────
ERA_ORDER = [
    "StoneAge","BronzeAge","IronAge","EarlyMiddleAge","HighMiddleAge",
    "LateMiddleAge","ColonialAge","IndustrialAge","ProgressiveEra",
    "ModernEra","PostModernEra","ContemporaryEra","TomorrowEra",
    "FutureEra","ArcticFuture","OceanicFuture","VirtualFuture",
    "SpaceAgeMars","SpaceAgeAsteroidBelt","SpaceAgeVenus",
    "SpaceAgeJupiterMoon","SpaceAgeTitan","SpaceAgeSpaceHub",
]

def era_value(era_map):
    """Return (boost_type, value) for the player's era from a boost era-map dict."""
    for key in ("AllAge", era):
        if key in era_map:
            d = era_map[key]
            btype = d.get("type")
            val   = d.get("value", 0)
            return btype, val
    # fall back to latest era present
    for e in reversed(ERA_ORDER):
        if e in era_map:
            d = era_map[e]
            return d.get("type"), d.get("value", 0)
    return None, 0

# ── Boost extraction ──────────────────────────────────────────────────────────
COMBAT_TYPES = {
    "att_boost_attacker",
    "def_boost_attacker",
    "att_def_boost_attacker",
    "att_boost_defender",
    "def_boost_defender",
    "att_def_boost_defender",
}

BOOST_LABEL = {
    "att_boost_attacker":     "ATK-ATT",
    "def_boost_attacker":     "ATK-DEF",
    "att_def_boost_attacker": "ATK-A+D",
    "att_boost_defender":     "DEF-ATT",
    "def_boost_defender":     "DEF-DEF",
    "att_def_boost_defender": "DEF-A+D",
}

def _era_comp(entity_id):
    """Return the components sub-dict for the player's era (or AllAge fallback)."""
    e = entities.get(entity_id, {})
    comp = e.get("components", {})
    return comp.get(era) or comp.get("AllAge") or {}

def get_boosts(entity_id, target="all"):
    """Return {boost_type: total_value} for one entity.
    target="all"         → general city combat (abilities.boostHints + components boosts with targetedFeature!=guild_raids)
    target="guild_raids" → GBG/GE-only boosts (components boosts with targetedFeature==guild_raids)
    """
    e = entities.get(entity_id, {})
    totals = defaultdict(float)
    if target == "all":
        for ability in e.get("abilities", []):
            for bh in (ability.get("boostHints") or []):
                btype, val = era_value(bh.get("boostHintEraMap", {}))
                if btype and val:
                    totals[btype] += val
            for bn in (ability.get("bonuses") or []):
                boost = bn.get("boost", {})
                if isinstance(boost, dict):
                    btype, val = era_value(boost)
                    if btype and val:
                        totals[btype] += val
    for b in (_era_comp(entity_id).get("boosts") or {}).get("boosts", []):
        if b.get("type") in COMBAT_TYPES and b.get("value"):
            if b.get("targetedFeature") == "guild_raids":
                if target == "guild_raids":
                    totals[b["type"]] += b["value"]
            else:
                if target == "all":
                    totals[b["type"]] += b["value"]
    return dict(totals)

def get_production(entity_id):
    """Return production resources from components[era]: {resource_type: amount}.
    Only includes motivated/base resources, not random rewards.
    """
    resources = defaultdict(int)
    for opt in _era_comp(entity_id).get("production", {}).get("options", []):
        for product in opt.get("products", []):
            if product.get("type") != "resources":
                continue
            for rtype, amount in product.get("playerResources", {}).get("resources", {}).items():
                resources[rtype] += amount
        # guild resources (goods contributed to guild bank)
        for product in opt.get("products", []):
            for rtype, amount in product.get("guildResources", {}).get("resources", {}).items():
                resources[f"guild_{rtype}"] += amount
    return dict(resources)

def get_happiness(entity_id):
    """Return static happiness provided by this building at current era."""
    hap = _era_comp(entity_id).get("happiness", {})
    return hap.get("provided", 0)

# ── Basic stats ───────────────────────────────────────────────────────────────
th          = next((b for b in buildings if b["type"] == "main_building"), None)
road_req    = [b for b in buildings if b["road_req"] > 0 and b["type"] != "main_building"]
no_road     = [b for b in buildings if b["road_req"] == 0 and b["type"] != "main_building"]
total_tiles = sum(b["tiles"] for b in buildings)

print(f"\nBASIC STATS")
print(f"  Total buildings  : {len(buildings)}")
print(f"  Road-requiring   : {len(road_req)}")
print(f"  No road needed   : {len(no_road)}")
print(f"  Building tiles   : {total_tiles}  /  {len(city['unlocked'])} unlocked")

# ── Building type breakdown ───────────────────────────────────────────────────
by_type = defaultdict(list)
for b in buildings:
    if b["type"] != "main_building":
        by_type[b["type"]].append(b)

print(f"\nBY TYPE")
for t, blist in sorted(by_type.items(), key=lambda x: -len(x[1])):
    tiles = sum(b["tiles"] for b in blist)
    print(f"  {t:<20s}  {len(blist):3d} bldgs  {tiles:4d} tiles")

# ── ATT/DEF boosts ────────────────────────────────────────────────────────────
boost_by_bldg = []
city_totals   = defaultdict(float)
for b in buildings:
    bd = get_boosts(b["entity_id"])
    combat = {k: v for k, v in bd.items() if k in COMBAT_TYPES}
    if combat:
        boost_by_bldg.append((b, combat))
        for k, v in combat.items():
            city_totals[k] += v

attacker_att = city_totals.get("att_boost_attacker", 0) + city_totals.get("att_def_boost_attacker", 0)
attacker_def = city_totals.get("def_boost_attacker", 0) + city_totals.get("att_def_boost_attacker", 0)
defender_att = city_totals.get("att_boost_defender", 0) + city_totals.get("att_def_boost_defender", 0)
defender_def = city_totals.get("def_boost_defender", 0) + city_totals.get("att_def_boost_defender", 0)

print(f"\nATT/DEF BOOSTS  ({len(boost_by_bldg)} buildings contribute)")
print(f"  Attacking army:  ATT {attacker_att:+.0f}%    DEF {attacker_def:+.0f}%")
print(f"  Defending army:  ATT {defender_att:+.0f}%    DEF {defender_def:+.0f}%")
print(f"\n  Breakdown by type:")
col_w = 28
for btype, label in BOOST_LABEL.items():
    val = city_totals.get(btype, 0)
    if val:
        full = {
            "ATK-ATT": "Attacker ATT boost",
            "ATK-DEF": "Attacker DEF boost",
            "ATK-A+D": "Attacker ATT+DEF boost",
            "DEF-ATT": "Defender ATT boost",
            "DEF-DEF": "Defender DEF boost",
            "DEF-A+D": "Defender ATT+DEF boost",
        }[label]
        print(f"    {full:<28s}  {val:+.0f}%")

def combat_total(bd):
    return sum(bd.values())

boost_by_bldg.sort(key=lambda x: -combat_total(x[1]))
print(f"\n  Top contributors:")
for b, bd in boost_by_bldg[:20]:
    total = combat_total(bd)
    parts = "  ".join(
        f"{BOOST_LABEL[k]} {v:+.0f}%"
        for k, v in sorted(bd.items(), key=lambda x: -x[1])
        if k in BOOST_LABEL
    )
    print(f"  {b['name']:<42s}  {total:+.0f}%  [{parts}]")

# ── FP production ─────────────────────────────────────────────────────────────
fp_sources = []
for b in buildings:
    prod = get_production(b["entity_id"])
    fp = prod.get("strategy_points", 0)
    if fp > 0:
        fp_sources.append((fp, b))
fp_sources.sort(reverse=True, key=lambda x: x[0])

total_fp = sum(fp for fp, _ in fp_sources)
print(f"\nFORGE POINT PRODUCTION  ({len(fp_sources)} buildings)")
print(f"  Total detected   : {total_fp} FP/day")
for fp, b in fp_sources:
    print(f"  {b['name']:<45s}  +{fp} FP")

# ── Set building status ───────────────────────────────────────────────────────
placed_by_eid    = defaultdict(list)
for b in buildings:
    placed_by_eid[b["entity_id"]].append(b)
all_partner_eids = set(eid for eids in BUILDING_SETS.values() for eid in eids)

print(f"\nSET BUILDINGS")
anchor_found = False
for b in buildings:
    if b["entity_id"] in BUILDING_SETS:
        anchor_found = True
        partner_eids = BUILDING_SETS[b["entity_id"]]
        partners_in_city = []
        for peid in partner_eids:
            partners_in_city.extend(placed_by_eid.get(peid, []))
        status = f"{len(partners_in_city)} partner(s) in city" if partners_in_city else "NO PARTNERS IN CITY"
        print(f"  ANCHOR  {b['name']:<40s}  {status}")
    elif b["entity_id"] in all_partner_eids:
        print(f"  PARTNER {b['name']}")
if not anchor_found:
    print("  None found")

# ── All buildings: unified output table ───────────────────────────────────────
GOOD_TYPES = {"random_good_of_age", "all_goods_of_age", "random_good_of_next_age",
              "all_goods_of_next_age", "random_good_of_previous_age"}

def bldg_outputs(b):
    eid    = b["entity_id"]
    bd     = get_boosts(eid, "all")
    bd_gbg = get_boosts(eid, "guild_raids")
    prod   = get_production(eid)
    hap    = get_happiness(eid)
    combat = sum(v for k, v in bd.items() if k in COMBAT_TYPES)
    gbg    = sum(v for k, v in bd_gbg.items() if k in COMBAT_TYPES)
    fp     = prod.get("strategy_points", 0)
    goods  = sum(prod.get(k, 0) for k in GOOD_TYPES)
    medals = prod.get("medals", 0)
    return combat, gbg, fp, goods, medals, hap

bldg_table = [(b, *bldg_outputs(b)) for b in buildings if b["type"] != "main_building"]
# sort: general combat desc, GBG desc, FP desc, tiles desc
bldg_table.sort(key=lambda r: (-r[1], -r[2], -r[3], -r[5], -r[0]["tiles"]))

no_data = [r for r in bldg_table if all(r[i] == 0 for i in range(1, 7))]

print(f"\nALL BUILDINGS — OUTPUTS  ({len(bldg_table)} buildings, {len(no_data)} with no data in export)")
print(f"  {'Name':<42}  {'Size':<7}  {'Combat%':>8}  {'GBG%':>6}  {'FP/d':>5}  {'Goods':>7}  {'Medals':>8}  {'Hap':>8}")
print(f"  {'-'*42}  {'-'*7}  {'-'*8}  {'-'*6}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*8}")
for r in bldg_table:
    b, combat, gbg, fp, goods, medals, hap = r
    size     = f"{b['width']}x{b['length']}"
    combat_s = f"{combat:+.0f}%" if combat else ""
    gbg_s    = f"{gbg:+.0f}%"   if gbg    else ""
    fp_s     = f"+{fp}"          if fp     else ""
    goods_s  = f"+{goods}"       if goods  else ""
    medals_s = f"+{medals}"      if medals else ""
    hap_s    = f"+{hap}"         if hap    else ""
    print(f"  {b['name']:<42}  {size:<7}  {combat_s:>8}  {gbg_s:>6}  {fp_s:>5}  {goods_s:>7}  {medals_s:>8}  {hap_s:>8}")

# ── Largest buildings ─────────────────────────────────────────────────────────
print(f"\nLARGEST BUILDINGS  (top 10 by tiles)")
for b in sorted(buildings, key=lambda b: -b["tiles"])[:10]:
    prod   = get_production(b["entity_id"])
    bd     = get_boosts(b["entity_id"])
    fp     = prod.get("strategy_points", 0)
    combat = sum(v for k, v in bd.items() if k in COMBAT_TYPES)
    extras = []
    if fp:     extras.append(f"+{fp} FP")
    if combat: extras.append(f"{combat:+.0f}% boost")
    extra_str = "  " + "  ".join(extras) if extras else ""
    print(f"  {b['name']:<42s}  {b['width']}x{b['length']} ({b['tiles']} tiles){extra_str}")

# ── Event vs standard breakdown ───────────────────────────────────────────────
event    = [b for b in buildings if b["entity_id"].startswith(("W_", "T_", "A_"))]
standard = [b for b in buildings if not b["entity_id"].startswith(("W_", "T_", "A_"))]

print(f"\nEVENT vs STANDARD")
print(f"  Event/Multi-age  : {len(event):3d}  ({sum(b['tiles'] for b in event)} tiles)")
print(f"  Standard/other   : {len(standard):3d}  ({sum(b['tiles'] for b in standard)} tiles)")

print(f"\n{'='*W}\n")
