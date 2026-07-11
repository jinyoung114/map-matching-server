from __future__ import annotations

import json

import folium
import numpy as np
from shapely import wkt
from shapely.geometry import LineString, mapping


def build_coords_from_committed(rn, committed):
    coords = []
    for u, v in zip(committed[:-1], committed[1:]):
        sp = rn.shortest_path(int(u), int(v))
        if sp is None or len(sp) < 2:
            continue

        for a, b in zip(sp[:-1], sp[1:]):
            geom = rn.edge_geom.get((a, b)) or rn.edge_geom.get((b, a))
            if geom is None:
                seg = [
                    (rn.G.nodes[a]["lat"], rn.G.nodes[a]["lon"]),
                    (rn.G.nodes[b]["lat"], rn.G.nodes[b]["lon"]),
                ]
            else:
                seg = [(y, x) for (x, y) in list(geom.coords)]

            if coords and coords[-1] == seg[0]:
                coords.extend(seg[1:])
            else:
                coords.extend(seg)
    return coords


def save_geojson(coords, out_geo):
    if len(coords) >= 2:
        line = LineString([(lon, lat) for lat, lon in coords])
        gj = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {"name": "realtime_committed_improved"},
            }],
        }
    else:
        gj = {"type": "FeatureCollection", "features": []}

    with open(out_geo, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False)


def save_map(rn, raw, coords, out_html):
    center = [
        float(np.mean([c[0] for c in coords])) if coords else float(raw["Lat"].mean()),
        float(np.mean([c[1] for c in coords])) if coords else float(raw["Lon"].mean()),
    ]

    m = folium.Map(location=center, zoom_start=14, control_scale=True)

    geom_col = "geometry" if "geometry" in rn.edges.columns else "geometry_wkt"
    for w in rn.edges[geom_col].dropna().astype(str):
        try:
            ln = wkt.loads(w)
            seg = [(y, x) for (x, y) in list(ln.coords)]
            folium.PolyLine(seg, weight=2, opacity=0.16).add_to(m)
        except Exception:
            pass

    folium.PolyLine(
        list(zip(raw["Lat"].astype(float), raw["Lon"].astype(float))),
        weight=3,
        opacity=0.55,
        color="black",
        tooltip="Raw GPS",
    ).add_to(m)

    if coords:
        folium.PolyLine(
            coords,
            weight=6,
            opacity=0.95,
            color="blue",
            tooltip="Realtime committed improved",
        ).add_to(m)
        m.fit_bounds(coords)

    m.save(out_html)
