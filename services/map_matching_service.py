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
    WINDOW_SIZE,
    COMMIT_SIZE
)
from src.preprocessing import GPSPoint, OnlinePreprocessor
from src.road_network import RoadNetwork
from src.viterbi import viterbi_window

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

        self.clean_buffer = deque() #viterbi_window에 전달할 GPS 목록

        self.committed = [] #commit된 노드 저장
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
        # 정상 GPS는 CleanPoint 객체로 반환됨.
        clean_point = self.preprocessor.update(gps_point)
        

        if clean_point is None:
            return {
                "status": "skipped",
                "message": "GPS point rejected by OnlinePreprocessor",
                "bus_id": bus_id,
                "route_id": route_id,
                "clean_buffer_size": len(self.clean_buffer),
            }

        # 전처리를 통과한 GPS를 Viterbi용 Sliding Window 버퍼에 저장
        self.clean_buffer.append(clean_point)
        
        # 최소 GPS 개수 확인(GPS가 3개 미만이면 Viterbi를 실행하지 않고 대기)
        if len(self.clean_buffer) < 3:
            return {
                "status": "warming",
                "message": "Waiting for at least 3 GPS points",
                "bus_id": bus_id,
                "route_id": route_id,
                "clean_buffer_size": len(self.clean_buffer),
                "minimum_points_required": 3,
            }

        # 최근 최대 24개의 GPS사용
        window = list(self.clean_buffer)[-WINDOW_SIZE:]
        
        committed_last = (
            self.committed[-1]
            if self.committed
            else None
        )

        # Viterbi 알고리즘 실행
        path = viterbi_window(
            self.road_network,
            window,
            committed_last=committed_last,
        )

        #후보 딕셔너리에서 노드 번호 추출
        window_nodes = [int(point["Node_ID"]) for point in path]

        #현재 GPS에 해당하는 마지막 매칭 노드
        current_node = window_nodes[-1] if window_nodes else None

        # WINDOW_SIZE가 찼을 때 앞에서 COMMIT_SIZE개 확정
        if len(window) >= WINDOW_SIZE:
            for node in window_nodes[:COMMIT_SIZE]:
                if not self.committed or self.committed[-1] != node:
                    self.committed.append(node)

            for _ in range(COMMIT_SIZE):
                if self.clean_buffer:
                    self.clean_buffer.popleft()        

        print(f"[COMMITTED] {self.committed}")

        # #최근 WINDOW_SIZE 개의 GPS만 유지
        # while len(self.clean_buffer) > WINDOW_SIZE:
        #     self.clean_buffer.popleft()

        return {
            "status": "matched",
            "message": "Viterbi map matching completed",
            "bus_id": bus_id,
            "route_id": route_id,
            "current_node": current_node,
            "window_nodes": window_nodes,
            "committed_node": (
                self.committed[-1]
                if self.committed
                else None
            ),
            "committed_nodes": self.committed.copy(),
            "committed_count": len(self.committed),
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