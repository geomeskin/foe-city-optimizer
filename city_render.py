"""
city_render.py - re-render the HTML layout from a saved optimizer result.
No SA re-run needed.

Usage:
    py city_render.py city_result_CTHG.json
    py city_render.py city_result_PMTHS.json
"""
import sys
import os
import json

_DIR = os.path.dirname(os.path.abspath(__file__))

from city_loader import load_city
from city_visualizer import render

if len(sys.argv) < 2:
    print("Usage: py city_render.py <city_result_XXX.json>")
    sys.exit(1)

result_file = sys.argv[1]
with open(result_file, encoding="utf-8") as f:
    data = json.load(f)

city_file = data["city_file"] or None
stem      = data["stem"]
seed      = data["seed"]
placed    = data["placed"]
roads     = set(tuple(r) for r in data["roads"])

city = load_city(city_file) if city_file else load_city()
out  = f"city_layout_{stem}.html" if stem else "city_layout.html"

render(city["unlocked"], placed, roads, out,
       original_roads=data.get("original_roads"), city_tag=stem)

print(f"Rendered: {out}  ({data['road_count']} roads, seed={seed})")
