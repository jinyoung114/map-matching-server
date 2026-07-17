# <역할>

# RoadNetwork 한 번 로드
# OnlinePreprocessor 유지
# GPS 한 점 입력
# Sliding Window 버퍼에 저장
# viterbi_window 실행
# 현재 매칭 노드 반환


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
)
from src.preprocessing import GPSPoint, OnlinePreprocessor
from src.road_network import RoadNetwork


class MapMatchingService:
    def __init__(self):
        print("Loading road network...")

        self.road_network = RoadNetwork(
            NODES_CSV,
            EDGES_CSV,
        )

        print("Road network loaded.")

        print("Initializing OnlinePreprocessor...")

        self.preprocessor = OnlinePreprocessor(
            speed_thresh=SPEED_THRESH,
            mad_window=MAD_WINDOW,
            mad_mult=MAD_MULT,
            min_mad=MIN_MAD,
            heading_dist_thresh=HEADING_DIST_THRESH,
            heading_jump_thresh=HEADING_JUMP_THRESH,
        )

        self.clean_buffer = deque()

        print("OnlinePreprocessor initialized.")

    def process_gps(
        self,
        bus_id: str,
        route_id: str,
        lat: float,
        lon: float,
        timestamp: str,
        heading: float | None = None,
    ):
        parsed_timestamp = pd.to_datetime(timestamp, errors="coerce")

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
            raw_heading=float(heading) if heading is not None else np.nan,
        )
        #전처리 조건에 걸린 GPS는 none이 반환됨. (이전 GPS와 너무 멀리 떨어져있거나, 속도, heading이 이상치인 경우)
        #정상 GPS는 clean_point에 저장됨. clean_point는 GPSPoint 객체임.
        clean_point = self.preprocessor.update(gps_point)

        if clean_point is None:
            return {
                "status": "skipped",
                "message": "GPS point rejected by OnlinePreprocessor",
                "bus_id": bus_id,
                "route_id": route_id,
            }

        return {
            "status": "accepted",
            "message": "GPS point accepted by OnlinePreprocessor",
            "bus_id": bus_id,
            "route_id": route_id,
            "clean_point": {
                "lat": clean_point.lat,
                "lon": clean_point.lon,
                "timestamp": (
                    clean_point.t.isoformat()
                    if clean_point.t is not None
                    else None
                ),
                "dt": clean_point.dt,
                "distance": clean_point.dist,
                "speed": clean_point.speed,
                "heading": (
                    None
                    if np.isnan(clean_point.heading)
                    else clean_point.heading
                ),
            },
            "preprocessor_buffer_size": len(self.preprocessor.buf),
        }

    def health(self):
        return {
            "status": "ok",
            "road_network_loaded": self.road_network is not None,
            "preprocessor_loaded": self.preprocessor is not None,
            "nodes_csv": str(NODES_CSV),
            "edges_csv": str(EDGES_CSV),
        }