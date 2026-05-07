"""
city_rank.py - rank every building in a city by its contribution.
Tier S = highest contributors (keep), D = lowest (first to replace).

Usage:
    py city_rank.py Exports/PMTHS_CityExport_20260502_2216.json
    py city_rank.py Exports/CTHG_CityExport_20260502_2215.json
    py city_rank.py Exports/CTHG_CityExport_20260502_2215.json SpaceAgeTitan
"""
import sys
import os
import json
from collections import defaultdict

_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Weights (adjust to taste) ─────────────────────────────────────────────────
WEIGHTS = {
    "combat":    0.40,   # general ATT/DEF %
    "gbg":       0.20,   # guild-raids-specific ATT/DEF %
    "fp":        0.25,   # forge points per day
    "goods":     0.10,   # goods per day
    "happiness": 0.05,   # static happiness provided
}

# -- Tier cutoffs (cumulative percentile from top) ─────────────────────────────
TIER_CUTS = [
    (0.15, "S"),
    (0.40, "A"),
    (0.70, "B"),
    (0.90, "C"),
    (1.00, "D"),
]

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

GOOD_TYPES = frozenset({
    "random_good_of_age", "all_goods_of_age",
    "random_good_of_next_age", "all_goods_of_next_age",
    "random_good_of_previous_age",
})

# ── Load ──────────────────────────────────────────────────────────────────────
export_file = sys.argv[1] if len(sys.argv) > 1 else None
era         = sys.argv[2] if len(sys.argv) > 2 else "SpaceAgeSpaceHub"

if not export_file:
    print("Usage: py city_rank.py <export_file> [era]")
    sys.exit(1)

with open(export_file, encoding="utf-8") as f:
    raw = json.load(f)

entities = raw["CityEntities"]
city_map = raw["CityMapData"]
stem = os.path.basename(export_file).split("_")[0]

# ── Helpers ───────────────────────────────────────────────────────────────────
def _era_value(era_map):
    for key in ("AllAge", era):
        if key in era_map:
            d = era_map[key]
            return d.get("type"), d.get("value", 0)
    for e in reversed(ERA_ORDER):
        if e in era_map:
            d = era_map[e]
            return d.get("type"), d.get("value", 0)
    return None, 0

def _era_comp(entity_id):
    e = entities.get(entity_id, {})
    comp = e.get("components", {})
    return comp.get(era) or comp.get("AllAge") or {}

def get_combat(entity_id):
    """General ATT/DEF % (abilities.boostHints + non-guild_raids components.boosts)."""
    e = entities.get(entity_id, {})
    total = 0.0
    for ability in e.get("abilities", []):
        for bh in (ability.get("boostHints") or []):
            btype, val = _era_value(bh.get("boostHintEraMap", {}))
            if btype in COMBAT_TYPES and val:
                total += val
        for bn in (ability.get("bonuses") or []):
            boost = bn.get("boost", {})
            if isinstance(boost, dict):
                btype, val = _era_value(boost)
                if btype in COMBAT_TYPES and val:
                    total += val
    for b in (_era_comp(entity_id).get("boosts") or {}).get("boosts", []):
        if b.get("type") in COMBAT_TYPES and b.get("targetedFeature") != "guild_raids":
            total += b.get("value", 0)
    return total

def get_gbg(entity_id):
    """Guild-raids-only ATT/DEF %."""
    total = 0.0
    for b in (_era_comp(entity_id).get("boosts") or {}).get("boosts", []):
        if b.get("type") in COMBAT_TYPES and b.get("targetedFeature") == "guild_raids":
            total += b.get("value", 0)
    return total

def get_fp(entity_id):
    prod = _era_comp(entity_id).get("production", {})
    total = 0
    for opt in prod.get("options", []):
        for product in opt.get("products", []):
            if product.get("type") == "resources":
                total += product.get("playerResources", {}).get("resources", {}).get("strategy_points", 0)
    return total

def get_goods(entity_id):
    prod = _era_comp(entity_id).get("production", {})
    total = 0
    for opt in prod.get("options", []):
        for product in opt.get("products", []):
            if product.get("type") == "resources":
                res = product.get("playerResources", {}).get("resources", {})
                total += sum(res.get(k, 0) for k in GOOD_TYPES)
            if product.get("type") == "guildResources":  # guild goods
                res = product.get("guildResources", {}).get("resources", {})
                total += sum(res.get(k, 0) for k in GOOD_TYPES)
    return total

def get_happiness(entity_id):
    hap = _era_comp(entity_id).get("happiness", {})
    return max(0, hap.get("provided", 0))

# ── Collect buildings from city map ───────────────────────────────────────────
from city_loader import load_city
city      = load_city(export_file)
buildings = [b for b in city["buildings"] if b["type"] != "main_building"]

# ── Compute raw outputs per building ─────────────────────────────────────────
rows = []
unscored = []

for b in buildings:
    eid     = b["entity_id"]
    combat  = get_combat(eid)
    gbg     = get_gbg(eid)
    fp      = get_fp(eid)
    goods   = get_goods(eid)
    hap     = get_happiness(eid)
    has_any = any([combat, gbg, fp, goods, hap])

    if not has_any:
        unscored.append(b)
    else:
        rows.append({
            "b":      b,
            "combat": combat,
            "gbg":    gbg,
            "fp":     fp,
            "goods":  goods,
            "hap":    hap,
        })

# ── Normalize each dimension by city max ─────────────────────────────────────
def city_max(key):
    vals = [r[key] for r in rows]
    return max(vals) if vals else 1

maxes = {k: city_max(k) or 1 for k in ("combat", "gbg", "fp", "goods", "hap")}

for r in rows:
    r["score"] = (
        WEIGHTS["combat"]    * r["combat"]  / maxes["combat"]  +
        WEIGHTS["gbg"]       * r["gbg"]     / maxes["gbg"]     +
        WEIGHTS["fp"]        * r["fp"]      / maxes["fp"]      +
        WEIGHTS["goods"]     * r["goods"]   / maxes["goods"]   +
        WEIGHTS["happiness"] * r["hap"]     / maxes["hap"]
    )

rows.sort(key=lambda r: -r["score"])

# ── Assign tiers ──────────────────────────────────────────────────────────────
n = len(rows)
def assign_tier(rank_0based):
    pct = rank_0based / n if n > 1 else 0
    for cutoff, tier in TIER_CUTS:
        if pct < cutoff:
            return tier
    return "D"

for i, r in enumerate(rows):
    r["tier"]  = assign_tier(i)
    r["rank"]  = i + 1

# ── Output ────────────────────────────────────────────────────────────────────
W = 72
print(f"\n{'='*W}")
print(f"  CITY RANKING — {stem}  (era: {era})")
print(f"  Weights: Combat {WEIGHTS['combat']:.0%}  GBG {WEIGHTS['gbg']:.0%}  "
      f"FP {WEIGHTS['fp']:.0%}  Goods {WEIGHTS['goods']:.0%}  Hap {WEIGHTS['happiness']:.0%}")
print(f"  {n} ranked  |  {len(unscored)} unscored (no data in export)")
print(f"{'='*W}")

current_tier = None
for r in rows:
    b = r["b"]
    if r["tier"] != current_tier:
        current_tier = r["tier"]
        print(f"\n-- Tier {current_tier} --")
    combat_s = f"{r['combat']:+.0f}%" if r["combat"] else ""
    gbg_s    = f"{r['gbg']:+.0f}%"   if r["gbg"]    else ""
    fp_s     = f"+{r['fp']}"          if r["fp"]     else ""
    goods_s  = f"+{r['goods']}"       if r["goods"]  else ""
    hap_s    = f"+{r['hap']}"         if r["hap"]    else ""
    score_s  = f"{r['score']:.3f}"
    size_s   = f"{b['width']}x{b['length']}"
    print(f"  [{r['rank']:3d}] {b['name']:<42}  {size_s:<5}  {score_s}  "
          f"{combat_s:>7}  {gbg_s:>6}  {fp_s:>5}  {goods_s:>7}  {hap_s:>8}")

if unscored:
    print(f"\n-- Unscored -- no data in city export ({len(unscored)} buildings) --")
    print(f"  (Great Buildings and buildings whose data lives server-side)")
    for b in sorted(unscored, key=lambda b: -b["tiles"]):
        print(f"  {b['name']:<42}  {b['width']}x{b['length']} ({b['tiles']} tiles)")

print(f"\n{'='*W}\n")
