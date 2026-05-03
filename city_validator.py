from collections import deque


def build_grid(unlocked, buildings):
    """Return a dict of (x,y) -> building name for all placed buildings."""
    grid = {}
    for b in buildings:
        for dy in range(b["length"]):
            for dx in range(b["width"]):
                grid[(b["x"] + dx, b["y"] + dy)] = b["name"]
    return grid


def check_bounds(buildings, unlocked):
    """Every cell of every building must be in the unlocked set."""
    errors = []
    for b in buildings:
        for dy in range(b["length"]):
            for dx in range(b["width"]):
                cell = (b["x"] + dx, b["y"] + dy)
                if cell not in unlocked:
                    errors.append(f"{b['name']} at ({b['x']},{b['y']}) has cell {cell} outside unlocked area")
    return errors


def check_overlaps(buildings):
    """No two buildings may share a cell."""
    seen = {}
    errors = []
    for b in buildings:
        for dy in range(b["length"]):
            for dx in range(b["width"]):
                cell = (b["x"] + dx, b["y"] + dy)
                if cell in seen:
                    errors.append(f"{b['name']} overlaps {seen[cell]} at {cell}")
                else:
                    seen[cell] = b["name"]
    return errors


def find_townhall(buildings):
    for b in buildings:
        if b["type"] == "main_building":
            return (b["x"], b["y"])
    return None


def road_cells_for(buildings, road_req_filter=None):
    """
    Return the set of cells that border any road-requiring building.
    road_req_filter: if set, only include buildings with that road_req value.
    """
    border = set()
    for b in buildings:
        if road_req_filter is not None and b["road_req"] != road_req_filter:
            continue
        if b["road_req"] == 0:
            continue
        # all cells adjacent (N/S/E/W) to the building footprint
        footprint = set()
        for dy in range(b["length"]):
            for dx in range(b["width"]):
                footprint.add((b["x"] + dx, b["y"] + dy))
        for (cx, cy) in footprint:
            for nx, ny in [(cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)]:
                if (nx, ny) not in footprint:
                    border.add((nx, ny))
    return border


def check_road_connectivity(buildings, roads, unlocked):
    """
    Every building with road_req > 0 must have at least one adjacent road cell
    that connects back to the Town Hall via a continuous road path.
    Roads is a set of (x,y) road cells.
    """
    th = find_townhall(buildings)
    if th is None:
        return ["No Town Hall found — cannot check road connectivity"]

    errors = []

    # seed BFS from all Town Hall footprint cells
    th_building = next((b for b in buildings if b["type"] == "main_building"), None)
    th_cells = set()
    if th_building:
        for dy in range(th_building["length"]):
            for dx in range(th_building["width"]):
                th_cells.add((th_building["x"] + dx, th_building["y"] + dy))
    else:
        th_cells = {th}

    connected_roads = set()
    queue = deque(th_cells)
    connected_roads.update(th_cells)
    while queue:
        cx, cy = queue.popleft()
        for nx, ny in [(cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)]:
            if (nx, ny) in roads and (nx, ny) not in connected_roads:
                connected_roads.add((nx, ny))
                queue.append((nx, ny))

    # Check each road-requiring building
    for b in buildings:
        if b["road_req"] == 0:
            continue
        footprint = set()
        for dy in range(b["length"]):
            for dx in range(b["width"]):
                footprint.add((b["x"] + dx, b["y"] + dy))

        adjacent_connected = False
        for (cx, cy) in footprint:
            for nx, ny in [(cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)]:
                # Must touch an actual road tile, not just the TH footprint
                if (nx, ny) in connected_roads and (nx, ny) not in th_cells:
                    adjacent_connected = True
                    break
            if adjacent_connected:
                break

        if not adjacent_connected:
            errors.append(f"{b['name']} at ({b['x']},{b['y']}) has no connected road path to Town Hall")

    return errors


def validate(city, roads=None):
    """
    Full validation pass. Returns (is_valid, errors_list).
    roads: set of (x,y) road cells. If None, extracted from city buildings of type street.
    """
    unlocked  = city["unlocked"]
    buildings = city["buildings"]

    if roads is None:
        roads = set()   # caller must supply road cells separately if needed

    errors = []
    errors += check_bounds(buildings, unlocked)
    errors += check_overlaps(buildings)
    errors += check_road_connectivity(buildings, roads, unlocked)

    return len(errors) == 0, errors


def print_validation(city, roads=None):
    valid, errors = validate(city, roads)
    if valid:
        print("VALID — all constraints satisfied")
    else:
        print(f"INVALID — {len(errors)} error(s):")
        for e in errors[:20]:
            print(f"  {e}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")


if __name__ == "__main__":
    from city_loader import load_city
    city = load_city()

    # Build road set from the original placed roads in export
    import json
    with open("FullCTHG_Export.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    def get_size(e):
        if "width" in e and "length" in e:
            return e["width"], e["length"]
        try:
            size = e["components"]["AllAge"]["placement"]["size"]
            return size["x"], size["y"]
        except (KeyError, TypeError):
            return 1, 1

    entities = data["CityEntities"]
    roads = set()
    for item in data["CityMapData"].values():
        if item["type"] == "street":
            e = entities.get(item["cityentity_id"])
            w, l = get_size(e) if e else (1, 1)
            for dy in range(l):
                for dx in range(w):
                    roads.add((item["x"] + dx, item["y"] + dy))

    print_validation(city, roads)
