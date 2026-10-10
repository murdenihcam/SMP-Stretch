#!/usr/bin/env python3
"""Bit-exact model of rom_stretch.asm56k, for checking the DSP code and for listening.

The model repeats the machine's integer arithmetic step by step, so the simulator
output must match it word for word (see simtest.py). It can also render a WAV:

  python rom_stretch_model.py in.wav out.wav --time 42 --gran 64 --flux 40 --ptch 64
  (settings are the Machinedrum's 0..127 values, as on the front panel)
"""
import argparse
import wave

from gen_tables import DECAY, PITCH, QTR, SPEED

M24 = 0xFFFFFF
# Y offsets, as the equ list in rom_stretch.asm56k
(P_PTCH, P_SMPL, P_DEC, P_TIME, P_STRT, P_END, P_GRAN, P_FLUX, S_BANK, S_ACT, S_GI, S_GF, S_PI, S_PF,
 S_LO, S_HI, S_WIN, S_STEP, S_CNT, S_GAIN, S_SEED, S_SLOT, S_REV, S_MIR, S_ENV, S_REL, S_FADE, S_OGI,
 S_OGF, T_RGI, T_RGF, T_RQ, T_F, T_OCT, T_VBI, T_VBF, T_RPQ, T_G0, T_G1, T_CO0, T_COS, T_CN0, T_CNS,
 T_K, T_GRAN, T_L64, T_J, T_CTR, T_R2I, T_R2F) = range(1, 51)   # S_BANK (Y+9): combined machine only
SEED0 = 0x2A5B3D
ONE = 0x7FFFFF


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


UW_SLOTS = 48                  # combined machine: SMPL settings before the internal samples


class Track:
    """One track: Y:(r6+0..63) as self.y.

    bank is the machine's BANK_ID: 1 UW ROM (SMP-ST), 0 internal (SMP-T2), or -1
    for both (UW_SLOTS UW ROM slots, then the internal ones)."""

    def __init__(self, track=0, bank=1):
        self.y = [0] * 64
        self.bank_id = bank
        self.bank = bank
        self.init(track)

    # ---- converted parameter values (what the firmware puts in Y+1..8) ----
    def set_params(self, ptch=64, smpl=1, dec=127, time=0, strt=0, end=127, gran=64, flux=0,
                   smpl_min=1):
        y = self.y
        y[P_PTCH] = ptch * 128                       # raw14
        y[P_SMPL] = smpl - smpl_min                  # index
        y[P_DEC] = dec * 128                         # raw14
        y[P_TIME] = time * 128                       # raw14
        y[P_STRT] = strt << 16                       # unipolar Q23
        y[P_END] = end << 16
        y[P_GRAN] = (gran * gran) << 9               # squared Q23: (v/128)^2
        y[P_FLUX] = flux << 16

    def init(self, track):
        y = self.y
        for i in (S_ACT, S_GAIN, S_CNT, S_REL, S_FADE):
            y[i] = 0
        y[S_SEED] = (track + SEED0) & M24

    def gran_len(self):
        return hi(mpy(4776, self.y[P_GRAN]) + acc(300))

    def rand(self):
        y = self.y
        a = mpy(y[S_SEED], 0x19660D) >> 1
        y[S_SEED] = hi(acc(lo(a)) + acc(0x6EF35F))
        return y[S_SEED]

    def trig(self, info):
        """info(bank, slot) -> (length, step)."""
        y = self.y
        if self.bank_id < 0:
            if y[P_SMPL] < UW_SLOTS:
                y[S_BANK], y[S_SLOT] = 1, y[P_SMPL]
            else:
                y[S_BANK], y[S_SLOT] = 0, y[P_SMPL] - UW_SLOTS
            self.bank = y[S_BANK]
        else:
            y[S_SLOT] = y[P_SMPL]
        length, step = info(self.bank, y[S_SLOT])
        if length == 0 or step == 0:
            y[S_ACT] = 0
            return
        y[S_STEP] = step

        def frame_at(u):
            return length if acc(u) >= acc(0x7F0000) else hi(mpy(length, u))
        start, end = frame_at(y[P_STRT]), frame_at(y[P_END])
        y[S_REV] = int(end < start)                  # END before STRT: reverse
        y[S_LO], y[S_HI] = min(start, end), max(start, end)
        y[S_GI] = y[S_PI] = y[S_LO]
        y[S_MIR] = hi(acc(y[S_LO]) + acc(y[S_HI]) - acc(1))
        b = acc(y[S_HI]) - acc(y[S_LO])
        y[S_WIN] = hi(b)
        if b < acc(64):
            y[S_ACT] = 0
            return
        y[S_GF] = y[S_PF] = y[S_REL] = y[S_FADE] = 0
        y[S_CNT] = self.gran_len()
        y[S_ENV] = y[S_GAIN] = ONE
        y[S_ACT] = 1

    def splice(self):
        y = self.y
        y[S_FADE] = 1
        y[S_OGI], y[S_OGF] = y[S_GI], y[S_GF]
        u = self.rand()
        y[T_K] = hi(mpy(hi(mpy(y[P_FLUX], 0x600000)), u))     # K = 0.75 * FLUX * U
        g = self.gran_len()
        y[T_GRAN] = g
        y[T_L64] = hi(acc(g) << 6)
        y[T_J] = hi(mpy(y[T_L64], y[T_RQ]))                    # J = GRAN * grain rate
        jp = hi(mpy(y[T_L64], y[T_RPQ]))
        y[T_CTR] = hi((acc(y[T_J]) - acc(jp)) >> 1)
        b = mpy(y[T_J], y[T_K])
        b = (b & ~M24) | y[S_PF]                     # move y:PF,b0
        b += acc(y[S_PI])
        b -= acc(y[T_CTR])
        if b < acc(y[S_LO]):
            b = acc(y[S_LO])
        top = hi(acc(y[S_HI]) - acc(1))
        if b > acc(top):
            b = acc(top)
        y[S_GI], y[S_GF] = hi(b), lo(b)
        u = self.rand()
        k1 = hi(mpy(hi(mpy(y[P_FLUX], 0x300000)), u))
        y[S_CNT] = hi(mpy(y[T_GRAN], k1) + acc(y[T_GRAN]) + acc(y[S_CNT]))

    def posgen(self, gi, gf):
        y = self.y
        a = acc(gi) + gf
        x = acc(y[T_RGI]) + y[T_RGF]
        if y[S_REV]:
            a = acc(y[S_MIR]) - a
            x = -x
        out = []
        for _ in range(32):
            out.append(hi(a))
            a += x
        if y[S_REV]:
            a = acc(y[S_MIR]) - a
        return out, a

    def render(self, read):
        """read(bank, slot, positions, n) -> list of 32 PCM words (or None on failure)."""
        y = self.y
        if y[S_ACT] == 0:
            return [0] * 32
        fading = y[S_FADE] != 0
        if not fading:                               # rates hold through crossfades
            a = (acc(y[P_PTCH]) - acc(8192)) >> 1    # half a semitone per step
            a = max(acc(-4096), min(acc(4095), a))
            s = s24(hi(a)) >> 7
            y[T_F] = ((hi(a) & 0x7F) << 16) & M24
            t = s + 72
            y[T_OCT] = octave = hi(mpy(t, 0x0AAAAB))
            n = t - 12 * octave
            m0, m1 = PITCH[n], PITCH[n + 1]
            m = hi(mpy(y[T_F], hi(acc(m1) - acc(m0))) + acc(m0))
            a = mpy(y[S_STEP], m) >> (20 - octave)
            y[T_RGI], y[T_RGF] = hi(a), lo(a)
            y[T_RQ] = hi(a << 17)
            a <<= 1
            y[T_R2I], y[T_R2F] = hi(a), lo(a)
            speed = SPEED[max(0, min(127, s24(hi(acc(y[P_TIME]) >> 7))))]
            a = mpy(y[S_STEP], speed) >> 1
            y[T_VBI], y[T_VBF] = hi(a), lo(a)
            y[T_RPQ] = hi(a << 12)
        # end fade, when the playhead reaches hi
        if y[S_REL]:
            y[S_REL] += 1
        elif acc(y[S_PI]) >= acc(y[S_HI]):
            y[S_REL] = 1
        # level
        d = max(0, min(127, s24(hi(acc(y[P_DEC]) >> 7))))
        mul = DECAY[d]
        env = y[S_ENV] if mul == ONE else hi(mpy(y[S_ENV], mul))
        y[S_ENV] = env
        if acc(env) < acc(0x40):
            y[S_ACT] = 0
        y[T_G1] = hi(mpy(env, QTR[y[S_REL]]))
        y[T_G0] = y[S_GAIN]
        y[S_GAIN] = y[T_G1]
        if y[S_REL] >= 4:
            y[S_ACT] = 0
        # gain ramps
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
            pos, a = self.posgen(y[S_OGI], y[S_OGF])
            y[S_OGI], y[S_OGF] = hi(a), lo(a)
            pcm = read(self.bank, y[S_SLOT], pos, 32)
            if pcm is None:
                y[S_ACT] = 0
                return [0] * 32
            b = acc(y[T_CO0])
            for k in range(32):
                out[k] = lim(mpy(pcm[k], hi(b)))
                b += acc(y[T_COS])
        pos, a = self.posgen(y[S_GI], y[S_GF])
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
        # count the grain down; outside crossfades, splice for the next block, or
        # early when the grain would leave the window within 8 blocks
        if y[S_REL] == 0:
            y[S_CNT] = hi(acc(y[S_CNT]) - acc(32))
            if not fading:
                if acc(y[S_CNT]) <= 0:
                    self.splice()
                elif ((acc(y[T_RGI]) + y[T_RGF]) << 8) + acc(y[S_GI]) + y[S_GF] >= acc(y[S_HI]):
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


def write_wav(path, channels):
    """channels: one list (mono) or two lists (left, right) of 24-bit words."""
    with wave.open(path, "wb") as w:
        w.setnchannels(len(channels)); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"".join((s24(v) >> 8).to_bytes(2, "little", signed=True)
                               for frame in zip(*channels) for v in frame))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input"); ap.add_argument("output")
    for name, default in (("ptch", 64), ("dec", 127), ("time", 0), ("strt", 0), ("end", 127),
                          ("gran", 64), ("flux", 0)):
        ap.add_argument("--" + name, type=int, default=default)
    ap.add_argument("--seconds", type=float, default=4.0)
    a = ap.parse_args()
    words, rate = read_wav(a.input)
    info, read = sample_services(words, round(rate / 44100 * 65536))
    tracks = [Track()]
    outs = []
    for t in tracks:
        t.set_params(ptch=a.ptch, dec=a.dec, time=a.time, strt=a.strt, end=a.end, gran=a.gran, flux=a.flux)
        t.trig(info)
        out = []
        for _ in range(int(a.seconds * 44100) // 32):
            out += t.render(read)
        outs.append(out)
    write_wav(a.output, outs)
    print("wrote", a.output)
