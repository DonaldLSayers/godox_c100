@ Preset code on the see-through display. The display is an HT1621 segment
@ panel (see docs/c100-firmware.md). In photo and video mode its readouts
@ are blank. There, the three cells of the shutter-speed (SS) readout show the
@ three-letter code of the preset the next photo/video will get (NEXT_IDX),
@ or of the one in use while recording (PAL_IDX).
@
@ The periodic display refresh (FUN_00021318) draws the readouts with
@ 0x21180(flag), flag = 1 in the readout state (UI state 2), else 0. It draws
@ ISO (FUN_0001ff10) and F (FUN_00020afc), then tail-calls 0x20fd0 (the video
@ icon and SS) with r0 = flag at 0x21218, or, in the readout state with SS
@ blinking, at 0x21200. lcd_jump.s points the tail call at 0x21218 here. In
@ photo and video mode (r0 = 0, readouts blank) run the stock routine, then
@ write the code over the blank SS cells (HT1621 addresses 0x0d..0x13, nothing
@ else lives there) and return to the refresh's caller. With r0 != 0 (the
@ readout state) just tail-call the stock routine.
@ The nibbles come from tools/palettes.py (LCD_TAG_DATA).
    .syntax unified
    .arm
    .include "palettes.inc"               @ NPAL, SS_*, LCD_TAG_DATA
base:
    .set    SS_ROUTINE,  base + 0x20fd0   @ video icon + SS readout (r0 = blink flag)
    .set    SEG_WRITE,   base + 0x49e34   @ seg_write(addr, nibble), updates SHADOW
    .set    PICK,        base + PICK_ADDR @ photo_cave.s pick (from build.sh)
    .equ    PVARS,       PVARS_ADDR       @ photo cave VARS (from build.sh)
    .equ    PAL_IDX,     8                @ offsets into PVARS
    .equ    NEXT_IDX,    16
    .equ    REC_FLAGS,   0x132abb         @ FUN_00035dac; bit 1 = recording
    .equ    SHADOW,      0x1240e0         @ firmware's copy of the HT1621 RAM

    .org    0xbc400
lcd_hook:
    cmp     r0, #0                        @ readout state: stock SS readout
    bne     SS_ROUTINE
    push    {r4-r6, lr}
    mov     lr, pc                        @ the stock routine (r0 = 0, blank)
    b       SS_ROUTINE
    ldr     r4, =PVARS
    ldr     r0, [r4, #NEXT_IDX]
    cmp     r0, #NPAL
    blo     1f
    mov     lr, pc                        @ first time: pick the preset now
    b       PICK
    str     r0, [r4, #NEXT_IDX]
1:  ldr     r1, =REC_FLAGS
    ldrb    r1, [r1]
    tst     r1, #2
    beq     2f
    ldr     r1, [r4, #PAL_IDX]            @ recording: the preset in use
    cmp     r1, #NPAL
    movlo   r0, r1
2:  ldr     r5, =LCD_TAGS - base          @ r5 = this preset's SS_COUNT nibbles
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
    .ltorg

LCD_TAGS:
    LCD_TAG_DATA
