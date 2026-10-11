#!/usr/bin/env python3
"""Render listening demos with the bit-exact model: python demo.py

Source: a synthetic 2-bar drum loop (kick / snare / hats, 120 BPM, 4 s),
written to demo\\00_source.wav. Each demo triggers the slicer every 16th note
or every beat with a pattern of SLNO values, as a sequencer would.
"""
import math
import random
from pathlib import Path

import slicer_model as m

HERE = Path(__file__).resolve().parent
OUT = HERE / "demo"
SR = 44100


def drum_loop():
    n = 4 * SR
    x = [0.0] * n
    rnd = random.Random(1)
    step = SR // 8                                   # 16ths at 120 BPM
    for s in range(32):
        t0 = s * step
        if s % 8 in (0, 3) or s in (22, 27):         # kick
            for i in range(int(0.35 * SR)):
                f = 50 + 120 * math.exp(-i / 900)
                x[t0 + i] += 0.9 * math.sin(2 * math.pi * f * i / SR) * math.exp(-i / 7000)
        if s % 8 == 4:                               # snare
            for i in range(int(0.25 * SR)):
                x[t0 + i] += (0.5 * rnd.uniform(-1, 1) * math.exp(-i / 3000)
                              + 0.4 * math.sin(2 * math.pi * 190 * i / SR) * math.exp(-i / 2500))
        if s % 2 == 0 or s % 8 == 7:                 # hats
            for i in range(int(0.06 * SR)):
                if t0 + i < n:
                    x[t0 + i] += 0.25 * rnd.uniform(-1, 1) * math.exp(-i / 500)
    peak = max(abs(v) for v in x)
    return [round(v / peak * 0.8 * 0x7FFFFF) & 0xFFFFFF for v in x]


def render(pcm, settings, pattern, every, seconds=4.0, time_st=False):
    """Trigger with SLNO from pattern every `every` samples (rounded to blocks)."""
    info, read = m.sample_services(pcm, 0x10000)
    t = m.Track(time_st=time_st)
    out, blocks, per = [], int(seconds * SR) // 32, max(1, every // 32)
    for b in range(blocks):
        if b % per == 0:
            t.set_params(**{**settings, "slno": pattern[(b // per) % len(pattern)]})
            t.trig(info)
        out += t.render(read)
    return out


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    pcm = drum_loop()
    m.write_wav(str(OUT / "00_source.wav"), pcm)
    beat, six = SR // 2, SR // 8
    base = dict(ptch=64, smpl=1, dec=127, time=0, play=0, mode=0, slic=16)
    demos = [
        ("01_equa16_shuffle", base, [1, 1, 5, 3, 9, 6, 13, 16], six),
        ("02_equa16_rev", {**base, "play": 1}, [1, 4, 5, 8, 9, 12, 13, 16], six),
        ("03_exp8_beats", {**base, "mode": 1, "slic": 8}, [1, 2, 3, 4, 5, 6, 7, 8], beat),
        ("04_log8_beats", {**base, "mode": 2, "slic": 8}, [1, 2, 3, 4, 5, 6, 7, 8], beat),
        ("05_sed2_12", {**base, "mode": 4, "slic": 12}, [1, 3, 2, 5, 7, 4, 9, 12], six),
        ("06_bi_loop_hold", {**base, "slic": 4, "play": 2}, [2], 8 * SR),
        ("07_fwd_loop_decay", {**base, "slic": 8, "dec": 100}, [1, 5], 2 * SR),
        ("08_time_half", {**base, "slic": 8, "time": 42}, [1, 2, 3, 4, 5, 6, 7, 8], beat),
        ("09_pitch_up_time", {**base, "slic": 8, "time": 42, "ptch": 88}, [1, 2, 3, 4, 5, 6, 7, 8], beat),
        ("10_pitch_up_time_st", {**base, "slic": 8, "time": 42, "ptch": 88}, [1, 2, 3, 4, 5, 6, 7, 8], beat,
         True),
        ("11_frozen_bi", {**base, "slic": 8, "time": 127, "play": 2}, [5], 8 * SR),
        ("12_stutter64", {**base, "slic": 64, "dec": 90}, [1, 1, 1, 1, 17, 17, 33, 49], six),
    ]
    for name, settings, pattern, every, *st in demos:
        m.write_wav(str(OUT / f"{name}.wav"), render(pcm, settings, pattern, every, time_st=bool(st)))
        print("wrote", name)
