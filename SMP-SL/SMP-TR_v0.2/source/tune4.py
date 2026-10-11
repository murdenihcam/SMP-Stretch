#!/usr/bin/env python3
"""Timing of the refined onsets for each refinement rule (detected - true, ms)."""
import proto
import tr_model as tm
from tune2 import notes

SR = 44100
SETS = [proto.drums(s, seed) for s, seed in ((2.0, 1), (4.0, 2), (3.0, 3))] + [notes(4.0, 1, s) for s in (1, 2)]
for rule, first, pre in ((None, False, 0), (None, True, 0), (None, True, 4), (None, True, 5), (2, True, 0),
                         (3, True, 0)):
    tm.REFINE, tm.FIRSTPOS, tm.PREROLL = rule, first, pre
    rule = f"refine {rule}" if rule is not None else f"pre-roll {pre and 2 ** pre}"
    rule += " first" if first else " strongest"
    errs = []
    for pcm, hits in SETS:
        ons, _, _ = proto.analyse(pcm)
        for pos, q, _ in ons:
            near = min(hits, key=lambda h: abs(h[0] - pos))
            if abs(near[0] - pos) < 0.03 * SR and 32768 / q >= 1.4:
                errs.append((pos - near[0]) * 1000 / SR)
    errs.sort()
    late = sum(e > 1.5 for e in errs)
    early = sum(e < -6 for e in errs)
    print(f"{rule:22s}: {len(errs)} onsets, error {errs[0]:6.1f} .. {errs[-1]:5.1f} ms, median"
          f" {errs[len(errs) // 2]:5.1f}; more than 1.5 ms late: {late}, more than 6 ms early: {early}")
