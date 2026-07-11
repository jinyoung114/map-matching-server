from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "data" / "output"

NODES_CSV = DATA_DIR / "road_nodes.csv"
EDGES_CSV = DATA_DIR / "road_edges_bidirectional.csv"
GPS_CSV = DATA_DIR / "synthetic_shuttle_gps_with_outliers.csv"

OUT_LOG = OUTPUT_DIR / "shuttle_realtime_log.csv"
OUT_COMM = OUTPUT_DIR / "shuttle_realtime_committed_nodes.csv"
OUT_GEO = OUTPUT_DIR / "shuttle_realtime_route.geojson"
OUT_HTML = OUTPUT_DIR / "shuttle_realtime_map.html"
OUT_ZIP = OUTPUT_DIR / "shuttle_realtime_bundle.zip"
OUT_SUMM = OUTPUT_DIR / "shuttle_realtime_summary.json"

WINDOW_SIZE = 24
COMMIT_SIZE = 1

SPEED_THRESH = 45.0
MAD_WINDOW = 9
MAD_MULT = 8.0
MIN_MAD = 1.0
HEADING_DIST_THRESH = 2.0
HEADING_JUMP_THRESH = 145.0