from __future__ import annotations

import math

from src.transition import (
    continuity_factor,
    trans_prob_adaptive,
    trans_prob_edge,
)
from src.utils import emit_prob, is_curve

def viterbi_window(rn, W, committed_last=None):
    cand = [rn.candidates(W, i) for i in range(len(W))]
    vit = []

    first = cand[0]
    complex0 = any(c["_complexity"] >= 4 for c in first)

    for c in first:
        base = emit_prob(c["Distance"]) * c["_head_bonus"]
        base *= continuity_factor(rn, committed_last, c["Node_ID"])
        if complex0:
            base *= 1.03
        c["delta"] = base
        c["psi"] = None
    vit.append(first)

    for t in range(1, len(W)):
        prev = vit[t - 1]
        curr = cand[t]

        local_curved = False
        if 0 < t < len(W) - 1:
            local_curved = is_curve(
                (W[t - 1].lat, W[t - 1].lon),
                (W[t].lat, W[t].lon),
                (W[t + 1].lat, W[t + 1].lon),
                thr=28,
            )

        local_complex = any(c["_complexity"] >= 4 for c in curr)

        for c in curr:
            best = -1.0
            bestp = None

            for p in prev:
                tp = trans_prob_adaptive(
                    rn,
                    p,
                    c,
                    (W[t - 1].lat, W[t - 1].lon),
                    (W[t].lat, W[t].lon),
                    W[t].dt,
                    W[t].heading,
                    curved=local_curved,
                    complex_zone=(local_complex or p["_complexity"] >= 4 or c["_complexity"] >= 4),
                )

                prob = p["delta"] * tp * emit_prob(c["Distance"]) * c["_head_bonus"]
                prob *= continuity_factor(rn, committed_last, c["Node_ID"])

                if prob > best:
                    best = prob
                    bestp = p

            c["delta"] = best
            c["psi"] = bestp

        vit.append(curr)

    last = max(vit[-1], key=lambda x: x["delta"])
    path = [last]
    for _ in range(len(W) - 1, 0, -1):
        path.insert(0, path[0]["psi"])
    return path

def viterbi_window_edge(rn, W):
    """
    Edge-based HMM + Viterbi using log probabilities.

    Returns the optimal sequence of projected road positions.
    """

    if not W:
        return []

    # 1. Generate edge candidates for each GPS point
    cand = [
        rn.edge_candidates(p, k=8)
        for p in W
    ]

    if any(not candidates for candidates in cand):
        raise ValueError("No edge candidates available")

    vit = []

    # 2. Initialize first GPS candidates
    first = cand[0]

    for c in first:
        emission = max(
            emit_prob(c["Distance"]) * c["_head_bonus"],
            1e-300
        )

        c["log_delta"] = math.log(emission)
        c["psi"] = None

    vit.append(first)

    # 3. Viterbi recursion
    for t in range(1, len(W)):

        prev = vit[t - 1]
        curr = cand[t]

        local_curved = False

        if 0 < t < len(W) - 1:
            local_curved = is_curve(
                (W[t - 1].lat, W[t - 1].lon),
                (W[t].lat, W[t].lon),
                (W[t + 1].lat, W[t + 1].lon),
                thr=28,
            )

        for c in curr:

            emission = max(
                emit_prob(c["Distance"]) * c["_head_bonus"],
                1e-300
            )

            log_emission = math.log(emission)

            best_score = -math.inf
            best_prev = None

            for p in prev:

                # Edge-based transition probability
                tp = trans_prob_edge(
                    rn,
                    p,
                    c,
                    (W[t - 1].lat, W[t - 1].lon),
                    (W[t].lat, W[t].lon),
                    W[t].dt,
                    curved=local_curved,
                )

                log_transition = math.log(
                    max(tp, 1e-300)
                )

                score = (
                    p["log_delta"]
                    + log_transition
                    + log_emission
                )

                if score > best_score:
                    best_score = score
                    best_prev = p

            c["log_delta"] = best_score
            c["psi"] = best_prev

        vit.append(curr)

    # 4. Select best final candidate
    last = max(
        vit[-1],
        key=lambda x: x["log_delta"]
    )

    # 5. Backtrack optimal path
    path = [last]

    for _ in range(len(W) - 1):
        previous = path[0]["psi"]

        if previous is None:
            raise RuntimeError("Viterbi backtracking failed")

        path.insert(0, previous)

    return path
