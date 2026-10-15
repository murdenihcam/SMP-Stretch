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
        if      TIME_GRAN
        bsr     GRANLEN
        asl     #6,a,a
        move    a1,x0           ; 64 * grain length (TIME sets it)
        else
        move    #>L64,x0
        endif
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
        if      TIME_GRAN
        bsr     GRANLEN
        move    a1,x0
        move    y:(r6+S_CNT),a
        else
        move    y:(r6+S_CNT),a
        move    #>GRAN,x0
        endif
        add     x0,a            ; keep the remainder: grains average GRAN samples
        move    a1,y:(r6+S_CNT)
        rts

