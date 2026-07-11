from __future__ import annotations

import math
from collections import defaultdict

import networkx as nx
import numpy as np
import pandas as pd
from geopy.distance import geodesic
from shapely import wkt
from sklearn.neighbors import BallTree

from src.utils import LRUCache, angle_diff, bearing_deg, is_curve


class RoadNetwork:
    def __init__(self, nodes_csv, edges_csv):
        nd = pd.read_csv(nodes_csv, encoding="utf-8-sig")

        node_id_col = "node_id" if "node_id" in nd.columns else "id"

        self.nodes = nd.rename(
            columns={
                node_id_col: "Node_ID",
                "lat": "Latitude",
                "lon": "Longitude",
            }
        )[["Node_ID", "Latitude", "Longitude"]].copy()

        self.nodes["Node_ID"] = self.nodes["Node_ID"].astype(int)
        self.nodes["Latitude"] = pd.to_numeric(self.nodes["Latitude"], errors="coerce")
        self.nodes["Longitude"] = pd.to_numeric(self.nodes["Longitude"], errors="coerce")
        self.nodes = self.nodes.dropna().reset_index(drop=True)

        self.edges = pd.read_csv(edges_csv, encoding="utf-8-sig")
        from_col = "from" if "from" in self.edges.columns else "u"
        to_col = "to" if "to" in self.edges.columns else "v"

        self.edges = self.edges.rename(
            columns={
                from_col: "from",
                to_col: "to",
            }
        )
        self.G = nx.DiGraph()
        for _, r in self.nodes.iterrows():
            self.G.add_node(
                int(r["Node_ID"]), lat=float(r["Latitude"]), lon=float(r["Longitude"])
            )

        self.edge_geom = {}
        self.node_headings = defaultdict(list)

        geom_col = "geometry" if "geometry" in self.edges.columns else "geometry_wkt"
        len_col = "length" if "length" in self.edges.columns else ("length_m" if "length_m" in self.edges.columns else None)

        for _, r in self.edges.iterrows():
            u = int(r["from"])
            v = int(r["to"])
            w = float(r[len_col]) if len_col and pd.notna(r[len_col]) else None

            geom = None
            if isinstance(r.get(geom_col), str):
                try:
                    geom = wkt.loads(str(r[geom_col]))
                    self.edge_geom[(u, v)] = geom
                except Exception:
                    geom = None

            if w is None:
                if geom is not None:
                    coords = list(geom.coords)
                    total = 0.0
                    for i in range(len(coords) - 1):
                        x1, y1 = coords[i]
                        x2, y2 = coords[i + 1]
                        total += geodesic((y1, x1), (y2, x2)).meters
                    w = total
                elif u in self.G.nodes and v in self.G.nodes:
                    w = geodesic(
                        (self.G.nodes[u]["lat"], self.G.nodes[u]["lon"]),
                        (self.G.nodes[v]["lat"], self.G.nodes[v]["lon"]),
                    ).meters
                else:
                    w = 1.0

            if u in self.G.nodes and v in self.G.nodes:
                self.G.add_edge(u, v, weight=w)
                self.G.add_edge(v, u, weight=w)

                h_uv = bearing_deg(
                    (self.G.nodes[u]["lat"], self.G.nodes[u]["lon"]),
                    (self.G.nodes[v]["lat"], self.G.nodes[v]["lon"]),
                )
                h_vu = bearing_deg(
                    (self.G.nodes[v]["lat"], self.G.nodes[v]["lon"]),
                    (self.G.nodes[u]["lat"], self.G.nodes[u]["lon"]),
                )
                self.node_headings[u].append(h_uv)
                self.node_headings[v].append(h_vu)

        self.tree = BallTree(np.radians(self.nodes[["Latitude", "Longitude"]].values), metric="haversine")
        self.sp_cache = LRUCache()
        self.path_cache = LRUCache()

    def sp_len(self, u, v):
        key = (u, v) if u <= v else (v, u)
        cached = self.sp_cache.get(key)
        if cached is not None:
            return cached

        if not nx.has_path(self.G, u, v):
            self.sp_cache.set(key, None)
            return None

        try:
            rd = nx.shortest_path_length(self.G, u, v, weight="weight")
        except Exception:
            rd = None

        self.sp_cache.set(key, rd)
        return rd

    def shortest_path(self, u, v):
        key = (u, v)
        cached = self.path_cache.get(key)
        if cached is not None:
            return cached
        try:
            sp = nx.shortest_path(self.G, u, v, weight="weight")
        except Exception:
            sp = None
        self.path_cache.set(key, sp)
        return sp

    def edge_heading(self, u, v):
        return bearing_deg(
            (self.G.nodes[u]["lat"], self.G.nodes[u]["lon"]),
            (self.G.nodes[v]["lat"], self.G.nodes[v]["lon"]),
        )

    def node_complexity(self, node_id):
        return self.G.degree(int(node_id))

    def representative_heading_penalty(self, node_id, obs_heading):
        hs = self.node_headings.get(int(node_id), [])
        if not hs or np.isnan(obs_heading):
            return 1.0
        diffs = [abs(angle_diff(h, obs_heading)) for h in hs]
        d = min(diffs)
        if d <= 25:
            return 1.15
        if d <= 45:
            return 1.0
        if d <= 90:
            return math.exp(-(d - 45) / 30.0)
        return 0.35

    def candidates(self, W, i):
        p = W[i]
        prev = W[i - 1] if i > 0 else None
        nxt = W[i + 1] if i < len(W) - 1 else None

        curved = False
        if prev is not None and nxt is not None:
            curved = is_curve((prev.lat, prev.lon), (p.lat, p.lon), (nxt.lat, nxt.lon), thr=28)

        if curved:
            radius = 24
            k = 10
        elif p.speed < 5.0:
            radius = 20
            k = 8
        else:
            radius = 14
            k = 6

        q = np.radians([[p.lat, p.lon]])
        inds = self.tree.query_radius(q, r=radius / 6371000.0, return_distance=True)

        idxs = inds[0][0] if len(inds[0]) > 0 else np.array([])
        dists = inds[1][0] * 6371000.0 if len(inds[1]) > 0 else np.array([])

        if len(idxs) == 0:
            d, idx = self.tree.query(q, k=min(k, len(self.nodes)))
            idxs = idx[0]
            dists = d[0] * 6371000.0

        raw = []
        for dist, idx in zip(dists, idxs):
            row = self.nodes.iloc[int(idx)]
            nid = int(row["Node_ID"])
            head_bonus = self.representative_heading_penalty(nid, p.heading)
            complexity = self.node_complexity(nid)
            score = float(dist) / head_bonus
            if complexity <= 2 and head_bonus < 0.6:
                score *= 1.2
            raw.append({
                "Node_ID": nid,
                "Latitude": float(row["Latitude"]),
                "Longitude": float(row["Longitude"]),
                "Distance": float(dist),
                "_cand_score": score,
                "_head_bonus": head_bonus,
                "_complexity": complexity,
            })

        raw = sorted(raw, key=lambda x: x["_cand_score"])[:k]
        return raw
