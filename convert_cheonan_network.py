import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "천안터미널역"

NODES_PATH = DATA_DIR / "road_nodes.csv"
FORWARD_EDGES_PATH = DATA_DIR / "road_edges_forward.csv"
BIDIRECTIONAL_EDGES_PATH = DATA_DIR / "road_edges_bidirectional.csv"

# =========================
# 1. CSV 읽기
# =========================

nodes = pd.read_csv(NODES_PATH)
edges = pd.read_csv(FORWARD_EDGES_PATH)

print("원본 데이터")
print(f"nodes: {len(nodes)}개")
print(f"forward edges: {len(edges)}개")


# =========================
# 2. 원본 백업
# =========================

nodes.to_csv(
    DATA_DIR / "road_nodes_original.csv",
    index=False,
    encoding="utf-8-sig",
)

edges.to_csv(
    DATA_DIR / "road_edges_forward_original.csv",
    index=False,
    encoding="utf-8-sig",
)


# =========================
# 3. 노드 ID → 정수 변환
# =========================

if "node_id" not in nodes.columns:
    raise ValueError("road_nodes.csv에 node_id 컬럼이 없습니다.")

if "u" not in edges.columns or "v" not in edges.columns:
    raise ValueError("road_edges_forward.csv에 u/v 컬럼이 없습니다.")

old_ids = nodes["node_id"].astype(str).tolist()

id_map = {
    old_id: index + 1
    for index, old_id in enumerate(old_ids)
}

nodes["node_id"] = (
    nodes["node_id"]
    .astype(str)
    .map(id_map)
)

edges["u"] = (
    edges["u"]
    .astype(str)
    .map(id_map)
)

edges["v"] = (
    edges["v"]
    .astype(str)
    .map(id_map)
)


# =========================
# 4. 누락 확인
# =========================

if nodes["node_id"].isna().any():
    raise ValueError("node_id 변환 중 누락이 발생했습니다.")

if edges["u"].isna().any() or edges["v"].isna().any():
    raise ValueError("edge u/v 변환 중 누락이 발생했습니다.")

nodes["node_id"] = nodes["node_id"].astype(int)
edges["u"] = edges["u"].astype(int)
edges["v"] = edges["v"].astype(int)


# =========================
# 5. 역방향 Edge 생성
# =========================

reverse_edges = edges.copy()

reverse_edges["u"] = edges["v"].values
reverse_edges["v"] = edges["u"].values

# edge_id가 있으면 역방향 edge ID 구분
if "edge_id" in reverse_edges.columns:
    reverse_edges["edge_id"] = (
        reverse_edges["edge_id"].astype(str) + "_reverse"
    )


# =========================
# 6. 정방향 + 역방향 합치기
# =========================

bidirectional_edges = pd.concat(
    [edges, reverse_edges],
    ignore_index=True,
)


# =========================
# 7. 저장
# =========================

nodes.to_csv(
    NODES_PATH,
    index=False,
    encoding="utf-8-sig",
)

bidirectional_edges.to_csv(
    BIDIRECTIONAL_EDGES_PATH,
    index=False,
    encoding="utf-8-sig",
)


print()
print("천안터미널 도로 네트워크 변환 완료")
print(f"nodes: {len(nodes)}개")
print(f"forward edges: {len(edges)}개")
print(f"bidirectional edges: {len(bidirectional_edges)}개")
print()
print(f"저장 위치: {BIDIRECTIONAL_EDGES_PATH}")