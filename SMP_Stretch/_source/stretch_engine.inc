; Shared engine of SMP-ST (UW ROM) and SMP-T2 (internal E12 samples): sample
; playback with a lo-fi splice time-stretch (S950 style). The wrapper defines
; BANK_ID, the SAMPLE_INFO / SAMPLE_READ bank: 0 internal, 1 UW ROM, or -1 for
; both: SMPL 0..UW_SLOTS-1 are UW ROM slots, the settings after them internal
; slots (the wrapper then also defines UW_SLOTS).
;
; One grain plays at a time. A playhead moves through the sample, slowed by TIME.
; Every GRAN output samples, on a 32-sample block boundary, a new grain starts
; near the playhead, centred on it and offset by a random FLUX amount, and the
; two grains crossfade over the next 4 blocks (128 samples). The splice is
; worked out at the end of an ordinary block, and PTCH and TIME are re-read
; only outside crossfades, which keeps the crossfade blocks (two sample reads)
; inside the cycle budget. PTCH sets the grain read rate, so time and pitch are
; independent. Grains read straight on past the window (no wrapping); a grain
; about to run out of the window splices back to the playhead early. The voice
; fades out over 4 blocks when the playhead reaches END; TIME 127 freezes it.
; DEC decays the level; 127 holds it.
;
; END before STRT plays the sample in reverse, from STRT back to END. The
; engine always runs forwards through the window lo..hi; in reverse, POSGEN
; reads at floor(lo + hi - 1 - p) instead of floor(p).
;
; Parameters, Y:(r6+1..8):
;   1 PTCH  raw14 bipolar  (setting - 64) / 2 semitones: -32..+32, 1/256 steps between
;   2 SMPL  index          slot in the bank: UW 0..47, internal 0..20 (latched at TRIG)
;   3 DEC   raw14          decay, 60 dB in 0.03..30 s; 127 = no decay
;   4 TIME  raw14          playhead slow-down from a table: 0 normal, 42 half, 127 frozen
;   5 STRT  unipolar Q23   start as a fraction of the sample; 127 = its end (latched)
;   6 END   unipolar Q23   end as a fraction; 127 = whole sample (latched)
;   7 GRAN  squared Q23    grain length 300 + 4776*s output samples (300..5000)
;   8 FLUX  unipolar Q23   jitter: position up to +-0.75 grain, length +-37.5%
;
; Persistent Y state (Y+9: the latched bank when BANK_ID is -1, otherwise unused):
;  10 active  11/12 grain position int/frac  13/14 playhead int/frac
;  15 lo  16 hi  17 hi-lo  18 native step (Q16.16)  19 samples to next splice
;  20 gain reached at the end of the last block  21 random seed  22 slot
;  23 reverse  24 lo + hi - 1  25 decay envelope  26 end fade step (0 = none, 1..4)
;  27 crossfade step (0 = none, 1..4)  28/29 old grain position int/frac
; Rates, recomputed in every block outside a crossfade:
;  30/31 grain rate (24.24)  32 grain rate * 2^17  49/50 twice the grain rate
;  35/36 playhead step per block (24.24)  37 playhead rate * 2^17
; Y scratch within one RENDER (services clobber most registers):
;  33 PTCH fraction  34 octave + 6  38/39 gain at block start/end
;  40/41 old grain gain start/step  42/43 new grain gain start/step
;  44 K  45 GRAN  46 64 * GRAN  47 J  48 centring

P_PTCH  equ 1
P_SMPL  equ 2
P_DEC   equ 3
P_TIME  equ 4
P_STRT  equ 5
P_END   equ 6
P_GRAN  equ 7
P_FLUX  equ 8
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
S_SEED  equ 21
S_SLOT  equ 22
S_REV   equ 23
S_MIR   equ 24
S_ENV   equ 25
S_REL   equ 26
S_FADE  equ 27
S_OGI   equ 28
S_OGF   equ 29
T_RGI   equ 30
T_RGF   equ 31
T_RQ    equ 32
T_F     equ 33
T_OCT   equ 34
T_VBI   equ 35
T_VBF   equ 36
T_RPQ   equ 37
T_G0    equ 38
T_G1    equ 39
T_CO0   equ 40
T_COS   equ 41
T_CN0   equ 42
T_CNS   equ 43
T_K     equ 44
T_GRAN  equ 45
T_L64   equ 46
T_J     equ 47
T_CTR   equ 48
T_R2I   equ 49
T_R2F   equ 50

MIN_WIN equ 64                  ; shortest STRT..END window in frames
ENV_OFF equ $000040             ; envelope level treated as silent (about -100 dB)
SEED0   equ $2a5b3d             ; random seed of track 0

        section ROM_STRETCH
INIT:
        movec   #>$ffffff,m6
        clr     a
        move    a,y:(r6+S_ACT)
        move    a,y:(r6+S_GAIN)
        move    a,y:(r6+S_CNT)
        move    a,y:(r6+S_REL)
        move    a,y:(r6+S_FADE)
        move    r1,a            ; a different random sequence on every track
        move    #>SEED0,x0
        add     x0,a
        move    a1,y:(r6+S_SEED)
        rts

TRIG:
        movec   #>$ffffff,m6
        if      BANK_ID<0
        ; One SMPL list over both banks: UW ROM slots first, then the internal ones.
        move    y:(r6+P_SMPL),a
        move    #>UW_SLOTS,x0
        move    #>1,b           ; UW ROM ...
        cmp     x0,a
        blt     TRIG_BANK
        sub     x0,a            ; ... or internal, counted from its first slot
        clr     b
TRIG_BANK:
        move    a1,y:(r6+S_SLOT)
        move    b1,y:(r6+S_BANK)
        move    a1,y0
        move    b1,x0
        else
        move    y:(r6+P_SMPL),y0
        move    y0,y:(r6+S_SLOT)
        move    #>BANK_ID,x0
        endif
TRIG_INFO:
        jsr     >$000000        ; kind 5 / SAMPLE_INFO: A1 length, B1 Q16.16 step
        tst     a
        beq     TRIG_EMPTY
        tst     b
        beq     TRIG_EMPTY
        move    b1,y:(r6+S_STEP)
        move    a1,x0           ; length
        move    y:(r6+P_STRT),y0
        bsr     FRAME_AT
        move    b1,y:(r6+S_LO)  ; start frame
        move    y:(r6+P_END),y0
        bsr     FRAME_AT
        move    b1,y:(r6+S_HI)  ; end frame
        move    y:(r6+S_LO),y1
        clr     a               ; forwards ...
        cmp     y1,b
        bge     TRIG_DIR
        move    b1,y:(r6+S_LO)  ; ... unless END is before STRT: the window
        move    y1,y:(r6+S_HI)  ; is END..STRT, played from its top down
        move    #>1,a
TRIG_DIR:
        move    a1,y:(r6+S_REV)
        move    y:(r6+S_LO),y1
        move    y1,y:(r6+S_GI)
        move    y1,y:(r6+S_PI)
        move    y:(r6+S_HI),b
        add     y1,b
        sub     #1,b
        move    b1,y:(r6+S_MIR)
        move    y:(r6+S_HI),b
        sub     y1,b
        move    b1,y:(r6+S_WIN)
        move    #>MIN_WIN,y1
        cmp     y1,b
        blt     TRIG_EMPTY      ; STRT and END too close together
        clr     a
        move    a,y:(r6+S_GF)
        move    a,y:(r6+S_PF)
        move    a,y:(r6+S_REL)
        move    a,y:(r6+S_FADE)
        bsr     GRAN_LEN
        move    a1,y:(r6+S_CNT) ; the first grain has no length jitter
        move    #>$7fffff,a
        move    a,y:(r6+S_ENV)
        move    a,y:(r6+S_GAIN)
        move    #>1,a
        move    a,y:(r6+S_ACT)
        rts
TRIG_EMPTY:
        clr     a
        move    a,y:(r6+S_ACT)
        rts

; B1 = floor(length X0 * fraction Y0), or the whole length at setting 127. Keeps X0.
FRAME_AT:
        mpy     x0,y0,b
        move    b1,b
        move    #>$7f0000,y1
        move    y0,a
        cmp     y1,a
        tfr     x0,b    ifge
        rts

RENDER:
        movec   #>$ffffff,m6
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
        move    a1,y:(r6+T_OCT)
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
        move    y:(r6+S_STEP),x0
        move    b1,y0
        mpy     x0,y0,a         ; A1:A0 = step * 2^(n/12) / 4 * 2^40
        move    y:(r6+T_OCT),x0
        move    #>20,b
        sub     x0,b
        move    b1,x0
        asr     x0,a,a          ; shift by 20 - (octave + 6): 24.24 frames/sample
        move    a1,y:(r6+T_RGI)
        move    a0,y:(r6+T_RGF)
        tfr     a,b
        asl     #17,b,b
        move    b1,y:(r6+T_RQ)
        asl     a
        move    a1,y:(r6+T_R2I) ; twice the grain rate, for POSGEN
        move    a0,y:(r6+T_R2F)

        ; ---- playhead step per block = 32 * step * speed / 8192, with speed
        ; from the TIME table: 8192 at 0 (normal), 4096 at 42, 0 at 127 ----
        move    y:(r6+P_TIME),a
        asr     #7,a,a
        move    #>127,x0
        cmp     x0,a
        tfr     x0,a    ifgt
        move    #0,x0
        cmp     x0,a
        tfr     x0,a    iflt
        move    #>TB_SPEED,x0
        add     x0,a
        move    a1,n4
        lua     (r4)+n4,r0
        movem   p:(r0),y0
        move    y:(r6+S_STEP),x0
        mpy     x0,y0,a
        asr     a
        move    a1,y:(r6+T_VBI)
        move    a0,y:(r6+T_VBF)
        asl     #12,a,a
        move    a1,y:(r6+T_RPQ) ; playhead rate per sample * 2^17
R_RATES_DONE:

        ; ---- end fade: starts when the playhead reaches hi ----
        move    y:(r6+S_REL),a
        tst     a
        bne     R_REL_STEP
        move    y:(r6+S_HI),y1
        move    y:(r6+S_PI),a
        cmp     y1,a
        blt     R_REL_DONE
        clr     a
R_REL_STEP:
        move    #>1,x0
        add     x0,a
        move    a1,y:(r6+S_REL)
R_REL_DONE:

        ; ---- level: decay envelope times the end fade ----
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
        move    a1,x0
        move    y:(r6+S_REL),a
        move    #>TB_QTR,y1
        add     y1,a
        move    a1,n4
        lua     (r4)+n4,r0
        movem   p:(r0),y0
        mpy     x0,y0,a
        move    a1,y:(r6+T_G1)
        move    y:(r6+S_GAIN),x1
        move    x1,y:(r6+T_G0)
        move    a1,y:(r6+S_GAIN)
        move    y:(r6+S_REL),a
        move    #>4,x0
        cmp     x0,a
        blt     R_REL_OK
        clr     b               ; end fade complete: stop after this block
        move    b,y:(r6+S_ACT)
R_REL_OK:

R_COEF:
        ; ---- per-grain gain ramps for this block ----
        bsr     TBASE
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
        ; ---- outside crossfades: splice once the grain has played GRAN samples,
        ; or early when the grain would leave the window within 8 blocks (high
        ; PTCH runs a grain through the sample fast). The new grain starts with
        ; the next block, at the playhead's new place.
        bsr     COUNT_GRAIN
        ble     R_SPLICE
        move    y:(r6+S_REL),a
        tst     a
        bne     R_DONE
        move    y:(r6+T_RGI),a
        move    y:(r6+T_RGF),a0
        asl     #8,a,a          ; 256 * grain rate
        move    y:(r6+S_GI),x1
        move    y:(r6+S_GF),x0
        add     x,a
        move    y:(r6+S_HI),x0
        cmp     x0,a
        blt     R_DONE
        clr     a               ; early splice: the next grain counts from zero
        move    a,y:(r6+S_CNT)
R_SPLICE:
        bsr     SPLICE
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
        bsr     COUNT_GRAIN     ; the grain keeps counting through the crossfade
        rts

; Unless the voice is fading out, count down one block of the grain:
; returns with the GT condition set while there is grain left.
COUNT_GRAIN:
        move    y:(r6+S_REL),a
        tst     a
        bne     COUNT_GRAIN_END
        move    y:(r6+S_CNT),a
        move    #>32,x0
        sub     x0,a
        move    a1,y:(r6+S_CNT)
        tst     a
        rts
COUNT_GRAIN_END:
        move    #>1,a           ; fading out: no splice
        tst     a
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

; New grain. The old one keeps playing through the 4-block crossfade. The new
; one starts at playhead + 0.75 * FLUX * U * GRAN * grain rate, moved back by half the
; distance it gains on the playhead during the grain, so the grain is centred
; on the playhead; then kept inside lo..hi-1. The grain after it lasts
; GRAN * (1 + 0.375 * FLUX * U').
SPLICE:
        move    #>1,a
        move    a,y:(r6+S_FADE)
        move    y:(r6+S_GI),a
        move    a,y:(r6+S_OGI)
        move    y:(r6+S_GF),a
        move    a,y:(r6+S_OGF)
        bsr     RAND
        move    a1,y1
        move    y:(r6+P_FLUX),x0
        move    #>$600000,y0    ; 0.75
        mpy     x0,y0,a
        move    a1,x0
        mpy     x0,y1,a
        move    a1,y:(r6+T_K)   ; K = 0.75 * FLUX * U
        bsr     GRAN_LEN
        move    a1,y:(r6+T_GRAN)
        asl     #6,a,a
        move    a1,y:(r6+T_L64)
        move    a1,x0
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
        move    y:(r6+T_J),x0
        move    y:(r6+T_K),y0
        mpy     x0,y0,b         ; B1 = floor(J * K)
        move    y:(r6+S_PF),b0
        move    y:(r6+S_PI),x0
        add     x0,b
        move    y:(r6+T_CTR),x0
        sub     x0,b            ; B = playhead + offset - centring, 24.24
        move    y:(r6+S_LO),x0
        cmp     x0,b
        tfr     x0,b    iflt
        move    y:(r6+S_HI),a
        sub     #1,a
        move    a1,x0
        cmp     x0,b
        tfr     x0,b    ifgt
        move    b1,y:(r6+S_GI)
        move    b0,y:(r6+S_GF)
        bsr     RAND
        move    a1,y1
        move    y:(r6+P_FLUX),x0
        move    #>$300000,y0    ; 0.375
        mpy     x0,y0,a
        move    a1,x0
        mpy     x0,y1,a
        move    a1,y1
        move    y:(r6+T_GRAN),x0
        mpy     x0,y1,b         ; B1 = floor(GRAN * 0.375 * FLUX * U')
        add     x0,b
        move    y:(r6+S_CNT),x0
        add     x0,b            ; keep the remainder: grains average GRAN samples
        move    b1,y:(r6+S_CNT)
        rts

; A1 = GRAN in output samples, 300 + floor(4776 * squared setting); A0 = 0.
GRAN_LEN:
        move    y:(r6+P_GRAN),y0
        move    #>4776,x0
        mpy     x0,y0,a
        move    #>300,x0
        add     x0,a
        move    a1,a
        rts

; A1 = next random value (signed Q23): seed = seed * $19660D + $6EF35F mod 2^24.
RAND:
        move    y:(r6+S_SEED),x0
        move    #>$19660d,y0
        mpy     x0,y0,a
        asr     a
        move    a0,a
        move    #>$6ef35f,x0
        add     x0,a
        move    a1,y:(r6+S_SEED)
        rts

; Write 32 integer source positions to temporary Y, from A (24.24) in steps of
; the grain rate. Returns the next position in A. Positions outside the sample
; read as silence. In reverse the loop runs downwards in mirrored coordinates
; r = lo + hi - 1 - p, and A converts back on return. A and B take turns
; (even and odd samples, each stepping by twice the rate) to avoid stalls.
POSGEN:
        move    y:(r6+T_RGI),x1
        move    y:(r6+T_RGF),x0
        move    y:(r6+T_R2I),y1
        move    y:(r6+T_R2F),y0
POSITIONS:
        move    #>$000000,r0    ; kind 4 / TEMP_Y
        movec   #>$ffffff,m0
        move    y:(r6+S_REV),b
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
        if      BANK_ID<0
        move    y:(r6+S_BANK),x0
        else
        move    #>BANK_ID,x0
        endif
        move    y:(r6+S_SLOT),y0
READ_SAMPLES:
        jsr     >$000000        ; kind 5 / SAMPLE_READ
        rts

        include 'tables.inc'
        endsec
