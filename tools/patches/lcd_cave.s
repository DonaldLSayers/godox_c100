@ Palette tag on the see-through display. The display is an HT1621 segment
@ panel (see docs/c100-firmware.md). In photo and video mode its ISO readout
@ is blank. There, this shows the two-letter tag of the palette the next
@ photo/video will get (NEXT_IDX), or of the one in use while recording
@ (PAL_IDX).
@
@ Hooks FUN_0001ff10, the ISO readout routine, which the periodic display
@ refresh (FUN_00021318) calls on every tick. In the readout state (UI state 2)
@ the stock routine runs. Otherwise the tag is written to HT1621 addresses
@ 0..5 (the two ISO 7-segment cells) instead. The tag nibbles come from
@ tools/palettes.py (LCD_TAG_DATA).
    .syntax unified
    .arm
    .include "palettes.inc"               @ NPAL, LCD_TAG_DATA
base:
    .set    RESUME,      base + 0x1ff14   @ FUN_0001ff10 after its first instruction
    .set    SEG_WRITE,   base + 0x49e34   @ seg_write(addr, nibble), updates SHADOW
    .set    PICK,        base + PICK_ADDR @ photo_cave.s pick (from build.sh)
    .equ    PVARS,       PVARS_ADDR       @ photo cave VARS (from build.sh)
    .equ    PAL_IDX,     8                @ offsets into PVARS
    .equ    NEXT_IDX,    16
    .equ    ISO_SRC,     0xe3279          @ what FUN_0001ff10's first instruction loads
    .equ    UI_STATE,    0x121706         @ 0/1 = photo/video mode, 2 = readout
    .equ    REC_FLAGS,   0x132abb         @ FUN_00035dac; bit 1 = recording
    .equ    SHADOW,      0x1240e0         @ firmware's copy of the HT1621 RAM

    .org    0xbc400
lcd_hook:
    ldr     r3, =UI_STATE
    ldrb    r3, [r3]
    cmp     r3, #2
    ldreq   r3, =ISO_SRC                  @ readout state: replaced instruction,
    beq     RESUME                        @  then the stock routine
    push    {r4-r6, lr}
    ldr     r4, =PVARS
    ldr     r0, [r4, #NEXT_IDX]
    cmp     r0, #NPAL
    blo     1f
    mov     lr, pc                        @ first time: pick the palette now
    b       PICK
    str     r0, [r4, #NEXT_IDX]
1:  ldr     r1, =REC_FLAGS
    ldrb    r1, [r1]
    tst     r1, #2
    beq     2f
    ldr     r1, [r4, #PAL_IDX]            @ recording: the palette in use
    cmp     r1, #NPAL
    movlo   r0, r1
2:  ldr     r5, =LCD_TAGS - base          @ r5 = this palette's 6 nibbles
    add     r5, r5, r0, lsl #2
    add     r5, r5, r0, lsl #1
    mov     r6, #0
3:  ldrb    r1, [r5, r6]
    ldr     r2, =SHADOW
    ldrb    r2, [r2, r6]
    cmp     r1, r2                        @ only send what changed
    movne   r0, r6
    movne   lr, pc
    bne     SEG_WRITE
    add     r6, r6, #1
    cmp     r6, #6
    blo     3b
    pop     {r4-r6, pc}
    .ltorg

LCD_TAGS:
    LCD_TAG_DATA
