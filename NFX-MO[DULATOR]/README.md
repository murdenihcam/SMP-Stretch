

# NFX-MO[dulator]
**what it is**
A multi-mode modulation effect, covering flanger, chorus, pitch and frequency shifting delays. Wild and exciting textural results abound: lots to explore and many spiralling sweet spots on this. 

**NOTE:** switching MODE does a short fade (about 1.5 ms out, 1.5 ms in) instead of jumping, so there’s a brief dip rather than a glitch. No trig is needed. A ringing feedback tail carries over into the new mode, but switching into a short delay (e.g. FLNG with low DLAY) can cut it off.

**parameters**
**MODE** - Toggles between 5 modes:

- **SPIN:** pitch-shifting delay. Feedback introduces spiral to the repeats. I love this one.
- **FLNG:** flanger
- **CHOR:** three-voice chorus (three taps 120° apart, feedback from all three). Low RATE with high FB gives a lovely clangy sound.
- **DBLR:** doubler: two slow, uneven, slightly detuned voices
- **BODE:** Bode shifter, a frequency shifting delay, causing clangy, inharmonic spirals. Another really exciting one.

**RATE** - LFO speed: 0.02–12 Hz in FLNG/DBLR, 0.05–10 Hz in CHOR. In SPIN it’s the shift, ±12 semitones. In BODE it’s the shift, ±1 kHz. 64 = no shift in SPIN and BODE.

**DPTH -** LFO depth in FLNG/CHOR/DBLR (up to 5 ms in CHOR). Window size (1.5–20 ms) in SPIN. In BODE: 0 = ring mod (static clang), 127 = pure shift (full spiral).

**FB -** Feedback. 64 = none, about 124 = unity (long trails), 125–127 = self-oscillation, below 64 = negative. In CHOR it tops out just below unity (0.98), so no self-oscillation there.

**SPRD -** Spread, per mode. FLNG adds a second tap. CHOR pulls the three voices’ delays apart (0 = the pure Monomachine-style sound). DBLR spreads the voice phase and delay. SPIN wobbles the shift (±25 cents). BODE wobbles the delay (±2 ms). This is a more subtle effect but interesting when modulated.

**ENTI -** Envelope time. This machine has a built-in envelope for modulating its delay time. At 64 (centre) it is deactivated. Left of centre = shorter delay times to longer, right = longer to shorter. Further from centre in either direction = longer envelope time. It is activated by trigs.

**DLAY -** Delay time, range dependent on mode (0.5–12 ms in CHOR).

**NBAL -** Input blend. Fully right = only the track just before, fully left = only two tracks before, centre = both. An empty neighbour track is ignored, so it can’t leak noise into the effect.