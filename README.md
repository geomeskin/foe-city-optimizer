# FoE City Optimizer

A simulated annealing optimizer for **Forge of Empires** city layouts. Given your city's export file, it finds a road network using 40–60% fewer road tiles than a typical hand-built city — while placing every building and respecting all game rules.

## Results

| City | Original roads | Optimized | Tiles freed |
|------|---------------|-----------|-------------|
| CTHG (176 buildings) | 297 | **180** | 117 |
| PMTHS (215 buildings) | 317 | **185** | 132 |

All buildings placed. All layouts validated (road connectivity, no overlaps, bounds check).

## How It Works

1. **Premier buildings** (large non-road buildings like the Eternal Market) are pre-placed in the far corners so they're never crowded out.
2. **Road-requiring buildings** (Great Buildings, event buildings) are placed near the Town Hall using a greedy BFS pass. Building set partners (Road to Victory, Iridescent Garden, Serpent accessories) are reserved adjacent to their anchors before roads are routed.
3. **Simulated annealing** (50,000 iterations) moves road buildings around and re-routes roads after each move, accepting slightly worse solutions occasionally to escape local minima.
4. **Full rebuild** fills remaining space with non-road buildings sorted by boost score.

## Features

- Handles irregular unlocked city grids
- Respects building set adjacency constraints (Battlegrounds, Great Elephant, Feathered Serpent Statue, Mughals Embassy sets)
- Parallel multi-seed runner — uses multiple CPU cores to explore more configurations in the same time
- Interactive HTML layout output with TH-relative coordinate grid, hover-to-name, click-to-pin
- Live progress bar during optimization

## Requirements

- Python 3.9+
- No external dependencies (standard library only)

## Usage

**Single run:**
```
py city_optimizer.py Exports\YourCity_Export.json
```

**Render layout to HTML:**
```
py city_visualizer.py Exports\YourCity_Export.json
```
Opens `city_layout_YourCity.html` — hover any building to see its name, click to pin.

**Multi-seed parallel run (recommended):**
```
py city_multirun.py Exports\YourCity_Export.json 6
```
Runs 6 seeds in parallel (~10 min), renders the best result.

## Getting Your City Export

In FoE Helper browser extension: **City** → **Export** → save the JSON file to the `Exports/` folder.

## File Reference

| File | Purpose |
|------|---------|
| `city_loader.py` | Parse FoE city export JSON into grid + building list |
| `city_validator.py` | Validate layout (road connectivity, overlaps, bounds) |
| `city_optimizer.py` | Core SA optimizer |
| `city_visualizer.py` | Interactive HTML renderer |
| `city_multirun.py` | Parallel multi-seed runner |
| `building_sets.json` | Building set definitions (anchor → partners) |
| `ranked_buildings.json` | Building boost scores for placement priority |
| `check_gbs.py` | List all Great Buildings in a city export |
| `check_free.py` | Show free cell distribution in optimized layout |
