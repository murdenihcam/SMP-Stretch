

# **SMP-GR[anulator]**

**what it is**
An experimental granulator machine for the Elektron Machinedrum, compatible with the X.20 firmware

**parameters**

**PTCH (pitch):** Playback pitch of the grains, in half-semitone steps. 64 is the original pitch, and the full range is ±32 semitones. Pitch modulation (LFO) also moves in half-semitone steps. Pitch doesn’t change scan speed or grain length.

**SMPL (sample):** Which sample to granulate. It’s read when the track is triggered. NOTE: this means when looping the sample on full DEC, changing SMPL will not change the sound until triggered again.

- SMP-GR: UW ROM slots 1–48, then the E12 samples E1–E21.
- SMP-GM: UW ROM slots 1–48.
- SMP-G2: E12 samples 1–21.

**DEC (decay):** Overall amplitude decay. The time to fade out ranges from about 30 ms to 30 s, and 127 holds the sound forever. The default is 64, about 1 second. Grains continue for as long as the sound lasts and loop back around again. This behavior is great with longer samples and loops.

**DENS (density):** Number of grains playing at once, on average, from 0.5 (sparse, with gaps) to 3. Up to about DENS 49, grains play one at a time at full quality (44.1 kHz). Above that, they overlap at half rate (22 kHz), up to 3 at a time at maximum. Volume is adjusted so busier settings don’t get louder.

**SEEK:** Where in the sample grains are taken from, from the start (0) to the end (127). With SCAN at 64, every grain starts here. The further SCAN is from 64, the less SEEK matters, because the position is moving on its own. Assigning an LFO to SCAN while this is happening does do some interesting stuff though.

**SCAN:** Moves the grain position through the sample over time. At 64, the position is locked. Higher values scan forward and lower values scan in reverse, up to about 2× normal speed. Small turns away from 64 give very slow, fine movement. At the end of the sample, the position wraps around to the other end.

**GRAN (grain size):** Length of each grain, from about 3 ms to 740 ms; 64 is about 46 ms. Each grain fades in and out linearly over roughly its first and last quarter.

**SPRY (spray):** Random variation in where each grain starts, around the SEEK/SCAN position. It reaches the whole sample at maximum. Above 64, grains also have a growing chance of playing backwards, up to 50% at 127.
