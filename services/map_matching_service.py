from collections import deque

import numpy as np
import pandas as pd

from src.config import (
    EDGES_CSV,
    HEADING_DIST_THRESH,
    HEADING_JUMP_THRESH,
    MAD_MULT,
    MAD_WINDOW,
    MIN_MAD,
    NODES_CSV,
    SPEED_THRESH,
    WINDOW_SIZE,
    COMMIT_SIZE,
)
from src.preprocessing import GPSPoint, OnlinePreprocessor
from src.viterbi import viterbi_window_edge


class MapMatchingService:
    def __init__(self, road_network):
        self.road_network = road_network

        self.preprocessor = OnlinePreprocessor(
            speed_thresh=SPEED_THRESH,
            mad_window=MAD_WINDOW,
            mad_mult=MAD_MULT,
            min_mad=MIN_MAD,
            heading_dist_thresh=HEADING_DIST_THRESH,
            heading_jump_thresh=HEADING_JUMP_THRESH,
        )

        self.clean_buffer = deque()

        # Legacy node history for API compatibility
        self.committed = []

        # Actual committed positions on road edges
        self.committed_matches = []

        print("Edge-based MapMatchingService initialized.")

    @staticmethod
    def format_match(candidate):
        if candidate is None:
            return None

        return {
            # Legacy field: destination node of the matched edge
            "node_id": int(candidate["edge_v"]),

            # Actual matched road position
            "lat": float(candidate["Latitude"]),
            "lon": float(candidate["Longitude"]),

            "edge_u": int(candidate["edge_u"]),
            "edge_v": int(candidate["edge_v"]),
            "fraction": float(candidate["fraction"]),

            "distance_to_road_m": float(candidate["Distance"]),

            # Legacy compatibility
            "distance_to_node_m": float(candidate["Distance"]),
        }

    def process_gps(
        self,
        bus_id: str,
        route_id: str,
        lat: float,
        lon: float,
        timestamp: str,
        heading: float | None = None,
    ):
        parsed_timestamp = pd.to_datetime(
            timestamp,
            errors="coerce",
        )

        if pd.isna(parsed_timestamp):
            return {
                "status": "error",
                "message": "Invalid timestamp format",
                "bus_id": bus_id,
                "route_id": route_id,
            }

        gps_point = GPSPoint(
            lat=float(lat),
            lon=float(lon),
            t=parsed_timestamp,
            raw_heading=(
                float(heading)
                if heading is not None
                else np.nan
            ),
        )

        clean_point = self.preprocessor.update(gps_point)

        if clean_point is None:
            return {
                "status": "skipped",
                "message": "GPS point rejected by OnlinePreprocessor",
                "bus_id": bus_id,
                "route_id": route_id,
                "clean_buffer_size": len(self.clean_buffer),
            }

        self.clean_buffer.append(clean_point)

        if len(self.clean_buffer) < 3:
            return {
                "status": "warming",
                "message": "Waiting for at least 3 GPS points",
                "bus_id": bus_id,
                "route_id": route_id,
                "clean_buffer_size": len(self.clean_buffer),
                "minimum_points_required": 3,
            }

        # Sliding Window
        window = list(self.clean_buffer)[-WINDOW_SIZE:]

        # Edge-based HMM + Viterbi
        path = viterbi_window_edge(
            self.road_network,
            window,
        )

        # Legacy node IDs represent edge destination nodes
        window_nodes = [
            int(point["edge_v"])
            for point in path
        ]

        current_match = path[-1] if path else None

        current_node = (
            int(current_match["edge_v"])
            if current_match is not None
            else None
        )

        # Commit oldest matched positions when window is full
        if len(window) >= WINDOW_SIZE:
            for point in path[:COMMIT_SIZE]:
                matched_position = self.format_match(point)

                self.committed_matches.append(
                    matched_position
                )

                node_id = int(point["edge_v"])

                if (
                    not self.committed
                    or self.committed[-1] != node_id
                ):
                    self.committed.append(node_id)

            for _ in range(COMMIT_SIZE):
                if self.clean_buffer:
                    self.clean_buffer.popleft()

        committed_match = (
            self.committed_matches[-1]
            if self.committed_matches
            else None
        )

        heading_value = clean_point.heading

        if heading_value is None or not np.isfinite(heading_value):
            heading_value = None
        else:
            heading_value = float(heading_value)

        return {
            "status": "matched",
            "message": "Edge-based Viterbi map matching completed",

            "bus_id": bus_id,
            "route_id": route_id,

            # Legacy compatibility
            "current_node": current_node,
            "window_nodes": window_nodes,

            # Actual matched position on a road edge
            "matched": self.format_match(current_match),

            "committed_node": (
                self.committed[-1]
                if self.committed
                else None
            ),
            "committed": committed_match,
            "committed_nodes": self.committed.copy(),
            "committed_count": len(self.committed_matches),

            "clean_point": {
                "lat": float(clean_point.lat),
                "lon": float(clean_point.lon),
                "timestamp": (
                    clean_point.t.isoformat()
                    if clean_point.t is not None
                    else None
                ),
                "dt": clean_point.dt,
                "distance": clean_point.dist,
                "speed": clean_point.speed,
                "heading": heading_value,
            },

            "preprocessor_buffer_size": len(
                self.preprocessor.buf
            ),
            "clean_buffer_size": len(self.clean_buffer),
            "viterbi_window_size": len(window),
            "configured_window_size": WINDOW_SIZE,
        }

    def health(self):
        return {
            "status": "ok",
            "road_network_loaded": self.road_network is not None,
            "preprocessor_loaded": self.preprocessor is not None,
            "nodes_csv": str(NODES_CSV),
            "edges_csv": str(EDGES_CSV),
        }