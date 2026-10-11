#!/usr/bin/env python3
"""SMP-TR vs SMP-TG at high TIME: the same held slice (DEC 127), from the bit-exact model."""
from pathlib import Path

import proto
import slicer_model as sm
import tr_model as tm

OUT = Path(__file__).resolve().parent / "demo_tg"
SR = 44100


def render(pcm, time_gran, settings, seconds=4.0):
    info, read = sm.sample_services(pcm, 0x10000)
    t = tm.TrTrack(3, time_gran=time_gran)
    t.set_params(**settings)
    t.trig(info)
    while not (t.y[tm.A_DONE] and t.y[tm.A_KEY] != tm.NONE):   # analyse first (silently)
        t.y[sm.S_ACT] = 0
        t.render(read, info)
    t.trig(info)
    out = []
    for _ in range(int(seconds * SR) // 32):
        out += t.render(read, info)
    return out


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    pcm, _ = proto.drums(4.0, 1)
    for time in (64, 100, 127):
        for tg, name in ((False, "TR"), (True, "TG")):
            settings = dict(smpl=5, dec=127, time=time, slic=8, slno=5, thrs=27, play=0)
            sm.write_wav(str(OUT / f"time{time}_{name}.wav"), render(pcm, tg, settings))
            print("wrote", f"time{time}_{name}.wav")
