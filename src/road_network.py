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

    def project_to_road(self, lat, lon, k=8):
        """
        GPS를 주변 도로 구간에 투영하고
        가까운 도로 후보 k개를 반환한다.
        """

        candidates = []

        # 위도·경도 차이를 미터 단위로 근사 변환
        lat_scale = 110574.0
        lon_scale = 111320.0 * math.cos(math.radians(lat))

        for u, v in self.G.edges():

            node_u = self.G.nodes[u]
            node_v = self.G.nodes[v]

            lat1 = node_u["lat"]
            lon1 = node_u["lon"]
            lat2 = node_v["lat"]
            lon2 = node_v["lon"]

            # 도로 시작점을 기준으로 좌표 변환
            dx = (lon2 - lon1) * lon_scale
            dy = (lat2 - lat1) * lat_scale

            px = (lon - lon1) * lon_scale
            py = (lat - lat1) * lat_scale

            length_sq = dx * dx + dy * dy

            if length_sq == 0:
                continue

            # 도로 구간 위에서 가장 가까운 위치 계산
            t = (px * dx + py * dy) / length_sq
            t = max(0.0, min(1.0, t))

            projected_lon = lon1 + t * (lon2 - lon1)
            projected_lat = lat1 + t * (lat2 - lat1)

            # GPS와 투영 위치 사이 거리
            distance = math.hypot(
                (lon - projected_lon) * lon_scale,
                (lat - projected_lat) * lat_scale
            )

            candidates.append({
                "u": int(u),
                "v": int(v),
                "lat": float(projected_lat),
                "lon": float(projected_lon),
                "distance_m": float(distance),
                "fraction": float(t),
            })

        candidates.sort(key=lambda c: c["distance_m"])

        return candidates[:k]


    def edge_candidates(self, p, k=8):
        """
        Generate directed edge candidates for one GPS point.
        Existing node-based candidates() remains unchanged.
        """

        projections = self.project_to_road(
            p.lat, p.lon, k=30
        )

        results = []

        heading = getattr(p, "heading", None)
        speed = getattr(p, "speed", None)

        use_heading = (
            heading is not None
            and math.isfinite(float(heading))
            and speed is not None
            and math.isfinite(float(speed))
            and float(speed) >= 2.0
        )

        for c in projections:
            u = c["u"]
            v = c["v"]

            edge_length = float(self.G[u][v]["weight"])
            fraction = c["fraction"]

            road_heading = self.edge_heading(u, v)

            if use_heading:
                heading_diff = abs(
                    angle_diff(road_heading, float(heading))
                )
                heading_bonus = max(
                    0.1,
                    math.exp(-heading_diff / 45.0)
                )
            else:
                heading_bonus = 1.0

            results.append({
                "edge_u": u,
                "edge_v": v,

                "Latitude": c["lat"],
                "Longitude": c["lon"],
                "Distance": c["distance_m"],

                "fraction": fraction,
                "edge_length_m": edge_length,

                "distance_from_u": edge_length * fraction,
                "distance_to_v": edge_length * (1.0 - fraction),

                "road_heading": road_heading,
                "_head_bonus": heading_bonus,

                "_cand_score": (
                    c["distance_m"] / heading_bonus
                ),
            })

        results.sort(
            key=lambda x: x["_cand_score"]
        )

        return results[:k]

    def edge_travel_distance(self, a, b):
        """
        Calculate forward road distance between two edge candidates.
        """

        u1 = int(a["edge_u"])
        v1 = int(a["edge_v"])
        u2 = int(b["edge_u"])
        v2 = int(b["edge_v"])

        start_offset = float(a["distance_from_u"])
        end_offset = float(b["distance_from_u"])

        # Same directed edge: forward movement
        if u1 == u2 and v1 == v2:
            if end_offset >= start_offset:
                return end_offset - start_offset

        # Finish first edge, follow graph, enter second edge
        middle_distance = self.sp_len(v1, u2)

        if middle_distance is None:
            return None

        return (
            float(a["distance_to_v"])
            + middle_distance
            + end_offset
        )