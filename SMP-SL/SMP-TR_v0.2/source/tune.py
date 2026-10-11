#!/usr/bin/env python3
"""Score analysis variants: for each, the best THRS cut (hits found vs false onsets)."""
import proto
import tr_model as tm

SR = 44100


def best(loops, tol=0.015):
    """Over all ratio cuts: the cut with the best F1, summed over the loops."""
    rows = []                                      # (ratio, true?, kind)
    totals = {}
    for pcm, hits in loops:
        ons, _, _ = proto.analyse(pcm)
        seen = set()
        for pos, q, rank in ons:
            near = min(hits, key=lambda h: abs(h[0] - pos))
            ok = abs(near[0] - pos) <= tol * SR and (id(hits), near[0]) not in seen
            if ok:
                seen.add((id(hits), near[0]))
            rows.append((32768 / max(q, 1), ok, near[1]))
        for p, k in hits:
            if p > 0:
                totals[k] = totals.get(k, 0) + 1
    n_hits = sum(totals.values())
    out = None
    for cut in sorted({r for r, _, _ in rows}):
        tp = sum(1 for r, ok, _ in rows if r >= cut and ok)
        fp = sum(1 for r, ok, _ in rows if r >= cut and not ok)
        f1 = 2 * tp / (2 * tp + fp + (n_hits - tp))
        kinds = {}
        for r, ok, k in rows:
            if r >= cut and ok:
                kinds[k] = kinds.get(k, 0) + 1
        if out is None or f1 > out[0]:
            out = (f1, cut, tp, fp, kinds)
    f1, cut, tp, fp, kinds = out
    return (f"F1 {f1:.2f} at ratio >= {cut:4.2f}: " + ", ".join(f"{k} {kinds.get(k, 0)}/{n}"
            for k, n in sorted(totals.items())) + f", false {fp}")


if __name__ == "__main__":
    loops = [proto.drums(s, seed) for s, seed in ((2.0, 1), (4.0, 2), (3.0, 3))]
    for hf, lf in ((None, 0), (0, 0), (1, 0), (2, 0), (2, 1), (3, 1), (0, -1), (2, -1)):
        for ms in (100, 40):
            tm.HF_SHIFT, tm.LF_SHIFT = hf, lf
            tm.DK = round(2 ** 23 * 32 / (SR * ms / 1000))
            name = "mean|x| only" if hf is None else (f"|dx|<<{hf}" + ("" if lf < 0 else f" + |x|>>{lf}"))
            print(f"{name:18s} env {ms:3d} ms  {best(loops)}")
