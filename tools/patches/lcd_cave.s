@ Preset mode on the see-through display, cycled with the center button.
@
@ The mode is the chosen preset (0..NPAL-1), NPAL = rnd (a random preset
@ per photo/recording, lut_fill, photo_cave.s), GB_MODE = the Game Boy
@ Camera look (gb_strip, photo_cave.s) or NORMAL_MODE = no effect at all (the
@ hooks leave the strips alone); the center button steps through them in that
@ order and then wraps. GB_CYCLE and NORMAL_CYCLE (build.sh GB_ON, NORMAL_ON)
@ leave the last two out; the site's editor patches the two places that say
@ what follows the last preset and what follows GB (after_last, after_gb). It lives in byte 0xf1 of the
@ camera's settings (0x132160, 0xf4 bytes, checksummed and saved to NVRAM at
@ power-off when its dirty byte +0xa0 is 1; no firmware instruction uses
@ offsets 0xf1-0xf3), so it survives power-off; any other value counts as the
@ first preset. The display is an HT1621 segment panel (see
@ docs/c100-firmware.md); in photo and video mode its readouts are blank.
@ There, the three cells of the shutter-speed (SS) readout show the mode's
@ code: the preset's tag (BW as an 8 and a two-cell W), "rnd" or "Gb" or "nor".
@
@ lcd_hook: the periodic display refresh (FUN_00021318) draws the readouts
@ with 0x21180(flag), flag = 1 in the readout state (UI state 2), else 0. It
@ draws ISO (FUN_0001ff10) and F (FUN_00020afc), then tail-calls 0x20fd0 (the
@ video icon and SS) with r0 = flag at 0x21218, or, in the readout state with
@ SS blinking, at 0x21200. lcd_jump.s points the tail call at 0x21218 here.
@ In photo and video mode (r0 = 0, readouts blank) run the stock routine,
@ then write the code over the blank SS cells (HT1621 addresses 0x0d..0x13,
@ nothing else lives there) and return to the refresh's caller. With r0 != 0
@ (the readout state) just tail-call the stock routine.
@
@ center_hook: the center button's handler (FUN_0001dd6c,
@ ap_peripheral_F_key_exe, an ADC key) posts message 0x7041 once per press;
@ only the readout state acts on it (it cycles ISO/F/SS there; the arrows are
@ IO_ISO = 0x7042 and T = 0x7043, aspect -1/+1 in photo and video mode).
@ key_jump.s points that post (bl 0x42c at 0x1ddf8) here: in photo and video
@ mode, and not while recording, step the mode and mark the settings dirty
@ (so the firmware saves them at power-off); then post the message as before.
@ (v015 hooked the IO_ISO key's post at 0x1dd44 by mistake, going by the
@ handler's name: that is an arrow, and the mode never moved.)
@ The nibbles come from tools/palettes.py (LCD_TAG_DATA, one entry per mode,
@ padded to MAX_PRESETS + 1, then GB's). The npal_* labels mark the instructions whose
@ immediate is NPAL, last_center the one that is NPAL - 1 + RND_MODE: the
@ site's editor rewrites them.
    .syntax unified
    .arm
    .include "palettes.inc"               @ NPAL, GB_MODE, NORMAL_MODE, SS_*, LCD_TAG_DATA
    .include "gb.inc"                     @ GB_ASPECT
base:
    .set    SS_ROUTINE,  base + 0x20fd0   @ video icon + SS readout (r0 = blink flag)
    .set    SEG_WRITE,   base + 0x49e34   @ seg_write(addr, nibble), updates SHADOW
    .set    MSG_POST,    base + 0x42c     @ post to a message queue (5 args, 1 on the stack)
    .set    RESUME_ASPECT, base + 0x213e4 @ FUN_000213e0 after its first instruction
    .set    RESUME_BRACKET, base + 0x4a81c @ the bracket routine FUN_0004a7f4 after its `sub r1, r1, #1`
    .equ    CFG,         0x132160         @ the camera's settings (see above)
    .equ    CFG_MODE,    0xf1             @ our mode byte in them
    .equ    CFG_DIRTY,   0xa0             @ 1 = save at power-off (FUN_00024094)
    .equ    UI_STATE,    0x121706         @ 0/1 = photo/video mode, 2 = readout
    .equ    REC_FLAGS,   0x132abb         @ FUN_00035dac; bit 1 = recording
    .equ    SHADOW,      0x1240e0         @ firmware's copy of the HT1621 RAM
    .equ    ASPECT,      0x1217bd         @ the aspect setting the UI cycles (the arrow keys, FUN_000213e0)
    .equ    CFG_ASPECT,  0xf2             @ our byte in the settings: the aspect from before the GB mode
    .equ    MSG_RESIZE,  0x7000           @ what the stock aspect change posts: apply it, rebuild the size
    .equ    AFTER_GB,    NORMAL_MODE * NORMAL_CYCLE
    .equ    AFTER_LAST,  GB_MODE * GB_CYCLE + (1 - GB_CYCLE) * NORMAL_MODE * NORMAL_CYCLE

    .org    0xbc400
lcd_hook:
    cmp     r0, #0                        @ readout state: stock SS readout
    bne     SS_ROUTINE
    push    {r4-r6, lr}
    mov     lr, pc                        @ the stock routine (r0 = 0, blank)
    b       SS_ROUTINE
    ldr     r0, =CFG
    ldrb    r0, [r0, #CFG_MODE]
    cmp     r0, #NORMAL_MODE
    cmpne   r0, #GB_MODE
npal_lcd:
    cmpne   r0, #NPAL
    movhi   r0, #0                        @ not a mode: the first (as lut_fill)
    ldr     r5, =LCD_TAGS - base          @ r5 = this mode's SS_COUNT nibbles
    mov     r1, #SS_COUNT
    mla     r5, r0, r1, r5
    mov     r6, #0
3:  ldrb    r1, [r5, r6]
    add     r0, r6, #SS_FIRST
    ldr     r2, =SHADOW
    ldrb    r2, [r2, r0]
    cmp     r1, r2                        @ only send what changed
    movne   lr, pc
    bne     SEG_WRITE
    add     r6, r6, #1
    cmp     r6, #SS_COUNT
    blo     3b
    pop     {r4-r6, pc}

center_hook:                            @ r0-r3 and [sp] are MSG_POST's arguments
    push    {r0-r3, lr}
    ldr     r0, =UI_STATE
    ldrb    r0, [r0]
    cmp     r0, #1                        @ photo or video mode only
    bhi     1f
    ldr     r0, =REC_FLAGS
    ldrb    r0, [r0]
    tst     r0, #2                        @ not while recording
    bne     1f
    ldr     r1, =CFG
    ldrb    r0, [r1, #CFG_MODE]
    mov     r2, r0                        @ r2 = the mode before
    cmp     r0, #NORMAL_MODE
    moveq   r0, #0                        @ after normal: the first preset
    beq     2f
    cmp     r0, #GB_MODE
after_gb:
    moveq   r0, #AFTER_GB                 @ after GB: normal, or the first preset
    beq     2f
npal_center:
    cmp     r0, #NPAL
    movhi   r0, #0                        @ not a mode: the first
    add     r0, r0, #1                    @ next preset, after the last rnd
last_center:                              @  (if RND_MODE), then GB
    cmp     r0, #NPAL - 1 + RND_MODE
after_last:
    movhi   r0, #AFTER_LAST               @ GB, else normal, else the first preset
2:  strb    r0, [r1, #CFG_MODE]
    mov     r3, #1
    strb    r3, [r1, #CFG_DIRTY]          @ save it at power-off
    mov     r3, #0                        @ r3 = the new mode's size class: 0 a regular mode, 1 the GB
    cmp     r0, #GB_MODE                  @  mode (its own 8:7 size, aspect GB_ASPECT), 2 the normal mode (the
    moveq   r3, #1                        @  factory's sizes, aspect NIDX[a]: slots the arrow keys don't reach).
    cmp     r0, #NORMAL_MODE              @  A change of class changes the aspect the way the stock arrow keys do:
    moveq   r3, #2                        @  set it, post MSG_RESIZE, and the firmware rebuilds the capture size.
    mov     r12, #0                       @ r12 = the old mode's class
    cmp     r2, #GB_MODE
    moveq   r12, #1
    cmp     r2, #NORMAL_MODE
    moveq   r12, #2
    cmp     r3, r12
    beq     1f
    ldr     r2, =ASPECT
    cmp     r12, #0
    ldrbeq  r0, [r2]                      @ out of a regular mode: the aspect now is the user's, remember it
    strbeq  r0, [r1, #CFG_ASPECT]
    ldrbne  r0, [r1, #CFG_ASPECT]         @ out of a special one: the remembered one
    cmp     r0, #4
    movhi   r0, #0                        @ keep it an aspect the arrow keys reach
    cmp     r3, #1
    moveq   r0, #GB_ASPECT
    cmp     r3, #2
    ldreq   r12, =NIDX - base
    ldrbeq  r0, [r12, r0]
    strb    r0, [r2]
    ldr     r0, [sp]                      @ the queue (MSG_POST's first argument)
    mov     r1, #MSG_RESIZE
    mov     r2, #0
    mov     r3, #0
    str     r2, [sp, #-4]!                @ MSG_POST's 5th argument
    mov     lr, pc
    b       MSG_POST
    add     sp, sp, #4
1:  pop     {r0-r3, lr}
    b       MSG_POST                      @ returns to the key handler

@ The arrow keys' aspect change, FUN_000213e0(delta) (aspect_jump.s): in the GB mode nothing, so the mode stays on
@ its own 8:7 size; in the normal mode it steps the remembered aspect as the stock function does (past the last
@ wraps to the first, before the first to the last) and selects that aspect's factory-size slot, NIDX. Only r0
@ (delta, a signed char) and lr are live at its entry.
aspect_hook:
    ldr     r1, =CFG
    ldrb    r1, [r1, #CFG_MODE]
    cmp     r1, #GB_MODE
    moveq   pc, lr
    cmp     r1, #NORMAL_MODE
    bne     1f
    ldr     r2, =CFG
    ldrb    r3, [r2, #CFG_ASPECT]
    mov     r0, r0, lsl #24
    add     r3, r3, r0, asr #24
    cmp     r3, #4
    movgt   r3, #0
    cmp     r3, #0
    movlt   r3, #4
    strb    r3, [r2, #CFG_ASPECT]
    ldr     r1, =NIDX - base
    ldrb    r3, [r1, r3]
    ldr     r2, =ASPECT
    strb    r3, [r2]
    mov     pc, lr
1:  ldr     r2, =ASPECT                   @ the instruction we replaced
    b       RESUME_ASPECT
NIDX:                                   @ the normal mode's slot for each aspect 0-4: the photo and video size tables'
    .byte   6, 7, 8, 10, 13             @  entries there are the factory handlers (build.sh); not slots we patch
    .align  2

@ The aspect bracket on the display, FUN_0004a7f4(state, aspect) (bracket_jump.s): it lights one for aspects 1-4
@ and nothing else, so in the normal mode (slots NIDX) it got nothing. Map a slot back to its aspect (an
@ unknown one to 5: nothing, as stock) and go on with the instruction we replaced, sub r1, r1, #1.
bracket_hook:
    cmp     r1, #5
    blo     2f
    adr     r0, NIDX
    mov     r12, #0
1:  ldrb    r2, [r0, r12]
    cmp     r2, r1
    addne   r12, r12, #1
    cmpne   r12, #5
    bne     1b
    mov     r1, r12
    mov     r2, #0                        @ as the stock routine had it
2:  sub     r1, r1, #1
    b       RESUME_BRACKET
    .ltorg

LCD_TAGS:
    LCD_TAG_DATA
