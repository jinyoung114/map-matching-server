from __future__ import annotations

from src.transition import continuity_factor, trans_prob_adaptive
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
