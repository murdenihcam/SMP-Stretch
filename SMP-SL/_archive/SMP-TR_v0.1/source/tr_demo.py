#!/usr/bin/env python3
"""Listening renders of the transient slicer draft, from the bit-exact model.

The source (demo\\00_source.wav, a synthetic drum loop: kick, snare, hats)
is analysed while the track is quiet; then the detected slices are triggered
on 16ths. Prints the onsets found."""
import sys
from pathlib import Path

import proto                                       # the drum loop
import slicer_model as sm                          # noqa: E402
import tr_model as tm                              # noqa: E402

OUT = Path(__file__).resolve().parent / "demo"
SR = 44100


def render(pcm, settings, pattern, every, seconds=4.0):
    info, read = sm.sample_services(pcm, 0x10000)
    t = tm.TrTrack(3)
    t.set_params(**{**settings, "slno": 1})
    t.trig(info)
    while not (t.y[tm.A_DONE] and t.y[tm.A_KEY] != tm.NONE):   # analyse first (silently)
        t.y[sm.S_ACT] = 0
        t.render(read, info)
    out, per = [], every // 32
    for b in range(int(seconds * SR) // 32):
        if b % per == 0:
            t.set_params(**{**settings, "slno": pattern[(b // per) % len(pattern)]})
            t.trig(info)
        out += t.render(read, info)
    return out, t


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    pcm, _ = proto.drums(4.0, 1)
    sm.write_wav(str(OUT / "00_source.wav"), pcm)
    six = SR // 8
    base = dict(smpl=5, dec=0, thrs=10, slic=64)
    for name, settings, pattern in (
            ("01_onsets_in_order", base, list(range(1, 33))),
            ("02_onsets_shuffled", base, [1, 2, 1, 4, 3, 3, 7, 5, 9, 2, 11, 6, 13, 13, 8, 16]),
            ("03_thrs60_in_order", {**base, "thrs": 60}, list(range(1, 33))),
            ("04_slic8_strongest", {**base, "slic": 8}, list(range(1, 9)))):
        out, t = render(pcm, settings, pattern, six)
        sm.write_wav(str(OUT / f"{name}.wav"), out)
        print("wrote", name)
    ons = [(t.x[2 * i], round(32768 / (t.x[2 * i + 1] >> 8), 1), t.x[2 * i + 1] & 255) for i in range(t.y[tm.A_CNT])]
    print(f"{len(ons)} onsets (frame, energy ratio, rank); hits are every {six} frames:")
    for pos, r, rank in ons:
        print(f"   {pos:7d} ({pos / six:5.2f} 16ths)  x{r:<5} rank {rank}")
