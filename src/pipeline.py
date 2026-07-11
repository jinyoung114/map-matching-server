from __future__ import annotations

import json
import os
import zipfile
from collections import deque

import pandas as pd

from src.config import (
    COMMIT_SIZE,
    EDGES_CSV,
    GPS_CSV,
    HEADING_DIST_THRESH,
    HEADING_JUMP_THRESH,
    MAD_MULT,
    MAD_WINDOW,
    MIN_MAD,
    NODES_CSV,
    OUT_COMM,
    OUT_GEO,
    OUT_HTML,
    OUT_LOG,
    OUT_SUMM,
    OUT_ZIP,
    SPEED_THRESH,
    WINDOW_SIZE,
)
from src.preprocessing import GPSPoint, OnlinePreprocessor, load_gps_adapted
from src.road_network import RoadNetwork
from src.visualization import build_coords_from_committed, save_geojson, save_map
from src.viterbi import viterbi_window


def ensure_output_dirs():
    for path in [OUT_LOG, OUT_COMM, OUT_GEO, OUT_HTML, OUT_SUMM, OUT_ZIP]:
        os.makedirs(os.path.dirname(path), exist_ok=True)


def main():
    ensure_output_dirs()

    rn = RoadNetwork(NODES_CSV, EDGES_CSV)
    raw = load_gps_adapted(GPS_CSV)

    pre = OnlinePreprocessor(
        speed_thresh=SPEED_THRESH,
        mad_window=MAD_WINDOW,
        mad_mult=MAD_MULT,
        min_mad=MIN_MAD,
        heading_dist_thresh=HEADING_DIST_THRESH,
        heading_jump_thresh=HEADING_JUMP_THRESH,
    )

    clean_buf = deque()
    committed = []
    records = []

    total = len(raw)
    ok = 0
    skipped = 0

    for i, row in raw.iterrows():
        cp = pre.update(
            GPSPoint(
                float(row["Lat"]),
                float(row["Lon"]),
                row["TripData"],
                float(row["HeadingRaw"]) if pd.notna(row["HeadingRaw"]) else float("nan"),
            )
        )

        if cp is None:
            skipped += 1
            records.append({"i": i, "status": "skip"})
            continue

        ok += 1
        clean_buf.append(cp)

        if len(clean_buf) < 3:
            records.append({"i": i, "status": "warming"})
            continue

        W = list(clean_buf)[-WINDOW_SIZE:]
        committed_last = committed[-1] if committed else None
        path = viterbi_window(rn, W, committed_last=committed_last)
        window_nodes = [int(p["Node_ID"]) for p in path]
        cur = window_nodes[-1] if window_nodes else None

        if len(W) >= WINDOW_SIZE:
            for n in window_nodes[:COMMIT_SIZE]:
                if not committed or committed[-1] != n:
                    committed.append(n)

            for _ in range(COMMIT_SIZE):
                if clean_buf:
                    clean_buf.popleft()

        records.append({
            "i": i,
            "status": "ok",
            "current_node": cur,
            "committed_len": len(committed),
        })

    if clean_buf:
        W = list(clean_buf)
        committed_last = committed[-1] if committed else None
        path = viterbi_window(rn, W, committed_last=committed_last)
        for n in [int(p["Node_ID"]) for p in path]:
            if not committed or committed[-1] != n:
                committed.append(n)

    log_df = pd.DataFrame(records)
    log_df.to_csv(OUT_LOG, index=False, encoding="utf-8-sig")

    comm_df = pd.DataFrame({"node_id": committed})
    comm_df.to_csv(OUT_COMM, index=False, encoding="utf-8-sig")

    coords = build_coords_from_committed(rn, committed)
    save_geojson(coords, OUT_GEO)
    save_map(rn, raw, coords, OUT_HTML)

    summary = {
        "raw_points": int(total),
        "accepted_points": int(ok),
        "skipped_points": int(skipped),
        "window_size": int(WINDOW_SIZE),
        "commit_size": int(COMMIT_SIZE),
        "committed_nodes": int(len(committed)),
        "route_coords": int(len(coords)),
        "notes": [
            "heading-aware candidate re-ranking",
            "adaptive transition relaxation for curve/complex zones",
            "continuity bonus using last committed node",
            f"window_size={WINDOW_SIZE}, commit_size={COMMIT_SIZE}",
        ],
    }

    with open(OUT_SUMM, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for f in [OUT_LOG, OUT_COMM, OUT_GEO, OUT_HTML, OUT_SUMM]:
            z.write(f, arcname=os.path.basename(f))

    print("DONE")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
