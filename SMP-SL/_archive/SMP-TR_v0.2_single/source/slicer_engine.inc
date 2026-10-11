; Engine of SMP-SL "ROM+E12 SLICER" (and SMP-SM ROM only, SMP-SN E12 only):
; plays one slice of a UW ROM or internal (E12) sample, looping it while the
; DEC envelope lasts. The wrapper defines BANK_ID, the SAMPLE_INFO / READ bank:
; 0 internal, 1 UW ROM, or -1 for both: SMPL 0..UW_SLOTS-1 are UW ROM slots, the
; settings after them the internal ones (the wrapper then defines UW_SLOTS).
;
; At TRIG the sample is cut into SLIC slices by MODE, and slice SLNO (taken
; modulo SLIC) becomes the window lo..hi. Boundary k of n is at u(k) * length:
;   EQUA k/n; SHUF (k + 1/3 for odd k)/n, long-short pairs; EXP / LOG a curve
;   table at k/n; Perlin seeds (MODE 4..127) P[k] / P[n], P the prefix sums of
;   slice widths read from a noise table (SEEDSUM). Slice 1 always starts at 0.
;
; Playback is the SMP-ST splice engine with GRAN fixed at 1494 samples (its
; setting 64) and no FLUX. A playhead runs through the window: at TIME 0 at
; the grain rate (a plain varispeed sampler); above 0 at the TIME speed alone,
; as SMP-ST (TIME_ST = 1; TIME_ST = 0 would scale the grain rate instead).
; One grain plays at a time; a new grain crossfades in over 4 blocks:
;   - when the playhead reaches the loop point W = hi - 160 samples of grain
;     travel (at most half the window), it wraps to lo and a grain starts there,
;     so the old grain's crossfade ends at hi. PLAY sets the next pass: FWD,
;     REV, or BI (turn round on every pass).
;   - with TIME above 0, every GRAN samples a grain starts at the playhead,
;     centred on it, or early when the grain itself reaches W.
; At TIME 0 the grain is the playhead and only the loop splices.
; The engine runs forwards through lo..hi; a reversed pass reads at
; lo + hi - 1 - p (each grain keeps its own direction through its crossfade).
; DEC decays the level (127 holds it); the voice stops when it has decayed.
; DEC 0 plays the slice once at full level: when the playhead reaches
; W1 = hi - 320 samples of grain travel (at most half the window), the voice
; fades out over 8 blocks (smoothstep), ending about a block before hi, and stops.
;
; Parameters, Y:(r6+1..8):
;   1 PTCH  raw14 bipolar  (setting - 64) / 2 semitones: -32..+32
;   2 SMPL  index          UW 0..47, then internal 0..20 (latched at TRIG)
;   3 DEC   raw14          0 = once, no envelope; 1..126 decay, 60 dB in
;                          0.03..30 s, looping; 127 = no decay, looping
;   4 TIME  raw14          playhead slow-down: 0 normal, 42 half, 127 frozen
;   5 PLAY  index          0 FWD, 1 REV, 2 BI (read at every loop)
;   6 MODE  index          0 EQUA, 1 SHUF, 2 EXP, 3 LOG, 4..127 Perlin seeds,
;                          more uneven and busier as the number rises (latched)
;   7 SLIC  index          slices - 1, 0..63 (latched)
;   8 SLNO  index          slice - 1, 0..63, modulo the slice count (latched)
;
; Persistent Y state:
;   9 bank  10 active  11/12 grain position int/frac  13/14 playhead int/frac
;  15 lo  16 hi  17 hi-lo  18 native step (Q16.16)  19 samples to next splice
;  20 gain at the end of the last block  21 slot  22 playhead pass reversed
;  23 grain reversed  24 old grain reversed  25 lo + hi - 1  26 envelope
;  27 crossfade step (0 = none, 1..4)  28/29 old grain position int/frac
; Rates, recomputed in every block outside a crossfade:
;  30/31 grain rate (24.24)  32 grain rate * 2^17  33/34 twice the grain rate
;  35/36 playhead step per block (24.24)  37 playhead rate * 2^17
;  38 PTCH fraction  39 rate shift  40 pitch multiplier  49 loop point W
;  50 TIME is 0
;  51 end fade step (0 = none, 1..8; DEC 0 only)  52 DEC 0 end point W1
; Y scratch within one call:
;  41/42 gain at block start/end  43/44 old grain gain start/step
;  45/46 new grain gain start/step  47 J  48 centring
;  TRIG: 41 length  42 slice count  43 slice  44 mode  45/46/47 P[k], P[k+1], P[n]
;  48 seed depth

P_PTCH  equ 1
P_SMPL  equ 2
P_DEC   equ 3
P_TIME  equ 4
P_PLAY  equ 5
P_MODE  equ 6
P_SLIC  equ 7
P_SLNO  equ 8
S_BANK  equ 9
S_ACT   equ 10
S_GI    equ 11
S_GF    equ 12
S_PI    equ 13
S_PF    equ 14
S_LO    equ 15
S_HI    equ 16
S_WIN   equ 17
S_STEP  equ 18
S_CNT   equ 19
S_GAIN  equ 20
S_SLOT  equ 21
S_PREV  equ 22
S_GREV  equ 23
S_OREV  equ 24
S_MIR   equ 25
S_ENV   equ 26
S_FADE  equ 27
S_OGI   equ 28
S_OGF   equ 29
T_RGI   equ 30
T_RGF   equ 31
T_RQ    equ 32
T_R2I   equ 33
T_R2F   equ 34
T_VBI   equ 35
T_VBF   equ 36
T_RPQ   equ 37
T_F     equ 38
T_SH    equ 39
T_M     equ 40
T_G0    equ 41
T_G1    equ 42
T_CO0   equ 43
T_COS   equ 44
T_CN0   equ 45
T_CNS   equ 46
T_J     equ 47
T_CTR   equ 48
T_W     equ 49
T_TZ    equ 50
S_REL   equ 51
T_W1    equ 52
T_LEN   equ T_G0
T_N     equ T_G1
T_K     equ T_CO0
T_MODE  equ T_COS

MIN_WIN equ 64                  ; shortest slice in frames
ENV_OFF equ $000040             ; envelope level treated as silent (about -100 dB)
GRAN    equ 1494                ; grain length in output samples
L64     equ GRAN*64
MAX_MODE equ 127
T_PK    equ T_CN0               ; TRIG scratch for the Perlin seeds
T_PK1   equ T_CNS
T_PN    equ T_J
T_DEPTH equ T_CTR

; Onset analysis (TRANS builds, SMP-TR): see onsets.inc
P_THRS  equ 6                   ; THRS takes MODE's place
A_KEY   equ 53                  ; SMPL setting analysed (NONE: nothing)
A_LEN   equ 54                  ; its length
A_STRIDE equ 55                 ; frames between read pairs / 2; a hop is 32 * stride
A_POS   equ 56                  ; next hop
A_ENV   equ 57                  ; peak follower
A_CNT   equ 58                  ; onsets in the list
A_PPOS  equ 59                  ; pending onset position (NONE: none)
A_PQ    equ 60                  ; its q (Q15)
A_PAGE  equ 61                  ; frames since it was found (REFINED once placed)
A_SKIP  equ 62                  ; 1: no analysis in this block (TRIG)
A_DONE  equ 63                  ; 1: nothing more to analyse
X_XF    equ 60                  ; X: crossfade step at the start of the block
X_E     equ 61                  ; X scratch
X_ENVD  equ 62
X_WS    equ 63
MAX_ON  equ 30                  ; onsets kept: X:(r6+0..59), position and (q << 8) | rank
NONE    equ $ffffff
GAP_FR  equ 1100                ; candidates closer than this (25 ms) merge
MINSTART equ 1100               ; no onsets in the first 25 ms
FLOOR   equ 1049                ; 0.001 on E's scale, added to the reference
EMIN    equ 3146                ; 0.003: quieter hops are never onsets
QMAX    equ 26214               ; Q15 0.8: E at least 1.25 times the reference
DK      equ 60870               ; peak follower fall per hop and stride unit (100 ms)
MIN_STRIDE equ 16
MAX_STRIDE equ 64
REFINED equ $7fffff
WALK_MAX equ 12                 ; REFINE steps back from the peak at most

        section SLICER
; Y0 = A1 / X0 as a Q23 fraction, for 0 <= A1 < X0.
DIVQ:
        and     #$fe,ccr
        rep     #24
        div     x0,a
        move    a0,y0
        rts

; A = (X0 * Y0) >> shift (Y+T_SH): a rate in 24.24 frames per sample.
RSHIFT:
        mpy     x0,y0,a
        move    y:(r6+T_SH),x0
        asr     x0,a,a
        rts

RENDER:
        movec   #>$ffffff,m6
        if      TRANS
        ; the voice, then (outside crossfade blocks and the block of a TRIG,
        ; which have no cycles to spare) one step of the onset analysis
        move    y:(r6+S_FADE),a
        move    a1,x:(r6+X_XF)
        bsr     VOICE
        move    y:(r6+A_SKIP),a
        tst     a
        beq     R_ANALYSE
        clr     a
        move    a,y:(r6+A_SKIP)
        rts
R_ANALYSE:
        move    x:(r6+X_XF),a
        tst     a
        bne     R_NO_ANALYSIS
        bra     ANALYSE
R_NO_ANALYSIS:
        rts
VOICE:
        endif
        move    y:(r6+S_ACT),a
        tst     a
        beq     SILENCE
        bsr     TBASE
        ; Rates are recomputed outside crossfades only: a crossfade (the costliest
        ; block, two sample reads) keeps the rates its splice was computed with.
        move    y:(r6+S_FADE),a
        tst     a
        bne     R_RATES_DONE

        ; ---- grain rate = step * 2^(PTCH/12): semitone table plus octave shift ----
        move    y:(r6+P_PTCH),a
        move    #>8192,x0       ; setting 64 = no shift
        sub     x0,a
        asr     a               ; half a semitone per setting step
        move    #>4095,x0
        cmp     x0,a
        tfr     x0,a    ifgt
        move    #>$fff000,x0    ; -4096
        cmp     x0,a
        tfr     x0,a    iflt
        tfr     a,b
        asr     #7,b,b          ; whole semitones s, -32..31
        and     #>$7f,a         ; 1/128-semitone steps ...
        lsl     #16,a           ; ... as a Q23 fraction
        move    a1,y:(r6+T_F)
        move    #>72,x0
        add     x0,b            ; t = s + 72, 8..135
        move    b1,x1
        move    #>$0aaaab,y0    ; 1/12, rounded up
        mpy     x1,y0,a         ; A1 = t / 12, the octave + 6
        move    a1,y:(r6+T_SH)
        move    a1,a
        asl     #2,a,a
        move    a1,y1
        asl     #1,a,a
        add     y1,a            ; 12 * octave
        move    x1,b
        sub     a,b             ; semitone within the octave, 0..11
        move    b1,n4
        lua     (r4)+n4,r0
        movem   p:(r0)+,x0      ; 2^(n/12)/4
        movem   p:(r0),x1       ; one semitone higher
        move    x1,b
        sub     x0,b
        move    b1,y1
        move    y:(r6+T_F),y0
        mpy     y0,y1,b
        add     x0,b
        move    b1,y:(r6+T_M)   ; the multiplier, 2^(semitones/12)/4
        move    y:(r6+T_SH),x0
        move    #>20,a
        sub     x0,a
        move    a1,y:(r6+T_SH)  ; shift by 20 - (octave + 6)
        move    y:(r6+S_STEP),x0
        move    b1,y0
        bsr     RSHIFT          ; 24.24 frames/sample
        move    a1,y:(r6+T_RGI)
        move    a0,y:(r6+T_RGF)
        tfr     a,b
        asl     #17,b,b
        move    b1,y:(r6+T_RQ)
        tfr     a,b
        asl     b
        move    b1,y:(r6+T_R2I) ; twice the grain rate, for POSGEN
        move    b0,y:(r6+T_R2F)
        ; ---- loop point W = hi - min(160 * grain rate, window / 2), and the
        ; DEC 0 end point W1 = hi - min(320 * grain rate, window / 2) ----
        tfr     a,b
        asl     #5,a,a          ; A = 32 * rate, the playhead step at TIME 0
        asl     #7,b,b
        add     a,b
        move    b1,x1           ; 160 * rate
        asl     b
        move    b1,y1           ; 320 * rate
        move    y:(r6+S_WIN),b
        asr     b
        move    b1,b
        move    b1,x0           ; window / 2
        cmp     x1,b
        tfr     x1,b    ifgt
        move    b1,x1
        move    x0,b
        cmp     y1,b
        tfr     y1,b    ifgt
        move    b1,y1
        move    y:(r6+S_HI),b
        sub     x1,b
        move    b1,y:(r6+T_W)
        move    y:(r6+S_HI),b
        sub     y1,b
        move    b1,y:(r6+T_W1)

        ; ---- playhead step per block: 32 * grain rate * speed, with speed from
        ; the TIME table (8192 at 0 = normal, 4096 at 42, 0 at 127) ----
        move    y:(r6+P_TIME),b
        asr     #7,b,b
        move    #>127,x0
        cmp     x0,b
        tfr     x0,b    ifgt
        move    #0,x0
        cmp     x0,b
        tfr     x0,b    iflt
        tst     b
        bne     R_SLOW
        move    #>1,b
        move    b1,y:(r6+T_TZ)
        bra     R_VB
R_SLOW:
        move    #>TB_SPEED,x0
        add     x0,b
        move    b1,n4
        lua     (r4)+n4,r0
        movem   p:(r0),y0
        clr     b
        move    b1,y:(r6+T_TZ)
        move    y:(r6+S_STEP),x0
        if      TIME_ST
        mpy     x0,y0,a         ; as SMP-ST: 32 * step * speed / 8192
        asr     a
        else
        move    y0,a
        lsl     #10,a
        move    a1,y0
        mpy     x0,y0,a         ; step * speed / 8192 ...
        move    a1,x0
        move    y:(r6+T_M),y0
        bsr     RSHIFT          ; ... at the grain's pitch
        asl     #5,a,a
        endif
R_VB:
        move    a1,y:(r6+T_VBI)
        move    a0,y:(r6+T_VBF)
        asl     #12,a,a
        move    a1,y:(r6+T_RPQ) ; playhead rate per sample * 2^17
R_RATES_DONE:

        ; ---- level: the decay envelope ----
        move    y:(r6+P_DEC),a
        asr     #7,a,a
        move    #>127,x0
        cmp     x0,a
        tfr     x0,a    ifgt
        move    #0,x0
        cmp     x0,a
        tfr     x0,a    iflt
        move    #>TB_DECAY,x0
        add     x0,a
        move    a1,n4
        lua     (r4)+n4,r0
        movem   p:(r0),y0
        move    y:(r6+S_ENV),x0
        mpy     x0,y0,a         ; envelope at the end of this block ...
        move    #>$7fffff,x1
        move    y0,b
        cmp     x1,b
        tfr     x0,a    ifeq    ; ... held exactly at DEC 127
        move    a1,y:(r6+S_ENV)
        move    #>ENV_OFF,x1
        cmp     x1,a
        bge     R_ENV_OK
        clr     b               ; decayed away: this is the last block
        move    b,y:(r6+S_ACT)
R_ENV_OK:
        ; ---- DEC 0 end fade: the gain follows FADE8 down to 0 over 8 blocks,
        ; then the voice stops ----
        move    y:(r6+S_REL),b
        tst     b
        beq     R_LEVEL
        move    a1,x0
        move    #>TB_FADE8,y1
        add     y1,b
        move    b1,n4
        lua     (r4)+n4,r0
        movem   p:(r0),y0
        mpy     x0,y0,a
        move    y:(r6+S_REL),b
        add     #1,b
        move    b1,y:(r6+S_REL)
        move    #>9,x0
        cmp     x0,b
        blt     R_LEVEL
        clr     b               ; end fade complete: this is the last block
        move    b,y:(r6+S_ACT)
R_LEVEL:
        move    a1,y:(r6+T_G1)
        move    y:(r6+S_GAIN),x1
        move    x1,y:(r6+T_G0)
        move    a1,y:(r6+S_GAIN)

        ; ---- per-grain gain ramps for this block ----
        move    y:(r6+S_FADE),a
        tst     a
        beq     R_COEF_PLAIN
        ; crossfade step j = FADE - 1: old grain G * (1 - j/4), new grain G * j/4
        move    #>TB_QTR-1,x0
        add     x0,a
        move    a1,n4
        lua     (r4)+n4,r0
        movem   p:(r0)+,y0
        movem   p:(r0),y1
        move    y:(r6+T_G0),x0
        move    y:(r6+T_G1),x1
        bsr     COEF
        move    b1,y:(r6+T_CO0)
        move    a1,y:(r6+T_COS)
        move    y:(r6+S_FADE),x0
        move    #>TB_QTR+5,a
        sub     x0,a
        move    a1,n4
        lua     (r4)+n4,r0
        movem   p:(r0)-,y0
        movem   p:(r0),y1
        move    y:(r6+T_G0),x0
        move    y:(r6+T_G1),x1
        bsr     COEF
        bra     R_COEF_STORE
R_COEF_PLAIN:
        move    y:(r6+T_G0),b
        move    y:(r6+T_G1),a
        sub     b,a
        asr     #5,a,a
R_COEF_STORE:
        move    b1,y:(r6+T_CN0)
        move    a1,y:(r6+T_CNS)

        ; ---- crossfade blocks: the old grain, 32 frames, into the output ----
        move    y:(r6+S_FADE),a
        tst     a
        beq     R_NEW
        move    y:(r6+S_OGI),a
        move    y:(r6+S_OGF),a0
        move    y:(r6+S_OREV),b
        bsr     POSGEN
        move    a1,y:(r6+S_OGI)
        move    a0,y:(r6+S_OGF)
        move    #32,n0
        bsr     SREAD
        tst     a
        beq     SILENCE
PCM_A:
        move    #>$000000,r0    ; kind 3 / TEMP_X
        movec   #>$ffffff,m0
        move    y:(r6+T_CO0),b
        move    y:(r6+T_COS),x1
        bsr     GAIN_OUT        ; R7 is back at the block start afterwards

R_NEW:
        ; ---- the current grain, 32 frames ----
        move    y:(r6+S_GI),a
        move    y:(r6+S_GF),a0
        move    y:(r6+S_GREV),b
        bsr     POSGEN
        move    a1,y:(r6+S_GI)
        move    a0,y:(r6+S_GF)
        move    y:(r6+S_PI),b
        move    y:(r6+S_PF),b0
        move    y:(r6+T_VBI),x1
        move    y:(r6+T_VBF),x0
        add     x,b
        move    b1,y:(r6+S_PI)
        move    b0,y:(r6+S_PF)
        move    #32,n0
        bsr     SREAD
        tst     a
        beq     SILENCE
PCM_B:
        move    #>$000000,r0    ; kind 3 / TEMP_X
        movec   #>$ffffff,m0
        move    y:(r6+T_CN0),b
        move    y:(r6+T_CNS),x1
        move    y:(r6+S_FADE),a
        tst     a
        bne     PCM_ADD
        bsr     GAIN_OUT
        ; ---- outside crossfades: loop when the playhead reaches W (or, at
        ; DEC 0, fade out instead); nothing more once the end fade runs ----
        move    y:(r6+S_REL),a
        tst     a
        bne     R_DONE
        move    y:(r6+S_PI),a
        move    y:(r6+P_DEC),b
        move    #>128,x1
        cmp     x1,b
        bge     R_LOOP_AT
        move    y:(r6+T_W1),x0  ; DEC 0: play once, fading out from W1
        cmp     x0,a
        blt     R_NOWRAP
        move    #>1,b
        move    b1,y:(r6+S_REL)
        rts
R_LOOP_AT:
        move    y:(r6+T_W),x0
        cmp     x0,a
        blt     R_NOWRAP
        sub     x0,a            ; back to lo, keeping the overshoot ...
        move    y:(r6+S_LO),x1
        add     x1,a
        cmp     x0,a
        tfr     x1,a    ifge    ; ... unless it is past W again (tiny slices)
        move    a1,y:(r6+S_PI)
        move    #>1,x1
        move    y:(r6+S_PREV),b
        move    y:(r6+P_PLAY),a
        tst     a
        bne     R_WRAP_REV
        clr     b               ; FWD
        bra     R_WRAP_SET
R_WRAP_REV:
        cmp     x1,a
        bne     R_WRAP_BI
        move    x1,b            ; REV
        bra     R_WRAP_SET
R_WRAP_BI:
        eor     x1,b            ; BI: turn round
R_WRAP_SET:
        move    b1,y:(r6+S_PREV)
        clr     a
        move    a,y:(r6+S_CNT)
        bra     SPLICE
R_NOWRAP:
        ; ---- splice every GRAN samples while TIME is above 0, or early when
        ; the grain reaches W. At TIME 0 the grain is the playhead.
        move    y:(r6+T_TZ),a
        tst     a
        beq     R_COUNT
        move    #>GRAN,a
        bra     R_COUNT_SET
R_COUNT:
        move    y:(r6+S_CNT),a
        move    #>32,x0
        sub     x0,a
R_COUNT_SET:
        move    a1,y:(r6+S_CNT)
        tst     a
        ble     SPLICE
        move    y:(r6+T_W),x0
        move    y:(r6+S_GI),a
        cmp     x0,a
        blt     R_DONE
        clr     a               ; early splice: the next grain counts from zero
        move    a,y:(r6+S_CNT)
        bra     SPLICE
R_DONE:
        rts
PCM_ADD:
        move    b1,y1
        dor     #32,PCM_ADD_END
        move    x:(r0)+,x0      y:(r7),a
        mac     x0,y1,a
        add     x1,b    a,y:(r7)+
        move    b1,y1
PCM_ADD_END:
        move    y:(r6+S_FADE),a
        move    #>1,x0
        add     x0,a
        move    #>5,x0
        cmp     x0,a
        blt     R_FADE_STORE
        clr     a               ; crossfade finished
R_FADE_STORE:
        move    a1,y:(r6+S_FADE)
        move    y:(r6+T_TZ),a   ; the grain keeps counting through the crossfade
        tst     a
        bne     R_FADE_DONE
        move    y:(r6+S_CNT),a
        move    #>32,x0
        sub     x0,a
        move    a1,y:(r6+S_CNT)
R_FADE_DONE:
        rts

; Y:(R7)+ = X:(R0)+ * gain for 32 samples; the gain starts at B1 and steps by X1.
; Software-pipelined: each store goes with the next sample's multiply.
GAIN_OUT:
        move    x:(r0)+,x0
        move    b1,y1
        add     x1,b
        mpy     x0,y1,a x:(r0)+,x0
        move    b1,y1
        dor     #30,GAIN_OUT_END
        add     x1,b
        mpy     x0,y1,a x:(r0)+,x0      a,y:(r7)+
        move    b1,y1
GAIN_OUT_END:
        mpy     x0,y1,a a,y:(r7)+
        move    a,y:(r7)+
        rts

SILENCE:
        clr     a
        move    a,y:(r6+S_ACT)
        rep     #32
        move    a,y:(r7)+       ; every path writes the whole output block
        rts

; R4 = the constant tables (linear addressing).
TBASE:
TABLE_BASE:
        move    #>TABLES,r4
        movec   #>$ffffff,m4
        rts

; Gain ramp from X0 * Y0 to X1 * Y1 over 32 samples: B1 = start, A1 = step.
COEF:
        mpy     x0,y0,b
        mpy     x1,y1,a
        sub     b,a
        asr     #5,a,a
        rts

; New grain. The old one keeps playing (in its own direction) through the
; 4-block crossfade. The new one starts at the playhead, moved back by half the
; distance it gains on the playhead during GRAN samples, so the grain is
; centred on it; then kept inside lo..W-1. It plays in the playhead's direction.
SPLICE:
        move    #>1,a
        move    a,y:(r6+S_FADE)
        move    y:(r6+S_GI),a
        move    a,y:(r6+S_OGI)
        move    y:(r6+S_GF),a
        move    a,y:(r6+S_OGF)
        move    y:(r6+S_GREV),a
        move    a,y:(r6+S_OREV)
        move    #>L64,x0
        move    y:(r6+T_RQ),y0
        mpy     x0,y0,a         ; J = GRAN * grain rate, in frames
        move    a1,y:(r6+T_J)
        move    y:(r6+T_RPQ),y0
        mpy     x0,y0,b         ; GRAN * playhead rate
        move    b1,x1
        move    y:(r6+T_J),a
        sub     x1,a
        asr     a
        move    a1,y:(r6+T_CTR) ; half of what the grain gains on the playhead
        move    a1,x0
        move    y:(r6+S_PI),b
        move    y:(r6+S_PF),b0
        sub     x0,b            ; B = playhead - centring, 24.24
        move    y:(r6+S_LO),x0
        cmp     x0,b
        tfr     x0,b    iflt
        move    y:(r6+T_W),a
        sub     #1,a
        move    a1,x0
        cmp     x0,b
        tfr     x0,b    ifgt
        move    b1,y:(r6+S_GI)
        move    b0,y:(r6+S_GF)
        move    y:(r6+S_PREV),a
        move    a,y:(r6+S_GREV)
        move    y:(r6+S_CNT),a
        move    #>GRAN,x0
        add     x0,a            ; keep the remainder: grains average GRAN samples
        move    a1,y:(r6+S_CNT)
        rts

; Write 32 integer source positions to temporary Y, from A (24.24) in steps of
; the grain rate; B1 nonzero reads reversed. Returns the next position in A.
; Positions outside the sample read as silence. Reversed, the loop runs
; downwards in mirrored coordinates r = lo + hi - 1 - p, and A converts back on
; return. A and B take turns (even and odd samples, each stepping by twice the
; rate) to avoid stalls.
POSGEN:
        move    y:(r6+T_RGI),x1
        move    y:(r6+T_RGF),x0
        move    y:(r6+T_R2I),y1
        move    y:(r6+T_R2F),y0
POSITIONS:
        move    #>$000000,r0    ; kind 4 / TEMP_Y
        movec   #>$ffffff,m0
        tst     b
        bne     POSGEN_REV
        tfr     a,b
        add     x,b
        dor     #16,POSGEN_END
        add     y,a     a,y:(r0)+       ; store a position, then advance
        add     y,b     b,y:(r0)+
POSGEN_END:
        rts
POSGEN_REV:
        move    y:(r6+S_MIR),b
        sub     a,b
        tfr     b,a
        sub     x,b
        dor     #16,POSGEN_REV_END
        sub     y,a     a,y:(r0)+
        sub     y,b     b,y:(r0)+
POSGEN_REV_END:
        move    y:(r6+S_MIR),b
        sub     a,b
        tfr     b,a
        rts

; SAMPLE_READ of N0 frames from the latched bank and slot. A1 = 0 on failure.
SREAD:
        move    y:(r6+S_BANK),x0
        move    y:(r6+S_SLOT),y0
READ_SAMPLES:
        jsr     >$000000        ; kind 5 / SAMPLE_READ
        rts

        if      TRANS
        include 'onsets.inc'
        endif
; ---- cold code: INIT, TRIG and the slice bounds, after the hot code so the
; code RENDER executes stays together in the instruction cache ----
INIT:
        movec   #>$ffffff,m6
        clr     a
        move    a,y:(r6+S_ACT)
        move    a,y:(r6+S_GAIN)
        move    a,y:(r6+S_CNT)
        move    a,y:(r6+S_FADE)
        move    a,y:(r6+S_REL)
        if      TRANS
        move    a,y:(r6+A_CNT)
        move    a,y:(r6+A_SKIP)
        move    #>NONE,b
        move    b1,y:(r6+A_KEY) ; nothing analysed yet
        move    #>1,b
        move    b1,y:(r6+A_DONE)
        endif
        rts

TRIG:
        movec   #>$ffffff,m6
        if      TRANS
        move    #>1,a
        move    a1,y:(r6+A_SKIP) ; no analysis in the block of a TRIG
        endif
        move    y:(r6+P_SMPL),a
        if      BANK_ID<0
        ; One SMPL list over both banks: UW ROM slots first, then the internal ones.
        move    #>UW_SLOTS,x0
        move    #>1,b           ; UW ROM ...
        cmp     x0,a
        blt     TRIG_BANK
        sub     x0,a            ; ... or internal, counted from its first slot
        clr     b
        else
        move    #>BANK_ID,b
        endif
TRIG_BANK:
        move    a1,y:(r6+S_SLOT)
        move    b1,y:(r6+S_BANK)
        move    a1,y0
        move    b1,x0
TRIG_INFO:
        jsr     >$000000        ; kind 5 / SAMPLE_INFO: A1 length, B1 Q16.16 step
        tst     a
        beq     TRIG_EMPTY
        tst     b
        beq     TRIG_EMPTY
        move    b1,y:(r6+S_STEP)
        move    a1,y:(r6+T_LEN)
        bsr     TBASE
        movec   #>$ffffff,m0    ; SAMPLE_INFO may change the M registers BOUND uses
        movec   #>$ffffff,m1
        movec   #>$ffffff,m2
        movec   #>$ffffff,m3
        if      TRANS
        ; Slices at the analysed onsets if the analysis is of this SMPL setting
        ; (a different length means a new sample bank: analyse again)
        move    y:(r6+P_SMPL),a
        move    y:(r6+A_KEY),x0
        cmp     x0,a
        bne     TRIG_EVEN
        move    y:(r6+T_LEN),a
        move    y:(r6+A_LEN),x0
        cmp     x0,a
        beq     TRIG_ONSETS
        move    #>NONE,a
        move    a1,y:(r6+A_KEY)
        bra     TRIG_EVEN
TRIG_ONSETS:
        bsr     ONSET_BOUNDS    ; S_LO, T_N, T_K; B1 = hi
        bra     TRIG_WINDOW
TRIG_EVEN:                      ; otherwise SLIC equal slices
        endif
        ; n = SLIC + 1, k = SLNO mod n, both settings at most 63
        move    #>63,x0
        move    y:(r6+P_SLIC),a
        cmp     x0,a
        tfr     x0,a    ifgt
        add     #1,a
        move    a1,y:(r6+T_N)
        move    a1,x1
        move    y:(r6+P_SLNO),a
        cmp     x0,a
        tfr     x0,a    ifgt
        dor     #63,TRIG_MOD    ; dor, not do: the loop address must be PC-relative
        tfr     a,b
        sub     x1,b
        tfr     b,a     ifge
TRIG_MOD:
        move    a1,y:(r6+T_K)
        if      TRANS
        clr     a               ; equal slices (Y+6 is THRS here)
        move    a1,y:(r6+T_MODE)
        else
        move    y:(r6+P_MODE),a
        move    #>MAX_MODE,x0
        cmp     x0,a
        tfr     x0,a    ifgt
        move    a1,y:(r6+T_MODE)
        move    #>SEED_MODES,x0
        cmp     x0,a
        blt     TRIG_BOUNDS
        bsr     SEEDSUM         ; Perlin seeds: prefix sums P[k], P[k+1], P[n]
        endif
TRIG_BOUNDS:
        ; the window: boundaries k and k + 1, at least MIN_WIN frames apart
        move    y:(r6+T_K),a
        bsr     BOUND
        move    b1,y:(r6+S_LO)
        move    y:(r6+T_K),a
        add     #1,a
        bsr     BOUND
TRIG_WINDOW:
        move    y:(r6+S_LO),x0
        move    #>MIN_WIN,a
        add     x0,a
        cmp     a,b
        tfr     a,b     iflt
        move    b1,y:(r6+S_HI)
        sub     x0,b
        move    b1,y:(r6+S_WIN)
        move    y:(r6+S_HI),b
        add     x0,b
        sub     #1,b
        move    b1,y:(r6+S_MIR)
        move    x0,y:(r6+S_GI)
        move    x0,y:(r6+S_PI)
        clr     a
        move    a,y:(r6+S_GF)
        move    a,y:(r6+S_PF)
        move    a,y:(r6+S_FADE)
        move    a,y:(r6+S_REL)
        move    y:(r6+P_PLAY),b
        move    #>1,x0
        cmp     x0,b
        tfr     x0,a    ifeq    ; REV starts reversed; FWD and BI forwards
        move    a1,y:(r6+S_PREV)
        move    a1,y:(r6+S_GREV)
        move    #>GRAN,a
        move    a1,y:(r6+S_CNT)
        move    #>$7fffff,a
        move    a1,y:(r6+S_ENV)
        move    a1,y:(r6+S_GAIN)
        move    #>1,a
        move    a1,y:(r6+S_ACT)
        rts
TRIG_EMPTY:
        clr     a
        move    a,y:(r6+S_ACT)
        rts

; B1 = frame of slice boundary A1 (0..n): 0 at 0, the length at n, otherwise
; floor(length * u) with u by MODE. Needs R4 = TABLES.
BOUND:
        tst     a
        bne     BOUND_1
        clr     b
        rts
BOUND_1:
        move    y:(r6+T_N),x0
        cmp     x0,a
        blt     BOUND_2
        move    y:(r6+T_LEN),b
        rts
BOUND_2:
        move    y:(r6+T_MODE),b
        tst     b
        beq     BOUND_EQ
        move    #>1,x1
        cmp     x1,b
        bne     BOUND_3
        ; SHUF: u = (3k + (k odd)) / 3n, every odd slice point a third of a slice late
        move    a1,x1
        asl     a
        add     x1,a
        move    x1,b
        and     #>1,b
        add     b,a
        move    x0,b
        asl     b
        add     x0,b
        move    b1,x0
        bra     BOUND_EQ
BOUND_3:
        move    #>SEED_MODES,x1
        cmp     x1,b
        bge     BOUND_SEED
        ; EXP / LOG: R0 = the curve table, 65 words each
        sub     #2,b
        move    b1,x1
        asl     #6,b,b
        add     x1,b
        move    #>TB_EXPC,x1
        add     x1,b
        move    b1,n4
        lua     (r4)+n4,r0
        bra     BOUND_CRV
BOUND_SEED:
        ; seeds: u = P[k] / P[n] (BOUND is only asked for k and k + 1 here)
        move    y:(r6+T_K),x1
        cmp     x1,a
        move    y:(r6+T_PK),a
        beq     BOUND_SEED_K
        move    y:(r6+T_PK1),a
BOUND_SEED_K:
        move    y:(r6+T_PN),x0
BOUND_EQ:
        bsr     DIVQ            ; EQUA: u = k / n
        bra     BOUND_FRAME
BOUND_CRV:
        bsr     DIVQ            ; t = k / n, then the curve at t
        move    y0,a
        asr     #17,a,b
        move    b1,n0           ; segment 0..63
        and     #>$1ffff,a
        lsl     #6,a            ; position within it, Q23
        lua     (r0)+n0,r1
        movem   p:(r1)+,x0
        movem   p:(r1),b
        sub     x0,b
        move    b1,y1
        move    a1,y0
        mpy     y0,y1,b
        add     x0,b
        move    b1,y0
BOUND_FRAME:
        move    y:(r6+T_LEN),x0
        mpy     x0,y0,b
        rts

; Perlin seed j = MODE - SEED_MODES: slice i has width NOISE_MAX + depth *
; N[offset + i * stride] (N the noise table). Writes the prefix sums
; P[k], P[k + 1] and P[n], where P[i] = NOISE_MAX * i + depth * (sum of the
; first i noise values). Needs R4 = TABLES; uses DOR loops of k and n-k-1 reads.
SEEDSUM:
        move    y:(r6+T_MODE),a
        move    #>SEED_MODES,x0
        sub     x0,a
        move    a1,x1           ; j
        asr     #5,a,b
        add     #1,b
        move    b1,n0           ; stride = 1 + j / 32
        move    #>GOLD,y0
        mpy     x1,y0,a         ; A0 = frac(j * golden ratio)
        move    a0,b
        lsr     #1,b
        move    b1,y0
        move    #>OFFMAX,x0
        mpy     x0,y0,a         ; A1 = offset
        move    #>TB_NOISE,x0
        add     x0,a
        move    a1,n4
        lua     (r4)+n4,r0      ; R0 = the seed's first noise value
        move    x1,a
        lsl     #16,a
        move    a1,y0
        move    #>DSPAN,x0
        mpy     x0,y0,a
        move    #>DEPTH0,x0
        add     x0,a
        move    a1,y:(r6+T_DEPTH) ; depth = DEPTH0 + DSPAN * j / 128
        clr     a
        move    y:(r6+T_K),b
        tst     b
        beq     SEEDSUM_K
        move    b1,x1
        dor     x1,SEEDSUM_K
        movem   p:(r0)+n0,x0
        add     x0,a
SEEDSUM_K:
        move    a1,y:(r6+T_PK)  ; sums of the first k, k + 1 and n values
        movem   p:(r0)+n0,x0
        add     x0,a
        move    a1,y:(r6+T_PK1)
        move    y:(r6+T_N),b
        move    y:(r6+T_K),x0
        sub     x0,b
        sub     #1,b
        tst     b
        beq     SEEDSUM_N
        move    b1,x1
        dor     x1,SEEDSUM_N
        movem   p:(r0)+n0,x0
        add     x0,a
SEEDSUM_N:
        move    a1,y:(r6+T_PN)
        ; sums -> prefix sums
        move    y:(r6+T_PK),x0
        move    y:(r6+T_K),b
        bsr     SEEDP
        move    b1,y:(r6+T_PK)
        move    y:(r6+T_PK1),x0
        move    y:(r6+T_K),b
        add     #1,b
        bsr     SEEDP
        move    b1,y:(r6+T_PK1)
        move    y:(r6+T_PN),x0
        move    y:(r6+T_N),b
        bsr     SEEDP
        move    b1,y:(r6+T_PN)
        rts

; B1 = NOISE_MAX * B1 + floor(depth * X0): the prefix sum of i = B1 widths from
; the sum X0 of their noise values.
SEEDP:
        asl     #12,b,b
        move    y:(r6+T_DEPTH),y0
        mpy     x0,y0,a
        move    a1,x0
        add     x0,b
        rts

        if      TRANS
        include 'onsets_trig.inc'
        endif

        include 'tables.inc'
        endsec

