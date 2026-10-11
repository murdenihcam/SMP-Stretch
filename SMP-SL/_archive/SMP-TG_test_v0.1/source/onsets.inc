; Onset analysis of SMP-TR (TRANS builds), included by slicer_engine.inc.
; tr_model.py is the bit-exact reference and describes the method.
;
; RENDER runs ANALYSE after the voice in blocks with cycles to spare. Each call
; does one step: restart for a new SMPL setting (SAMPLE_INFO), read a hop and
; look for an onset, place a pending onset (REFINE, one read), or add it to the
; list (COMMIT). The list, X:(r6+0..59), holds up to MAX_ON onsets in position
; order: X+2i = position, X+2i+1 = (q << 8) | rank, q = reference / energy in
; Q15 (smaller is stronger), rank 0 = the strongest.

; X0 = bank, Y0 = slot of the SMPL setting now (not the latched one).
KEYSEL:
        move    y:(r6+P_SMPL),a
        if      BANK_ID<0
        move    #>UW_SLOTS,x0
        move    #>1,b
        cmp     x0,a
        blt     KEYSEL_DONE
        sub     x0,a
        clr     b
        else
        move    #>BANK_ID,b
        endif
KEYSEL_DONE:
        move    a1,y0
        move    b1,x0
        rts

ANALYSE:
        movec   #>$ffffff,m0    ; the voice's service calls may have changed them
        movec   #>$ffffff,m1
        movec   #>$ffffff,m2
        movec   #>$ffffff,m3
        movec   #>$ffffff,m4
        movec   #>$ffffff,m5
        move    y:(r6+P_SMPL),a
        move    y:(r6+A_KEY),x0
        cmp     x0,a
        beq     AN_SAME
        ; ---- a new SMPL setting: start over ----
        move    a1,y:(r6+A_KEY)
        bsr     KEYSEL
ANA_INFO:
        jsr     >$000000        ; kind 5 / SAMPLE_INFO: A1 length
        move    a1,y:(r6+A_LEN)
        move    a1,b
        asr     #15,b,b
        add     #1,b            ; stride = 1 + length / 32768, 16..64
        move    #>MIN_STRIDE,x0
        cmp     x0,b
        tfr     x0,b    iflt
        move    #>MAX_STRIDE,x0
        cmp     x0,b
        tfr     x0,b    ifgt
        move    b1,y:(r6+A_STRIDE)
        clr     b
        move    b,y:(r6+A_POS)
        move    b,y:(r6+A_ENV)
        move    b,y:(r6+A_CNT)
        move    #>NONE,b
        move    b1,y:(r6+A_PPOS)
        clr     b
        move    y:(r6+A_LEN),a
        tst     a
        bne     AN_RESTARTED
        move    #>1,b           ; no sample: nothing to analyse
AN_RESTARTED:
        move    b1,y:(r6+A_DONE)
        rts
AN_SAME:
        move    y:(r6+A_DONE),a
        tst     a
        beq     AN_GO
        rts
AN_GO:
        ; ---- a pending onset is due GAP_FR frames on, or at the end ----
        move    y:(r6+A_PPOS),a
        move    #>NONE,x0
        cmp     x0,a
        beq     AN_NOPEND
        move    y:(r6+A_PAGE),a
        move    #>GAP_FR,x0
        cmp     x0,a
        bge     AN_DUE
        move    y:(r6+A_POS),a
        move    y:(r6+A_LEN),x0
        cmp     x0,a
        blt     AN_NOPEND
AN_DUE:
        move    y:(r6+A_PAGE),a
        move    #>REFINED,x0
        cmp     x0,a
        beq     COMMIT
        bra     REFINE
AN_NOPEND:
        move    y:(r6+A_POS),a
        move    y:(r6+A_LEN),x0
        cmp     x0,a
        blt     AN_HOP
        move    #>1,a           ; the end
        move    a1,y:(r6+A_DONE)
        rts
AN_HOP:
        ; ---- one hop: 16 pairs of neighbouring frames, 2 * stride apart ----
        move    y:(r6+A_STRIDE),b
        asl     b
        move    b1,x0
        move    #>1,y1
ANA_POS:
        move    #>$000000,r0    ; kind 4 / TEMP_Y
        move    y:(r6+A_POS),a
        dor     #16,AN_POS_END
        tfr     a,b     a,y:(r0)+
        add     y1,b
        move    b,y:(r0)+
        add     x0,a
AN_POS_END:
        bsr     KEYSEL
        move    #32,n0
ANA_READ:
        jsr     >$000000        ; kind 5 / SAMPLE_READ
        tst     a
        bne     AN_READ_OK
        move    #>1,a
        move    a1,y:(r6+A_DONE)
        rts
AN_READ_OK:
ANA_PCM:
        move    #>$000000,r0    ; kind 3 / TEMP_X
        movec   #>$ffffff,m0
        movec   #>$ffffff,m1
        move    r0,r1
        clr     b
        dor     #32,AN_SX       ; B = sum |x| ...
        move    x:(r0)+,a
        abs     a
        add     a,b
AN_SX:
        dor     #16,AN_SD       ; ... + 4 * sum |x1 - x0|
        move    x:(r1)+,x0
        move    x:(r1)+,a
        sub     x0,a
        abs     a
        asl     #2,a,a
        add     a,b
AN_SD:
        asr     #8,b,b
        move    b1,x:(r6+X_E)   ; E
        ; the peak follower, fallen by one hop
        move    y:(r6+A_STRIDE),x0
        move    #>DK,y0
        mpy     x0,y0,a
        asr     a
        move    a0,y0
        move    y:(r6+A_ENV),x0
        mpy     x0,y0,a
        move    a1,x1
        move    x0,a
        sub     x1,a
        move    a1,x:(r6+X_ENVD)
        move    #>FLOOR,x0
        add     x0,a            ; ref
        ; an onset candidate?
        move    x:(r6+X_E),b
        move    #>EMIN,x0
        cmp     x0,b
        blt     AN_NOCAND
        move    a1,x0
        cmp     x0,b
        ble     AN_NOCAND
        move    y:(r6+A_POS),a
        move    #>MINSTART,y0
        cmp     y0,a
        blt     AN_NOCAND
        move    x0,a
        move    b1,x0
        bsr     DIVQ            ; ref / E
        move    y0,a
        asr     #8,a,a
        move    a1,a
        move    #>QMAX,x0
        cmp     x0,a
        bgt     AN_NOCAND
        move    a1,x1           ; q
        move    y:(r6+A_PPOS),a
        move    #>NONE,x0
        cmp     x0,a
        bne     AN_PEND_UPD
        move    y:(r6+A_POS),a  ; the first: pending from here
        move    a1,y:(r6+A_PPOS)
        move    x1,y:(r6+A_PQ)
        clr     a
        move    a,y:(r6+A_PAGE)
        bra     AN_NOCAND
AN_PEND_UPD:
        move    y:(r6+A_PQ),a   ; a later, stronger one: keep its strength
        cmp     x1,a
        ble     AN_NOCAND
        move    x1,y:(r6+A_PQ)
AN_NOCAND:
        move    x:(r6+X_E),a
        move    x:(r6+X_ENVD),x0
        cmp     x0,a
        tfr     x0,a    iflt
        move    a1,y:(r6+A_ENV)
        move    y:(r6+A_STRIDE),a
        asl     #5,a,a
        move    a1,x0           ; hop length
        move    y:(r6+A_PPOS),a
        move    #>NONE,y0
        cmp     y0,a
        beq     AN_ADVANCE
        move    y:(r6+A_PAGE),a
        add     x0,a
        move    a1,y:(r6+A_PAGE)
AN_ADVANCE:
        move    y:(r6+A_POS),a
        add     x0,a
        move    a1,y:(r6+A_POS)
        rts

; Place the pending onset: 32 frames 2 * stride apart from one hop before it;
; from the loudest back to where two in a row are below 1/8 of it, one step earlier.
REFINE:
        move    y:(r6+A_STRIDE),b
        move    y:(r6+A_PPOS),a
        asl     #5,b,b
        sub     b,a
        clr     b
        cmp     b,a
        tfr     b,a     iflt
        move    a1,x:(r6+X_WS)  ; window start
        move    y:(r6+A_STRIDE),b
        asl     b
        move    b1,x0
REF_POS:
        move    #>$000000,r0    ; kind 4 / TEMP_Y
        dor     #32,REF_POS_END
        move    a,y:(r0)+
        add     x0,a
REF_POS_END:
        bsr     KEYSEL
        move    #32,n0
REF_READ:
        jsr     >$000000        ; kind 5 / SAMPLE_READ
        move    #>REFINED,b
        move    b1,y:(r6+A_PAGE)
        tst     a
        bne     REF_OK
        rts
REF_OK:
REF_PCM:
        move    #>$000000,r0    ; kind 3 / TEMP_X
        movec   #>$ffffff,m0
        movec   #>$ffffff,m1
        movec   #>$ffffff,m2
        movec   #>$ffffff,m3
        movec   #>$ffffff,m4
        movec   #>$ffffff,m5
        move    r0,r5
        move    r0,r2
        move    (r2)+           ; R2 = just past the largest so far (index 0 if all are 0)
        clr     b
        dor     #32,REF_MAG     ; |x| in place (limited to $7fffff), B = the largest
        move    x:(r0),a
        abs     a
        move    a,x:(r0)
        move    x:(r0)+,a
        cmp     b,a
        tgt     a,b     r0,r2   ; a strictly larger one: the first largest wins
REF_MAG:
        move    b1,x1
        move    x1,a
        asr     #3,a,a
        move    a1,y1           ; 1/8 of the largest
        move    r2,r3
        move    (r3)-
        move    (r3)-           ; R3 = |x[i - 1]|
        move    r2,a
        move    r5,x0
        sub     x0,a
        sub     #1,a            ; i
        move    #WALK_MAX,r2    ; steps left
REF_BACK:
        move    #>2,x0
        cmp     x0,a
        blt     REF_BACK_END
        move    r2,b
        tst     b
        beq     REF_BACK_END
        move    r3,r4
        move    x:(r4)-,b
        cmp     y1,b
        bge     REF_STEP
        move    x:(r4),b
        cmp     y1,b
        blt     REF_BACK_END
REF_STEP:
        sub     #1,a
        move    (r3)-
        move    (r2)-
        bra     REF_BACK
REF_BACK_END:
        tst     a
        beq     REF_AT_WS
        sub     #1,a
        move    a1,x0
        move    y:(r6+A_STRIDE),y0
        mpy     x0,y0,b         ; B0 = (i - 1) * 2 * stride
        move    b0,x0
        move    x:(r6+X_WS),a
        add     x0,a
        bra     REF_FLOOR
REF_AT_WS:
        move    x:(r6+X_WS),a
REF_FLOOR:
        ; not before the last listed onset + MIN_WIN (or MINSTART)
        move    y:(r6+A_CNT),b
        tst     b
        bne     REF_AFTER
        move    #>MINSTART,x0
        bra     REF_SET
REF_AFTER:
        asl     b
        sub     #2,b
        move    b1,n1
        move    r6,r1
        nop
        move    x:(r1+n1),x0
        move    #>MIN_WIN,b
        add     x0,b
        move    b1,x0
REF_SET:
        cmp     x0,a
        tfr     x0,a    iflt
        move    a1,y:(r6+A_PPOS)
        rts

; Add the pending onset to the list, which keeps the MAX_ON strongest.
COMMIT:
        move    y:(r6+A_PQ),x1  ; q
        move    y:(r6+A_PPOS),x0
        move    x0,x:(r6+X_WS)  ; position
        move    #>NONE,a
        move    a1,y:(r6+A_PPOS)
        move    #0,r2           ; its rank: the listed onsets at least as strong
        move    r6,r1
        move    y:(r6+A_CNT),b
        tst     b
        beq     CM_RANKED
        move    b1,n3
        dor     n3,CM_RANK_END
        move    (r1)+
        move    x:(r1),a
        tfr     a,b
        asr     #8,b,b
        cmp     x1,b
        bgt     CM_WEAKER
        move    (r2)+
        bra     CM_RANK_NEXT
CM_WEAKER:
        add     #1,a            ; a weaker one moves down a rank
        move    a1,x:(r1)
CM_RANK_NEXT:
        move    (r1)+
CM_RANK_END:
CM_RANKED:
        move    #>MAX_ON,x0
        move    y:(r6+A_CNT),a
        cmp     x0,a
        blt     CM_APPEND
        move    r2,b            ; a full list ...
        cmp     x0,b
        blt     CM_REMOVE
        rts                     ; ... and the new one the weakest: dropped
CM_REMOVE:
        move    r6,r1           ; drop the one now ranked MAX_ON
        dor     #MAX_ON,CM_FIND
        move    (r1)+
        move    x:(r1)+,a
        and     #>$ff,a
        cmp     x0,a
        teq     x0,a    r1,r4   ; R4 = just past it
CM_FIND:
        move    r4,r1
        move    r4,r3
        move    (r3)-
        move    (r3)-
        move    r1,a
        move    r6,x0
        sub     x0,a
        move    #>2*MAX_ON,b
        sub     a,b
        tst     b
        beq     CM_SHIFTED
        move    b1,n3
        dor     n3,CM_SHIFT
        move    x:(r1)+,a
        move    a,x:(r3)+
CM_SHIFT:
CM_SHIFTED:
        move    y:(r6+A_CNT),a
        sub     #1,a
        move    a1,y:(r6+A_CNT)
CM_APPEND:
        move    y:(r6+A_CNT),a
        asl     a
        move    a1,n1
        move    r6,r1
        nop
        lua     (r1)+n1,r1
        move    x:(r6+X_WS),x0
        move    x0,x:(r1)+
        move    x1,a
        asl     #8,a,a
        move    r2,x0
        add     x0,a
        move    a1,x:(r1)
        move    y:(r6+A_CNT),a
        add     #1,a
        move    a1,y:(r6+A_CNT)
        rts
