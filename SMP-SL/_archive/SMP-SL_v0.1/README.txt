SMP-SL  ROM+E12 SLICER  v0.1  (MDS user machine, X.20 firmware)
================================================================

SMP-SL\rom_e12_slicer.syx       -> USR slot 4   (the main machine)
SMP-SX_test\rom_e12_slicer_st.syx -> USR slot 5 (test variant, see TIME below)
Declared cost 3500 cycles (measured worst block 3303 + 75 overhead; limit 3951).
No machine logo yet (sprite is blank).

Controls
--------
PTCH  pitch, half a semitone per step, +-32 semitones (64 = original)
SMPL  1..48 UW ROM slots, E1..E21 internal samples          (taken at the trig)
DEC   decay, 60 dB in 0.03..30 s; 127 = no decay. The slice loops for as long
      as the sound lasts, so a long DEC loops the slice.
TIME  0 = normal (plain varispeed sampler). Above 0 the playhead slows down
      (42 = half speed, 127 = frozen) using SMP-ST's splice stretch at grain 64.
PLAY  FWD / REV / BI. BI turns round at each end of the slice. Read at every
      loop, so it can change while a slice loops.
MODE  how the sample is cut                                  (taken at the trig)
        EQUA  equal slices
        EXP   slices get longer along the sample
        LOG   slices get shorter along the sample
        SED1..SED4  fixed Perlin-noise slice widths (smooth -> busy); with N
              slices the first N widths of the seed fill the whole sample
SLIC  number of slices, 1..64                                (taken at the trig)
SLNO  which slice plays, 1..64, wrapping round past SLIC     (taken at the trig)

Each slice runs from its slice point up to the next slice point (slice 1 starts at
the very start of the sample, the last slice ends at its end). Loops and BI
turnarounds crossfade over 128 samples, finishing exactly at the slice end, so
nothing of the next slice leaks in. The first pass starts at full level.

SMP-SX (test variant): identical except that with TIME above 0 the playhead speed
comes from TIME alone and PTCH only changes the pitch, as in SMP-ST.

demo\  listening renders from the bit-exact model on a synthetic drum loop.
source\  everything needed to rebuild: python gen_tables.py, build.cmd NAME SLOT,
python simtest.py NAME (simulator vs model, all 22 scenarios bit-exact).
