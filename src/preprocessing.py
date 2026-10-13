from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from geopy.distance import geodesic

from src.utils import angle_diff, bearing_deg


@dataclass
class GPSPoint:
    lat: float
    lon: float
    t: Optional[pd.Timestamp]
    raw_heading: float = np.nan


@dataclass
class CleanPoint:
    lat: float
    lon: float
    t: Optional[pd.Timestamp]
    dt: float
    dist: float
    speed: float
    heading: float


class OnlinePreprocessor:
    def __init__(
        self,
        speed_thresh=45.0,
        mad_window=9,
        mad_mult=8.0,
        min_mad=1.0,
        heading_dist_thresh=2.0,
        heading_jump_thresh=145.0,
    ):
        self.speed_thresh = speed_thresh
        self.mad_window = mad_window
        self.mad_mult = mad_mult
        self.min_mad = min_mad
        self.heading_dist_thresh = heading_dist_thresh
        self.heading_jump_thresh = heading_jump_thresh
        self.buf = deque(maxlen=300)
        self.prev: Optional[GPSPoint] = None

    def update(self, p: GPSPoint):
        if self.prev is None:
            cp = CleanPoint(
                lat=p.lat, lon=p.lon, t=p.t, dt=1.0, dist=0.0, speed=0.0, heading=np.nan
            )
            self.prev = p
            self.buf.append(cp)
            return cp

        dt = 1.0
        if p.t is not None and self.prev.t is not None:
            secs = (p.t - self.prev.t).total_seconds()
            dt = secs if (secs and secs > 0) else 1.0

        dist = geodesic((self.prev.lat, self.prev.lon), (p.lat, p.lon)).meters
        speed = dist / dt
        heading = bearing_deg((self.prev.lat, self.prev.lon), (p.lat, p.lon)) if dist > 0 else np.nan


        if speed > self.speed_thresh:
            print(
                f"[REJECT][SPEED] "
                f"speed={speed:.2f}m/s, "
                f"threshold={self.speed_thresh:.2f}m/s, "
                f"distance={dist:.2f}m, "
                f"dt={dt:.2f}s"
            )
            return None

        if len(self.buf) >= 1 and dist < self.heading_dist_thresh:
            prev_h = self.buf[-1].heading

            if not np.isnan(prev_h) and not np.isnan(heading):
                heading_diff = abs(angle_diff(heading, prev_h))

                if heading_diff > self.heading_jump_thresh:
                    print(
                        f"[REJECT][HEADING] "
                        f"heading={heading:.2f}, "
                        f"previous_heading={prev_h:.2f}, "
                        f"difference={heading_diff:.2f}, "
                        f"threshold={self.heading_jump_thresh:.2f}, "
                        f"distance={dist:.2f}m"
                    )
                    return None
                
        recent = list(self.buf)[-self.mad_window + 1:]
        speeds = [c.speed for c in recent] + [speed]
        med = float(np.median(speeds))
        mad = float(np.median(np.abs(np.array(speeds) - med)))
        mad = max(mad, self.min_mad)

        speed_deviation = abs(speed - med)
        mad_threshold = self.mad_mult * mad

        if speed_deviation > mad_threshold:
            print(
                f"[REJECT][MAD] "
                f"speed={speed:.2f}m/s, "
                f"median={med:.2f}m/s, "
                f"mad={mad:.2f}, "
                f"deviation={speed_deviation:.2f}, "
                f"threshold={mad_threshold:.2f}"
            )
            return None

        cp = CleanPoint(
            lat=p.lat,
            lon=p.lon,
            t=p.t,
            dt=dt,
            dist=dist,
            speed=speed,
            heading=heading,
        )

        self.prev = p
        self.buf.append(cp)

        return cp


def load_gps_adapted(path):
    raw = pd.read_csv(path, encoding="utf-8-sig").copy()

    raw["Lon"] = pd.to_numeric(raw["PosX"], errors="coerce") / 1e6
    raw["Lat"] = pd.to_numeric(raw["PosY"], errors="coerce") / 1e6

    ts_col = "ParsedTime" if "ParsedTime" in raw.columns else ("Timestamp" if "Timestamp" in raw.columns else None)
    if ts_col is not None:
        raw["TripData"] = pd.to_datetime(raw[ts_col], errors="coerce")
    else:
        raw["TripData"] = pd.NaT

    if "Heading" in raw.columns:
        raw["HeadingRaw"] = pd.to_numeric(raw["Heading"], errors="coerce")
    else:
        raw["HeadingRaw"] = np.nan

    raw = raw.dropna(subset=["Lat", "Lon"]).reset_index(drop=True)
    raw = raw[raw["Lat"].between(32, 39) & raw["Lon"].between(124, 132)].copy()
    raw = raw.sort_values("TripData", kind="stable").reset_index(drop=True)
    return raw
