#!/usr/bin/env python3
"""Bit-exact model of rom_e12_slicer.asm56k (SMP-SL), for checking the DSP code and for listening.

The model repeats the machine's integer arithmetic step by step, so the simulator
output must match it word for word (see simtest.py). It can also render a WAV:

  python slicer_model.py in.wav out.wav --mode 0 --slic 7 --slno 2 --play 2 --dec 100
  (settings are the Machinedrum's front-panel values; MODE 0 EQUA 1 EXP 2 LOG 3..6 SED1..4,
   PLAY 0 FWD 1 REV 2 BI; DEC 0 plays the slice once)
"""
import argparse
import wave

from gen_tables import DECAY, EXPC, FADE8, LOGC, NOISE, PITCH, QTR, SEED_MODES, SPEED, seed_params

M24 = 0xFFFFFF
# Y offsets, as the equ list in slicer_engine.inc
(P_PTCH, P_SMPL, P_DEC, P_TIME, P_PLAY, P_MODE, P_SLIC, P_SLNO, S_BANK, S_ACT, S_GI, S_GF, S_PI, S_PF,
 S_LO, S_HI, S_WIN, S_STEP, S_CNT, S_GAIN, S_SLOT, S_PREV, S_GREV, S_OREV, S_MIR, S_ENV, S_FADE, S_OGI,
 S_OGF, T_RGI, T_RGF, T_RQ, T_R2I, T_R2F, T_VBI, T_VBF, T_RPQ, T_F, T_SH, T_M, T_G0, T_G1, T_CO0, T_COS,
 T_CN0, T_CNS, T_J, T_CTR, T_W, T_TZ, S_REL, T_W1) = range(1, 53)
T_LEN, T_N, T_K, T_MODE = T_G0, T_G1, T_CO0, T_COS      # TRIG scratch
T_PK, T_PK1, T_PN, T_DEPTH = T_CN0, T_CNS, T_J, T_CTR
ONE = 0x7FFFFF
ENV_OFF = 0x40
UW_SLOTS = 48
MIN_WIN = 64
GRAN = 1494                    # SMP-ST's grain length at GRAN 64: 300 + 4776 / 4
L64 = GRAN * 64
MAX_MODE = 127


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


def divq(num, den):            # rep #24 div: Q23 quotient of 0 <= num < den
    return (num << 23) // den


class Track:
    """One track: Y:(r6+0..63) as self.y. bank_id: the machine's BANK_ID, 1 UW ROM
    (SMP-SM), 0 internal (SMP-SN) or -1 both (SMP-SL). time_st: TIME works as in
    SMP-ST (the playhead speed ignores PTCH once TIME is above 0), as the machine does."""

    def __init__(self, track=0, time_st=True, bank_id=-1):
        self.y = [0] * 64
        self.bank_id = bank_id
        self.bank = 1
        self.time_st = time_st
        self.time_gran = False                      # SMP-TG: TIME also sets the grain length
        self.init(track)

    # ---- converted parameter values (what the firmware puts in Y+1..8) ----
    def set_params(self, ptch=64, smpl=1, dec=0, time=0, mode=0, play=0, slic=8, slno=1):
        y = self.y
        y[P_PTCH] = ptch * 128                       # raw14
        y[P_SMPL] = smpl - 1                         # index, min 1
        y[P_DEC] = dec * 128                         # raw14
        y[P_TIME] = time * 128                       # raw14
        y[P_PLAY] = play                             # index, min 0
        y[P_MODE] = mode                             # index, min 0
        y[P_SLIC] = slic - 1                         # index, min 1
        y[P_SLNO] = slno - 1                         # index, min 1

    def init(self, track):
        y = self.y
        for i in (S_ACT, S_GAIN, S_CNT, S_FADE, S_REL):
            y[i] = 0

    def seedsum(self, mode, k, n):
        """Perlin seed prefix sums P[k], P[k+1], P[n] (SEEDSUM)."""
        y = self.y
        depth, stride, offset = seed_params(mode - SEED_MODES)
        y[T_DEPTH] = depth
        sums, s = {}, 0
        for i in range(n + 1):
            if i in (k, k + 1, n):
                sums[i] = s
            if i < n:
                s += NOISE[offset + i * stride]
        y[T_PK], y[T_PK1], y[T_PN] = ((((j << 12) + s24(hi(mpy(sums[j], depth)))) & M24)
                                      for j in (k, k + 1, n))

    def bound(self, j, n, mode, length):
        """Frame of slice boundary j of n."""
        y = self.y
        if j == 0:
            return 0
        if j >= n:
            return length
        if mode >= SEED_MODES:
            u = divq(y[T_PK] if j == y[T_K] else y[T_PK1], y[T_PN])
        elif mode == 1:                               # SHUF
            u = divq(3 * j + (j & 1), 3 * n)
        else:
            u = divq(j, n)
            if mode:
                tab = EXPC if mode == 2 else LOGC
                i, f = u >> 17, (u & 0x1FFFF) << 6
                u = hi(mpy(f, tab[i + 1] - tab[i]) + acc(tab[i]))
        return hi(mpy(length, u))

    def trig(self, info):
        """info(bank, slot) -> (length, step)."""
        y = self.y
        if self.bank_id >= 0:
            y[S_BANK], y[S_SLOT] = self.bank_id, y[P_SMPL]
        elif y[P_SMPL] < UW_SLOTS:
            y[S_BANK], y[S_SLOT] = 1, y[P_SMPL]
        else:
            y[S_BANK], y[S_SLOT] = 0, y[P_SMPL] - UW_SLOTS
        self.bank = y[S_BANK]
        length, step = info(self.bank, y[S_SLOT])
        if length == 0 or step == 0:
            y[S_ACT] = 0
            return
        y[S_STEP] = step
        y[T_LEN] = length
        n = min(y[P_SLIC], 63) + 1
        k = min(y[P_SLNO], 63)
        while k >= n:
            k -= n
        mode = min(y[P_MODE], MAX_MODE)
        y[T_N], y[T_K], y[T_MODE] = n, k, mode
        if mode >= SEED_MODES:
            self.seedsum(mode, k, n)
        start = self.bound(k, n, mode, length)
        end = self.bound(k + 1, n, mode, length)
        if end - start < MIN_WIN:
            end = start + MIN_WIN
        y[S_LO], y[S_HI], y[S_WIN] = start, end, end - start
        y[S_MIR] = start + end - 1
        y[S_GI] = y[S_PI] = start
        y[S_GF] = y[S_PF] = y[S_FADE] = y[S_REL] = 0
        y[S_PREV] = y[S_GREV] = int(y[P_PLAY] == 1)
        y[S_CNT] = GRAN
        y[S_ENV] = y[S_GAIN] = ONE
        y[S_ACT] = 1

    def rates(self):
        y = self.y
        a = (acc(y[P_PTCH]) - acc(8192)) >> 1        # half a semitone per step
        a = max(acc(-4096), min(acc(4095), a))
        s = s24(hi(a)) >> 7
        y[T_F] = ((hi(a) & 0x7F) << 16) & M24
        t = s + 72
        octave = hi(mpy(t, 0x0AAAAB))
        n = t - 12 * octave
        m0, m1 = PITCH[n], PITCH[n + 1]
        y[T_M] = m = hi(mpy(y[T_F], hi(acc(m1) - acc(m0))) + acc(m0))
        y[T_SH] = sh = 20 - octave
        r = mpy(y[S_STEP], m) >> sh
        y[T_RGI], y[T_RGF] = hi(r), lo(r)
        y[T_RQ] = hi(r << 17)
        y[T_R2I], y[T_R2F] = hi(r << 1), lo(r << 1)
        ti = max(0, min(127, s24(hi(acc(y[P_TIME]) >> 7))))
        if ti == 0:
            y[T_TZ] = 1
            vb = r << 5
        else:
            y[T_TZ] = 0
            if self.time_st:
                vb = mpy(y[S_STEP], SPEED[ti]) >> 1
            else:
                st = hi(mpy(y[S_STEP], SPEED[ti] << 10))
                vb = (mpy(st, m) >> sh) << 5
        y[T_VBI], y[T_VBF] = hi(vb), lo(vb)
        y[T_RPQ] = hi(vb << 12)
        b = (r << 7) + (r << 5)
        lead = hi(b)                                 # 160 samples of grain travel
        lead1 = hi(b << 1)                           # 320, for the DEC 0 end fade
        half = y[S_WIN] >> 1
        y[T_W] = y[S_HI] - min(lead, half)           # loop point: the crossfade ends at hi
        y[T_W1] = y[S_HI] - min(lead1, half)         # DEC 0: the fade ends about a block before hi

    def gran_len(self):
        """Grain length in output samples: 1494, or from GRANT by TIME (SMP-TG)."""
        if not self.time_gran:
            return GRAN
        from gen_tables import GRANT
        return GRANT[max(0, min(127, s24(hi(acc(self.y[P_TIME]) >> 7))))]

    def splice(self):
        y = self.y
        y[S_FADE] = 1
        y[S_OGI], y[S_OGF], y[S_OREV] = y[S_GI], y[S_GF], y[S_GREV]
        l64 = self.gran_len() << 6
        y[T_J] = hi(mpy(l64, y[T_RQ]))              # GRAN * grain rate
        jp = hi(mpy(l64, y[T_RPQ]))                  # GRAN * playhead rate
        y[T_CTR] = hi((acc(y[T_J]) - acc(jp)) >> 1)
        b = acc(y[S_PI]) + y[S_PF] - acc(y[T_CTR])
        if b < acc(y[S_LO]):
            b = acc(y[S_LO])
        top = y[T_W] - 1
        if b > acc(top):
            b = acc(top)
        y[S_GI], y[S_GF] = hi(b), lo(b)
        y[S_GREV] = y[S_PREV]
        y[S_CNT] = hi(acc(y[S_CNT]) + acc(self.gran_len()))

    def posgen(self, gi, gf, rev):
        y = self.y
        a = acc(gi) + gf
        x = acc(y[T_RGI]) + y[T_RGF]
        if rev:
            a = acc(y[S_MIR]) - a
            x = -x
        out = []
        for _ in range(32):
            out.append(hi(a))
            a += x
        if rev:
            a = acc(y[S_MIR]) - a
        return out, a

    def render(self, read):
        """read(bank, slot, positions, n) -> list of 32 PCM words (or None on failure)."""
        y = self.y
        if y[S_ACT] == 0:
            return [0] * 32
        fading = y[S_FADE] != 0
        if not fading:                               # rates hold through crossfades
            self.rates()
        # level
        d = max(0, min(127, s24(hi(acc(y[P_DEC]) >> 7))))
        mul = DECAY[d]
        env = y[S_ENV] if mul == ONE else hi(mpy(y[S_ENV], mul))
        y[S_ENV] = env
        if acc(env) < acc(ENV_OFF):
            y[S_ACT] = 0
        g = env
        if y[S_REL]:                                 # DEC 0 end fade
            g = hi(mpy(env, FADE8[y[S_REL]]))
            y[S_REL] += 1
            if y[S_REL] >= 9:
                y[S_ACT] = 0
        y[T_G1] = g
        y[T_G0] = y[S_GAIN]
        y[S_GAIN] = g
        g0, g1 = y[T_G0], y[T_G1]
        if fading:
            j = y[S_FADE] - 1
            b = mpy(g0, QTR[j])
            y[T_CO0] = hi(b)
            y[T_COS] = hi((mpy(g1, QTR[j + 1]) - b) >> 5)
            b = mpy(g0, QTR[4 - j])
            y[T_CN0] = hi(b)
            y[T_CNS] = hi((mpy(g1, QTR[3 - j]) - b) >> 5)
        else:
            y[T_CN0] = g0
            y[T_CNS] = hi((acc(g1) - acc(g0)) >> 5)
        out = [0] * 32
        if fading:
            pos, a = self.posgen(y[S_OGI], y[S_OGF], y[S_OREV])
            y[S_OGI], y[S_OGF] = hi(a), lo(a)
            pcm = read(self.bank, y[S_SLOT], pos, 32)
            if pcm is None:
                y[S_ACT] = 0
                return [0] * 32
            b = acc(y[T_CO0])
            for k in range(32):
                out[k] = lim(mpy(pcm[k], hi(b)))
                b += acc(y[T_COS])
        pos, a = self.posgen(y[S_GI], y[S_GF], y[S_GREV])
        y[S_GI], y[S_GF] = hi(a), lo(a)
        b = acc(y[S_PI]) + y[S_PF] + acc(y[T_VBI]) + y[T_VBF]
        y[S_PI], y[S_PF] = hi(b), lo(b)
        pcm = read(self.bank, y[S_SLOT], pos, 32)
        if pcm is None:
            y[S_ACT] = 0
            return [0] * 32
        b = acc(y[T_CN0])
        for k in range(32):
            a = mpy(pcm[k], hi(b))
            if fading:
                a += acc(out[k])
            b += acc(y[T_CNS])
            out[k] = lim(a)
        if fading:
            y[S_FADE] = 0 if y[S_FADE] + 1 >= 5 else y[S_FADE] + 1
            if not y[T_TZ]:
                y[S_CNT] = hi(acc(y[S_CNT]) - acc(32))
            return out
        # Outside crossfades: loop when the playhead reaches the loop point,
        # otherwise splice every GRAN samples (TIME above 0), or early when the
        # grain itself reaches the loop point.
        if y[S_REL]:
            return out
        if acc(y[P_DEC]) < acc(128):                 # DEC 0: play once, fade out from W1
            if acc(y[S_PI]) >= acc(y[T_W1]):
                y[S_REL] = 1
                return out
        elif acc(y[S_PI]) >= acc(y[T_W]):
            p = y[S_PI] - y[T_W] + y[S_LO]
            if acc(p) >= acc(y[T_W]):
                p = y[S_LO]
            y[S_PI] = p
            play = y[P_PLAY]
            if play == 0:
                y[S_PREV] = 0
            elif play == 1:
                y[S_PREV] = 1
            else:
                y[S_PREV] ^= 1
            y[S_CNT] = 0
            self.splice()
            return out
        if y[T_TZ]:
            y[S_CNT] = GRAN
        else:
            y[S_CNT] = hi(acc(y[S_CNT]) - acc(32))
        if acc(y[S_CNT]) <= 0:
            self.splice()
        elif acc(y[S_GI]) >= acc(y[T_W]):
            y[S_CNT] = 0
            self.splice()
        return out


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


def write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"".join((s24(v) >> 8).to_bytes(2, "little", signed=True) for v in samples))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input"); ap.add_argument("output")
    for name, default in (("ptch", 64), ("dec", 0), ("time", 0), ("mode", 0), ("play", 0),
                          ("slic", 8), ("slno", 1)):
        ap.add_argument("--" + name, type=int, default=default)
    ap.add_argument("--seconds", type=float, default=2.0)
    a = ap.parse_args()
    words, rate = read_wav(a.input)
    info, read = sample_services(words, round(rate / 44100 * 65536))
    t = Track()
    t.set_params(ptch=a.ptch, dec=a.dec, time=a.time, play=a.play, mode=a.mode, slic=a.slic, slno=a.slno)
    t.trig(info)
    out = []
    for _ in range(int(a.seconds * 44100) // 32):
        out += t.render(read)
    write_wav(a.output, out)
    print("slice frames", t.y[S_LO], "..", t.y[S_HI], "- wrote", a.output)
