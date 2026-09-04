from pathlib import Path
import time

import pandas as pd
import requests


SERVER_URL = "http://127.0.0.1:8000/mapmatch"

BASE_DIR = Path(__file__).resolve().parent.parent

CSV_PATH = (
    BASE_DIR
    / "data"
    / "synthetic_shuttle_gps_with_outliers.csv"
)

OUTPUT_PATH = (
    BASE_DIR
    / "data"
    / "replay_mapmatch_results.csv"
)

# 실제 3초 재생이면 3.0
# 빠르게 테스트하려면 0.1 또는 0.0
PLAYBACK_INTERVAL_SEC = 0.1


def safe_float(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    df = pd.read_csv(CSV_PATH)

    results = []

    for _, row in df.iterrows():
        payload = {
            "bus_id": str(row["bus_id"]),
            "route_id": str(row["route_id"]),
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "heading": safe_float(row.get("heading_deg")),
            "timestamp": str(row["timestamp"]),
        }

        try:
            response = requests.post(
                SERVER_URL,
                json=payload,
                timeout=10,
            )

            response.raise_for_status()
            result = response.json()

        except requests.RequestException as exc:
            print(
                f"[ERROR] SEQ={row['seq']} "
                f"request failed: {exc}"
            )

            results.append(
                {
                    "seq": int(row["seq"]),
                    "timestamp": row["timestamp"],
                    "raw_lat": float(row["lat"]),
                    "raw_lon": float(row["lon"]),
                    "true_lat": safe_float(row.get("true_lat")),
                    "true_lon": safe_float(row.get("true_lon")),
                    "status": "request_error",
                    "message": str(exc),
                }
            )
            continue

        matched = result.get("matched") or {}
        committed = result.get("committed") or {}
        clean_point = result.get("clean_point") or {}

        output_row = {
            "seq": int(row["seq"]),
            "timestamp": row["timestamp"],
            "bus_id": row["bus_id"],
            "route_id": row["route_id"],

            # CSV 원본 GPS
            "raw_lat": float(row["lat"]),
            "raw_lon": float(row["lon"]),

            # synthetic 데이터의 정답 위치
            "true_lat": safe_float(row.get("true_lat")),
            "true_lon": safe_float(row.get("true_lon")),

            # 처리 결과
            "status": result.get("status"),
            "message": result.get("message"),

            # 현재 추정 노드
            "current_node": result.get("current_node"),
            "matched_node_id": matched.get("node_id"),
            "matched_lat": matched.get("lat"),
            "matched_lon": matched.get("lon"),
            "distance_to_node_m": matched.get(
                "distance_to_node_m"
            ),

            # Commit 결과
            "committed_node": result.get("committed_node"),
            "committed_lat": committed.get("lat"),
            "committed_lon": committed.get("lon"),
            "committed_count": result.get(
                "committed_count"
            ),

            # 전처리 결과
            "clean_lat": clean_point.get("lat"),
            "clean_lon": clean_point.get("lon"),
            "clean_speed_mps": clean_point.get("speed"),
            "clean_heading": clean_point.get("heading"),

            "quality_label": row.get("quality_label"),
        }

        results.append(output_row)

        print(
            f"SEQ={row['seq']} | "
            f"status={result.get('status')} | "
            f"current={result.get('current_node')} | "
            f"committed={result.get('committed_node')} | "
            f"distance={matched.get('distance_to_node_m')}"
        )

        time.sleep(PLAYBACK_INTERVAL_SEC)

    output_df = pd.DataFrame(results)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("=" * 60)
    print(f"결과 저장 완료: {OUTPUT_PATH}")
    print(f"전체 요청 수: {len(output_df)}")
    print(output_df["status"].value_counts(dropna=False))


if __name__ == "__main__":
    main()