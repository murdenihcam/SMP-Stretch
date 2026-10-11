#!/usr/bin/env python3
"""Behaviour checks on the bit-exact model (the simulator matches it word for word).

  1. neutral settings reproduce the source, apart from small rounding in crossfades
  2. TIME 42 (half speed, a third of the turn) lasts twice as long and keeps the pitch
  3. PTCH +12 / -12 / +24 shift the pitch and keep the length
  4. TIME 127 freezes: the voice is still playing after 3 seconds
  5. reverse at neutral settings is the source backwards
  6. the end of the voice is a fade: no step larger than the signal's own slope
  7. DEC shortens the sound; DEC 127 holds it
"""
import math
import rom_stretch_model as m

SR = 44100


def tone(seconds, hz=441, amp=0.5):
    return [round(amp * math.sin(2 * math.pi * hz * i / SR) * 0x7FFFFF) & 0xFFFFFF
            for i in range(int(seconds * SR))]


def run(src, seconds, **params):
    info, read = m.sample_services(src, 0x10000)
    t = m.Track()
    t.set_params(**{"gran": 64, **params})
    t.trig(info)
    out = []
    for _ in range(int(seconds * SR) // 32):
        out += [m.s24(v) for v in t.render(read)]
    return out, t


def freq(x):
    """Frequency from rising zero crossings."""
    ups = [i for i in range(1, len(x)) if x[i - 1] < 0 <= x[i]]
    return (len(ups) - 1) * SR / (ups[-1] - ups[0]) if len(ups) > 2 else 0.0


def length(x, floor=0):
    """Seconds until the output stays below floor for good."""
    last = max((i for i, v in enumerate(x) if abs(v) > floor), default=0)
    return (last + 1) / SR


def last_steps(x, n=600):
    """Largest sample-to-sample step in the final n samples before silence."""
    end = max((i for i, v in enumerate(x) if v), default=0) + 2
    seg = x[max(0, end - n):end]
    return max(abs(b - a) for a, b in zip(seg, seg[1:]))


src = tone(1.0)
want = [m.s24(v) for v in src]
slope = max(abs(b - a) for a, b in zip(want, want[1:]))

out, _ = run(src, 0.9)
err = max(abs(o - w) for o, w in zip(out, want))
print(f"1. neutral: largest difference from the source = {err} LSB of 2^23")

out, _ = run(src, 2.5, time=42)
print(f"2. TIME 42: length {length(out):.2f} s (source 1.00 s), pitch {freq(out[:SR]):.1f} Hz (source 441)")

for setting in (40, 52, 76, 88, 112, 127):         # half a semitone per step
    semis = (setting - 64) / 2
    out, _ = run(src, 1.5, ptch=setting)
    print(f"3. PTCH {setting - 64:+d} ({semis:+.1f} semitones): length {length(out):.2f} s,"
          f" pitch {freq(out[:SR // 2]):.1f} Hz (want {441 * 2 ** (semis / 12):.1f})")

out, t = run(src, 3.0, time=127, flux=60)
print(f"4. TIME 127: still playing after 3 s: {bool(t.y[m.S_ACT])}, pitch {freq(out[SR:2 * SR]):.1f} Hz")

out, _ = run(src, 0.9, strt=127, end=0)
err = max(abs(o - w) for o, w in zip(out, want[::-1]))
print(f"5. STRT 127, END 0: largest difference from the reversed source = {err} LSB")

# A short loud sample that ends mid-wave (no natural fade), stretched: the old
# version cut it off or wrapped to its start; the end must now be a fade.
short = tone(0.08, hz=300, amp=0.9)
slope = max(abs(m.s24(b) - m.s24(a)) for a, b in zip(short, short[1:]))
for time in (0, 32, 64, 96):
    out, _ = run(short, 0.5, time=time, gran=30)
    print(f"6. short sample, TIME {time}: last step {last_steps(out) / slope:.2f} x the tone's own"
          f" largest step, length {length(out) * 1000:.0f} ms")

for ptch in (64, 88, 112, 127):
    out, _ = run(src, 4.0, ptch=ptch, time=64, gran=127)
    print(f"8. PTCH {ptch - 64:+d}, TIME 64, longest GRAN: length {length(out):.2f} s"
          f" (TIME 64 alone: {1 / (m.SPEED[64] / 8192):.2f} s)")

for dec in (0, 40, 90, 126, 127):
    out, t = run(src, 2.5, dec=dec, time=96)
    print(f"7. DEC {dec:3d}: audible (> -60 dB) for {length(out, 0x7FFFFF // 2000):.2f} s,"
          f" still active {bool(t.y[m.S_ACT])}")
