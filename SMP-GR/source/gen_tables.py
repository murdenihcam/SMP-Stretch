#!/usr/bin/env python3
"""Write tables.inc, the constant tables of granular_engine.inc and granular_dsp_model.py.

Knob laws (settings 0..127; tune them here, then rebuild):
  PITCH  2^((k - 64) / 24) / 8 for PTCH settings k = 0..127 (half a semitone per
         step; modulation moves in these steps too)
  FRAMES frames to read for a buffer's 2-bit slot mask: 0, 16, 32, 32
  DECAY  envelope multiplier per 32-sample block: DEC 0..126 fall 60 dB in
         DEC_MIN_S .. DEC_MAX_S seconds; 127 holds the level
  GRAN   grain length NB in 32-sample blocks (GRAN_MIN .. GRAN_MAX samples,
         exponential) | fade shift << 16: a grain fades in over its first and out
         over its last 2^(23 - shift) blocks, the power of two nearest NB * FADE_FRAC
         (at least 2), so the fade position t / fade is t << shift as Q23
  KD     2^22 / overlap: DENS sets the average number of grains sounding at once,
         DENS_MIN .. DENS_MAX, exponential; a grain starts every GRAN / overlap
  NORM   level correction 1 / sqrt(max(1, overlap))
  TIER   grain quality for DENS: 1 full rate (overlap up to FULL_UPTO), else 2 half rate
  SCAN   scan speed / 2 (signed Q23): +-SCAN_MAX x native speed, squared law
  SPRAY  random start range as a fraction of the sample, (SPRY/127)^SPRAY_POW
  REVT   reverse threshold 2p - 1, p = 0 up to SPRY 64, then up to 0.5 at 127
  FREE   for tier 1..2 and the slot state s (bits 0-3: slots in use; bit 4 / 5:
         slots 0,1 / 2,3 hold a full-rate grain): the first slot v a new grain can
         take (full rate: two aligned slots) with the block's worst-case cycles
         within VBUDGET, packed as v | state bits it adds << 2; -1 when none. The
         cycle budget is applied here, offline, so the DSP code only looks it up.

Read slots: SAMPLE_READ is called at most twice per block (buffer 0 = slots 0,1,
buffer 1 = slots 2,3), 16 frames per slot.
"""
import math
from pathlib import Path

DEC_MIN_S, DEC_MAX_S = 0.03, 30.0
GRAN_MIN, GRAN_MAX = 128, 32768
FADE_FRAC = 0.25
DENS_MIN, DENS_MAX = 0.5, 3.0
FULL_UPTO = 1.0
SCAN_MAX = 2.0
SPRAY_POW = 3.0

# Cycle model of one RENDER, from the simulator (see simtest.py). A grain is only
# started if BASE + reads and buffers + the grains' PCOST stays within LIMIT.
PCOST = [0, 301, 211]          # per grain, tier 1..2, including a free (simtest.py fit)
BUF_CYCLES = 167               # own code per read buffer in use, on top of its SAMPLE_READ
BASE_CYCLES = 859              # worst block less grains and buffers, + margin (simtest.py)
LIMIT = 3951 - 75              # per-track limit less firmware overhead
VBUDGET = LIMIT - BASE_CYCLES  # what reads, buffers and grains may use

ONE = 0x7FFFFF


def q23(v):
    return max(-0x800000, min(ONE, round(v * 2 ** 23))) & 0xFFFFFF


def overlap(k):
    return DENS_MIN * (DENS_MAX / DENS_MIN) ** (k / 127)


PITCH = [round(2 ** ((k - 64) / 24) / 8 * 2 ** 23) for k in range(128)]   # PTCH setting k, / 8
DECAY = [min(ONE, round(10 ** (-3 * 32 / (44100 * DEC_MIN_S * (DEC_MAX_S / DEC_MIN_S) ** (d / 126)))
                        * 2 ** 23)) for d in range(127)] + [ONE]
NB = [max(4, round(GRAN_MIN * (GRAN_MAX / GRAN_MIN) ** (k / 127) / 32)) for k in range(128)]
FADE_SHIFT = [23 - max(1, round(math.log2(n * FADE_FRAC))) for n in NB]   # fade = 2^(23 - shift) blocks
GRAN = [n | s << 16 for n, s in zip(NB, FADE_SHIFT)]
KD = [min(ONE, round(2 ** 22 / overlap(k))) for k in range(128)]
NORM = [q23(1 / math.sqrt(max(1.0, overlap(k)))) for k in range(128)]
TIER = [(1 if overlap(k) <= FULL_UPTO else 2) for k in range(128)]
SCAN = [q23(math.copysign(((k - 64) / 64) ** 2 * SCAN_MAX / 2, k - 64)) for k in range(128)]
SPRAY = [q23((k / 127) ** SPRAY_POW) for k in range(128)]
REVT = [q23(2 * max(0.0, (k - 64) / 63) * 0.5 - 1) for k in range(128)]
FRAMES = [0, 16, 32, 32]                                   # per buffer: 2-bit slot mask -> frames read
RC = [0 if n == 0 else 202 + 33 * FRAMES[n] for n in range(4)]
RCB = [0 if n == 0 else RC[n] + BUF_CYCLES for n in range(4)]   # with the buffer's own code


def state_cycles(s):
    """Worst-case cycles of a block with slot state s (bits 0-3 slots in use, bit 4 /
    bit 5: slots 0,1 / 2,3 hold a full-rate grain), besides BASE."""
    full = (s >> 4 & 1) + (s >> 5 & 1)
    half = bin(s & 15).count("1") - 2 * full
    return RCB[s & 3] + RCB[s >> 2 & 3] + full * PCOST[1] + half * PCOST[2]


def free_slot(tier, s):
    """The first slot a grain of this tier can start in from state s within the cycle
    budget: v | the state bits it adds << 2; -1 when none."""
    for v in range(0, 4, 3 - tier):
        bits = (3 << v | 16 << (v >> 1)) if tier == 1 else 1 << v
        if s & bits & 15 == 0 and state_cycles(s | bits) <= VBUDGET:
            return v | bits << 2
    return 0xFFFFFF                       # -1


FREE = [free_slot(t, s) for t in (1, 2) for s in range(64)]

LAYOUT = [("PITCH", PITCH), ("FRAMES", FRAMES), ("DECAY", DECAY), ("GRAN", GRAN), ("KD", KD), ("NORM", NORM),
          ("TIER", TIER), ("SCAN", SCAN), ("SPRAY", SPRAY), ("REVT", REVT), ("FREE", FREE)]
AT = {}
_pos = 0
for _name, _vals in LAYOUT:
    AT[_name] = _pos
    _pos += len(_vals)
TABLES = [v for _, vals in LAYOUT for v in vals]


def dc(values):
    return ["        dc      " + ",".join("$%06x" % (v & 0xFFFFFF) for v in values[i:i + 8])
            for i in range(0, len(values), 8)]


if __name__ == "__main__":
    lines = ["; Generated by gen_tables.py: do not edit."]
    lines += ["TB_%-6s equ %d" % (name, AT[name]) for name, _ in LAYOUT]
    lines += ["; budget %d cycles for reads, buffers and grains (PCOST %s), BASE %d" % (VBUDGET, PCOST[1:], BASE_CYCLES)]
    lines += ["TABLES:"]
    for name, vals in LAYOUT:
        lines += ["; " + name] + dc(vals)
    Path(__file__).with_name("tables.inc").write_text("\n".join(lines) + "\n")
    print("wrote tables.inc: %d words; grain %d..%d blocks; overlap %.2f..%.2f; budget %d"
          % (len(TABLES), NB[0], NB[-1], overlap(0), overlap(127), VBUDGET))
