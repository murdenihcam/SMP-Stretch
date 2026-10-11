; TRIG, with R4 = TABLES: S_LO = slice SLNO's start, B1 = its end, from the
; sample start and the listed onsets with q <= the THRS threshold and a rank
; below SLIC - 1. Also writes T_N (slices) and T_K (slice).
ONSET_BOUNDS:
        move    y:(r6+P_THRS),a
        asr     #7,a,a
        move    #>127,x0
        cmp     x0,a
        tfr     x0,a    ifgt
        move    #0,x0
        cmp     x0,a
        tfr     x0,a    iflt
        move    #>TB_QTHR,x0
        add     x0,a
        move    a1,n4
        lua     (r4)+n4,r0
        movem   p:(r0),a        ; threshold ...
        add     #1,a
        move    a1,y1           ; ... + 1
        move    #>63,x0
        move    y:(r6+P_SLIC),a
        cmp     x0,a
        tfr     x0,a    ifgt
        move    a1,x1           ; ranks allowed: SLIC - 1
        movec   #>$ffffff,m5
OB_TMP:
        move    #>$000000,r2    ; kind 4 / TEMP_Y: the positions of the onsets that pass
        move    r2,r3
        move    #1,n3
        clr     a
        move    a,y:(r6+S_LO)   ; slice start 0 ...
        move    y:(r6+T_LEN),a
        move    a1,y:(r6+T_PK)  ; ... and end the sample's end, unless an onset says otherwise
        move    y:(r6+A_CNT),b
        tst     b
        beq     OB_COUNTED
        move    b1,n0
        move    r6,r1
        dor     n0,OB_P1_END    ; branch-free: each position is written at R3,
        lua     (r3)+n3,r5      ; and R3 moves on if the onset passes
        move    x:(r1)+,x0
        move    x:(r1)+,a
        move    x0,y:(r3)
        tfr     a,b
        asr     #8,b,b
        sub     y1,b            ; q - threshold - 1 < 0 ...
        and     #>$ff,a
        sub     x1,a            ; ... and rank - (SLIC - 1) < 0
        max     a,b
        tst     b
        tlt     x0,a    r5,r3
OB_P1_END:
OB_COUNTED:
        move    r3,a
        move    r2,x0
        sub     x0,a
        add     #1,a            ; slices n = passing onsets + 1
        move    a1,y:(r6+T_N)
        move    a1,x0
        move    x0,b
        asl     #5,b,b          ; 32 n
        move    #>63,y0
        move    y:(r6+P_SLNO),a
        cmp     y0,a
        tfr     y0,a    ifgt
        dor     #6,OB_MOD       ; k = SLNO mod n: take off 32n, 16n, .. n where they fit
        sub     b,a
        add     b,a     iflt
        asr     b
OB_MOD:
        move    a1,y:(r6+T_K)
        move    a1,n2
        move    a1,n5
        move    r2,r5
        move    (r5)-
        tst     a
        beq     OB_HI
        move    y:(r5+n5),x0    ; start: passing onset k
        move    x0,y:(r6+S_LO)
OB_HI:
        add     #1,a
        move    y:(r6+T_N),x0
        cmp     x0,a
        beq     OB_DONE
        move    y:(r2+n2),x0    ; end: passing onset k + 1
        move    x0,y:(r6+T_PK)
OB_DONE:
        move    y:(r6+T_PK),b
        rts

