"""
city_multirun.py - run optimizer with multiple random seeds in parallel,
render the best result.

Usage:
    py city_multirun.py <export_file> [num_workers]

    export_file : path to city export JSON
    num_workers : parallel processes to use (default: cpu_count - 1)

Example:
    py city_multirun.py Exports/PMTHS_CityExport_20260502_2216.json 6
"""
import sys
import os
import re
import multiprocessing
from contextlib import redirect_stdout
from io import StringIO

from city_loader import load_city
from city_optimizer import optimize
from city_visualizer import render


SEEDS = [42, 7, 13, 99, 123, 500, 1337, 2024, 9999, 31415, 27182, 11111]
ANNEAL_ITERS = 50000


def _run_one(args):
    export_file, seed, anneal_iters = args
    city = load_city(export_file) if export_file else load_city()
    buf = StringIO()
    with redirect_stdout(buf):
        placed, roads = optimize(city, anneal_iters=anneal_iters, seed=seed)
    return seed, len(roads), placed, roads


if __name__ == "__main__":
    export_file = sys.argv[1] if len(sys.argv) > 1 else None
    max_cores   = multiprocessing.cpu_count()
    num_workers = int(sys.argv[2]) if len(sys.argv) > 2 else max(1, max_cores - 1)
    num_workers = min(num_workers, len(SEEDS))

    seeds = SEEDS[:num_workers]

    print(f"CPU cores available : {max_cores}")
    print(f"Running             : {num_workers} parallel seeds  {seeds}")
    print(f"Iterations each     : {ANNEAL_ITERS:,}")
    print(f"ETA                 : ~10 minutes")
    print("-" * 50)

    args_list = [(export_file, s, ANNEAL_ITERS) for s in seeds]

    results = []
    with multiprocessing.Pool(num_workers) as pool:
        jobs = [pool.apply_async(_run_one, (a,)) for a in args_list]
        for job, seed in zip(jobs, seeds):
            seed_out, roads, placed, roads_set = job.get()
            results.append((seed_out, roads, placed, roads_set))
            marker = "  ** best so far" if roads == min(r[1] for r in results) else ""
            print(f"  seed={seed_out:5d}  done  ->  {roads} roads{marker}")

    results.sort(key=lambda r: r[1])

    print()
    print("Leaderboard:")
    for i, (seed, roads, _, _) in enumerate(results):
        tag = "  ** BEST" if i == 0 else ""
        print(f"  #{i+1}  seed={seed:5d}  {roads} roads{tag}")

    best_seed, best_roads, best_placed, best_roads_set = results[0]

    city = load_city(export_file) if export_file else load_city()
    if export_file:
        stem = re.sub(r"^Full", "", os.path.basename(export_file).split("_")[0])
        out  = f"city_layout_{stem}.html"
    else:
        out = "city_layout.html"

    render(city["unlocked"], best_placed, best_roads_set, out,
           original_roads=city.get("original_roads"), city_tag=stem if export_file else "")
    print(f"\nBest: seed={best_seed}, {best_roads} roads  ->  {out}")
