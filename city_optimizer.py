import json
import math
import os
import random
import sys
import time
from collections import deque, defaultdict
from city_loader import load_city
from city_validator import validate

_DIR = os.path.dirname(os.path.abspath(__file__))

PREMIER_IDS = frozenset({'W_MultiAge_LTE24A5'})   # Eternal Market - Neon Horizon
PREMIER_TILE_THRESHOLD = 20
_BOOST_FILE = os.path.join(_DIR, "ranked_buildings.json")

def _load_boost_scores():
    try:
        with open(_BOOST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {e["id"]: e["scores"]["balanced"] for e in data if "scores" in e}
    except Exception:
        return {}

BOOST_SCORES = _load_boost_scores()

_SETS_FILE = os.path.join(_DIR, "building_sets.json")

def _load_building_sets():
    try:
        with open(_SETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        return {}

BUILDING_SETS = _load_building_sets()

def is_premier(b):
    return b["road_req"] == 0 and (b["tiles"] >= PREMIER_TILE_THRESHOLD or b["entity_id"] in PREMIER_IDS)


# -----------------------------------------
# GEOMETRY
# -----------------------------------------

def footprint(b):
    return {(b["x"]+dx, b["y"]+dy)
            for dy in range(b["length"])
            for dx in range(b["width"])}


def adjacent_cells(b):
    fp = footprint(b)
    return {(cx+ddx, cy+ddy)
            for cx, cy in fp
            for ddx, ddy in [(1,0),(-1,0),(0,1),(0,-1)]
            if (cx+ddx, cy+ddy) not in fp}


def bfs_order(seeds, passable):
    visited = set(seeds)
    queue   = deque(seeds)
    order   = []
    while queue:
        cx, cy = queue.popleft()
        order.append((cx, cy))
        for nx, ny in [(cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)]:
            if (nx, ny) not in visited and (nx, ny) in passable:
                visited.add((nx, ny))
                queue.append((nx, ny))
    return order


# -----------------------------------------
# PLACEMENT
# -----------------------------------------

def can_place(x, y, w, l, unlocked, occupied):
    for dy in range(l):
        for dx in range(w):
            c = (x+dx, y+dy)
            if c not in unlocked or c in occupied:
                return False
    return True


def do_place(b, x, y, occupied):
    b = dict(b)
    b["x"], b["y"] = x, y
    for dy in range(b["length"]):
        for dx in range(b["width"]):
            occupied.add((x+dx, y+dy))
    return b


def first_fit(b, scan, unlocked, occupied):
    for cx, cy in scan:
        if can_place(cx, cy, b["width"], b["length"], unlocked, occupied):
            return do_place(b, cx, cy, occupied)
    return None


def near_cells(anchor_b, partner_b, unlocked, occupied):
    """Placement origins for partner_b that land it adjacent to anchor_b."""
    adj = adjacent_cells(anchor_b)
    pw, pl = partner_b["width"], partner_b["length"]
    seen, candidates = set(), []
    for ax, ay in sorted(adj):
        for dy in range(-pl + 1, 1):
            for dx in range(-pw + 1, 1):
                cx, cy = ax + dx, ay + dy
                if (cx, cy) not in seen:
                    seen.add((cx, cy))
                    if can_place(cx, cy, pw, pl, unlocked, occupied):
                        candidates.append((cx, cy))
    return candidates


def place_set_buddies(road_placed, buildings, unlocked, occupied, placed):
    """
    After road buildings are placed, immediately place their set partners
    (from building_sets.json) in adjacent cells.
    Returns set of inst_ids placed as buddies (excluded from normal non-road phase).
    """
    already_placed = {b["inst_id"] for b in placed}
    buddy_inst_ids = set()

    for anchor in road_placed:
        partner_eids = BUILDING_SETS.get(anchor["entity_id"])
        if not partner_eids:
            continue
        for peid in partner_eids:
            partners = [b for b in buildings
                        if b["entity_id"] == peid
                        and b["road_req"] == 0
                        and b["inst_id"] not in already_placed
                        and b["inst_id"] not in buddy_inst_ids]
            for partner in partners:
                scan = near_cells(anchor, partner, unlocked, occupied)
                pb = first_fit(partner, scan, unlocked, occupied)
                if pb:
                    placed.append(pb)
                    buddy_inst_ids.add(partner["inst_id"])

    return buddy_inst_ids


# -----------------------------------------
# ROAD ROUTING (single building)
# -----------------------------------------

def connect_to_network(b, road_net, unlocked, occupied, th_fp=frozenset()):
    """
    Extend road_net to reach building b.
    Returns (new_road_cells, already_connected).
    already_connected=True means b is adjacent to an actual road tile (not just TH).
    TH adjacency alone does NOT satisfy road connectivity.
    """
    adj = adjacent_cells(b)
    actual_roads = road_net - th_fp   # exclude TH footprint cells
    if any(a in actual_roads for a in adj):
        return set(), True

    prev    = {}
    visited = set(road_net)
    queue   = deque(road_net)
    found   = None

    while queue and not found:
        cx, cy = queue.popleft()
        for nx, ny in [(cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)]:
            if (nx, ny) in visited:
                continue
            if (nx, ny) not in unlocked:
                continue
            if (nx, ny) in occupied and (nx, ny) not in road_net:
                continue
            prev[(nx, ny)] = (cx, cy)
            visited.add((nx, ny))
            if (nx, ny) in adj:
                found = (nx, ny)
                break
            queue.append((nx, ny))

    if not found:
        return set(), False   # unreachable

    new_roads = set()
    cur = found
    while cur not in road_net:
        new_roads.add(cur)
        cur = prev[cur]
    return new_roads, False


# -----------------------------------------
# ROAD-ROUTE + FULL REBUILD
# -----------------------------------------

UNREACHABLE_PENALTY = 500   # per unroutable road building
NO_FIT_PENALTY      = 500   # per large non-road building that won't fit
BUDDY_SPACE_PENALTY = 250   # per set partner that can't fit adjacent to its anchor

def route_roads(city, road_positioned, th_fp, premier_fp=frozenset()):
    """
    Route roads for fixed road building positions.
    Also penalises any configuration that leaves no room for large non-road buildings.
    Returns (roads_set, penalty_int). Never returns None.
    premier_fp: cells already occupied by pre-placed premier buildings (fixed, not moved by SA).
    """
    unlocked  = city["unlocked"]
    buildings = city["buildings"]
    th_b  = next(b for b in buildings if b["type"] == "main_building")
    th_cx = th_b["x"] + th_b["width"]  / 2
    th_cy = th_b["y"] + th_b["length"] / 2

    occupied = set(th_fp) | set(premier_fp)
    for b in road_positioned:
        occupied.update(footprint(b))

    road_net  = set(th_fp)
    penalties = 0
    for b in sorted(road_positioned, key=lambda b: abs(b["x"]-th_cx)+abs(b["y"]-th_cy)):
        new_roads, already = connect_to_network(b, road_net, unlocked, occupied, th_fp)
        if new_roads:
            road_net.update(new_roads)
            occupied.update(new_roads)
        elif not already:
            penalties += UNREACHABLE_PENALTY

    # Penalise configurations where large non-road buildings can't fit
    roads = road_net - th_fp
    full_occ = occupied | roads
    free = unlocked - full_occ
    large_nonroad = sorted(
        [b for b in buildings if b["road_req"] == 0 and b["tiles"] >= 16 and not is_premier(b)],
        key=lambda b: -b["tiles"]
    )
    for b in large_nonroad:
        fits = any(
            can_place(cx, cy, b["width"], b["length"], unlocked, full_occ)
            for (cx, cy) in free
        )
        if not fits:
            penalties += NO_FIT_PENALTY

    # Penalise set anchors whose adjacent area can't fit all their partners.
    # This steers SA away from packing road buildings so tightly around an anchor
    # that Road to Victory / Iridescent Garden etc. have nowhere to go.
    for anchor in road_positioned:
        partner_eids = BUILDING_SETS.get(anchor["entity_id"])
        if not partner_eids:
            continue
        for peid in partner_eids:
            partner = next(
                (b for b in buildings if b["entity_id"] == peid and b["road_req"] == 0),
                None
            )
            if partner is None:
                continue
            needed    = sum(1 for b in buildings if b["entity_id"] == peid and b["road_req"] == 0)
            available = len(near_cells(anchor, partner, unlocked, full_occ))
            shortfall = max(0, needed - available)
            penalties += shortfall * BUDDY_SPACE_PENALTY

    return roads, penalties


def full_rebuild(city, road_positioned, premier_positioned=None):
    """
    Given fixed positions for road-requiring buildings (and optionally pre-placed premiers):
      1. Place set buddies adjacent to road anchors (before routing so roads avoid them).
      2. Route roads from TH to each road building.
      3. Fill remaining space with non-road, non-premier buildings (sorted by boost score).
    Returns (placed, roads) or None if any road building is unreachable.
    """
    if premier_positioned is None:
        premier_positioned = []

    unlocked  = city["unlocked"]
    buildings = city["buildings"]
    th_b  = next(b for b in buildings if b["type"] == "main_building")
    th_fp = footprint(th_b)
    th_cx = th_b["x"] + th_b["width"]  / 2
    th_cy = th_b["y"] + th_b["length"] / 2

    occupied = set(th_fp)
    for b in premier_positioned:
        occupied.update(footprint(b))
    for b in road_positioned:
        occupied.update(footprint(b))

    placed = [dict(th_b)] + [dict(b) for b in premier_positioned] + [dict(b) for b in road_positioned]

    # Place set buddies BEFORE routing so roads route around them
    buddy_ids = place_set_buddies(road_positioned, buildings, unlocked, occupied, placed)

    road_net = set(th_fp)
    for b in sorted(road_positioned, key=lambda b: abs(b["x"]-th_cx)+abs(b["y"]-th_cy)):
        new_roads, already = connect_to_network(b, road_net, unlocked, occupied, th_fp)
        if new_roads:
            road_net.update(new_roads)
            occupied.update(new_roads)
        elif not already:
            return None   # building is genuinely unreachable

    roads = road_net - th_fp

    other_bldgs = sorted(
        [b for b in buildings
         if b["road_req"] == 0 and not is_premier(b) and b["inst_id"] not in buddy_ids],
        key=lambda b: (-b["tiles"], -BOOST_SCORES.get(b["entity_id"], 0), b["entity_id"])
    )
    rowmajor = sorted(unlocked, key=lambda c: (c[1], c[0]))

    failed = []
    for b in other_bldgs:
        pb = first_fit(b, rowmajor, unlocked, occupied)
        if pb:
            placed.append(pb)
        else:
            failed.append(f"{b['name']} ({b['width']}x{b['length']})")
    if failed:
        print(f"  full_rebuild failed to place: {failed}")

    return placed, roads


# -----------------------------------------
# SCORING
# -----------------------------------------

def clustering_score(placed):
    groups = defaultdict(list)
    for b in placed:
        groups[b["entity_id"]].append((b["x"], b["y"]))
    total = 0
    for pos in groups.values():
        if len(pos) < 2:
            continue
        for i in range(len(pos)):
            for j in range(i+1, len(pos)):
                total += abs(pos[i][0]-pos[j][0]) + abs(pos[i][1]-pos[j][1])
    return total


# -----------------------------------------
# MUTATION LOOP (simulated annealing)
# -----------------------------------------

def anneal(city, placed_init, roads_init, premier_positioned=None, iterations=50000, temp_start=5.0, temp_end=0.01, seed=42):
    """
    Improve road count by moving road-requiring buildings and re-routing.
    Scores using roads-only (fast). Rebuilds full layout only for the best result.
    premier_positioned: pre-placed buildings whose footprints are fixed (not moved by SA).
    """
    if premier_positioned is None:
        premier_positioned = []

    rng = random.Random(seed)
    unlocked  = city["unlocked"]
    buildings = city["buildings"]
    th_b  = next(b for b in buildings if b["type"] == "main_building")
    th_fp = footprint(th_b)

    premier_fp = frozenset(cell for b in premier_positioned for cell in footprint(b))

    bfs_scan = bfs_order(list(th_fp), unlocked)

    current_road = [dict(b) for b in placed_init
                    if b["road_req"] > 0 and b["type"] != "main_building"]

    def score(roads, penalty):
        return len(roads) + penalty

    cur_roads, cur_pen = route_roads(city, current_road, th_fp, premier_fp)
    cur_score  = score(cur_roads, cur_pen)
    best_road  = [dict(b) for b in current_road]
    best_roads_set = cur_roads
    best_score = cur_score

    alpha = (temp_end / temp_start) ** (1.0 / max(iterations, 1))
    T = temp_start
    accepted = improved = 0

    # Progress bar only when running interactively (not in multirun workers)
    _interactive = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    _BAR_W = 28
    _t0 = time.time()

    def _draw_bar(it):
        pct  = (it + 1) / iterations
        done = int(pct * _BAR_W)
        bar  = "=" * done + (">" if done < _BAR_W else "") + " " * (_BAR_W - done - (1 if done < _BAR_W else 0))
        elapsed = time.time() - _t0
        eta_s   = int(elapsed / (it + 1) * (iterations - it - 1)) if it > 0 else 0
        eta_fmt = f"{eta_s // 60}m{eta_s % 60:02d}s"
        sys.stderr.write(
            f"\r  [{bar}] {pct*100:4.0f}%  {it+1:6,}/{iterations:,}  "
            f"best:{best_score:4d} roads  T={T:.3f}  ETA {eta_fmt}   "
        )
        sys.stderr.flush()

    print(f"Annealing: {iterations} iters, T {temp_start}->{temp_end}, start={best_score} roads")

    for it in range(iterations):
        T *= alpha

        idx = rng.randrange(len(current_road))
        b   = current_road[idx]

        occ = set(th_fp) | set(premier_fp)
        for i, rb in enumerate(current_road):
            if i != idx:
                occ.update(footprint(rb))

        candidates = [
            (cx, cy) for cx, cy in bfs_scan
            if can_place(cx, cy, b["width"], b["length"], unlocked, occ)
               and not (cx == b["x"] and cy == b["y"])
        ]
        if not candidates:
            continue

        near = candidates[:max(1, len(candidates) // 3)]
        pool = near if (rng.random() < 0.8 and near) else candidates
        nx, ny = rng.choice(pool)

        trial_road = [dict(rb) for rb in current_road]
        trial_road[idx]["x"] = nx
        trial_road[idx]["y"] = ny

        new_roads, new_pen = route_roads(city, trial_road, th_fp, premier_fp)
        new_score = score(new_roads, new_pen)
        delta = new_score - cur_score

        if delta <= 0 or rng.random() < math.exp(-delta / T):
            current_road   = trial_road
            cur_score      = new_score
            cur_roads, cur_pen = new_roads, new_pen
            accepted += 1

            if new_score < best_score:
                best_road      = [dict(rb) for rb in current_road]
                best_roads_set = new_roads
                best_score     = new_score
                improved      += 1
                penalty_note = f" +{new_pen//UNREACHABLE_PENALTY}unreachable" if new_pen else ""
                if _interactive:
                    sys.stderr.write("\n")   # preserve bar line before milestone
                    sys.stderr.flush()
                print(f"  [{it:4d}] T={T:.3f}  roads={len(new_roads)}{penalty_note}")

        if _interactive and it % 500 == 0:
            _draw_bar(it)

    if _interactive:
        _draw_bar(iterations - 1)
        sys.stderr.write("\n")
        sys.stderr.flush()

    print(f"Annealing done: {len(best_roads_set)} roads  (accepted={accepted}, improved={improved})")

    # Re-build full layout for the best road configuration found
    result = full_rebuild(city, best_road, premier_positioned)
    if result is None:
        print("Warning: best result infeasible in full_rebuild, returning greedy")
        return placed_init, roads_init
    return result


# -----------------------------------------
# MAIN OPTIMIZER
# -----------------------------------------

def optimize(city, anneal_iters=50000, seed=42):
    unlocked  = city["unlocked"]
    buildings = city["buildings"]

    th_b  = next(b for b in buildings if b["type"] == "main_building")
    th_fp = footprint(th_b)
    th_cx = th_b["x"] + th_b["width"]  / 2
    th_cy = th_b["y"] + th_b["length"] / 2

    occupied = set(th_fp)
    road_net = set(th_fp)
    placed   = [dict(th_b)]
    failed   = []

    bfs_scan = bfs_order(list(th_fp), unlocked)
    rowmajor = sorted(unlocked, key=lambda c: (c[1], c[0]))
    reverse_rowmajor = sorted(unlocked, key=lambda c: (-c[1], -c[0]))

    print("-" * 50)

    # -- Premier buildings: pre-place far from TH (bottom-right first) --
    # This guarantees large/high-value non-road buildings always get placed
    # before road buildings claim space near TH.
    premier_bldgs = sorted(
        [b for b in buildings if is_premier(b)],
        key=lambda b: -b["tiles"]
    )
    premier_positioned = []
    print(f"Pre-placing {len(premier_bldgs)} premier buildings (reverse row-major)...")
    for b in premier_bldgs:
        pb = first_fit(b, reverse_rowmajor, unlocked, occupied)
        if pb:
            placed.append(pb)
            premier_positioned.append(pb)
        else:
            failed.append(b["name"])

    # -- Road-requiring buildings: place near TH, route each immediately --
    # For set anchors: reserve buddy spots before routing so roads route around them.
    # Set anchors get a tile bonus so they're placed early (before dense packing blocks buddy space).
    def _anchor_sort_key(b):
        partner_eids = BUILDING_SETS.get(b["entity_id"]) or []
        buddy_tiles  = sum(
            p["tiles"] for p in buildings
            if p["entity_id"] in partner_eids and p["road_req"] == 0
        )
        return (-(b["tiles"] + buddy_tiles), abs(b["x"] - th_cx) + abs(b["y"] - th_cy))

    road_bldgs = sorted(
        [b for b in buildings if b["road_req"] > 0 and b["type"] != "main_building"],
        key=_anchor_sort_key
    )
    road_placed_greedy = []
    buddy_ids = set()
    print(f"Placing {len(road_bldgs)} road-requiring buildings + routing...")
    for b in road_bldgs:
        placed_ok = False
        partner_eids = BUILDING_SETS.get(b["entity_id"])

        for cx, cy in bfs_scan:
            if not can_place(cx, cy, b["width"], b["length"], unlocked, occupied):
                continue

            fp = {(cx+dx, cy+dy) for dy in range(b["length"]) for dx in range(b["width"])}
            occupied.update(fp)

            # For set anchors: tentatively reserve adjacent buddy spots so roads avoid them
            buddy_tentative = []   # (partner, bx, by)
            reserved_cells = set()
            if partner_eids:
                anchor_shell = {"x": cx, "y": cy, "width": b["width"], "length": b["length"]}
                placed_iids  = {pb["inst_id"] for pb in placed} | buddy_ids
                for peid in partner_eids:
                    avail = [p for p in buildings
                             if p["entity_id"] == peid and p["road_req"] == 0
                             and p["inst_id"] not in placed_iids
                             and p["inst_id"] not in {pt[0]["inst_id"] for pt in buddy_tentative}]
                    for partner in avail:
                        scan = near_cells(anchor_shell, partner, unlocked, occupied | reserved_cells)
                        if scan:
                            bx, by = scan[0]
                            bfp = {(bx+dx, by+dy)
                                   for dy in range(partner["length"])
                                   for dx in range(partner["width"])}
                            buddy_tentative.append((partner, bx, by))
                            reserved_cells |= bfp

            new_roads, already = connect_to_network(
                {"x": cx, "y": cy, "width": b["width"], "length": b["length"]},
                road_net, unlocked, occupied | reserved_cells, th_fp
            )
            if new_roads or already:
                pb = dict(b)
                pb["x"], pb["y"] = cx, cy
                placed.append(pb)
                road_placed_greedy.append(pb)

                # Commit buddy placements
                occupied.update(reserved_cells)
                for partner, bx, by in buddy_tentative:
                    pb2 = dict(partner)
                    pb2["x"], pb2["y"] = bx, by
                    placed.append(pb2)
                    buddy_ids.add(partner["inst_id"])

                if new_roads:
                    road_net.update(new_roads)
                    occupied.update(new_roads)
                placed_ok = True
                break
            else:
                occupied -= fp
                # reserved_cells were only used for the check, not committed

        if not placed_ok:
            failed.append(b["name"])

    if buddy_ids:
        print(f"  Set buddies placed: {len(buddy_ids)}")

    # -- Non-road, non-premier, non-buddy buildings: sorted by boost score descending --
    other_bldgs = sorted(
        [b for b in buildings
         if b["road_req"] == 0 and not is_premier(b) and b["inst_id"] not in buddy_ids],
        key=lambda b: (-BOOST_SCORES.get(b["entity_id"], 0), -b["tiles"], b["entity_id"])
    )
    print(f"Placing {len(other_bldgs)} non-road buildings...")
    for b in other_bldgs:
        pb = first_fit(b, rowmajor, unlocked, occupied)
        if pb:
            placed.append(pb)
        else:
            failed.append(b["name"])

    greedy_roads = road_net - th_fp
    greedy_count = len(greedy_roads)
    print(f"  Greedy: {len(placed)}/{len(buildings)} placed, {greedy_count} road tiles")
    if failed:
        print(f"  Failed: {failed}")

    # -- Mutation loop --
    if anneal_iters > 0:
        placed, roads = anneal(city, placed, greedy_roads, premier_positioned=premier_positioned, iterations=anneal_iters, seed=seed)
    else:
        roads = greedy_roads

    # -- Final report --
    original_roads = city.get("original_roads", "?")
    reduction = (original_roads - len(roads)) if isinstance(original_roads, int) else "?"
    print("-" * 50)
    print(f"  Placed     : {len(placed)} / {len(buildings)}")
    print(f"  Road tiles : {len(roads)}  (greedy: {greedy_count}, original: {original_roads})")
    print(f"  Reduction  : {reduction} tiles freed")
    print(f"  Cluster    : {clustering_score(placed)} (lower = better)")

    print("Validating...")
    opt_city = {"unlocked": unlocked, "buildings": placed}
    valid, errors = validate(opt_city, roads)
    if valid:
        print("  VALID")
    else:
        print(f"  INVALID - {len(errors)} error(s)")
        for e in errors[:10]:
            print(f"    {e}")

    print("-" * 50)
    free = len(unlocked) - sum(b["tiles"] for b in placed) - len(roads)
    print(f"Free cells: {free}")

    return placed, roads


if __name__ == "__main__":
    import sys
    export_file = sys.argv[1] if len(sys.argv) > 1 else None
    city = load_city(export_file) if export_file else load_city()
    placed, roads = optimize(city)
