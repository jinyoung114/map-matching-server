from pathlib import Path

import folium
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent

RESULT_CSV = (
    BASE_DIR
    / "data"
    / "replay_mapmatch_results.csv"
)

OUTPUT_HTML = (
    BASE_DIR
    / "data"
    / "replay_mapmatch_visualization.html"
)


def valid_coordinates(df, lat_col, lon_col):
    valid = df.dropna(
        subset=[lat_col, lon_col]
    ).copy()

    valid[lat_col] = pd.to_numeric(
        valid[lat_col],
        errors="coerce",
    )
    valid[lon_col] = pd.to_numeric(
        valid[lon_col],
        errors="coerce",
    )

    return valid.dropna(
        subset=[lat_col, lon_col]
    )


def main():
    df = pd.read_csv(RESULT_CSV)

    raw_df = valid_coordinates(
        df,
        "raw_lat",
        "raw_lon",
    )

    matched_df = valid_coordinates(
        df,
        "matched_lat",
        "matched_lon",
    )

    true_df = valid_coordinates(
        df,
        "true_lat",
        "true_lon",
    )

    if raw_df.empty:
        raise ValueError(
            "시각화할 원본 GPS 좌표가 없습니다."
        )

    center_lat = raw_df["raw_lat"].mean()
    center_lon = raw_df["raw_lon"].mean()

    map_view = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=16,
        control_scale=True,
    )

    # 원본 GPS 경로
    folium.PolyLine(
        raw_df[["raw_lat", "raw_lon"]].values.tolist(),
        tooltip="Raw GPS",
        color="red",
        weight=3,
        opacity=0.7,
    ).add_to(map_view)

    # Synthetic 정답 경로
    if not true_df.empty:
        folium.PolyLine(
            true_df[["true_lat", "true_lon"]].values.tolist(),
            tooltip="Ground truth",
            color="green",
            weight=5,
            opacity=0.8,
        ).add_to(map_view)

    # 맵매칭 결과
    if not matched_df.empty:
        folium.PolyLine(
            matched_df[["matched_lat", "matched_lon"]].values.tolist(),
            tooltip="Matched nodes",
            color="blue",
            weight=4,
            opacity=0.9,
            dash_array="8, 6",
        ).add_to(map_view)

    # 시작점
    start = raw_df.iloc[0]

    folium.Marker(
        location=[
            start["raw_lat"],
            start["raw_lon"],
        ],
        popup="시작점",
        tooltip="Start",
        icon=folium.Icon(
            icon="play",
            prefix="fa",
        ),
    ).add_to(map_view)

    # 종료점
    end = raw_df.iloc[-1]

    folium.Marker(
        location=[
            end["raw_lat"],
            end["raw_lon"],
        ],
        popup="종료점",
        tooltip="End",
        icon=folium.Icon(
            icon="flag-checkered",
            prefix="fa",
        ),
    ).add_to(map_view)

    # skipped 포인트
    skipped_df = raw_df[
        raw_df["status"] == "skipped"
    ]

    for _, row in skipped_df.iterrows():
        folium.CircleMarker(
            location=[
                row["raw_lat"],
                row["raw_lon"],
            ],
            radius=5,
            popup=(
                f"SEQ: {row['seq']}<br>"
                f"Status: {row['status']}<br>"
                f"Quality: {row.get('quality_label')}"
            ),
            tooltip=f"Skipped SEQ {row['seq']}",
            fill=True,
        ).add_to(map_view)

    # 맵매칭 포인트 일부 표시
    for index, row in matched_df.iterrows():
        # 너무 많은 점이 찍히는 것을 막기 위해 10개마다 표시
        if index % 10 != 0:
            continue

        folium.CircleMarker(
            location=[
                row["matched_lat"],
                row["matched_lon"],
            ],
            radius=4,
            popup=(
                f"SEQ: {row['seq']}<br>"
                f"Node: {row['matched_node_id']}<br>"
                f"Distance: "
                f"{row['distance_to_node_m']:.2f} m"
            ),
            tooltip=(
                f"SEQ {row['seq']} / "
                f"Node {row['matched_node_id']}"
            ),
            fill=True,
        ).add_to(map_view)

    folium.LayerControl().add_to(map_view)

    OUTPUT_HTML.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    map_view.save(OUTPUT_HTML)

    print(f"지도 생성 완료: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()