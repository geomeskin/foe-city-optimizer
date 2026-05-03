from city_loader import load_city
from city_optimizer import optimize

CELL = 14      # px per grid cell
MARGIN_L = 36  # left margin for y-axis labels
MARGIN_T = 22  # top margin for x-axis labels

COLORS = {
    "main_building":    "#e74c3c",
    "greatbuilding":    "#9b59b6",
    "generic_building": "#3498db",
    "residential":      "#2ecc71",
    "production":       "#f39c12",
    "military":         "#e67e22",
    "tower":            "#1abc9c",
    "culture":          "#f1c40f",
    "decoration":       "#bdc3c7",
    "road":             "#7f8c8d",
    "free":             "#ecf0f1",
    "locked":           "#2c3e50",
}


def render(unlocked, placed, roads, out="city_layout.html", original_roads=None, city_tag=""):
    xs = [x for x, y in unlocked]
    ys = [y for x, y in unlocked]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    th_b = next(b for b in placed if b["type"] == "main_building")
    th_x, th_y = th_b["x"], th_b["y"]

    def px(x): return MARGIN_L + (x - min_x) * CELL
    def py(y): return MARGIN_T + (y - min_y) * CELL

    svg_w = MARGIN_L + (max_x - min_x + 1) * CELL
    svg_h = MARGIN_T + (max_y - min_y + 1) * CELL

    # occupied set for free-cell detection
    occ = set(roads)
    for b in placed:
        for dy in range(b["length"]):
            for dx in range(b["width"]):
                occ.add((b["x"] + dx, b["y"] + dy))

    parts = []

    # 1 — locked cells
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if (x, y) not in unlocked:
                parts.append(
                    f'<rect x="{px(x)}" y="{py(y)}" width="{CELL}" height="{CELL}" '
                    f'fill="{COLORS["locked"]}"/>'
                )

    # 2 — free unlocked cells
    for x, y in unlocked:
        if (x, y) not in occ:
            parts.append(
                f'<rect x="{px(x)}" y="{py(y)}" width="{CELL}" height="{CELL}" '
                f'fill="{COLORS["free"]}" stroke="#ccc" stroke-width="0.2"/>'
            )

    # 3 — road cells
    for rx, ry in roads:
        if (rx, ry) in unlocked:
            parts.append(
                f'<rect x="{px(rx)}" y="{py(ry)}" width="{CELL}" height="{CELL}" '
                f'fill="{COLORS["road"]}"/>'
            )

    # 4 — subtle grid lines every 5 cells (TH-relative)
    for x in range(min_x, max_x + 2):
        if (x - th_x) % 5 == 0:
            parts.append(
                f'<line x1="{px(x)}" y1="{MARGIN_T}" x2="{px(x)}" y2="{svg_h}" '
                f'stroke="#4a5568" stroke-width="0.6"/>'
            )
    for y in range(min_y, max_y + 2):
        if (y - th_y) % 5 == 0:
            parts.append(
                f'<line x1="{MARGIN_L}" y1="{py(y)}" x2="{svg_w}" y2="{py(y)}" '
                f'stroke="#4a5568" stroke-width="0.6"/>'
            )

    # 5 — buildings: single rect + label for tiles >= 4
    for b in placed:
        color = COLORS.get(b["type"], "#95a5a6")
        bw    = b["width"]  * CELL
        bl    = b["length"] * CELL
        bx_px = px(b["x"])
        by_px = py(b["y"])
        name_safe = (b["name"]
                     .replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace('"', "&quot;"))

        parts.append(
            f'<rect class="bldg" x="{bx_px}" y="{by_px}" '
            f'width="{bw}" height="{bl}" '
            f'fill="{color}" stroke="#1a2744" stroke-width="1.5" '
            f'onmouseenter="hover(this)" onmouseleave="unhover()" '
            f'onclick="pick(this)" style="cursor:pointer">'
            f'<title>{name_safe}</title></rect>'
        )

        if b["tiles"] >= 4:
            fs = min(10, max(6, min(b["width"], b["length"]) * CELL // 6))
            max_chars = max(3, bw // max(1, fs - 1))
            label = b["name"][:max_chars]
            label_safe = (label.replace("&", "&amp;")
                               .replace("<", "&lt;")
                               .replace('"', "&quot;"))
            cx = bx_px + bw // 2
            cy = by_px + bl // 2

            # outline trick: stroke rendered before fill via paint-order
            parts.append(
                f'<text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="middle" '
                f'font-size="{fs}" font-family="sans-serif" font-weight="bold" '
                f'fill="#fff" stroke="#000" stroke-width="2.5" paint-order="stroke" '
                f'pointer-events="none">{label_safe}</text>'
            )

    # 6 — axis labels (TH-relative, every 5 cells)
    axis = []
    for x in range(min_x, max_x + 1):
        rel = x - th_x
        if rel % 5 == 0:
            axis.append(
                f'<text x="{px(x) + CELL // 2}" y="{MARGIN_T - 4}" '
                f'text-anchor="middle" font-size="9" fill="#888" '
                f'font-family="sans-serif">{rel}</text>'
            )
    for y in range(min_y, max_y + 1):
        rel = y - th_y
        if rel % 5 == 0:
            axis.append(
                f'<text x="{MARGIN_L - 4}" y="{py(y) + CELL // 2 + 3}" '
                f'text-anchor="end" font-size="9" fill="#888" '
                f'font-family="sans-serif">{rel}</text>'
            )

    # stats
    road_count = len(roads)
    bldg_count = len(placed)
    orig   = original_roads if original_roads is not None else "?"
    freed  = (orig - road_count) if isinstance(orig, int) else "?"

    legend = "".join(
        f'<span style="background:{c};padding:2px 8px;margin:3px;border-radius:3px;'
        f'font-size:11px;color:{"#fff" if c not in ("#f1c40f","#ecf0f1") else "#333"}">'
        f'{k}</span>'
        for k, c in COLORS.items() if k not in ("free", "locked")
    )

    page_title = "FoE Optimized City Layout" + (f" ({city_tag})" if city_tag else "")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{page_title}</title>
<style>
body{{font-family:sans-serif;background:#1a1a2e;color:#eee;padding:20px;margin:0}}
h2{{margin-bottom:4px}}
.stats{{margin:6px 0 10px;font-size:13px;color:#aaa}}
.legend{{margin-bottom:8px;line-height:2}}
#infobar{{
  background:#2c3e50;border:1px solid #4a6278;border-radius:4px;
  padding:7px 14px;margin-bottom:10px;font-size:14px;font-weight:bold;
  min-height:32px;position:sticky;top:8px;z-index:10;
  box-shadow:0 2px 8px rgba(0,0,0,0.4)
}}
.bldg:hover{{filter:brightness(1.2);stroke:#ffe000;stroke-width:2px}}
.bldg.selected{{stroke:#ffe000 !important;stroke-width:3px !important;
  filter:brightness(1.3)}}
</style>
</head>
<body>
<h2>{page_title}</h2>
<div class="stats">
  Buildings: {bldg_count} &nbsp;|&nbsp;
  Road tiles: {road_count} (was {orig}) &nbsp;|&nbsp;
  Tiles freed: {freed}
</div>
<div class="legend">{legend}</div>
<div id="infobar">Hover a building to see its name &nbsp;|&nbsp; Click to pin.</div>
<svg width="{svg_w}" height="{svg_h}" style="border:1px solid #444;display:block">
{''.join(parts)}
{''.join(axis)}
</svg>
<p style="font-size:11px;color:#666;margin-top:8px">
  Axis labels = offset from Town Hall corner (0,0). Grid lines every 5 cells.
  Hover any building (including tiny ones) to see its name above. Click to pin.
</p>
<script>
var sel = null;
var IDLE = 'Hover a building to see its name  |  Click to pin.';
function _name(el) {{ return el.querySelector('title').textContent; }}
function hover(el) {{
  var bar = document.getElementById('infobar');
  bar.textContent = sel ? _name(sel) + '  [pinned]  —  hovering: ' + _name(el) : _name(el);
}}
function unhover() {{
  document.getElementById('infobar').textContent = sel ? _name(sel) + '  [pinned]' : IDLE;
}}
function pick(el) {{
  if (sel) sel.classList.remove('selected');
  if (sel === el) {{
    sel = null;
    document.getElementById('infobar').textContent = IDLE;
    return;
  }}
  el.classList.add('selected');
  sel = el;
  document.getElementById('infobar').textContent = _name(el) + '  [pinned]';
}}
</script>
</body></html>"""

    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved: {out}  ({svg_w}x{svg_h}px)")


if __name__ == "__main__":
    import sys, os, re
    export_file = sys.argv[1] if len(sys.argv) > 1 else None
    city = load_city(export_file) if export_file else load_city()
    placed, roads = optimize(city)
    if export_file:
        stem     = re.sub(r"^Full", "", os.path.basename(export_file).split("_")[0])
        city_tag = os.path.splitext(os.path.basename(export_file))[0]
        out      = f"city_layout_{stem}.html"
    else:
        city_tag = ""
        out = "city_layout.html"
    render(city["unlocked"], placed, roads, out,
           original_roads=city.get("original_roads"), city_tag=city_tag)
