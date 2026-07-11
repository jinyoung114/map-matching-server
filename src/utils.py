from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np


def bearing_deg(p1, p2):
    lat1, lon1 = np.radians(p1[0]), np.radians(p1[1])
    lat2, lon2 = np.radians(p2[0]), np.radians(p2[1])
    dlon = lon2 - lon1
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    brng = np.degrees(np.arctan2(y, x))
    return (brng + 360) % 360


def angle_diff(a, b):
    return (a - b + 180) % 360 - 180


def emit_prob(distance_m, sigma=35.0):
    return math.exp(-distance_m / sigma)


def is_curve(prev, curr, nxt, thr=28):
    a1 = bearing_deg(prev, curr)
    a2 = bearing_deg(curr, nxt)
    diff = (a2 - a1 + 180) % 360 - 180
    return abs(diff) > thr


class LRUCache:
    def __init__(self, cap=100000):
        self.cap = cap
        self.od = OrderedDict()

    def get(self, k):
        if k not in self.od:
            return None
        self.od.move_to_end(k)
        return self.od[k]

    def set(self, k, v):
        self.od[k] = v
        self.od.move_to_end(k)
        if len(self.od) > self.cap:
            self.od.popitem(last=False)
