"""ETA v1: ordered CSV route + RTDB stop order, independent of HMM/Viterbi.

Only the registered outbound traversal is supported. For route_002 this traversal
already includes the return to campus. No automatic next-lap or inbound guessing.
"""
import csv
import math
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

STALE_SECONDS = 30
MAX_SPEED_MPS = 25
MAX_STOP_SNAP_M = 120
KST = timezone(timedelta(hours=9))


def timestamp_seconds(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    # Existing terminal replay files use local Korean timestamps without an offset.
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=KST)
    return stamp.timestamp()


def distance_m(lat1, lon1, lat2, lon2):
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return math.hypot(x, y) * 6371000


def project(lat, lon, segment):
    scale = math.cos(math.radians(lat))
    ax, ay = (segment['lon1'] - lon) * scale, segment['lat1'] - lat
    bx, by = (segment['lon2'] - lon) * scale, segment['lat2'] - lat
    dx, dy = bx - ax, by - ay
    fraction = max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy))) if dx or dy else 0
    return fraction, math.hypot(ax + fraction * dx, ay + fraction * dy) * math.pi / 180 * 6371000


class OrderedRoute:
    def __init__(self, edges_csv, stop_ids, stops):
        with Path(edges_csv).open(encoding='utf-8-sig') as handle:
            rows = [row for row in csv.DictReader(handle)
                    if row.get('direction') == 'forward' and not row.get('edge_id', '').endswith('_reverse')]
        rows.sort(key=lambda row: int(row['seq']))
        if not rows or len({row['seq'] for row in rows}) != len(rows):
            raise ValueError('Ordered forward route is missing or ambiguous')
        self.segments, self.edge_index, self.stops = [], {}, []
        total = 0.0
        for row in rows:
            segment = dict(u=int(row.get('from') or row['u']), v=int(row.get('to') or row['v']),
                           lat1=float(row['from_lat']), lon1=float(row['from_lon']),
                           lat2=float(row['to_lat']), lon2=float(row['to_lon']),
                           length=float(row['length_m']), start=total)
            if not math.isfinite(segment['length']) or segment['length'] <= 0:
                raise ValueError('Invalid route segment length')
            if self.segments:
                previous = self.segments[-1]
                if previous['v'] != segment['u'] or distance_m(previous['lat2'], previous['lon2'], segment['lat1'], segment['lon1']) > 5:
                    raise ValueError('Forward route is not continuous')
            self.segments.append(segment)
            self.edge_index.setdefault((segment['u'], segment['v']), []).append(segment)
            total += segment['length']
        self.length = total
        if isinstance(stop_ids, dict):
            stop_ids = [value for _, value in sorted(stop_ids.items(), key=lambda item: int(item[0]))]
        if not isinstance(stop_ids, list) or len(stop_ids) < 2 or len(set(stop_ids)) != len(stop_ids):
            raise ValueError('Unique ordered stops are required')
        last_progress = -1.0
        for stop_id in stop_ids:
            stop = stops[stop_id]
            lat, lon = float(stop['latitude']), float(stop['longitude'])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError('Invalid stop coordinate')
            candidates = []
            for segment in self.segments:
                fraction, offset = project(lat, lon, segment)
                progress = segment['start'] + fraction * segment['length']
                if progress > last_progress:
                    candidates.append((offset, progress))
            if not candidates:
                raise ValueError('Stop order is incompatible with route')
            offset, progress = min(candidates)
            if offset > MAX_STOP_SNAP_M:
                raise ValueError(f'Stop {stop_id} is {offset:.0f}m away from route')
            self.stops.append(dict(id=stop_id, progress=progress, snap_distance_m=round(offset, 1), lat=lat, lon=lon))
            last_progress = progress

    def progress(self, matched, previous=None):
        u, v = int(matched['edge_u']), int(matched['edge_v'])
        fraction = float(matched['fraction'])
        if not math.isfinite(fraction) or not 0 <= fraction <= 1:
            return None
        candidates = [s['start'] + fraction * s['length'] for s in self.edge_index.get((u, v), [])]
        candidates += [s['start'] + (1 - fraction) * s['length'] for s in self.edge_index.get((v, u), [])]
        if not candidates or (previous is None and len(candidates) > 1):
            return None
        return min(candidates, key=lambda p: abs(p - previous)) if previous is not None else candidates[0]


class EtaService:
    def __init__(self, route, simulation=False, dwell_seconds=0):
        self.route = route
        self.simulation = simulation
        # No measured dwell-time data exists; default to 0 rather than inventing it.
        self.dwell_seconds = dwell_seconds
        self.history = deque(maxlen=30)
        self.high_water = None

    def update(self, matched, timestamp, now=None):
        now = datetime.now(timezone.utc).timestamp() if now is None else now
        base = dict(status='calculating', updated_at=int(now * 1000), expires_at=int((now + STALE_SECONDS) * 1000),
                    direction_id='outbound', simulation=self.simulation, method='ordered_route_recent_speed_v1',
                    dwell_seconds_per_stop=self.dwell_seconds)
        def unavailable(status, reset=True):
            if reset:
                self.history.clear()
            return {**base, 'status': status}
        try:
            measured_at = timestamp_seconds(timestamp)
        except (ValueError, TypeError, OverflowError):
            return unavailable('invalid_timestamp')
        base['gps_timestamp'] = int(measured_at * 1000)
        if not self.simulation and not -5 <= now - measured_at <= STALE_SECONDS:
            return unavailable('stale')
        if not self.simulation:
            base['expires_at'] = int(min(now + STALE_SECONDS, measured_at + STALE_SECONDS) * 1000)
        if float(matched.get('distance_to_road_m', 0)) > 80:
            return unavailable('off_route')
        previous = self.history[-1] if self.history else None
        try:
            progress = self.route.progress(matched, previous[1] if previous else None)
        except (KeyError, ValueError, TypeError):
            return unavailable('off_route')
        if progress is None:
            return unavailable('off_route')
        if previous:
            dt, delta = measured_at - previous[0], progress - previous[1]
            if dt <= 0:
                return unavailable('invalid_timestamp', reset=False)
            if dt > STALE_SECONDS:
                self.history.clear()
            elif abs(delta) / dt > MAX_SPEED_MPS:
                return unavailable('position_jump')
            elif delta < -8:
                return unavailable('direction_unknown')
        # Once progressing on a trip, do not silently treat a reverse traversal or
        # a new lap as outbound. A new /trip/start is required to reset this guard.
        if self.high_water is not None and progress < self.high_water - 35:
            return unavailable('direction_unknown')
        self.high_water = progress if self.high_water is None else max(self.high_water, progress)
        self.history.append((measured_at, progress))
        while len(self.history) > 1 and measured_at - self.history[0][0] > 45:
            self.history.popleft()
        base['progress_m'] = round(progress, 1)
        if len(self.history) < 3 or measured_at - self.history[0][0] < 6:
            return unavailable('calculating', reset=False)
        elapsed = measured_at - self.history[0][0]
        speed = (progress - self.history[0][1]) / elapsed
        recent = [sample for sample in self.history if measured_at - sample[0] <= 12]
        if len(recent) >= 2 and measured_at - recent[0][0] >= 9 and progress - recent[0][1] < 5:
            return unavailable('stopped', reset=False)
        if not 0.5 <= speed <= MAX_SPEED_MPS:
            return unavailable('calculating', reset=False)
        arrivals = {}
        upcoming = [stop for stop in self.route.stops if stop['progress'] >= progress - 25]
        for index, stop in enumerate(upcoming):
            remaining = max(0, stop['progress'] - progress)
            nearby = remaining <= 25 and distance_m(matched['lat'], matched['lon'], stop['lat'], stop['lon']) <= 60
            seconds = math.ceil(remaining / speed + index * self.dwell_seconds)
            arrivals[stop['id']] = dict(status='near_stop' if nearby else 'estimated',
                                       estimated_arrival_at=int(((now if self.simulation else measured_at) + seconds) * 1000),
                                       remaining_distance_m=round(remaining, 1),
                                       stops_remaining=index + 1, eta_seconds=seconds)
        return {**base, 'status': 'estimated' if arrivals else 'completed',
                'speed_mps': round(speed, 2), 'arrivals': arrivals}
