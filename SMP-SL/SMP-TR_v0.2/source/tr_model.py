#!/usr/bin/env python3
"""Bit-exact model of the transient slicer draft (SMP-TR), on top of slicer_model.

Knobs: PTCH SMPL DEC TIME / PLAY THRS SLIC SLNO. THRS takes MODE's place (Y+6,
raw14); SLIC is now the most slices to use (the strongest onsets); SLNO picks
one, modulo the count. Playback is the SMP-SL engine unchanged.

Background analysis (in RENDER, after the voice, in every block that is not a
crossfade block and not the block right after a TRIG; one step per block):
  - a new SMPL setting restarts it (SAMPLE_INFO for the length);
  - a hop: 16 pairs of neighbouring frames, the pairs 2 * STRIDE apart, read
    from a hop of 32 * STRIDE frames (STRIDE = 1 + length / 32768, at least 16
    and at most 64: hops of 11.6 .. 46 ms, at most about 1024 hops a sample);
      E   = (sum |x| + 4 * sum |x1 - x0|) / 256: (mean level + 2 * mean first
            difference) / 8, the difference term making snares and hats stand out
      env = a peak follower falling 63 % in 100 ms; ref = env (fallen, before this
            hop) + FLOOR
      a candidate where E >= EMIN, E > ref, q = ref / E <= QMAX (E at least 1.25
      times ref), past the first MINSTART frames;
    candidates within GAP_FR frames of the first merge: the onset stays at the
    first one's hop, with the strongest q;
  - GAP_FR frames later, a refine step: 32 frames 2 * STRIDE apart over the hop
    before the onset and its own; from the loudest of them back to where two in
    a row are below 1/8 of it (at most WALK_MAX steps), then one step earlier;
  - then a commit step: the onset joins the list, which keeps the MAX_ON
    strongest in position order, each with its strength rank (0 = strongest),
    in X:(r6+0..59) as position, (q << 8) | rank.

At TRIG, if the list belongs to the triggered SMPL setting (complete or still
growing), the slices are the sample start and then every listed onset with
q <= the THRS threshold (THRS 0: energy x1.25, 127: x40) and rank < SLIC - 1.
Otherwise (not analysed yet, or another SMPL) SLIC equal slices.
"""
from gen_tables import QTHR
import slicer_model as sm
from slicer_model import (acc, divq, hi, mpy, s24, M24, P_SMPL, P_SLIC, P_SLNO, P_PLAY, S_BANK,
                          S_SLOT, S_ACT, S_STEP, S_LO, S_HI, S_WIN, S_MIR, S_GI, S_PI, S_GF, S_PF, S_FADE,
                          S_REL, S_PREV, S_GREV, S_CNT, S_ENV, S_GAIN, T_LEN, T_N, T_K, MIN_WIN, GRAN, ONE,
                          UW_SLOTS)

P_THRS = 6
(A_KEY, A_LEN, A_STRIDE, A_POS, A_ENV, A_CNT, A_PPOS, A_PQ, A_PAGE, A_SKIP, A_DONE) = range(53, 64)
X_XF = 60                      # X: crossfade step at the start of this block
MAX_ON = 30
NONE = 0xFFFFFF                # A_PPOS / A_KEY: nothing
GAP_FR = 1100                  # candidates closer than this (25 ms) merge
MINSTART = 1100                # no onsets in the first 25 ms: slice 1 starts at 0
FLOOR = 1049                   # 0.001 (-60 dB) on E's scale (a level / 8), added to the reference
EMIN = 3146                    # 0.003 (-50 dB): quieter hops are never onsets
QMAX = 26214                   # Q15 0.8: E at least 1.25 times the reference
DK = 60870                     # envelope fall per hop and stride unit: 100 ms (32 / 4410)
MIN_STRIDE = 16                # shortest hop 512 frames (11.6 ms)
MAX_STRIDE = 64
REFINED = 0x7FFFFF             # A_PAGE once the pending onset has been placed
WALK_MAX = 12                  # refine: steps back from the peak at most


class TrTrack(sm.Track):
    def __init__(self, track=0, bank_id=-1):
        self.x = [0] * 64
        super().__init__(track, time_st=True, bank_id=bank_id)

    def set_params(self, ptch=64, smpl=1, dec=0, time=0, play=0, thrs=0, slic=64, slno=1):
        super().set_params(ptch=ptch, smpl=smpl, dec=dec, time=time, play=play, mode=0, slic=slic,
                           slno=slno)
        self.y[P_THRS] = thrs * 128                  # raw14

    def init(self, track):
        super().init(track)
        y = self.y
        y[A_KEY] = NONE
        y[A_CNT] = y[A_SKIP] = 0
        y[A_DONE] = 1

    def key_bank_slot(self):
        y = self.y
        if self.bank_id >= 0:
            return self.bank_id, y[P_SMPL]
        if y[P_SMPL] < UW_SLOTS:
            return 1, y[P_SMPL]
        return 0, y[P_SMPL] - UW_SLOTS

    # ---- TRIG ----
    def trig(self, info):
        y = self.y
        y[A_SKIP] = 1                                # no analysis in the TRIG block
        bank, slot = self.key_bank_slot()
        y[S_BANK], y[S_SLOT] = bank, slot
        self.bank = bank
        length, step = info(bank, slot)
        if length == 0 or step == 0:
            y[S_ACT] = 0
            return
        y[S_STEP] = step
        y[T_LEN] = length
        if y[P_SMPL] == y[A_KEY] and length != y[A_LEN]:
            y[A_KEY] = NONE                          # the sample changed (new bank): analyse again
        cap = min(y[P_SLIC], 63)                     # onsets allowed: SLIC - 1
        if y[P_SMPL] == y[A_KEY]:
            thr = QTHR[max(0, min(127, s24(hi(acc(y[P_THRS]) >> 7))))]
            ok = []
            for i in range(y[A_CNT]):
                w = self.x[2 * i + 1]
                if (w >> 8) <= thr and (w & 0xFF) < cap:
                    ok.append(self.x[2 * i])
            bounds = [0] + ok + [length]
            n = len(bounds) - 1
            k = min(y[P_SLNO], 63)
            while k >= n:
                k -= n
            y[T_N], y[T_K] = n, k
            start, end = bounds[k], bounds[k + 1]
        else:                                        # not analysed: SLIC equal slices
            n = cap + 1
            k = min(y[P_SLNO], 63)
            while k >= n:
                k -= n
            y[T_N], y[T_K] = n, k
            start = 0 if k == 0 else hi(mpy(length, divq(k, n)))
            end = length if k + 1 >= n else hi(mpy(length, divq(k + 1, n)))
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

    # ---- RENDER: the voice, then one analysis step ----
    def render(self, read, info=None):
        y = self.y
        self.step = None                             # the analysis step taken (for tests)
        self.x[X_XF] = y[S_FADE]
        out = super().render(read)
        if y[A_SKIP]:
            y[A_SKIP] = 0
        elif self.x[X_XF] == 0:
            self.analyse(read, info)
        return out

    def analyse(self, read, info):
        y = self.y
        if y[P_SMPL] != y[A_KEY]:                    # a new sample: start over
            self.step = "restart"
            y[A_KEY] = y[P_SMPL]
            length, _ = info(*self.key_bank_slot())
            y[A_LEN] = length
            y[A_STRIDE] = min(MAX_STRIDE, max(MIN_STRIDE, 1 + (length >> 15)))
            y[A_POS] = y[A_ENV] = y[A_CNT] = 0
            y[A_PPOS] = NONE
            y[A_DONE] = int(length == 0)
            return
        if y[A_DONE]:
            return
        if y[A_PPOS] != NONE and (y[A_PAGE] >= GAP_FR or y[A_POS] >= y[A_LEN]):
            if y[A_PAGE] != REFINED:
                self.step = "refine"
                self.refine(read)
            else:
                self.step = "commit"
                self.commit()
            return
        if y[A_POS] >= y[A_LEN]:
            y[A_DONE] = 1
            return
        self.step = "hop"
        h0, st = y[A_POS], y[A_STRIDE]
        pcm = read(*self.key_bank_slot(), [(h0 + (i >> 1) * 2 * st + (i & 1)) & M24 for i in range(32)], 32)
        if pcm is None:
            y[A_DONE] = 1
            return
        sx = sum(abs(s24(v)) for v in pcm)
        sd = sum(abs(s24(pcm[2 * i + 1]) - s24(pcm[2 * i])) for i in range(16))
        e = (sx + 4 * sd) >> 8
        env = y[A_ENV]
        env = env - hi(mpy(env, st * DK))
        ref = env + FLOOR
        if e >= EMIN and e > ref and h0 >= MINSTART:
            q = divq(ref, e) >> 8
            if q <= QMAX:
                if y[A_PPOS] == NONE:
                    y[A_PPOS], y[A_PQ], y[A_PAGE] = h0, q, 0
                elif q < y[A_PQ]:
                    y[A_PQ] = q
        y[A_ENV] = max(e, env)
        if y[A_PPOS] != NONE:
            y[A_PAGE] += 32 * st
        y[A_POS] = h0 + 32 * st

    def refine(self, read):
        y, x = self.y, self.x
        st = y[A_STRIDE]
        sp = 2 * st
        ws = max(0, y[A_PPOS] - 32 * st)
        pcm = read(*self.key_bank_slot(), [(ws + i * sp) & M24 for i in range(32)], 32)
        y[A_PAGE] = REFINED
        if pcm is None:
            return
        mags = [min(0x7FFFFF, abs(s24(v))) for v in pcm]
        top = max(mags)
        thr = top >> 3
        i = mags.index(top)
        steps = WALK_MAX
        while i >= 2 and steps and (mags[i - 1] >= thr or mags[i - 2] >= thr):
            i -= 1
            steps -= 1
        pos = ws + (i - 1) * sp if i else ws
        floor = x[2 * y[A_CNT] - 2] + MIN_WIN if y[A_CNT] else MINSTART
        y[A_PPOS] = max(pos, floor)

    def commit(self):
        """Add the pending onset to the list, keeping the MAX_ON strongest."""
        y, x = self.y, self.x
        q, pos = y[A_PQ], y[A_PPOS]
        y[A_PPOS] = NONE
        cnt, r = y[A_CNT], 0
        for i in range(cnt):
            w = x[2 * i + 1]
            if (w >> 8) <= q:
                r += 1
            else:
                x[2 * i + 1] = w + 1
        if cnt == MAX_ON:
            if r >= MAX_ON:
                return                               # weaker than everything kept
            d = next(i for i in range(cnt) if x[2 * i + 1] & 0xFF == MAX_ON)
            x[2 * d:2 * cnt - 2] = x[2 * d + 2:2 * cnt]
            cnt -= 1
        x[2 * cnt], x[2 * cnt + 1] = pos, (q << 8) | r
        y[A_CNT] = cnt + 1
