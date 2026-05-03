import sys
from collections import Counter
from city_loader import load_city
from city_optimizer import optimize, footprint, can_place

export = sys.argv[1] if len(sys.argv) > 1 else None
city = load_city(export) if export else load_city()
placed, roads = optimize(city, anneal_iters=0)

unlocked = city["unlocked"]
occupied = set()
for b in placed:
    occupied.update(footprint(b))
occupied.update(roads)

free = sorted(unlocked - occupied, key=lambda c: (-c[1], c[0]))

by_row = Counter(y for x, y in free)
print(f"\nFree cells by row (bottom rows first, top 15):")
for y in sorted(by_row, reverse=True)[:15]:
    bar = "#" * by_row[y]
    print(f"  y={y:2d}: {by_row[y]:3d}  {bar}")

print(f"\nTotal free: {len(free)} cells\n")
print("Building sizes that fit in free space:")
for w, l in [(1,1),(2,2),(2,3),(3,2),(3,3),(4,2),(2,4),(4,3),(3,4),(4,4)]:
    fits = sum(1 for cx, cy in free if can_place(cx, cy, w, l, unlocked, occupied))
    if fits:
        print(f"  {w}x{l} = {w*l:2d} tiles : {fits} valid placements")
