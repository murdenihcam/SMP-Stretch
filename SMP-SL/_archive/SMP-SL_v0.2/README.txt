SMP-SL  ROM+E12 SLICER  v0.2  (MDS user machine, X.20 firmware)
================================================================

SMP-SL\rom_e12_slicer.syx -> USR slot 4
Declared cost 3500 cycles (measured worst block 3311 + 75 overhead; limit 3951).
No machine logo yet (sprite is blank).

Changes from v0.1
-----------------
- DEC 0 (now the default) plays the slice once at full level and stops at the
  next slice point (3 ms fade at the end). 1..126 decay + loop, 127 loops forever.
- MODE and PLAY swapped: PTCH SMPL DEC TIME / MODE PLAY SLIC SLNO.
- TIME works as in SMP-ST: above 0 the playhead speed comes from TIME alone, so
  PTCH changes only the pitch. The SMP-SX test variant is retired.

Controls
--------
PTCH  pitch, half a semitone per step, +-32 semitones (64 = original). At TIME 0
      it also changes speed, like a normal sampler.
SMPL  1..48 UW ROM slots, E1..E21 internal samples          (taken at the trig)
DEC   0 = play once, no envelope. 1..126 = decay, 60 dB in about 0.03..30 s,
      looping the slice while audible. 127 = no decay, loops forever.
TIME  0 = normal. Above 0 the slice slows down at unchanged pitch (SMP-ST splice
      stretch, grain 64): 42 = half speed, 127 = frozen.
MODE  how the sample is cut                                  (taken at the trig)
        EQUA  equal slices
        EXP   slices get longer along the sample
        LOG   slices get shorter along the sample
        SED1..SED4  fixed Perlin-noise slice widths (smooth -> busy); with N
              slices the first N widths of the seed fill the whole sample
PLAY  FWD / REV / BI (BI turns round at each end of the slice). Read at every
      loop, so it can change while a slice loops.
SLIC  number of slices, 1..64                                (taken at the trig)
SLNO  which slice plays, 1..64, wrapping round past SLIC     (taken at the trig)

Each slice runs from its slice point up to the next slice point (slice 1 starts at
the very start of the sample, the last slice ends at its end). Loops and BI
turnarounds crossfade over 128 samples, finishing exactly at the slice end, so
nothing of the next slice leaks in. The first pass starts at full level.

demo\  listening renders from the bit-exact model on a synthetic drum loop.
source\  everything needed to rebuild: python gen_tables.py, python make_json.py,
build.cmd rom_e12_slicer SLOT, python simtest.py (simulator vs model, all 28
scenarios bit-exact).
