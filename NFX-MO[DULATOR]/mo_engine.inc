; NFX-MO v0.10 engine (included by mo.asm56k with GRIT 0, mo_grit.asm56k with GRIT 1).
;
; A modulated-delay effect on the track before, after Valhalla Space Modulator:
;   SPIN  pitch-shifting delay (two crossfaded sawtooth taps); with feedback the
;         repeats spiral up or down
;   FLNG  flanger, DBLR doubler (sine LFO)
;   CHOR  3-tap chorus after the Monomachine's (NFX-MC v0.1): three taps 120 degrees
;         apart on one LFO, feedback from their sum; slow + high FB = clangy combs
;   BODE  frequency-shifting delay (Hilbert all-pass pair + quadrature oscillator):
;         clangy, inharmonic spirals; DPTH 0 ring modulation ... 127 pure shift
;
; MODE changes fade: the wet (output and feedback) fades out over 2 blocks (1.5 ms),
; the new mode starts in a silent block (the ring takes the input only; the new
; mode's taps start at their targets, the BODE filters are cleared), then fades in
; over 2 blocks.
;
; Import (JSON):
;   TRACK_MEMORY        kind 2, symbol 6: track 1's 1,536 words of external memory
;   X_*, Y_* labels     kinds 3 and 4, symbols 7 and 8: the shared temporary areas
;
; Output is wet only: blend with the levels of this track and the source track
; (the NFX output is sample-aligned with it).
;
; The delay line is a 1,024-word ring (23 ms) aligned to 1,024 words inside this
; track's region (modulo addressing, M = 1023); INIT clears it 256 words a block,
; silent meanwhile. Delays are Q13 sample counts (one sample = 8192).
;
; CHOR's knobs follow NFX-MC: RATE = SPD 0.05...10 Hz, DPTH = DEP (0...5 ms, squared),
; DLAY = DEL 0.5...12 ms, FB 64 none ... 127 0.98 (no self-oscillation; left of 64
; negative).
;
; SPRD: FLNG a second, offset flanger tap; CHOR pulls the three taps' delays apart
; (+-20 % x SPRD^2; 0 = NFX-MC exactly);
; DBLR the second voice's delay and phase; SPIN a slow wobble of the shift (up to
; +-25 cents); BODE a slow wobble of the delay (up to +-2 ms).
;
; Envelope (ENTI): TRIG restarts it. The delay jumps by about 30 % of DLAY's range
; and releases exponentially back to DLAY: longer then back (right of 64) or
; shorter then back (left of 64); |ENTI - 64| sets the time constant, 3 ms ... 3 s;
; 64: off.
;
; Input (NBAL): an equal-power blend of the track before (T1) and two before (T2):
; 127 T1 only, 0 T2 only (exactly), centre both at -3 dB. An input whose buffer has
; kept the same first and last words for 8 blocks in a row (an empty track: no
; machine rewrites it) counts as silent; any change, e.g. a sound starting anywhere
; in the block, lets it through at once.
;
; State guards: the ring's address is checked every block against a copy kept
; inverted (S_RINGN); when that fails the write pointer is also put back into the
; ring (only this code writes it); clearing always stays in the ring. A bad address is repaired if it is still a sane ring address (e.g. a new
; version was sent without INIT), else rebuilt from the saved track number (a clean
; restart, as INIT), with one silent block; if nothing can be trusted the track is
; silent and touches no memory until INIT runs again.
;
; DC: the input mix's offset (every 4th sample, smoothed over ~512 blocks, 0.37 s) is
; taken off every ring write, so an offset in the source cannot build up in the
; feedback loop. Not in BODE: its shifter moves an offset away from DC on every pass
; (and the per-block steps of the estimate would add faint block-rate sidebands).
;
; Feedback: ring <- in - DC + sat(fb wet).
;   GRIT 0: sat(f) = f - f|f|/4 (|f| <= 2), smooth, up to full scale
;   GRIT 1: f hard-clipped at +-1/2 and rounded to 8 bits every pass
;
; Y:(r6+1) MODE  0 SPIN 1 FLNG 2 CHOR 3 DBLR 4 BODE
; Y:(r6+2) RATE  raw14: LFO rate 0.02...12 Hz; SPIN +-12 semitones, BODE +-1 kHz (64 = 0)
; Y:(r6+3) DPTH  unipolar Q23: LFO depth; SPIN window; BODE ring mod (0) ... shift (127)
; Y:(r6+4) FB    raw14: feedback (FB_TAB): 64 none, ~124 unity, 127 +1.05, 0 -1.05
; Y:(r6+5) SPRD  unipolar Q23: spread (per mode)
; Y:(r6+6) ENTI  raw14: envelope time and direction (64 = off)
; Y:(r6+7) DLAY  unipolar Q23: base delay (per mode)
; Y:(r6+8) NBAL  bipolar Q23: T2 ... both ... T1

P_MODE  equ     1
P_RATE  equ     2
P_DPTH  equ     3
P_FB    equ     4
P_SPRD  equ     5
P_ENTI  equ     6
P_DLAY  equ     7
P_NBAL  equ     8
S_RING  equ     9                       ; the ring's first word (1,024-aligned)
S_W     equ     10                      ; write pointer
S_PH    equ     11                      ; LFO phase, 2^24 a cycle
S_D1    equ     12                      ; tap delays now (Q13)
S_D2    equ     13
S_D3    equ     14
S_AM    equ     15                      ; the mode being rendered (MODE fades to it)
S_CLR   equ     16                      ; ring words cleared so far
S_SU    equ     17                      ; SPIN ramp phase
S_DM    equ     18                      ; SPIN centre delay now
S_ENV   equ     19                      ; envelope, ONE at TRIG, decaying
S_OSC   equ     20                      ; BODE oscillator phase
S_FG    equ     21                      ; the fade gain at the next block's start
T_D1    equ     22                      ; this block: tap delay targets
T_D2    equ     23
T_D3    equ     24
T_A     equ     25                      ; mode scratch
T_B     equ     26
T_C     equ     27
T_E     equ     28
T_K     equ     29                      ; NBAL: the T1 gain this block
T_M     equ     30                      ; feedback / 2 this block
T_OFF   equ     31                      ; envelope delay offset this block (Q13)
T_R5    equ     32                      ; this block: the T1 buffer's address
S_SP    equ     33                      ; SPIN / BODE spread wobble phase
T_EV    equ     34                      ; the envelope this block: +-e, or 0
T_N2    equ     35                      ; NBAL: the T2 gain this block
T_FG    equ     36                      ; the fade gain at this block's start (0: snap)
T_DG    equ     37                      ; the fade gain's step a sample
S_CP    equ     38                      ; CHOR LFO phase
T_GN    equ     39                      ; the LFO modes: the fade gain now
S_RINGN equ     54                      ; S_RING inverted (the check word)
S_TRK   equ     55                      ; the track number, from INIT
S_TRKN  equ     56                      ; ... inverted
S_Q1    equ     57                      ; T1: words 0 and 31 last block, the repeat count
S_Q2    equ     60                      ; T2: the same
T_N5    equ     63                      ; this block: the T2 buffer - the T1 buffer
H_T     equ     40                      ; BODE all-pass histories, [x-2, x-1] per signal:
H_P1    equ     42                      ; the tap signal, then path 1's three section
H_P2    equ     48                      ; outputs, then path 2's three. A section's new
                                        ; history is staged at the same offset in X and
                                        ; committed once the pair has run

C_G1    equ     0                       ; X: per-sample coefficients, in loop order (CHOR)
C_G2    equ     1
C_G3    equ     2
C_DG    equ     3                       ; the fade gain's step
C_FB2   equ     4
C_N2    equ     5                       ; the T2 gain
C_E     equ     6                       ; the input's DC
C_N1    equ     7                       ; the T1 gain
NCOEF   equ     8
D_FB2   equ     2                       ; FLNG / DBLR (two taps): G1 G2 FB2 N2 E N1
D_N2    equ     3
D_E     equ     4
D_N1    equ     5
NCOEF2  equ     6
X_DC    equ     54                      ; X: the input's DC (smoothed) (X 42-53 holds
X_OC    equ     55                      ; the BODE all-pass staging) BODE oscillator: cos
X_OS    equ     56                      ; ... and sin, carried between blocks
XB      equ     8                       ; X: BODE path 1 buffer, 32 words

S       equ     8192                    ; one sample, Q13
MIN_D   equ     2*S
MAX_D   equ     1020*S
BODE_MIN equ    34*S                    ; BODE reads whole blocks: at least 33 samples back
RING    equ     1024
CLEAR   equ     256
SPW_INC equ     4504                    ; SPIN wobble: 0.37 Hz, per block
WOBK    equ     1896                    ; SPIN wobble: 25 cents, as a slope / 64
FSTEP   equ     131071                  ; the fade gain's step a sample: 2 blocks 0 <-> FULL
BSTEP   equ     32*FSTEP
FULL    equ     2*BSTEP

ONE     equ     $7fffff
HALF    equ     $400000
EIGHTH  equ     $200000                 ; an eighth of a cycle (NBAL)
PH3     equ     $555555                 ; a third of a cycle
PH6     equ     $aaaaaa                 ; two thirds
G3      equ     $2aaaab                 ; 1/3
K97     equ     8136949
K03     equ     251658
K90     equ     7549747
K60     equ     5033165
K40     equ     3355443
K62     equ     5201035
K20     equ     1677722
K225    equ     1887437                 ; 0.225
K775    equ     6501171                 ; 0.775

; ---- the end of every sample: B = wet, y0 = fb / 2, r6 -> the T2 gain in the
; coefficients (then the DC, the T1 gain), r5 -> T1, n5 = T2 - T1.
; out = wet; ring <- in - DC + sat(fb wet)
FBTAIL  macro
        move    b,x0                    ; the output
        mpy     x0,y0,b x:(r6)+,y0      ; h = fb out / 2 ; T2 gain
        move    x0,y:(r7)+
    if GRIT
        asl     #2,b,b                  ; 2 f
        move    b,x1                    ; clipped: f at +-1/2
        move    x1,b
        add     #>$008000,b
        and     #>$ff0000,b             ; rounded to 8 bits
        asr     b       x:(r6)+,y1      ; ; the input's DC
    else
        move    b,x1                    ; h, clipped to +-1
        abs     b
        move    b,y1                    ; |h|
        mpy     -x1,y1,b
        asr     b       x:(r6)+,y1      ; ; the input's DC
        add     x1,b                    ; h - h|h|/2
        asl     b                       ; = f - f|f|/4 with f = 2h
    endif
        sub     y1,b    y:(r5+n5),x0    ; - the DC ; T2
        mac     x0,y0,b x:(r6)+,y0      ; T1 gain
        move    y:(r5)+,x0              ; T1
        mac     x0,y0,b
        move    (r6)-n6
        move    b,y:(r0)+               ; into the ring
        endm

        section NFXMO

; ---------------------------------------------------------------- RENDER
RENDER:
        movec   #>$ffffff,m6
        move    y:(r6+S_RING),a         ; the ring's address must match its check word
        move    y:(r6+S_RINGN),x0
        eor     x0,a
        not     a
        bne     RING_FIX
RENDER_GO:
        move    y:(r6+S_CLR),a
        move    #>RING,x0
        cmp     x0,a
        blt     CLEARING

        ; NBAL: T1 gain sin(pi/4 (1 + NBAL)) = NBAL_TAB[n], T2 gain NBAL_TAB[128 - n]
        move    y:(r6+P_NBAL),a
        asr     #17,a,a                 ; -64...63
        move    #>64,x0
        add     x0,a
        move    a1,n0
        move    a1,n1
NBAL_ADDR:
        move    #>NBAL_TAB,r0
NBAL2_ADDR:
        move    #>NBAL_TAB+128,r1
        lua     (r0)+n0,r0
        lua     (r1)-n1,r1
        ; the neighbour buffers (for SETIO), and the empty-track guard: an input whose
        ; words 0 and 31 have equalled last block's for 8 blocks in a row (a buffer no
        ; machine rewrites) is silent; the count = identical blocks + 1, at most 9
        move    y:$7f0,r4               ; this track's neighbour descriptor
        lua     (r6+S_Q1),r5            ; T1 words, count; T2 words, count
        move    y:(r4+1),r2             ; T1
        move    y:(r4+2),r3             ; T2
        move    r2,y:(r6+T_R5)
        move    r3,a
        move    r2,x0
        sub     x0,a
        move    a1,y:(r6+T_N5)
        move    #0,y0
        move    #1,x1
        move    #9,y1
        move    y:(r2),a
        move    y:(r5),x0
        move    a1,y:(r5)+
        eor     x0,a                    ; word 0 changed?
        move    y:(r2+31),b
        move    y:(r5),x0
        move    b1,y:(r5)+
        eor     x0,b                    ; word 31?
        move    a1,x0
        or      x0,b
        move    y:(r5),a                ; the count
        tne     y0,a                    ; restarts on a change
        add     x1,a
        cmp     y1,a
        tgt     y1,a                    ; at most 9
        move    a,y:(r5)+
        movem   p:(r0),b
        tge     y0,b                    ; 8 identical blocks in a row: silent
        move    b,y:(r6+T_K)          ; T1
        move    y:(r3),a
        move    y:(r5),x0
        move    a1,y:(r5)+
        eor     x0,a                    ; word 0 changed?
        move    y:(r3+31),b
        move    y:(r5),x0
        move    b1,y:(r5)+
        eor     x0,b                    ; word 31?
        move    a1,x0
        or      x0,b
        move    y:(r5),a                ; the count
        tne     y0,a                    ; restarts on a change
        add     x1,a
        cmp     y1,a
        tgt     y1,a                    ; at most 9
        move    a,y:(r5)+
        movem   p:(r1),b
        tge     y0,b                    ; 8 identical blocks in a row: silent
        move    b,y:(r6+T_N2)          ; T2
        ; DC: the input mix's mean over every 4th sample of this block, smoothed over
        ; ~512 blocks (FBTAIL takes it off every ring write; slow, so its per-block steps
        ; stay ~70 dB down)
        move    #4,n2
        move    #4,n3
        clr     a
        move    y:(r6+T_K),y0
        move    y:(r2)+n2,x0
        rep     #8
        mac     x0,y0,a y:(r2)+n2,x0
        move    y:(r6+T_N2),y0
        move    y:(r3)+n3,x0
        rep     #8
        mac     x0,y0,a y:(r3)+n3,x0
        asr     #12,a,a                 ; the mean / 512
        move    x:(r6+X_DC),b
        add     b,a
        asr     #9,b,b
        sub     b,a                     ; D + (mean - D) / 512
        move    a,x:(r6+X_DC)
        ; feedback
        move    y:(r6+P_FB),a
        asr     #7,a,a
        move    a1,n0
FB_ADDR:
        move    #>FB_TAB,r0
        lua     (r0)+n0,r0
        nop
        movem   p:(r0),x0
        move    x0,y:(r6+T_M)           ; feedback / 2
        bsr     ENVELOPE
        ; the MODE fade: down while MODE differs from the active mode, a silent block to
        ; switch once at 0, then back up to FULL. T_FG = this block's starting gain,
        ; T_DG = its step a sample (sample n of the block gets T_FG + (n + 1) T_DG)
        ; (clamped at every step, so any start value - e.g. memory left from another
        ; machine when INIT has not run - still reaches 0 and switches)
        move    y:(r6+S_FG),a
        clr     b
        tst     a
        tlt     b,a                     ; g = max(g, 0)
        move    y:(r6+P_MODE),x0
        move    y:(r6+S_AM),b
        cmp     x0,b
        tfr     a,b
        beq     <FD_UP
        tst     a
        beq     GAP
        move    #>BSTEP,x0
        sub     x0,b
        move    #0,x0
        tlt     x0,b                    ; down to 0 at most
        bra     <FD_SET
FD_UP:
        move    #>BSTEP,x0
        add     x0,b
        move    #>FULL,x0
        cmp     x0,b
        tgt     x0,b
FD_SET:
        move    a,y:(r6+T_FG)
        move    b,y:(r6+S_FG)
        sub     a,b
        asr     #5,b,b
        move    b,y:(r6+T_DG)

        move    y:(r6+S_AM),a
        tst     a
        beq     SPIN
        cmp     #4,a
        beq     BODE
        ; the LFO modes: defaults (the two-tap layout; CHOR rewrites its own)
        clr     b
        move    b,x:(r6+C_G2)
        move    y:(r6+T_M),x0
        move    x0,x:(r6+D_FB2)
        move    y:(r6+T_N2),x0
        move    x0,x:(r6+D_N2)
        move    x:(r6+X_DC),x0
        move    x0,x:(r6+D_E)
        move    y:(r6+T_K),x0
        move    x0,x:(r6+D_N1)
        move    #>MIN_D,x0
        move    x0,y:(r6+T_D2)
        move    x0,y:(r6+T_D3)
        cmp     #2,a
        beq     M_CHOR
        bgt     M_DBLR
        bra     M_FLNG

; ---- FLNG: D = 0.1...10 ms, swept D (1 +- 0.9 DPTH sin); SPRD adds a second tap
; at D (1 + SPRD / 2), SPRD x 180 degrees later, mixed in at SPRD / 2
M_FLNG:
        bsr     LFOPH
        move    #>131*S,y0
        bsr     ENVOFF
        move    #>436*S,y1
        move    #>4*S,b
        bsr     DSQ
        move    x1,y:(r6+T_A)           ; D
        move    y:(r6+P_DPTH),x0
        move    #>K90,y0
        mpy     x0,y0,a
        move    a,y:(r6+T_B)            ; m
        clr     a
        move    a,x0
        bsr     FVOICE
        move    a,y:(r6+T_D1)
        move    y:(r6+P_SPRD),x0
        mpy     x0,#1,a
        move    a,x0
        move    x0,y:(r6+T_C)           ; SPRD / 2
        move    y:(r6+T_A),y0
        mpy     x0,y0,a
        add     y0,a
        move    a,y:(r6+T_A)
        move    y:(r6+P_SPRD),x0
        bsr     FVOICE
        move    a,y:(r6+T_D2)
        move    y:(r6+T_C),x0
        move    x0,x:(r6+C_G2)
        move    #>ONE,a
        sub     x0,a
        move    a,x:(r6+C_G1)
        bra     TAIL

; ---- CHOR: NFX-MC's 3-tap chorus. B = 220 S DPTH^2 (5 ms), Dc = 22 S + 508 S DLAY
; + B; tap k = Dc (1 + (k - 2) q) + B sin(phase + (k - 1)/3 cycle), q = 0.2 SPRD^2;
; gains 1/3; its own LFO (SPD_TAB) and feedback curve (CFB_TAB)
M_CHOR:
        move    #>152*S,y0
        bsr     ENVOFF
        move    y:(r6+P_RATE),a
        asr     #7,a,a
        move    a1,n0
SPD_ADDR:
        move    #>SPD_TAB,r0
        lua     (r0)+n0,r0
        move    y:(r6+S_CP),a
        movem   p:(r0),x0
        add     x0,a
        move    a1,y:(r6+S_CP)
        move    y:(r6+P_FB),a
        asr     #7,a,a
        move    a1,n0
CFB_ADDR:
        move    #>CFB_TAB,r0
        lua     (r0)+n0,r0
        nop
        movem   p:(r0),x0
        move    x0,x:(r6+C_FB2)         ; feedback / 2
        move    y:(r6+P_DPTH),x0
        mpy     x0,x0,a
        move    a,x0
        move    #>220*S,y0
        mpy     x0,y0,a
        move    a,y:(r6+T_B)            ; B
        move    #>508*S,y1
        move    #>22*S,b
        bsr     DLIN
        move    y:(r6+T_B),a
        add     x1,a
        move    a,y:(r6+T_E)            ; Dc
        move    y:(r6+P_SPRD),x0
        mpy     x0,x0,a
        move    a,x0
        move    #>K20,y0
        mpy     x0,y0,a
        move    a,y:(r6+T_C)            ; q
        move    a,y0
        move    y:(r6+T_E),x0
        mpy     -x0,y0,a
        add     x0,a
        move    a,y:(r6+T_A)            ; Dc (1 - q)
        clr     a
        move    a,x0
        bsr     CHV
        move    a,y:(r6+T_D1)
        tfr     y1,b                    ; s1
        move    y:(r6+T_E),x0
        move    x0,y:(r6+T_A)           ; Dc
        move    #>PH3,x0
        bsr     CHV
        move    a,y:(r6+T_D2)
        add     y1,b                    ; s1 + s2
        move    y:(r6+T_E),x0
        move    y:(r6+T_C),y0
        mpy     x0,y0,a
        add     x0,a
        move    a,y:(r6+T_A)            ; Dc (1 + q)
        neg     b
        move    b,x0                    ; s3 = -(s1 + s2), 240 degrees on
        bsr     CHV_S
        move    a,y:(r6+T_D3)
        move    #>G3,x0
        move    x0,x:(r6+C_G1)
        move    x0,x:(r6+C_G2)
        move    x0,x:(r6+C_G3)
        move    y:(r6+T_N2),x0
        move    x0,x:(r6+C_N2)
        move    x:(r6+X_DC),x0
        move    x0,x:(r6+C_E)
        move    y:(r6+T_K),x0
        move    x0,x:(r6+C_N1)
        bra     TAIL

; ---- DBLR: two voices at D = 10...23 ms and D (1 - 0.6 SPRD), slow uneven wobble
; (0.6 sin(t) + 0.4 sin(3t) and 0.6 sin(t') + 0.4 sin(5t)), t' = t + SPRD / 3 cycle;
; sin 3t and sin 5t come from s = sin t (Chebyshev identities)
M_DBLR:
        bsr     LFOPH
        move    #>168*S,y0
        bsr     ENVOFF
        move    #>560*S,y1
        move    #>440*S,b
        bsr     DLIN
        move    x1,y:(r6+T_E)           ; D
        move    x1,y:(r6+T_A)
        move    #>40*S,y1
        bsr     SPAN
        move    y1,y:(r6+T_B)           ; span
        move    y:(r6+S_PH),x0
        bsr     SIN
        move    x0,x:(r6+XB)            ; s = sin t (XB is free outside BODE)
        move    #>K60,y0
        mpy     x0,y0,a
        move    a,y:(r6+T_C)
        mpy     x0,x0,a                 ; sin 3t = 4 s (3/4 - s^2)
        move    a,y0
        move    #>$600000,a
        sub     y0,a
        move    a,y0
        mpy     x0,y0,a
        asl     #2,a,a
        move    a,x0
        move    #>K40,y0
        mpy     x0,y0,a
        move    y:(r6+T_C),x0
        add     x0,a
        move    a,x0
        move    y:(r6+T_B),y0
        mpy     x0,y0,a
        move    y:(r6+T_A),x0
        add     x0,a
        move    a,y:(r6+T_D1)
        move    y:(r6+P_SPRD),x0
        move    #>K60,y0
        mpy     x0,y0,a
        move    a,y0
        move    y:(r6+T_E),x0
        mpy     -x0,y0,a
        add     x0,a
        move    a,y:(r6+T_A)            ; D (1 - 0.6 SPRD)
        move    y:(r6+P_SPRD),x0
        move    #>PH3,y0
        mpy     x0,y0,a
        move    a,x0
        bsr     LSIN
        move    #>K60,y0
        mpy     x0,y0,a
        move    a,y:(r6+T_C)
        move    x:(r6+XB),x0            ; sin 5t = 16 s (u^2 - 1.25 u + 0.3125), u = s^2
        mpy     x0,x0,a
        move    x0,x1                   ; s
        move    a,x0                    ; u
        mpy     x0,x0,a
        sub     x0,a
        move    #>$200000,y0
        mac     -x0,y0,a
        move    #>$280000,y0
        add     y0,a
        move    a,y0
        mpy     x1,y0,a
        asl     #4,a,a
        move    a,x0
        move    #>K40,y0
        mpy     x0,y0,a
        move    y:(r6+T_C),x0
        add     x0,a
        move    a,x0
        move    y:(r6+T_B),y0
        mpy     x0,y0,a
        move    y:(r6+T_A),x0
        add     x0,a
        move    a,y:(r6+T_D2)
        move    #>HALF,x0
        move    x0,x:(r6+C_G1)
        move    x0,x:(r6+C_G2)
        bra     TAIL

; ---- clearing the ring after INIT; silent meanwhile
CLEARING:
        clr     b
        tst     a
        tlt     b,a                     ; (a negative count: from 0)
        move    a1,x0
        move    #>RING-1,b
        and     x0,b                    ; inside the ring
        move    y:(r6+S_RING),x0
        add     x0,b
        move    b1,r0
        movec   #>RING-1,m0
        clr     b
        rep     #CLEAR
        move    b,y:(r0)+
        movec   #>$ffffff,m0
        move    #>CLEAR,x0
        add     x0,a
        move    a1,y:(r6+S_CLR)
        rep     #32
        move    b,y:(r7)+
        rts

;---- the old mode has faded out: switch to MODE in a silent block (x0 = MODE). The
; ring takes the input only; the BODE filters are cleared; next block the new mode
; starts its taps at their targets and fades in.
GAP:
        move    x0,y:(r6+S_AM)
        clr     a
        move    a,x:(r6+XB-1)
        move    a,x:(r6+X_OS)           ; the BODE oscillator starts at cos 1
        move    #>ONE,x1
        move    x1,x:(r6+X_OC)
        lua     (r6+H_T),r0
        rep     #14
        move    a,y:(r0)+
        move    y:(r6+T_N2),y0
        move    y:(r6+T_K),y1
        bsr     SETIO
        clr     a
        dor     #32,GAP_END
        move    y:(r5+n5),x0            ; T2
        mpy     x0,y0,b y:(r5)+,x1      ; T1
        mac     x1,y1,b a,y:(r7)+       ; out: silence
        move    b,y:(r0)+               ; into the ring
GAP_END:
        move    r0,y:(r6+S_W)
        rts

; ---------------------------------------------------------------- the LFO modes' block
TAIL:
        ; add the envelope, clamp each target, glide from where the tap is now (or, the
        ; first block after a mode switch, start at the target)
        move    #>MIN_D,x1
        move    #>MAX_D,y1
        move    y:(r6+T_OFF),y0
        move    y:(r6+T_D1),a
        add     y0,a
        cmp     x1,a
        tlt     x1,a
        cmp     y1,a
        tgt     y1,a
        move    y:(r6+T_FG),b
        tst     b
        move    y:(r6+S_D1),b
        teq     a,b
        move    b,x0
        sub     x0,a
        asr     #5,a,a
        move    a1,n2
        move    x0,r2
        move    y:(r6+T_D2),a
        add     y0,a
        cmp     x1,a
        tlt     x1,a
        cmp     y1,a
        tgt     y1,a
        move    y:(r6+T_FG),b
        tst     b
        move    y:(r6+S_D2),b
        teq     a,b
        move    b,x0
        sub     x0,a
        asr     #5,a,a
        move    a1,n3
        move    x0,r3
        move    y:(r6+S_AM),a
        cmp     #2,a
        beq     TAIL3
        ; FLNG / DBLR: two taps; the fade gain in r4
        move    y:(r6+T_FG),r4
        move    y:(r6+T_DG),n4
        bsr     SETIO
        move    #NCOEF2,n6
        dor     #32,LOOP2_END
        ; tap 1
        move    r2,x1
        mpy     x1,#13,a
        move    (r2)+n2
        move    a1,n0
        move    a0,y1                   ; the fraction, unsigned
        lua     (r0)-n0,r1
        move    x:(r6)+,y0              ; g1
        move    y:(r1)-,x0              ; the newer sample
        move    y:(r1),x1               ; the older one
        mpysu   x1,y1,a
        macsu   -x0,y1,a                ; 2 f (older - newer)
        asr     a       (r4)+n4         ; ; the fade gain steps
        add     x0,a                    ; t1
        ; tap 2
        move    r3,x1
        move    a,x0
        mpy     x1,#13,a
        mpy     x0,y0,b                 ; wet = g1 t1
        move    a1,n0
        move    a0,y1
        move    (r3)+n3
        lua     (r0)-n0,r1
        move    x:(r6)+,y0              ; g2
        move    y:(r1)-,x0
        move    y:(r1),x1
        mpysu   x1,y1,a
        macsu   -x0,y1,a
        asr     a
        add     x0,a                    ; t2
        move    a,x0
        mac     x0,y0,b r4,y1           ; + g2 t2 ; the fade gain
        move    b,x0
        mpy     x0,y1,b x:(r6)+,y0      ; B = the faded wet ; fb / 2
        FBTAIL
LOOP2_END:
        move    r0,y:(r6+S_W)
        move    r2,y:(r6+S_D1)
        move    r3,y:(r6+S_D2)
        rts

; CHOR: tap 3 too; the fade gain in Y:T_GN, its step in X:C_DG
TAIL3:
        move    y:(r6+T_D3),a
        add     y0,a
        cmp     x1,a
        tlt     x1,a
        cmp     y1,a
        tgt     y1,a
        move    y:(r6+T_FG),b
        tst     b
        move    y:(r6+S_D3),b
        teq     a,b
        move    b,x0
        sub     x0,a
        asr     #5,a,a
        move    a1,n4
        move    x0,r4
        move    y:(r6+T_FG),x0          ; the fade gain
        move    x0,y:(r6+T_GN)
        move    y:(r6+T_DG),x0
        move    x0,x:(r6+C_DG)
        bsr     SETIO
        move    #NCOEF,n6

        dor     #32,LOOP_END
        ; tap 1 (each tap's address work overlaps the previous tap's tail)
        move    r2,x1
        mpy     x1,#13,a
        move    (r2)+n2
        move    a1,n0
        move    a0,y1                   ; the fraction, unsigned
        lua     (r0)-n0,r1
        move    x:(r6)+,y0              ; g1
        move    y:(r1)-,x0              ; the newer sample
        move    y:(r1),x1               ; the older one
        mpysu   x1,y1,a
        macsu   -x0,y1,a                ; 2 f (older - newer)
        asr     a
        add     x0,a                    ; t1
        ; tap 2
        move    r3,x1
        move    a,x0
        mpy     x1,#13,a
        mpy     x0,y0,b                 ; wet = g1 t1
        move    a1,n0
        move    a0,y1
        move    (r3)+n3
        lua     (r0)-n0,r1
        move    x:(r6)+,y0              ; g2
        move    y:(r1)-,x0
        move    y:(r1),x1
        mpysu   x1,y1,a
        macsu   -x0,y1,a
        asr     a
        add     x0,a                    ; t2
        ; tap 3
        move    r4,x1
        move    a,x0
        mpy     x1,#13,a
        mac     x0,y0,b                 ; + g2 t2
        move    a1,n0
        move    a0,y1
        move    (r4)+n4
        lua     (r0)-n0,r1
        move    x:(r6)+,y0              ; g3
        move    y:(r1)-,x0
        move    y:(r1),x1
        mpysu   x1,y1,a
        macsu   -x0,y1,a
        asr     a
        add     x0,a    x:(r6)+,x1      ; t3 ; the gain step
        move    y:(r6+T_GN-4),y1        ; the fade gain (r6 is 4 on)
        move    a,x0
        mac     x0,y0,b y1,a            ; B = wet ; the gain
        add     x1,a                    ; this sample's gain
        move    b,x0
        move    a,y1
        mpy     x0,y1,b x:(r6)+,y0      ; B = the faded wet ; fb / 2
        move    a,y:(r6+T_GN-5)         ; (r6 is 5 on; ordered to avoid stalls)
        FBTAIL
LOOP_END:
        move    r0,y:(r6+S_W)
        move    r2,y:(r6+S_D1)
        move    r3,y:(r6+S_D2)
        move    r4,y:(r6+S_D3)
        rts

; SETIO: r5 = the track before, n5 = two before - r5, r0 = the write pointer
; (ring modulo in m0/m1)
SETIO:
        move    y:(r6+T_R5),r5          ; the track before
        move    y:(r6+T_N5),n5          ; two before - the track before
        move    y:(r6+S_W),r0
        movec   #>RING-1,m0
        movec   #>RING-1,m1
        rts

; ---------------------------------------------------------------- SPIN
; Two taps half a cycle apart ramp through the window and jump back, crossfaded
; with triangle windows: a pitch shifter. The ramp phase s runs -1...1 (signed 24
; bits): d = Dmid + span s / 2, window 1 - |s|. RATE sets the ramp speed: pitch
; ratio r = 1 - slope, slope = SLOPE_TAB x 64; the ramp moves |slope| / span a
; sample. Dmid glides to Dmin + span / 2 + the envelope.
SPIN:
        move    #>60*S,y0
        bsr     ENVOFF
        bsr     COEF3
        move    y:(r6+P_DPTH),x0
        move    #>736*S,y0
        mpy     x0,y0,a
        add     #>64*S,a
        move    a,y:(r6+T_B)            ; span, 1.5...20 ms
        move    #>200*S,y1
        move    #>2*S,b
        bsr     DSQ                     ; x1 = Dmin
        move    y:(r6+T_B),x0
        mpy     x0,#1,a
        move    a,y:(r6+T_E)            ; span / 2
        add     x1,a
        move    y:(r6+T_OFF),x0
        add     x0,a                    ; Dmid + the envelope
        move    y:(r6+T_E),x0
        move    #>MIN_D,b
        add     x0,b
        cmp     b,a
        tlt     b,a                     ; at least span / 2 + 2 samples
        move    #>MAX_D,b
        sub     x0,b
        cmp     b,a
        tgt     b,a                     ; at most MAX_D - span / 2
        move    y:(r6+T_FG),b
        tst     b
        move    y:(r6+S_DM),b
        teq     a,b                     ; after a mode switch: start at the target
        move    b,x0
        sub     x0,a
        asr     #5,a,a
        move    a1,n4                   ; glide step
        move    x0,r4
        ; the spread: a slow wobble of the shift, up to +-25 cents
        move    y:(r6+S_SP),a
        move    #>SPW_INC,x0
        add     x0,a
        move    a1,y:(r6+S_SP)
        move    a1,x0
        bsr     SIN
        move    y:(r6+P_SPRD),y0
        mpy     x0,y0,a
        move    a,x0
        move    #>WOBK,y0
        mpy     x0,y0,a
        move    a,y:(r6+T_C)            ; the wobble, as a slope / 64
        move    y:(r6+P_RATE),a
        asr     #7,a,a
        move    a1,n0
SLOPE_ADDR:
        move    #>SLOPE_TAB,r0
        lua     (r0)+n0,r0
        nop
        movem   p:(r0),x0
        move    y:(r6+T_C),a
        add     x0,a
        move    a,x0
        move    x0,y:(r6+T_C)           ; slope / 64
        move    x0,a
        abs     a
        move    y:(r6+T_B),x0
        and     #$fe,ccr
        rep     #24
        div     x0,a                    ; A0 = |slope| / 64 / (span / 1024), Q23
        move    a0,x0
        move    x0,a
        asr     #3,a,a
        move    a1,x0
        move    x0,a                    ; the ramp step, 2^24 a cycle
        move    y:(r6+T_C),b
        tst     b
        bge     <SP_POS
        neg     a
SP_POS:
        move    a1,n2
        move    y:(r6+S_SU),a
        move    a1,r2
        move    y:(r6+T_FG),r3          ; the fade gain
        move    y:(r6+T_DG),n3
        move    y:(r6+T_E),n1
        bsr     SETIO
        move    #4,n6

        dor     #32,SP_END
        ; tap 1
        move    r2,x1                   ; s = 2u - 1, -1...1
        move    n1,y0
        mpy     x1,y0,a
        move    r4,x0
        add     x0,a                    ; d = Dmid + span s / 2
        move    a,x0
        mpy     x0,#13,a
        move    a1,n0
        move    a0,y1
        lua     (r0)-n0,r1
        move    x1,a
        abs     a
        neg     a
        add     #>ONE,a
        move    a,y0                    ; window: 1 - |s|
        move    y:(r1)-,x0
        move    y:(r1),x1
        mpysu   x1,y1,a
        macsu   -x0,y1,a
        asr     a       (r3)+n3         ; the fade gain steps
        add     x0,a
        move    a,x0
        mpy     x0,y0,b                 ; wet = g1 t1
        ; tap 2, half a cycle on: s + 1 (mod 2)
        move    r2,a
        eor     #>$800000,a
        move    a1,x1
        move    n1,y0
        mpy     x1,y0,a (r2)+n2
        move    r4,x0
        add     x0,a
        move    a,x0
        mpy     x0,#13,a
        move    a1,n0
        move    a0,y1
        lua     (r0)-n0,r1
        move    x1,a
        abs     a
        neg     a
        add     #>ONE,a
        move    a,y0
        move    y:(r1)-,x0
        move    y:(r1),x1
        mpysu   x1,y1,a
        macsu   -x0,y1,a
        asr     a
        add     x0,a
        move    a,x0
        mac     x0,y0,b r3,y1           ; + g2 t2 ; the fade gain
        move    (r4)+n4                 ; Dmid glides
        move    b,x0
        mpy     x0,y1,b x:(r6)+,y0      ; B = the faded wet ; fb / 2
        FBTAIL
SP_END:
        move    r0,y:(r6+S_W)
        move    r2,y:(r6+S_SU)
        move    r4,y:(r6+S_DM)
        rts

; ---------------------------------------------------------------- BODE
; A whole block of the delayed signal goes through the Hilbert pair at once (the
; tap is at least 33 samples back, so nothing in this block feeds it), then
; W = I cos + DPTH Q sin shifts it by the oscillator frequency (DPTH 127: one
; sideband, a pure shift; 0: both, ring modulation).
BODE:
        move    #>288*S,y0
        bsr     ENVOFF
        move    r7,y:(r6+T_A)           ; the output address, kept
        movec   #>$ffffff,m7
        move    y:(r6+T_M),x0           ; (COEF3, inline)
        move    x0,x:(r6+0)
        move    y:(r6+T_N2),x0
        move    x0,x:(r6+1)
        move    #0,x0                   ; no DC removal in BODE
        move    x0,x:(r6+2)
        move    y:(r6+T_K),x0
        move    x0,x:(r6+3)
        ; SPRD: a slow wobble of the delay, +-2 ms at 0.37 Hz
        move    y:(r6+S_SP),a
        move    #>SPW_INC,x0
        add     x0,a
        move    a1,y:(r6+S_SP)
        move    a1,x0                   ; (SIN, inline)
        move    x0,a
        abs     a
        move    a,y0
        mpy     -x0,y0,a
        add     x0,a
        asl     #2,a,a
        move    a,x0
        move    y:(r6+P_SPRD),y0
        mpy     x0,y0,a
        move    a,x0
        move    #>88*S,y0
        mpy     x0,y0,a
        move    a,y:(r6+T_B)
        ; the tap: D = 1...23 ms + the envelope + the wobble, at least 34 samples
        move    #>960*S,y1
        move    #>44*S,b
        bsr     DSQ
        move    x1,a
        move    y:(r6+T_OFF),x0
        add     x0,a
        move    y:(r6+T_B),x0
        add     x0,a
        move    #>BODE_MIN,x0
        cmp     x0,a
        tlt     x0,a
        move    #>MAX_D,x0
        cmp     x0,a
        tgt     x0,a
        move    y:(r6+T_FG),b
        tst     b
        move    y:(r6+S_D1),b
        teq     a,b                     ; after a mode switch: start at the target
        move    b,x0
        sub     x0,a
        asr     #5,a,a
        move    a1,n2
        move    x0,r2
        bsr     SETIO
X_TAP:
        move    #>0,r4                  ; the tap signal -> X:0..31
        dor     #32,BT_END
        move    r2,x1
        mpy     x1,#13,a
        move    a1,n0
        move    a0,y1
        lua     (r0)-n0,r1
        move    y:(r1)-,x0
        move    y:(r1),x1
        mpysu   x1,y1,a
        macsu   -x0,y1,a
        asr     a       (r2)+n2
        add     x0,a    (r0)+           ; t ; where the next sample would be written
        move    a,x:(r4)+
BT_END:
        move    r2,y:(r6+S_D1)
        movec   #>$ffffff,m0
        movec   #>$ffffff,m1
        ; Hilbert pair, 3 + 3 sections: path 1 X:0 -> Y:0 -> XB -> Y:0, copied to XB;
        ; path 2 X:0 -> Y:0 -> X:0 -> Y:0
HILB_ADDR:
        move    #>HILB,r7
        lua     (r6+H_T),r1
        lua     (r6+H_P1),r3
X_HA0:
        move    #>0,r0
Y_HA5:
        move    #>0,r5
        bsr     SEC_XY
        lua     (r6+H_P1),r1
        lua     (r6+H_P1+2),r3
Y_HB4:
        move    #>0,r4
        lua     (r6+XB),r5
        bsr     SEC_YX
        lua     (r6+H_P1+2),r1
        lua     (r6+H_P1+4),r3
        lua     (r6+XB),r0
Y_HC5:
        move    #>0,r5
        bsr     SEC_XY
Y_HD4:
        move    #>0,r4                  ; I -> XB
        lua     (r6+XB),r5
        dor     #32,HCP_END
        move    y:(r4)+,x0
        move    x0,x:(r5)+
HCP_END:
        lua     (r6+H_T),r1
        lua     (r6+H_P2),r3
X_HE0:
        move    #>0,r0
Y_HE5:
        move    #>0,r5
        bsr     SEC_XY
        ; the tap signal's history, now that both paths have read it
X_HT:
        move    #>30,r0
        lua     (r6+H_T),r1
        move    x:(r0)+,x0
        move    x0,y:(r1)+
        move    x:(r0)+,x0
        move    x0,y:(r1)+
        lua     (r6+H_P2),r1
        lua     (r6+H_P2+2),r3
Y_HF4:
        move    #>0,r4
X_HF5:
        move    #>0,r5
        bsr     SEC_YX
        lua     (r6+H_P2+2),r1
        lua     (r6+H_P2+4),r3
X_HG0:
        move    #>0,r0
Y_HG5:
        move    #>0,r5
        bsr     SEC_XY                  ; Q in Y:0
        lua     (r6+H_P1),r0            ; commit the section histories
        lua     (r6+H_P1),r4
        move    x:(r0)+,a
        rep     #11
        move    x:(r0)+,a a,y:(r4)+
        move    a,y:(r4)+
        ; the oscillator: carried over from the last block and renormalised (one
        ; Newton step: (c, s) (1 + (1 - c^2 - s^2) / 2)), then turned by its step
        move    y:(r6+P_RATE),a
        asr     #7,a,a
        move    a1,n0
BODE_ADDR:
        move    #>BODE_DC,r0
        lua     (r0)+n0,r0
        move    #128,n0
        movem   p:(r0)+n0,x0
        move    x0,n2                   ; cos of the step
        movem   p:(r0),x0
        move    x0,n3                   ; sin of the step
        move    x:(r6+X_OC),x0
        move    x:(r6+X_OS),y0
        mpy     x0,x0,a
        mac     y0,y0,a
        asr     a
        move    #>HALF,b
        sub     a,b
        move    b,y1                    ; e
        mpy     x0,y1,a
        add     x0,a
        mpy     y1,y0,b
        add     y0,b
        move    a,x1                    ; cos
        move    b,y1                    ; sin
        move    y:(r6+P_DPTH),x0        ; the mirror sideband's weight: DPTH
        move    x0,n4
        lua     (r6+XB-1),r2            ; I[n - 1]: X:XB-1 holds the last block's I[31]
Y_MQ3:
        move    #>0,r3                  ; Q
Y_MW5:
        move    #>0,r5                  ; W -> Y:0..31 (over Q, behind the reads)
        dor     #32,BM_END
        move    y:(r3)+,x0              ; Q[n]
        move    n4,y0
        mpy     x0,y0,b x:(r2)+,x0      ; DPTH Q ; I[n - 1]
        mpy     x0,x1,a                 ; cos I[n - 1]
        move    b,y0
        mac     y1,y0,a                 ; + sin DPTH Q (RATE right: up)
        move    n2,x0
        move    a,y:(r5)+               ; W[n]
        move    n3,y0
        mpy     x1,x0,a
        mac     -y1,y0,a
        mpy     y1,x0,b
        mac     x1,y0,b
        move    a,x1                    ; cos
        move    b,y1                    ; sin
BM_END:
        move    x1,x:(r6+X_OC)          ; carried to the next block
        move    y1,x:(r6+X_OS)
        move    x:(r6+XB+31),x0
        move    x0,x:(r6+XB-1)          ; I[31] for the next block
        ; the samples: fade, output and feedback
        move    y:(r6+T_A),r7
        movec   #$1f,m7
        move    y:(r6+T_R5),r5          ; (SETIO; n5 and m1 as they are)
        move    y:(r6+S_W),r0
        movec   #>RING-1,m0
        move    #4,n6
        move    y:(r6+T_FG),a
        move    y:(r6+T_DG),x0
        add     x0,a                    ; the first sample's gain
        move    x0,n2
Y_BW4:
        move    #>0,r4
        dor     #32,BW_END
        move    a,x0    y:(r4)+,y1      ; the fade gain ; W[n]
        mpy     x0,y1,b n2,x1           ; the faded W ; the gain step
        add     x1,a    x:(r6)+,y0      ; the next gain ; fb / 2
        FBTAIL
BW_END:
        move    r0,y:(r6+S_W)
        rts

; SEC_XY / SEC_YX: one all-pass section over a block, y[n] = c (x[n] + y[n-2]) - x[n-2].
; In: r0/r4 the input (X for SEC_XY, Y for SEC_YX), r5 the output (the other space),
; r1 the input's history [x-2, x-1], r3 the output's history (Y track), r7 -> c.
; Out: the output's new history staged at X:r3 (same offset), r7 advanced.
SEC_XY:
        movem   p:(r7)+,y0              ; c
        move    r0,r2
        move    r5,r4
        ; n = 0, 1 from the histories
        move    x:(r0)+,x0
        move    y:(r3)+,y1
        mpy     x0,y0,b
        mac     y1,y0,b
        move    y:(r1)+,x1
        sub     x1,b
        move    b,y:(r5)+
        move    x:(r0)+,x0
        move    y:(r3)+,y1
        mpy     x0,y0,b
        mac     y1,y0,b
        move    y:(r1)+,x1
        sub     x1,b
        move    b,y:(r5)+
        dor     #15,SXL_END         ; two samples a pass
        move    x:(r0)+,x0 y:(r4)+,y1   ; x[n], y[n-2]
        mpy     x0,y0,a x:(r2)+,x1      ; c x[n] ; x[n-2]
        mac     y1,y0,a x:(r0)+,x0 y:(r4)+,y1   ; x[n+1], y[n-1]
        sub     x1,a    x:(r2)+,x1      ; y[n] ; x[n-1]
        mpy     x0,y0,b
        mac     y1,y0,b a,y:(r5)+
        sub     x1,b
        move    b,y:(r5)+               ; y[n+1]
SXL_END:
        lua     (r3-2),r3
        move    y:(r4)+,x0              ; y[30]
        move    x0,x:(r3)+              ; staged
        move    y:(r4)+,x0              ; y[31]
        move    x0,x:(r3)+
        rts

SEC_YX:
        movem   p:(r7)+,y0              ; c
        move    r4,r2
        move    r5,r0
        move    y:(r4)+,x0
        move    y:(r3)+,y1
        mpy     x0,y0,b
        mac     y1,y0,b
        move    y:(r1)+,x1
        sub     x1,b
        move    b,x:(r5)+
        move    y:(r4)+,x0
        move    y:(r3)+,y1
        mpy     x0,y0,b
        mac     y1,y0,b
        move    y:(r1)+,x1
        sub     x1,b
        move    b,x:(r5)+
        dor     #15,SYL_END         ; two samples a pass
        move    x:(r0)+,x1 y:(r4)+,y1   ; y[n-2] ; x[n]
        mpy     y1,y0,a y:(r2)+,y1      ; c x[n] ; x[n-2]
        mac     x1,y0,a x:(r0)+,x1      ; y[n-1]
        sub     y1,a    y:(r4)+,y1      ; y[n] ; x[n+1]
        mpy     y1,y0,b y:(r2)+,y1      ; c x[n+1] ; x[n-1]
        mac     x1,y0,b a,x:(r5)+
        sub     y1,b
        move    b,x:(r5)+               ; y[n+1]
SYL_END:
        lua     (r3-2),r3
        move    x:(r0)+,x0              ; y[30]
        move    x0,x:(r3)+              ; staged
        move    x:(r0)+,x0              ; y[31]
        move    x0,x:(r3)+
        rts

; ---------------------------------------------------------------- helpers
; ENVELOPE: T_EV = +e (ENTI right of 64), -e (left) or 0 (64); then e decays
ENVELOPE:
        move    y:(r6+P_ENTI),a
        asr     #7,a,a
        move    a1,n0
        move    a1,x1
ENV_ADDR:
        move    #>ENVK_TAB,r0
        lua     (r0)+n0,r0
        move    y:(r6+S_ENV),x0         ; e
        movem   p:(r0),y0               ; this time's decay a block
        mpy     x0,y0,b
        move    b,y:(r6+S_ENV)
        move    x1,a
        move    #>64,y0
        cmp     y0,a
        beq     <ENV_OFF
        bgt     <ENV_DN
        move    x0,a
        neg     a
        move    a,x0                    ; left: shorter, then back
ENV_DN:
        move    x0,y:(r6+T_EV)
        rts
ENV_OFF:
        clr     a
        move    a,y:(r6+T_EV)
        rts

; COEF3: the SPIN / BODE coefficients: fb / 2, the T2 gain, the DC, the T1 gain
COEF3:
        move    y:(r6+T_M),x0
        move    x0,x:(r6+0)
        move    y:(r6+T_N2),x0
        move    x0,x:(r6+1)
        move    x:(r6+X_DC),x0
        move    x0,x:(r6+2)
        move    y:(r6+T_K),x0
        move    x0,x:(r6+3)
        rts

; ENVOFF: T_OFF = T_EV x y0 (the mode's envelope depth, Q13)
ENVOFF:
        move    y:(r6+T_EV),x0
        mpy     x0,y0,a
        move    a,y:(r6+T_OFF)
        rts

; FVOICE: a = T_A (1 + T_B sin(LFO + x0))
FVOICE:
        bsr     LSIN
        move    y:(r6+T_B),y0
        mpy     x0,y0,a
        move    a,y0
        move    y:(r6+T_A),x0
        mpy     x0,y0,a
        add     x0,a
        rts

; CVOICE: a = T_A + T_B sin(LFO + x0)
CVOICE:
        bsr     LSIN
        move    y:(r6+T_B),y0
        mpy     x0,y0,a
        move    y:(r6+T_A),x0
        add     x0,a
        rts

; LFOPH: the FLNG / DBLR LFO phase (RATE_TAB)
LFOPH:
        move    y:(r6+P_RATE),a
        asr     #7,a,a                  ; the RATE setting, 0...127
        move    a1,n0
RATE_ADDR:
        move    #>RATE_TAB,r0
        lua     (r0)+n0,r0
        move    y:(r6+S_PH),a
        movem   p:(r0),x0
        add     x0,a
        move    a1,y:(r6+S_PH)
        rts

; CHV: a = T_A + T_B sin(the CHOR phase + x0); y1 = the sine
; CHV_S: the same from a sine in x0
CHV:
        move    y:(r6+S_CP),a
        add     x0,a
        move    a1,x0
        move    x0,a                    ; (SIN, inline)
        abs     a
        move    a,y0
        mpy     -x0,y0,a
        add     x0,a
        asl     #2,a,a
        move    a,x0
CHV_S:
        move    x0,y1
        move    y:(r6+T_B),y0
        mpy     x0,y0,a
        move    y:(r6+T_A),x0
        add     x0,a
        rts

; LSIN: x0 = phase offset -> x0 = sin(the LFO phase + x0)
LSIN:
        move    y:(r6+S_PH),a
        add     x0,a
        move    a1,x0

; SIN: x0 = phase (2^24 a cycle) -> x0 = sine, parabolic: 4 p (1 - |p|)
SIN:
        move    x0,a
        abs     a
        move    a,y0
        mpy     -x0,y0,a
        add     x0,a
        asl     #2,a,a
        move    a,x0
        rts

; SIN2: a closer sine for the BODE oscillator: y = SIN; y = 0.775 y + 0.225 y |y|
SIN2:
        bsr     SIN
        move    x0,a
        abs     a
        move    a,y0
        mpy     x0,y0,a                 ; y |y|
        move    a,y0
        move    #>K225,x1
        mpy     x1,y0,a
        move    #>K775,y0
        mac     x0,y0,a
        move    a,x0
        rts

; x1 = b + DLAY^2 y1
DSQ:
        move    y:(r6+P_DLAY),x0
        mpy     x0,x0,a
        move    a,x0
        mpy     x0,y1,a
        add     b,a
        move    a,x1
        rts

; x1 = b + DLAY y1
DLIN:
        move    y:(r6+P_DLAY),x0
        mpy     x0,y1,a
        add     b,a
        move    a,x1
        rts

; y1 = DPTH y1
SPAN:
        move    y:(r6+P_DPTH),x0
        mpy     x0,y1,a
        move    a,y1
        rts

; ---------------------------------------------------------------- cold code
; RING_FIX: the check word does not match S_RING
RING_FIX:
        ; 1. S_RING is still a sane ring address (1,024-aligned, in track memory): keep it
        move    y:(r6+S_RING),a
        move    #>RING-1,x0
        and     x0,a
        bne     <RF_TRK
        move    y:(r6+S_RING),b
TM_CHK:
        move    #>$000000,x0            ; symbol 6: track memory
        sub     x0,b
        move    b1,x1                   ; the offset in track memory
        move    #>$ff8000,x0
        and     x0,b
        bne     <RF_TRK
        move    x1,b
        move    #>15*1536+RING-1,x0     ; the highest ring start
        cmp     x0,b
        bgt     <RF_TRK
        move    y:(r6+S_RING),a
        not     a
        move    a1,y:(r6+S_RINGN)
        move    y:(r6+S_W),a            ; and the write pointer into the ring
        move    #>RING-1,x0
        and     x0,a
        move    y:(r6+S_RING),x0
        add     x0,a
        move    a1,y:(r6+S_W)
        bra     <RF_DEAD                ; this block silent (keeps the repair out of the budget)
RF_TRK:
        ; 2. a valid saved track number: start again as INIT does
        move    y:(r6+S_TRK),a
        move    y:(r6+S_TRKN),x0
        eor     x0,a
        not     a
        bne     <RF_DEAD
        move    y:(r6+S_TRK),a
        move    #>$fffff0,x0
        and     x0,a
        bne     <RF_DEAD
        move    y:(r6+S_TRK),a
        bsr     SETRING
        bsr     RESET
RF_DEAD:
        ; a silent block after a repair; 3. nothing to trust: silence, no memory
        ; access, every block until INIT runs
        clr     a
        rep     #32
        move    a,y:(r7)+
        rts

INIT:
        movec   #>$ffffff,m6
        move    r1,a                    ; the track number, 0...15
        bsr     SETRING
        bra     RESET

; SETRING: a = the track number -> S_TRK(N), S_RING(N), S_W
SETRING:
        move    a1,y:(r6+S_TRK)
        not     a
        move    a1,y:(r6+S_TRKN)
        move    y:(r6+S_TRK),a
        move    a1,x0
        asl     a
        add     x0,a
        asl     #9,a,a                  ; 1,536 x track
TRACK_MEMORY:
        move    #>$000000,x0            ; symbol 6: track 1's first word
        add     x0,a
        add     #>RING-1,a
        and     #>$fffc00,a             ; the first 1,024-aligned word
        move    a1,y:(r6+S_RING)
        move    a1,y:(r6+S_W)
        not     a
        move    a1,y:(r6+S_RINGN)
        rts

; RESET: everything else as INIT leaves it (the ring is cleared first)
RESET:
        clr     a
        move    a,x:(r6+X_DC)
        move    a,x:(r6+X_OS)
        move    #>ONE,x0
        move    x0,x:(r6+X_OC)
        move    a,y:(r6+S_CLR)
        move    a,y:(r6+S_PH)
        move    a,y:(r6+S_SU)
        move    a,y:(r6+S_ENV)
        move    a,y:(r6+S_OSC)
        move    a,x:(r6+XB-1)
        move    a,y:(r6+S_SP)
        move    a,y:(r6+S_CP)
        move    a,y:(r6+S_FG)           ; the wet fades in
        move    y:(r6+P_MODE),x0
        move    x0,y:(r6+S_AM)
        lua     (r6+H_T),r0
        rep     #14
        move    a,y:(r0)+               ; the all-pass histories
        move    #>MIN_D,x0
        move    x0,y:(r6+S_D1)
        move    x0,y:(r6+S_D2)
        move    x0,y:(r6+S_D3)
        move    #>64*S,x0
        move    x0,y:(r6+S_DM)
        rts

TRIG:
        movec   #>$ffffff,m6
        move    #>ONE,x0
        move    x0,y:(r6+S_ENV)         ; restart the envelope (the LFO runs free)
        rts

        include 'tables.inc'

        endsec
