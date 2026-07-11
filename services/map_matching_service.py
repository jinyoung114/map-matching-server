# <역할>

# RoadNetwork 한 번 로드
# OnlinePreprocessor 유지
# GPS 한 점 입력
# Sliding Window 버퍼에 저장
# viterbi_window 실행
# 현재 매칭 노드 반환


from src.config import NODES_CSV, EDGES_CSV
from src.road_network import RoadNetwork


class MapMatchingService:
    def __init__(self):
        print("Loading road network...")

        self.road_network = RoadNetwork(
            NODES_CSV,
            EDGES_CSV,
        )

        print("Road network loaded.")

    def health(self):
        return {
            "status": "ok",
            "road_network_loaded": self.road_network is not None,
            "nodes_csv": str(NODES_CSV),
            "edges_csv": str(EDGES_CSV),
        }