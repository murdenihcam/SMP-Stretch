#!/usr/bin/env python3
"""The chosen detector on drums, plucked/keys notes and a slow pad, with the ratio of every onset."""
import math
import random

import proto
from tune import best

SR = 44100


def notes(seconds, attack_ms, seed, decay_s=0.6, gap=(0.12, 0.5)):
    """Harmonic notes at random times (true onsets returned)."""
    rnd = random.Random(seed)
    n = int(seconds * SR)
    x = [0.0] * n
    hits, t = [], int(0.05 * SR)
    while t < n - SR // 10:
        f = 110 * 2 ** (rnd.randint(0, 24) / 12)
        amp = rnd.uniform(0.3, 1.0)
        att = max(1, int(attack_ms * SR / 1000))
        for i in range(min(n - t, int(4 * decay_s * SR))):
            env = min(1, i / att) * math.exp(-i / (decay_s * SR))
            x[t + i] += amp * env * sum(math.sin(2 * math.pi * f * h * i / SR) / h for h in (1, 2, 3, 5))
        hits.append((t, "n"))
        t += int(rnd.uniform(*gap) * SR)
    peak = max(abs(v) for v in x)
    return [round(v / peak * 0.8 * 0x7FFFFF) & 0xFFFFFF for v in x], hits


def run():
    print("  drums  ", best([proto.drums(s, seed) for s, seed in ((2.0, 1), (4.0, 2), (3.0, 3))]))
    print("  plucks ", best([notes(4.0, 1, seed) for seed in (1, 2)]))
    print("  keys   ", best([notes(4.0, 8, seed, 1.5) for seed in (3, 4)]))
    pad, _ = notes(4.0, 250, 5, 2.0, (0.6, 1.0))
    ons, _, _ = proto.analyse(pad)
    r = sorted(round(32768 / q, 2) for _, q, _ in ons)
    print(f"  slow pad: {len(r)} onsets, ratios {r[:3]} .. {r[-3:]}")


if __name__ == "__main__":
    import sys
    import tr_model as tm
    for arg in sys.argv[1:] or ["100:1"]:
        ms, st = (int(v) for v in arg.split(":"))
        tm.DK = round(2 ** 23 * 32 / (SR * ms / 1000))
        tm.MIN_STRIDE = st
        print(f"envelope {ms} ms, hop at least {32 * st} frames")
        run()
