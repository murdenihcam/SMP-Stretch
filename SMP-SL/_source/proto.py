#!/usr/bin/env python3
"""Try the transient analysis (tr_model) on test material and compare with the true hits."""
import math
import random
import sys

import tr_model as tm                              # noqa: E402
import slicer_model as sm                          # noqa: E402

SR = 44100


def drums(seconds=4.0, seed=1):
    """Kick / snare / hats on 16ths at 120 BPM; returns (pcm words, true hit frames, kind)."""
    n = int(seconds * SR)
    x = [0.0] * n
    rnd = random.Random(seed)
    step = SR // 8
    hits = []
    for s in range(int(seconds * 8)):
        t0 = s * step
        kinds = []
        if s % 8 in (0, 3) or s % 32 in (22, 27):
            kinds.append("K")
            for i in range(min(n - t0, int(0.35 * SR))):
                f = 50 + 120 * math.exp(-i / 900)
                x[t0 + i] += 0.9 * math.sin(2 * math.pi * f * i / SR) * math.exp(-i / 7000)
        if s % 8 == 4:
            kinds.append("S")
            for i in range(min(n - t0, int(0.25 * SR))):
                x[t0 + i] += (0.5 * rnd.uniform(-1, 1) * math.exp(-i / 3000)
                              + 0.4 * math.sin(2 * math.pi * 190 * i / SR) * math.exp(-i / 2500))
        if s % 2 == 0 or s % 8 == 7:
            kinds.append("h")
            for i in range(min(n - t0, int(0.06 * SR))):
                x[t0 + i] += 0.25 * rnd.uniform(-1, 1) * math.exp(-i / 500)
        if kinds:
            hits.append((t0, "".join(kinds)))
    peak = max(abs(v) for v in x)
    return [round(v / peak * 0.8 * 0x7FFFFF) & 0xFFFFFF for v in x], hits


def analyse(pcm):
    info, read = sm.sample_services(pcm, 0x10000)
    t = tm.TrTrack(3)
    t.set_params(smpl=5)
    blocks = 0
    while blocks < 20000:
        t.render(read, info)
        blocks += 1
        if t.y[tm.A_DONE] and t.y[tm.A_KEY] != tm.NONE:
            break
    ons = [(t.x[2 * i], t.x[2 * i + 1] >> 8, t.x[2 * i + 1] & 0xFF) for i in range(t.y[tm.A_CNT])]
    return ons, blocks, t.y[tm.A_STRIDE]


if __name__ == "__main__":
    for secs in (2.0, 4.0, 12.0):
        pcm, hits = drums(secs)
        ons, blocks, stride = analyse(pcm)
        print(f"\n{secs:.0f} s drum loop: {len(pcm)} frames, stride {stride}, analysed in {blocks} blocks"
              f" ({blocks * 32 / SR:.2f} s), {len(ons)} onsets kept")
        for pos, q, rank in ons:
            near = min(hits, key=lambda h: abs(h[0] - pos))
            print(f"   frame {pos:7d}  ratio {32768 / max(q, 1):5.1f}  rank {rank:2d}   nearest hit {near[1]:3s}"
                  f" at {near[0]:7d} ({(pos - near[0]) / SR * 1000:+5.1f} ms)")
        found = {min(hits, key=lambda h: abs(h[0] - p))[0] for p, _, _ in ons}
        missed = [h for h in hits if h[0] not in found and h[0] > 0]
        print("   hits without an onset:", [f"{k}@{p}" for p, k in missed][:16], "..." if len(missed) > 16 else "")
