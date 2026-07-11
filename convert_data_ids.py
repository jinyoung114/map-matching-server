import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

nodes_path = DATA_DIR / "road_nodes.csv"
edges_path = DATA_DIR / "road_edges_bidirectional.csv"

nodes = pd.read_csv(nodes_path)
edges = pd.read_csv(edges_path)

# 원본 백업
nodes.to_csv(DATA_DIR / "road_nodes_original.csv", index=False, encoding="utf-8-sig")
edges.to_csv(DATA_DIR / "road_edges_bidirectional_original.csv", index=False, encoding="utf-8-sig")

# id 컬럼 확인
if "id" not in nodes.columns:
    raise ValueError("road_nodes.csv에 id 컬럼이 없습니다.")

# N0001 같은 문자열 ID를 1, 2, 3... 정수 ID로 매핑
old_ids = nodes["id"].astype(str).tolist()
id_map = {old_id: idx + 1 for idx, old_id in enumerate(old_ids)}

nodes["id"] = nodes["id"].astype(str).map(id_map)

# edges의 u, v도 같은 방식으로 변환
edges["u"] = edges["u"].astype(str).map(id_map)
edges["v"] = edges["v"].astype(str).map(id_map)

# 혹시 매핑 안 된 값 있는지 확인
if nodes["id"].isna().any():
    raise ValueError("nodes id 변환 중 누락 발생")

if edges["u"].isna().any() or edges["v"].isna().any():
    raise ValueError("edges u/v 변환 중 누락 발생")

nodes["id"] = nodes["id"].astype(int)
edges["u"] = edges["u"].astype(int)
edges["v"] = edges["v"].astype(int)

nodes.to_csv(nodes_path, index=False, encoding="utf-8-sig")
edges.to_csv(edges_path, index=False, encoding="utf-8-sig")

print("CSV ID 변환 완료")
print(f"nodes: {len(nodes)}개")
print(f"edges: {len(edges)}개")