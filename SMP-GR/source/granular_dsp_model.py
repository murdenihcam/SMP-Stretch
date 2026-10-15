#!/usr/bin/env python3
"""Bit-exact model of granular_engine.inc (SMP-GR / GM / G2 v0.4), for checking the
DSP code and for listening.

The model repeats the machine's integer arithmetic step by step, so the simulator
output must match it word for word (see simtest.py). It also renders WAVs:

  python granular_dsp_model.py in.wav out.wav --dens 100 --gran 70 --spry 30 --seconds 6
  python granular_dsp_model.py in.wav out.wav --sweep scan=64:100
  python granular_dsp_model.py --demo in.wav outdir
  (settings are the Machinedrum's 0..127 values, as on the front panel)
"""
import argparse
import os
import wave

import gen_tables as T

M24 = 0xFFFFFF
ONE = 0x7FFFFF
(P_PTCH, P_SMPL, P_DEC, P_DENS, P_SEEK, P_SCAN, P_GRAN, P_SPRY, S_BANK, S_SLOT, S_ACT, S_LEN, S_STEP,
 S_SEED, S_ENV, S_OFFI, S_OFFF, S_CNT, S_MASK, S_PROC, S_HP) = range(1, 22)
H_ACC = 40
V_TD, V_NB, V_W, V_SH, V_G, V_BITS, V_PI, V_PF = range(8)
SLOTS = 4                       # read slots of 16 frames; buffer 0 = slots 0,1, buffer 1 = 2,3
UW_SLOTS = 48
MIN_LEN = 256
ENV_OFF = 0x40
SEED0 = 0x2A5B3D
STATE_Y = range(9, 22)          # persistent Y words (the rest is scratch)


def s24(v):
    v &= M24
    return v - (1 << 24) if v & 0x800000 else v


def acc(word):                 # move word,a: into A1, sign-extended, A0 cleared
    return s24(word) << 24


def hi(a):                     # A1
    return (a >> 24) & M24


def lo(a):                     # A0
    return a & M24


def mpy(x, y):                 # fractional multiply: A = 2 * x * y
    return 2 * s24(x) * s24(y)


def lim(a):                    # move a,dest: saturate to 48 bits, take A1
    a = max(-(1 << 47), min((1 << 47) - 1, a))
    return hi(a)


def knob(raw):                 # whole setting 0..127
    v = s24(hi(acc(raw) >> 7))
    return max(0, min(127, v))


class Track:
    """One track: Y:(r6+0..63) as self.y, X:(r6+0..63) as self.x.

    bank is the machine's BANK_ID: -1 both (SMP-GR), 1 UW ROM (SMP-GM), 0 internal (SMP-G2)."""

    def __init__(self, track=0, bank=-1):
        self.y = [0] * 64
        self.x = [0] * 64
        self.bank_id = bank
        self.init(track)

    def set_params(self, ptch=64, smpl=1, dec=127, dens=64, seek=0, scan=64, gran=64, spry=0, smpl_min=1):
        y = self.y
        y[P_PTCH] = round(ptch * 128)                # raw14 (fractions = modulation)
        y[P_SMPL] = smpl - smpl_min                  # index
        y[P_DEC] = round(dec * 128)
        y[P_DENS] = round(dens * 128)
        y[P_SEEK] = round(seek * 65536)              # unipolar Q23
        y[P_SCAN] = round(scan * 128)
        y[P_GRAN] = round(gran * 128)
        y[P_SPRY] = round(spry * 128)

    def clear_grains(self):
        self.x[:32] = [0] * 32
        self.y[S_MASK] = self.y[S_PROC] = 0

    def tier(self, r):
        """Tier and direction (+1 / -1) of the grain at record r; tier 0 = free."""
        td = s24(self.x[r + V_TD])
        return abs(td), (-1 if td < 0 else 1)

    def init(self, track):
        y = self.y
        y[S_ACT] = 0
        self.clear_grains()
        y[S_SEED] = (track + SEED0) & M24

    def rand(self):
        y = self.y
        a = mpy(y[S_SEED], 0x19660D) >> 1
        y[S_SEED] = hi(acc(lo(a)) + acc(0x6EF35F))
        return y[S_SEED]

    def trig(self, info):
        """info(bank, slot) -> (length, step)."""
        y = self.y
        if self.bank_id >= 0:
            y[S_BANK], y[S_SLOT] = self.bank_id, y[P_SMPL]
        elif y[P_SMPL] < UW_SLOTS:
            y[S_BANK], y[S_SLOT] = 1, y[P_SMPL]
        else:
            y[S_BANK], y[S_SLOT] = 0, y[P_SMPL] - UW_SLOTS
        length, step = info(y[S_BANK], y[S_SLOT])
        if length == 0 or step == 0:
            y[S_ACT] = 0
            return
        y[S_STEP], y[S_LEN] = step, length
        if length < MIN_LEN:
            y[S_ACT] = 0
            return
        self.clear_grains()
        for i in (S_OFFI, S_OFFF, S_CNT, S_HP):
            y[i] = 0
        y[S_ENV] = ONE
        y[S_ACT] = 1

    # ---- per-block pieces ----
    def rates(self):
        y = self.y
        r = mpy(y[S_STEP], T.PITCH[y[P_PTCH] >> 7]) >> 13   # half-semitone steps
        self.r = r                                  # 24.24 frames per output sample
        self.rq = hi(r << 17)

    def spawn(self):
        y, x = self.y, self.x
        gran = T.GRAN[knob(y[P_GRAN])]
        nb, sh = gran & 0xFFFF, gran >> 16
        a = mpy(nb, T.KD[self.di]) << 6
        if a < acc(32):
            a = acc(32)
        y[S_CNT] = hi(acc(y[S_CNT]) + a)
        tier = T.TIER[self.di]
        while True:                                   # its tier, else half rate
            e = s24(T.FREE[(tier - 1) * 64 + y[S_MASK]])
            if e >= 0:
                break
            if tier >= 2:                             # full rate falls back to half, half is skipped
                return
            tier = 2
            self.events["fallback"] = 1
        self.events["ok"] = 1
        v, bits = e & 3, e >> 2
        r = 8 * v
        y[S_MASK] += bits
        length = y[S_LEN]
        ph = hi(mpy(length, y[P_SEEK])) + s24(y[S_OFFI])
        if ph >= length:
            ph -= length
        u = self.rand()
        si = knob(y[P_SPRY])
        rng = hi(mpy(length, T.SPRAY[si]))
        a = s24(hi(mpy(rng, u))) + ph
        if a < 0:
            a += length
        if a >= length:
            a -= length
        span = s24(hi(mpy(nb << 11, self.rq)))
        start = min(a, length - span)
        if start < 0:
            start = 0
        td = tier
        if s24(self.rand()) < s24(T.REVT[si]):
            start = start + span - 1               # same material, from its end backwards
            td = -tier
        x[r + V_TD] = td & M24
        x[r + V_NB] = nb
        x[r + V_W] = nb                            # played 0 << 12 | left NB
        x[r + V_SH] = sh
        x[r + V_G] = 0
        x[r + V_BITS] = bits
        x[r + V_PI] = start & M24
        x[r + V_PF] = 0

    def free(self, r, tier):
        y, x = self.y, self.x
        self.events["frees"] += 1
        y[S_MASK] = hi(acc(y[S_MASK]) - acc(x[r + V_BITS]))
        x[r + V_TD] = 0

    def envelope(self, r, tier):
        """Smoothstep fade gain at the end of this block."""
        x = self.x
        w = x[r + V_W] + 0xFFF                       # played + 1, left - 1
        x[r + V_W] = w
        left, played = w & 0xFFF, w >> 12
        t = min(played, left)
        if left == 0:
            self.free(r, tier)
        xx = lim(acc(t) << x[r + V_SH])               # min(1, t / fade): the limiter clips
        return lim(mpy(xx, self.mg))                  # linear fade

    def buffer(self, first, read, out):
        """Slots first, first + 1 (first = 0 or 2)."""
        y, x = self.y, self.x
        nib = (y[S_MASK] >> first) & 3
        if nib == 0:
            return
        n0 = T.FRAMES[nib]
        temp = [0] * 32
        for g in range(2):
            r = 8 * (first + g)
            tier, sign = self.tier(r)
            if tier == 0:
                continue
            step = self.r << (tier - 1)
            a = acc(x[r + V_PI]) + x[r + V_PF]
            base = 16 * g
            for k in range(64 >> tier):
                temp[base + k] = hi(a + sign * k * step)
            a += sign * (32 >> tier) * 2 * step
            x[r + V_PI], x[r + V_PF] = hi(a), lo(a)
        pcm = read(y[S_BANK], y[S_SLOT], temp, n0)
        if pcm is None:
            y[S_ACT] = 0
            return
        for g in range(2):
            r = 8 * (first + g)
            tier, _ = self.tier(r)
            if tier == 0:
                continue
            g1 = self.envelope(r, tier)
            dest, at = (out, 0) if tier == 1 else (self.y, H_ACC)
            g0 = x[r + V_G]
            x[r + V_G] = g1
            d = hi((acc(g1) - acc(g0)) >> (6 - tier))
            b = acc(g0)
            base = 16 * g
            for k in range(64 >> tier):
                gain = lim(b)
                b += acc(d)
                dest[at + k] = lim(acc(dest[at + k]) + mpy(pcm[base + k], gain))

    @staticmethod
    def upsample(src, dst, prev):
        for i, s in enumerate(src):
            dst[2 * i] = lim(acc(dst[2 * i]) + mpy(prev, 0x400000) + mpy(s, 0x400000))
            prev = s
            dst[2 * i + 1] = lim(acc(dst[2 * i + 1]) + acc(prev))
        return prev

    def render(self, read):
        """read(bank, slot, positions, n) -> list of 32 PCM words (or None on failure)."""
        y = self.y
        if y[S_ACT] == 0:
            return [0] * 32
        self.rates()
        # level
        mul = T.DECAY[knob(y[P_DEC])]
        env = y[S_ENV] if mul == ONE else hi(mpy(y[S_ENV], mul))
        y[S_ENV] = env
        if acc(env) < acc(ENV_OFF):
            y[S_ACT] = 0
        self.di = knob(y[P_DENS])
        self.mg = hi(mpy(env, T.NORM[self.di]))
        # grains
        self.events = {"attempt": 0, "ok": 0, "fallback": 0, "frees": 0}
        if s24(y[S_CNT]) <= 0:
            self.events["attempt"] = 1
            self.spawn()
        y[S_CNT] = hi(acc(y[S_CNT]) - acc(32))
        # what this block costs in the cycle model: slot mask, grain load, grains per tier
        tiers = [self.tier(8 * g)[0] for g in range(SLOTS)]
        counts = [tiers.count(t) for t in (1, 2)]
        self.block = (y[S_MASK], counts[0] * T.PCOST[1] + counts[1] * T.PCOST[2], counts, self.events)
        out = [0] * 32
        y[H_ACC:H_ACC + 16] = [0] * 16
        self.buffer(0, read, out)
        self.buffer(2, read, out)
        y[S_HP] = self.upsample(y[H_ACC:H_ACC + 16], out, y[S_HP])
        # scan
        a = mpy(y[S_STEP], T.SCAN[knob(y[P_SCAN])]) >> 10
        b = acc(y[S_OFFI]) + y[S_OFFF] + a
        if b >= acc(y[S_LEN]):
            b -= acc(y[S_LEN])
        elif b < 0:
            b += acc(y[S_LEN])
        y[S_OFFI], y[S_OFFF] = hi(b), lo(b)
        return out

    def grains(self):
        return sum(1 for g in range(SLOTS) if self.tier(8 * g)[0])


def sample_services(pcm_words, step, internal_words=None):
    """SAMPLE_INFO / SAMPLE_READ over lists of 24-bit PCM words: pcm_words for
    bank 1 (UW), internal_words (default: the same) for bank 0. Both banks
    report the length of pcm_words, as the simulator stand-ins do."""
    banks = {1: pcm_words, 0: pcm_words if internal_words is None else internal_words}

    def info(bank, slot):
        return len(pcm_words), step

    def read(bank, slot, positions, n):
        words = banks[bank]
        return [words[p] if k < n and 0 <= p < len(words) else 0
                for k, p in enumerate(s24(q) for q in positions)]
    return info, read


def read_wav(path):
    with wave.open(path, "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise SystemExit("only 16-bit WAV files are supported")
    vals = [int.from_bytes(raw[i:i + 2], "little", signed=True) for i in range(0, len(raw), 2)]
    mono = [sum(vals[i:i + ch]) // ch for i in range(0, len(vals), ch)]
    return [(v << 8) & M24 for v in mono], rate


def write_wav(path, words):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"".join((s24(v) >> 8).to_bytes(2, "little", signed=True) for v in words))


KNOBS = ("ptch", "dec", "dens", "seek", "scan", "gran", "spry")
DEFAULTS = dict(ptch=64, dec=127, dens=64, seek=0, scan=64, gran=64, spry=0)
DEMOS = [
    ("01_default", {}),
    ("02_sparse_short", dict(dens=10, gran=30, spry=40)),
    ("03_full_rate_single", dict(dens=38, gran=80, spry=20)),
    ("04_half_rate_cloud", dict(dens=95, gran=80, spry=30)),
    ("05_max_density_cloud", dict(dens=127, gran=85, spry=30)),
    ("06_scan_forward_slow", dict(scan=84, dens=100, gran=70)),
    ("07_scan_reverse_fast", dict(scan=10, dens=100, gran=60)),
    ("08_spray_reverse", dict(spry=110, dens=110, gran=75)),
    ("09_freeze_mid", dict(seek=64, dens=115, gran=75, spry=8)),
    ("10_pitch_down_decay", dict(ptch=40, dec=80, dens=100, gran=70, spry=15)),
    ("11_tiny_grains_dense", dict(dens=127, gran=20, spry=50, scan=70)),
    ("12_long_grains_dense", dict(dens=127, gran=127, spry=60)),
]


def run(words, rate, knobs, seconds, sweeps=(), track=0):
    info, read = sample_services(words, round(rate / 44100 * 65536))
    t = Track(track)
    k = dict(DEFAULTS, **knobs)
    t.set_params(**k)
    t.trig(info)
    nblocks = int(seconds * 44100) // 32
    out, most = [], 0
    for b in range(nblocks):
        if sweeps:
            for name, a, z in sweeps:
                k[name] = a + (z - a) * b / max(1, nblocks - 1)
            t.set_params(**k)
        out += t.render(read)
        most = max(most, t.grains())
    return out, most


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    for name in KNOBS:
        ap.add_argument("--" + name, type=float, default=DEFAULTS[name])
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--sweep", action="append", default=[], help="knob=start:end over the render")
    ap.add_argument("--demo", action="store_true", help="output is a directory; render the demo set")
    a = ap.parse_args()
    words, rate = read_wav(a.input)
    if a.demo:
        os.makedirs(a.output, exist_ok=True)
        for name, knobs in DEMOS:
            out, most = run(words, rate, knobs, a.seconds)
            write_wav(os.path.join(a.output, name + ".wav"), out)
            print("%-26s most grains at once: %d" % (name, most))
        return
    sweeps = []
    for s in a.sweep:
        name, rng = s.split("=")
        lo_, hi_ = rng.split(":")
        sweeps.append((name.lower(), float(lo_), float(hi_)))
    out, most = run(words, rate, {n: getattr(a, n) for n in KNOBS}, a.seconds, sweeps)
    write_wav(a.output, out)
    print("wrote", a.output, "- most grains at once:", most)


if __name__ == "__main__":
    main()
