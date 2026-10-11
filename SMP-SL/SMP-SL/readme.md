

# SMP-SL[ice]
**what it is**
A transient-detecting sample slicer and looper for the Machinedrum, compatible with the [X.20 firmware](https://github.com/jmamma/MDX) . Fun with longer samples but can also get interesting textural results with shorter ones. the magic comes with plocking the SLNO parameter (slice number!)

**parameters**
**PTCH** - half a semitone per step (±32 semitones). It changes speed as well. This interacts with TIME in interesting ways.

**SMPL** - Which sample: 1–48 are the UW ROM slots, E1–E21 the internal samples. Takes effect at the next trig.

**DEC -** 0: plays the slice once at full level. 1–126: decay from about 0.03 s to 30 s, with the slice looping in the PLAY direction while it’s audible. 127: no decay, loops forever.

**TIME** - 0: normal playback. Above 0, slows the slice down without changing pitch, using a timestretching algorithm. 42: half speed. After 50% turn, grain sizes get smaller127: frozen in place (infinite repeat). DEC at 0 means no amp envelope on the time, decay at higher levels, there is.

**PLAY** - Direction of playback. FWD: forwards. REV: backwards. BI: turns round at each end of the slice. When DEC loops, it’s checked at every loop, so you can change it while a slice is held.

**THRS** - Threshold for transient slicing to occur. higher means fewer slices made.

**SLIC** - Number of slices across the whole sample. Takes effect at the next trig.

**SLNO** - Which slice plays. Values above SLIC wrap round (for example SLNO 10 with 8 slices plays slice 2). Takes effect at the next trig.
