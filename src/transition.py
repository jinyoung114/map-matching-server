from __future__ import annotations

import math

import numpy as np
from geopy.distance import geodesic

from src.utils import angle_diff


def trans_prob_adaptive(rn, n1, n2, g1, g2, dt, obs_heading, curved=False, complex_zone=False):
    u = int(n1["Node_ID"])
    v = int(n2["Node_ID"])

    rd = rn.sp_len(u, v)
    if rd is None:
        return 1e-12

    gd = geodesic(g1, g2).meters

    ratio_limit = 4.8 if (curved or complex_zone) else 3.2
    diff_limit = 65.0 if (curved or complex_zone) else 35.0
    near_stop_rd_limit = 65.0 if (curved or complex_zone) else 40.0

    if gd > 5.0:
        if (rd / max(gd, 1.0)) > ratio_limit and (rd - gd) > diff_limit:
            return 1e-12
    else:
        if rd > near_stop_rd_limit:
            return 1e-12

    if dt and dt > 0:
        rs = rd / dt
        os_ = gd / dt
        rs_limit = 52.0 if (curved or complex_zone) else 45.0
        if rs > rs_limit:
            return 1e-12
        if os_ < 15.0:
            limit = max(28.0 if (curved or complex_zone) else 25.0, 2.8 * max(os_, 1.0))
            if rs > limit:
                return 1e-12

    head_term = 1.0
    try:
        rh = rn.edge_heading(u, v)
    except Exception:
        rh = np.nan

    if not np.isnan(obs_heading) and not np.isnan(rh):
        diff = abs(angle_diff(rh, obs_heading))
        hard_block = 170 if (curved or complex_zone) else 150
        if diff >= hard_block:
            return 1e-12
        elif diff >= 110:
            head_term = math.exp(-((diff - 110) / 18.0)) * 0.35
        elif diff >= 70:
            head_term = math.exp(-((diff - 70) / 20.0)) * 0.7
        else:
            head_term = math.exp(-(diff / 40.0))

    dist_scale = 60.0 if (curved or complex_zone) else 40.0
    dist_term = math.exp(-abs(rd - gd) / dist_scale)

    degree_bonus = 1.08 if max(rn.node_complexity(u), rn.node_complexity(v)) >= 4 else 1.0

    return max(dist_term * head_term * degree_bonus, 1e-12)


def continuity_factor(rn, committed_last, cand_node_id):
    if committed_last is None:
        return 1.0
    rd = rn.sp_len(int(committed_last), int(cand_node_id))
    if rd is None:
        return 0.7
    if rd <= 20:
        return 1.08
    if rd <= 60:
        return 1.0
    if rd <= 120:
        return 0.9
    return 0.78


def trans_prob_edge(
    rn,
    a,
    b,
    g1,
    g2,
    dt,
    curved=False,
    complex_zone=False,
):
    """
    Edge-based HMM transition probability.

    a, b: edge candidate dictionaries
    g1, g2: GPS coordinates (lat, lon)
    dt: elapsed time in seconds
    """
    import math
    from geopy.distance import geodesic

    MIN_PROB = 1e-12

    # 1. Road travel distance between projected positions
    rd = rn.edge_travel_distance(a, b)

    if rd is None or not math.isfinite(rd):
        return MIN_PROB

    # 2. Straight-line GPS displacement
    gd = geodesic(g1, g2).meters

    # 3. Reject unreasonable detours
    ratio_limit = 4.8 if (curved or complex_zone) else 3.2
    diff_limit = 65.0 if (curved or complex_zone) else 35.0

    if gd > 5.0:
        if rd / gd > ratio_limit and rd - gd > diff_limit:
            return MIN_PROB
    else:
        stop_limit = 65.0 if (curved or complex_zone) else 40.0

        if rd > stop_limit:
            return MIN_PROB

    # 4. Reject physically implausible travel speeds
    if dt is not None and dt > 0:
        road_speed = rd / dt

        if road_speed > 45.0:
            return MIN_PROB

    # 5. Transition probability
    beta = 60.0 if (curved or complex_zone) else 40.0

    distance_difference = abs(rd - gd)

    probability = math.exp(
        -distance_difference / beta
    )

    return max(probability, MIN_PROB)