#!/usr/bin/env python3
"""Onset timing error (detected - true, ms) and the effect of the merge gap."""
import proto
import tr_model as tm
from tune import best
from tune2 import notes

SR = 44100
tm.MIN_STRIDE = 16
for gap in (1100, 2200):
    tm.GAP_FR = gap
    print(f"merge gap {gap * 1000 // SR} ms")
    print("  drums  ", best([proto.drums(s, seed) for s, seed in ((2.0, 1), (4.0, 2), (3.0, 3))]))
    print("  plucks ", best([notes(4.0, 1, seed) for seed in (1, 2)]))
tm.GAP_FR = 1100
errs = []
for pcm, hits in [proto.drums(s, seed) for s, seed in ((2.0, 1), (4.0, 2), (3.0, 3))] + \
        [notes(4.0, 1, seed) for seed in (1, 2)]:
    ons, _, _ = proto.analyse(pcm)
    for pos, q, _ in ons:
        near = min(hits, key=lambda h: abs(h[0] - pos))
        if abs(near[0] - pos) < 0.02 * SR and 32768 / q >= 1.4:
            errs.append((pos - near[0]) * 1000 / SR)
errs.sort()
print(f"timing error over {len(errs)} onsets: min {errs[0]:.1f} ms, median {errs[len(errs) // 2]:.1f},"
      f" max {errs[-1]:.1f}; later than the hit: {sum(e > 0 for e in errs)}")
