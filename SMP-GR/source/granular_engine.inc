; Shared engine of SMP-GR (UW ROM + E12), SMP-GM (UW ROM) and SMP-G2 (E12): a
; Granulator II-style granular player. The wrapper defines BANK_ID, the
; SAMPLE_INFO / SAMPLE_READ bank: 0 internal, 1 UW ROM, or -1 for both: then
; SMPL 0..UW_SLOTS-1 are UW ROM slots and the settings after them internal slots
; (the wrapper also defines UW_SLOTS). SMPL is latched at TRIG.
;
; v0.4: written for a small code footprint (loops, one routine for every grain):
; on the hardware the code runs through the instruction cache, and v0.3's
; unrolled code overflowed it with many tracks running.
;
; Grains start at the playhead (SEEK plus the SCAN offset, wrapping round the
; sample), moved by a random SPRY amount, and fade in and out linearly over
; about their first and last quarter. DENS sets how many grains sound
; at once on average (a new grain every GRAN / overlap samples); GRAN their
; length. Past SPRY 64 a grain may play backwards (up to 50 % at 127).
;
; Read budget: SAMPLE_READ is called at most twice per block (buffer 0 = slots
; 0,1; buffer 1 = slots 2,3), 16 frames per slot. A full-rate grain takes two
; aligned slots (32 frames per block), a half-rate grain one slot (16 frames,
; mixed at 22.05 kHz and interpolated up to 44.1 kHz). DENS chooses the rate
; (table TIER: full rate up to one grain at once, half rate above, up to 3). A
; grain only starts if the block's worst-case cycles stay within the budget (the
; FREE table, worked out offline by gen_tables.py), otherwise a full-rate grain
; tries half rate, otherwise it is skipped.
;
; Parameters, Y:(r6+1..8):
;   1 PTCH  raw14 bipolar  (setting - 64) / 2 semitones: -32..+32
;   2 SMPL  index          sample slot (latched at TRIG)
;   3 DEC   raw14          decay, 60 dB in 0.03..30 s; 127 = none
;   4 DENS  raw14          grains at once (tables KD, NORM, TIER)
;   5 SEEK  unipolar Q23   playhead start as a fraction of the sample
;   6 SCAN  raw14 bipolar  playhead speed (table SCAN), 64 = still
;   7 GRAN  raw14          grain length and fade (table GRAN)
;   8 SPRY  raw14          random start range and reverse chance (SPRAY, REVT)
;
; Y state: 9 bank  10 slot  11 active  12 length  13 native step (Q16.16)
;  14 random seed  15 decay envelope  16/17 scan offset int/frac  18 samples to
;  the next grain  19 slot state (bit n = slot n in use; bit 4 / 5: slots 0,1 /
;  2,3 hold a full-rate grain)  20 unused  21 last half-rate sample of the last block
; Y scratch within one RENDER: 22..27 R, 2R, 4R (24.24 int/frac)  28 R * 2^17
;  29 master gain  30..33 see the T_ equates  40..55 half-rate sum
; X: 4 grain records of 8 words, the grain in slot n at X:(r6+8n):
;   +0 tier (1 full, 2 half; negative = reversed; 0 = free)  +1 unused
;   +2 blocks played << 12 | blocks left  +3 fade shift (fade = 2^(23 - shift)
;   blocks)  +4 gain reached at the end of the last block  +5 its slot mask bits
;   +6/7 position int/frac

P_PTCH  equ 1
P_SMPL  equ 2
P_DEC   equ 3
P_DENS  equ 4
P_SEEK  equ 5
P_SCAN  equ 6
P_GRAN  equ 7
P_SPRY  equ 8
S_BANK  equ 9
S_SLOT  equ 10
S_ACT   equ 11
S_LEN   equ 12
S_STEP  equ 13
S_SEED  equ 14
S_ENV   equ 15
S_OFFI  equ 16
S_OFFF  equ 17
S_CNT   equ 18
S_MASK  equ 19
S_PROC  equ 20
S_HP    equ 21
T_R1I   equ 22
T_R1F   equ 23
T_R2I   equ 24
T_R2F   equ 25
T_R4I   equ 26
T_R4F   equ 27
T_RQ    equ 28
T_MG    equ 29
T_F     equ 30                  ; pitch fraction
T_OCT   equ 31                  ; octave
T_BUF   equ 32                  ; first slot of the buffer, 0 or 2
T_N0    equ 33                  ; frames to read
H_ACC   equ 40

V_TD    equ 0
V_W     equ 2
V_SH    equ 3
V_G     equ 4
V_BITS  equ 5
V_PI    equ 6
V_PF    equ 7

MIN_LEN equ 256                 ; shorter samples do not play
ENV_OFF equ $000040             ; envelope level treated as silent (about -100 dB)
SEED0   equ $2a5b3d

        section GRANULAR
RENDER:
        movec   #>$ffffff,m6
        move    y:(r6+S_ACT),a
        tst     a
        beq     SILENCE
TABLE_BASE:
        move    #>TABLES,r4

        ; ---- grain rate R = step * 2^((PTCH - 64) / 24), in half-semitone steps ----
        move    y:(r6+P_PTCH),a
        move    #0,x0           ; (TB_PITCH is 0)
        bsr     KLOOK           ; Y0 = PITCH[k] = 2^((k - 64) / 24) / 8
        move    y:(r6+S_STEP),x0
        mpy     x0,y0,a
        asr     #13,a,a         ; 24.24 frames per output sample
        move    a1,y:(r6+T_R1I)
        move    a0,y:(r6+T_R1F)
        asl     #17,a,a
        move    a1,y:(r6+T_RQ)

        ; ---- level: decay envelope (DEC 127 holds it) times the DENS correction ----
        ; (raw14 settings are below 128 * 128: no clamping needed)
        move    y:(r6+P_DEC),a
        move    #>TB_DECAY,x0
        bsr     KLOOK           ; Y0 = decay multiplier per block
        move    y:(r6+S_ENV),x1
        mpy     x1,y0,a         ; envelope at the end of this block ...
        move    #>$7fffff,x0
        move    y0,b
        cmp     x0,b
        tfr     x1,a    ifeq    ; ... held exactly at DEC 127
        move    a1,y:(r6+S_ENV)
        move    a1,x1
        move    #>ENV_OFF,x0
        cmp     x0,a
        bge     R_ENV_OK
        clr     b               ; decayed away: this is the last block
        move    b,y:(r6+S_ACT)
R_ENV_OK:
        move    y:(r6+P_DENS),a
        asr     #7,a,a
        move    a1,n2           ; DENS setting, for SPAWN
        move    #>TB_NORM,x0
        bsr     LOOK            ; Y0 = 1 / sqrt(overlap)
        mpy     x1,y0,b
        move    b1,y:(r6+T_MG)  ; master gain

        ; ---- a new grain when the countdown has run out ----
        move    y:(r6+S_CNT),a
        tst     a
        bgt     R_COUNT
        bsr     SPAWN
R_COUNT:
        move    y:(r6+S_CNT),a
        move    #>32,x0
        sub     x0,a
        move    a1,y:(r6+S_CNT)

        ; ---- clear the output and the half-rate sum ----
        clr     a
        move    #H_ACC,n6
        rep     #32
        move    a,y:(r7)+       ; R7 is back at the block start afterwards
        lua     (r6)+n6,r0
        rep     #16
        move    a,y:(r0)+

        ; ---- the two read buffers: slots 0,1, then 2,3 ----
        move    a,y:(r6+T_BUF)
        bsr     BUFFER
        move    #>2,a
        move    a,y:(r6+T_BUF)
        bsr     BUFFER

        ; ---- half-rate sum into the output: out[2i] += (prev + h[i]) / 2,
        ; out[2i+1] += h[i] (linear interpolation, half a sample late) ----
        bsr     LINEAR
        move    #>$1f,x0
        movec   x0,m3
        movec   x0,m2
        move    #H_ACC,n6
        move    r7,r3
        lua     (r6)+n6,r0
        move    r7,r2
        move    y:(r6+S_HP),y0
        move    #>$400000,x1    ; 0.5
        move    y:(r0)+,y1      ; (the next h is loaded a step early)
        dor     #16,R_UP_END
        move    y:(r3)+,a
        mac     y0,x1,a y:(r3)+,b
        mac     y1,x1,a y1,y0
        add     y0,b    y:(r0)+,y1
        move    a,y:(r2)+
        move    b,y:(r2)+
R_UP_END:
        move    y0,y:(r6+S_HP)

        ; ---- scan: move the offset, wrapping round the sample (R4 set by LINEAR) ----
        move    y:(r6+P_SCAN),a
        move    #>TB_SCAN,x0
        bsr     KLOOK           ; Y0 = speed / 2
        move    y:(r6+S_STEP),x0
        mpy     x0,y0,a
        asr     #10,a,a         ; 32 * step * speed, 24.24 frames per block
        move    y:(r6+S_OFFI),b
        move    y:(r6+S_OFFF),b0
        add     a,b
        move    y:(r6+S_LEN),x0
        tfr     b,a
        add     x0,a            ; below zero: + length
        tst     b
        tlt     a,b
        tfr     b,a
        sub     x0,a            ; length or more: - length
        tge     a,b
        move    b1,y:(r6+S_OFFI)
        move    b0,y:(r6+S_OFFF)
        rts

; Y0 = the table entry at offset X0 + a setting: KLOOK takes a raw14 setting in
; A, LOOK a setting or index in A1. R4 = tables. Uses A, R0, N4.
KLOOK:
        asr     #7,a,a
LOOK:
        add     x0,a
        move    a1,n4
        lua     (r4)+n4,r0
        movem   p:(r0),y0
        rts

; R4 = the tables and linear addressing on R0..R5 (services leave R4 and M0..M5
; undefined). Uses X1.
LINEAR:
TABLE_BASE2:
        move    #>TABLES,r4
        move    #>$ffffff,x1
        movec   x1,m0
        movec   x1,m1
        movec   x1,m2
        movec   x1,m3
        movec   x1,m4
        movec   x1,m5
        rts

; Start a grain if the cycle budget allows one (table FREE, worked out offline).
; Also restarts the countdown. In: N2 = DENS setting, R4 = tables; M4, M5 linear.
; Keeps in registers: R2 grain length NB, R3 its GRAN entry, N3 tier, R1 playhead
; then span, N0 start, N1 SPRY setting, N7 the state bits it adds.
SPAWN:
        ; ---- next grain in GRAN / overlap samples, at least one block ----
        move    y:(r6+P_GRAN),a
        move    #>TB_GRAN,x0
        bsr     KLOOK
        move    y0,r3           ; NB | fade shift << 16
        move    n2,a
        move    #>TB_KD,x0
        bsr     LOOK            ; Y0 = 2^22 / overlap
        move    #>$ffff,x0
        move    r3,a
        and     x0,a            ; NB
        move    a1,x1
        move    a1,r2
        mpy     x1,y0,a
        asl     #6,a,a          ; NB * 32 / overlap samples
        move    #>32,x1
        cmp     x1,a
        tfr     x1,a    iflt
        move    y:(r6+S_CNT),x1
        add     x1,a
        move    a1,y:(r6+S_CNT)
        move    n2,a
        move    #>TB_TIER,x0
        bsr     LOOK
        move    y0,b            ; tier

        ; ---- a slot for that tier within the budget; else half rate ----
SP_TRY:
        move    b1,n3
        asl     #6,b,b
        move    y:(r6+S_MASK),x0
        add     x0,b
        move    b1,a
        move    #>TB_FREE-64,x0
        bsr     LOOK            ; Y0 = v | state bits << 2, or -1
        move    y0,b
        tst     b
        bge     SP_FOUND
        move    n3,b            ; a full-rate grain that does not fit tries half
        move    #>2,x1          ; rate; a half-rate one is skipped
        cmp     x1,b
        bge     SP_NONE
        move    x1,b
        bra     SP_TRY
SP_NONE:
        rts

SP_FOUND:
        move    b1,a
        move    #>3,x0
        and     x0,b            ; slot v
        asl     #3,b,b
        move    b1,n6
        asr     #2,a,a          ; the state bits it adds
        move    y:(r6+S_MASK),b
        lua     (r6)+n6,r5      ; the grain's record
        move    a1,x0
        add     x0,b
        move    a1,n7
        move    b1,y:(r6+S_MASK)

        ; ---- start: playhead (SEEK + scan offset) plus spray, round the sample ----
        move    y:(r6+S_LEN),x0
        move    y:(r6+P_SEEK),y0
        mpy     x0,y0,a
        move    y:(r6+S_OFFI),x1
        move    a1,a
        add     x1,a
        tfr     a,b
        sub     x0,b
        tge     b,a             ; playhead
        move    y:(r6+S_SEED),x1
        move    a1,r1
        bsr     RAND
        move    a1,x1           ; U, -1..1 (and the seed)
        move    y:(r6+P_SPRY),a
        asr     #7,a,a
        move    a1,n1           ; SPRY setting
        move    #>TB_SPRAY,x0
        bsr     LOOK            ; Y0 = spray as a fraction of the sample
        move    y:(r6+S_LEN),x0
        mpy     x0,y0,b         ; spray range in frames
        move    b1,y1
        mpy     x1,y1,a         ; times U
        move    a1,a
        move    r1,y0
        add     y0,a            ; + playhead
        tfr     a,b
        add     x0,b
        tst     a
        tlt     b,a             ; below zero: + length
        tfr     a,b
        sub     x0,b
        tge     b,a             ; length or more: - length
        ; keep the whole grain inside the sample: start <= length - span
        move    r2,b
        asl     #11,b,b         ; length in samples * 64
        move    b1,y0
        move    y:(r6+T_RQ),y1
        mpy     y0,y1,b         ; B1 = frames the grain covers
        move    b1,r1
        move    b1,y1
        move    x0,b
        sub     y1,b
        cmp     b,a
        tgt     b,a
        clr     b
        tst     a
        tlt     b,a             ; longer than the sample: from its start
        move    a1,n0

        ; ---- backwards? a second random number against REVT[SPRY] ----
        bsr     RAND
        move    a1,y:(r6+S_SEED)
        move    a1,x1           ; U'
        move    n1,a
        move    #>TB_REVT,x0
        bsr     LOOK            ; Y0 = threshold
        move    n3,b            ; tier ...
        move    x1,a
        cmp     y0,a
        bge     SP_FORWARD
        move    n0,a            ; same material, from its end backwards
        move    r1,y1
        add     y1,a
        move    #>1,y1
        sub     y1,a
        move    a1,n0
        neg     b               ; ... negative when reversed
SP_FORWARD:
        move    r2,x1
        move    r3,a
        asr     #16,a,a
        move    b1,x:(r5)+      ; +0 tier
        clr     b       x1,x:(r5)+      ; +1 (NB, unused)
        move    x1,x:(r5)+      ; +2 played 0, left NB
        move    a1,x:(r5)+      ; +3 fade shift
        move    n7,x0
        move    b,x:(r5)+       ; +4 gain 0
        move    x0,x:(r5)+      ; +5 slot bits
        move    n0,x0
        move    x0,x:(r5)+      ; +6 start
        move    b,x:(r5)+       ; +7
        rts

; A1 = next random value (signed Q23) from the seed X1: X1 * $19660D + $6EF35F
; mod 2^24. Uses Y0, Y1.
RAND:
        move    #>$19660d,y0
        mpy     x1,y0,a
        move    #>$6ef35f,y1
        asr     a
        move    a0,a
        add     y1,a
        rts

; One read buffer (T_BUF 0: slots 0,1; 2: slots 2,3): its grains' positions,
; one SAMPLE_READ, then each grain's envelope and mix.
BUFFER:
        bsr     LINEAR
        move    y:(r6+T_BUF),x0
        move    y:(r6+S_MASK),a
        asr     x0,a,a
        move    a1,a
        move    #>3,x1
        and     x1,a
        beq     BF_DONE         ; no grain here: no read
        move    #>TB_FRAMES,x0
        bsr     LOOK            ; frames: 16 for the first slot alone, else 32
        move    y0,y:(r6+T_N0)
        bsr     BF_FIRST

        ; ---- positions: stride * R apart (full rate: R, 32; half rate: 2R, 16) ----
POS_ADDR:
        move    #>$000000,r1    ; kind 4 / TEMP_Y
        dor     #2,BF_POS_END
        move    x:(r5),b
        tst     b
        beq     BF_POS_NEXT
        abs     b
        move    b1,x0           ; tier
        move    #>32,a
        asr     x0,a,a
        move    a1,n2           ; positions / 2
        move    y:(r6+T_R1I),a
        move    y:(r6+T_R1F),a0
        asl     x0,a,a          ; 2 * stride * R: A and B take turns
        move    a1,y1
        move    a0,y0
        asr     a               ; stride * R
        move    a1,x1
        move    a0,x0
        move    x:(r5+V_PI),a
        move    x:(r5+V_PF),a0
        move    r1,r0
        tfr     a,b
        brclr   #23,x:(r5),BF_FWD
        sub     x,b
        dor     n2,BF_REV_END
        sub     y,a     a,y:(r0)+
        sub     y,b     b,y:(r0)+
BF_REV_END:
        bra     BF_POS_STORE
BF_FWD:
        add     x,b
        dor     n2,BF_FWD_END
        add     y,a     a,y:(r0)+       ; store a position, then advance
        add     y,b     b,y:(r0)+
BF_FWD_END:
BF_POS_STORE:
        move    a1,x:(r5+V_PI)
        move    a0,x:(r5+V_PF)
BF_POS_NEXT:
        lua     (r5)+n5,r5
        lua     (r1)+n1,r1
BF_POS_END:

        ; ---- read ----
        move    y:(r6+T_N0),n0
        move    y:(r6+S_BANK),x0
        move    y:(r6+S_SLOT),y0
READ_SAMPLES:
        jsr     >$000000        ; kind 5 / SAMPLE_READ
        tst     a
        beq     BF_FAIL
        bsr     LINEAR
        bsr     BF_FIRST
        move    #H_ACC,n6

        ; ---- each grain: envelope, then its samples into the output or the half-rate sum ----
PCM_ADDR:
        move    #>$000000,r1    ; kind 3 / TEMP_X
        dor     #2,BF_MIX_END
        move    x:(r5),b
        tst     b
        beq     BF_MIX_NEXT
        abs     b
        move    b1,n3           ; tier
        ; grain envelope at the end of this block: min(1, t / fade),
        ; t = min(blocks played, blocks left)
        move    #>$000fff,x1
        move    x:(r5+V_W),a
        add     x1,a            ; played + 1, left - 1
        move    a1,x:(r5+V_W)
        tfr     a,b
        and     x1,b            ; left
        asr     #12,a,a
        move    a1,a            ; played
        cmp     a,b
        tfr     b,a     iflt    ; t
        tst     b
        bne     BF_ALIVE
        bsr     FREE_GRAIN      ; its last block
BF_ALIVE:
        move    x:(r5+V_SH),y0
        asl     y0,a,a          ; t / fade = t << fade shift
        move    y:(r6+T_MG),y1
        move    a,x1            ; min(1, t / fade): the limiter clips (linear fade)
        mpy     x1,y1,a
        move    a,y1            ; gain at the end of the block
        move    x:(r5+V_G),b    ; gain at its start
        move    y1,x:(r5+V_G)
        move    y1,a
        sub     b,a
        move    r1,r0
        brset   #1,n3,BF_HALF
        asr     #5,a,a          ; full rate: 32 samples into the output
        move    #>$1f,x0
        movec   x0,m2
        movec   x0,m4
        move    r7,r2
        move    r7,r4
        move    #32,n2
        bra     BF_SUM
BF_HALF:
        asr     #4,a,a          ; half rate: 16 samples into the half-rate sum
        lua     (r6)+n6,r2
        lua     (r6)+n6,r4
        move    #16,n2
BF_SUM:
        move    a1,x1           ; gain step
        move    x:(r0)+,x0
        move    y:(r4)+,a
        move    b,y1
        add     x1,b
        dor     n2,BF_SUM_END
        mac     x0,y1,a x:(r0)+,x0      b,y1
        add     x1,b    a,y:(r2)+
        move    y:(r4)+,a
BF_SUM_END:
        move    #>$ffffff,x0
        movec   x0,m2
        movec   x0,m4
BF_MIX_NEXT:
        lua     (r5)+n5,r5
        lua     (r1)+n1,r1
BF_MIX_END:
BF_DONE:
        rts

; R5 = the buffer's first grain record, N5 = 8 (record stride), N1 = 16 (slot stride).
BF_FIRST:
        move    y:(r6+T_BUF),a
        asl     #3,a,a
        move    a1,n6
        move    #8,n5
        move    #16,n1
        lua     (r6)+n6,r5
        rts

; The grain at R5 ends with this block: free its slots and its record. Keeps A.
FREE_GRAIN:
        move    x:(r5+V_BITS),x0
        move    y:(r6+S_MASK),b
        sub     x0,b
        move    b1,y:(r6+S_MASK)
        clr     b
        move    b,x:(r5)        ; free (the mix after this still uses N3)
        rts

; The sample slot could not be read: stop after this block (return from BUFFER).
BF_FAIL:
        clr     a
        move    a,y:(r6+S_ACT)
        rts

; ---- code that runs once per trigger or while silent: kept after the per-block
; code, so the code a playing block runs stays compact in the instruction cache ----
INIT:
        movec   #>$ffffff,m6
        clr     a
        move    a,y:(r6+S_ACT)
        bsr     CLEAR_GRAINS
        move    r1,a            ; a different random sequence on every track
        move    #>SEED0,x0
        add     x0,a
        move    a1,y:(r6+S_SEED)
        rts

TRIG:
        movec   #>$ffffff,m6
        move    y:(r6+P_SMPL),a
        if      BANK_ID<0
        move    #>UW_SLOTS,x0   ; one SMPL list: UW ROM slots, then internal ones
        move    #>1,b
        cmp     x0,a
        blt     TRIG_BANK
        sub     x0,a
        clr     b
        else
        move    #>BANK_ID,b     ; one bank only
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
        move    a1,y:(r6+S_LEN)
        move    #>MIN_LEN,x1
        cmp     x1,a
        blt     TRIG_EMPTY
        bsr     CLEAR_GRAINS    ; (the firmware's anti-click fade covers the cut)
        move    a,y:(r6+S_OFFI)
        move    a,y:(r6+S_OFFF)
        move    a,y:(r6+S_CNT)  ; the first grain starts at once
        move    a,y:(r6+S_HP)
        move    #>$7fffff,a
        move    a,y:(r6+S_ENV)
        move    #>1,a
        move    a,y:(r6+S_ACT)
        rts
TRIG_EMPTY:
        clr     a
        move    a,y:(r6+S_ACT)
        rts

; Every grain record free, no slots in use. Returns A = 0.
CLEAR_GRAINS:
        movec   #>$ffffff,m0
        move    r6,r0
        clr     a
        rep     #32
        move    a,x:(r0)+
        move    a,y:(r6+S_MASK)
        rts

SILENCE:
        clr     a
        move    a,y:(r6+S_ACT)
        rep     #32
        move    a,y:(r7)+       ; every path writes the whole output block
        rts

        include 'tables.inc'
        endsec
