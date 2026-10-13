@ Code cave in FUN_000bab6c (unreferenced dead function), 0xbab6c..0xbad6b.
@
@   0xbab6c  hook     photo pixel hook on FUN_00015448 (via hook_jump.s)
@   0xbad00  photo43  4:3 photo size setup (via photo43_jump.s)
@   0xbad68  DIAG     diagnostic bits set by the hook (RAM is writable)
@
@ With DIAG_WIDTH = 1 the 4:3 photo width is 336 + 16 * DIAG, so the 4:3
@ photo after an aspect-ratio change reports what the hook saw since boot:
@   1 hook called          2 status 0x200000..0xffffff
@   4 format '!' (4:2:2)   8 format '"' (4:2:0)
@  16 buffer == full frame 32 buffer == scaler strip A/B
@ (336 rather than 320 also proves this build is the one running.)

    .syntax unified
    .arm
base:
    .set    RESUME,      base + 0x1544c   @ callback, after replaced instruction
    .set    PHOTO_PATH,  base + 0xf188    @ FUN_0000f004 photo path
    .set    CACHE_INV,   base + 0x401ac   @ (addr, len) discard cached lines
    .set    CACHE_CLEAN, base + 0x401b8   @ (addr, len) write cache to RAM
    .equ    PHOTO,       0x1317ac         @ photo struct, see FUN_0001808c
    .equ    STRIP_BYTES, 0x13155c         @ scaler strip size in bytes
    .equ    DIAG,        0xbad68
    .equ    DIAG_WIDTH,  0                @ 1 = report DIAG in the 4:3 width

@ ---------------------------------------------------------------------------
@ hook(status r0, buffer r1, extra r2) -- interrupt context
@ Photo struct: [1]=+4 width, [2]=+8 height, [5]=+0x14 full-frame buffer,
@ [6]=+0x18 strip A (B follows), [8]=+0x20 format.
@ Seen on camera (diag 43): called with status 0x2xxxxx, buffer = strip A/B,
@ format '"' = YUV 4:2:0.
@ Test effect: black & white.
@   4:2:2 ('!'): YUYV assumed, odd bytes are U/V.
@   4:2:0 ('"'): Y first (2/3 of the buffer), then U/V (last 1/3), planar or
@                interleaved -- either way set the last third to 0x80.
    .org    0xbab6c
@ hook(status r0, buffer r1) -- interrupt context.
@ Per-row parity layout (stride 480, third 160):
@   even rows: luma [0,320),  left chroma  [320,480)
@   odd  rows: right chroma [0,160), luma [160,480)
@ Effect: neutralise chroma (0x80) + dither luma to 4 grey levels with a 4x4
@ Bayer ordered-dither pattern. Only strip A / strip B buffers are touched.
hook:
    push    {r0-r11, lr}

    sub     r3, r0, #0x200000           @ frame-ready status only
    cmp     r3, #0xe00000
    bhs     done

    ldr     r4, =PHOTO
    ldr     r6, =STRIP_BYTES
    ldr     r6, [r6]
    cmp     r6, #96
    bls     done
    ldr     r5, [r4, #0x18]             @ strip A?
    cmp     r1, r5
    beq     1f
    add     r5, r5, r6
    cmp     r1, r5                      @ strip B?
    bne     done

1:  ldr     r5, [r4, #0x18]             @ base = buffer A
    mov     r7, r6, lsr #5              @ stride = STRIP_BYTES/32 (=480)
    ldr     r2, =0xAAAAAAAB
    umull   r0, r3, r7, r2
    mov     r8, r3, lsr #1             @ third = stride/3 (=160)
    add     r6, r5, r6, lsl #1          @ end = A + 2*STRIP_BYTES

    mov     r0, r5                      @ invalidate cache over whole buffer
    sub     r1, r6, r5
    mov     lr, pc
    b       CACHE_INV

    adr     r11, BAYER
    mov     r9, r5                      @ r9 = row base
    mov     r10, #0                     @ r10 = row index
rowloop:
    tst     r10, #1
    moveq   r12, r9                     @ even: luma start = row
    addeq   r0, r9, r8, lsl #1          @ even: chroma start = row + 2*third
    addne   r12, r9, r8                 @ odd:  luma start = row + third
    movne   r0, r9                      @ odd:  chroma start = row

    add     r2, r0, r8                  @ zero chroma third -> 0x80
    mov     r3, #0x80
czero:
    strb    r3, [r0], #1
    cmp     r0, r2
    blo     czero

    add     r1, r12, r8, lsl #1         @ luma end = luma start + 2*third (320)
    and     r3, r10, #3
    add     r3, r11, r3, lsl #2         @ r3 = &BAYER[(row&3)*4]
    mov     r0, #0                      @ x = 0
ditloop:
    and     r2, r0, #3
    ldrb    r2, [r3, r2]                @ d = BAYER[(row&3)*4 + (x&3)]  (0..15)
    sub     r2, r2, #8
    mov     r2, r2, lsl #2              @ offset = (d-8)*4  (-32..+28)
    ldrb    lr, [r12]                   @ Y
    add     lr, lr, r2                  @ t = Y + offset (signed)
    cmp     lr, #0
    movlt   lr, #0
    cmp     lr, #255
    movgt   lr, #255                    @ clamp 0..255
    mov     lr, lr, lsr #6             @ level 0..3
    add     r2, r11, #16                @ LEVELS table
    ldrb    lr, [r2, lr]               @ out = LEVELS[level]
    strb    lr, [r12], #1               @ write luma, advance
    add     r0, r0, #1
    cmp     r12, r1
    blo     ditloop

    add     r10, r10, #1                @ next row
    add     r9, r9, r7
    add     r0, r9, r7
    cmp     r0, r6
    bls     rowloop

    mov     r0, r5                      @ clean cache back to RAM
    sub     r1, r6, r5
    mov     lr, pc
    b       CACHE_CLEAN

done:
    pop     {r0-r11, lr}
    str     lr, [sp, #-4]!              @ replaced instruction from 0x15448
    b       RESUME
    .ltorg
BAYER:
    .byte 0, 8, 2, 10
    .byte 12, 4, 14, 6
    .byte 3, 11, 1, 9
    .byte 15, 7, 13, 5
LEVELS:
    .byte 0, 85, 170, 255

@ ---------------------------------------------------------------------------
@ photo43: 4:3 photo setting, inside FUN_0000f004 (r4 = capture-size struct,
@ r9 = sensor height 1080). Struct fields (as used by FUN_0001109c):
@   +6/+8 crop window (centred), +0xa/+0xc first scaler output,
@   +0xe/+0x10 final JPEG size.
@ Keep the full 1440x1080 4:3 crop, shrink only the final size.
    .org    0xbad00
photo43:
    .if DIAG_WIDTH
    ldr     r6, =DIAG
    ldr     r6, [r6]
    and     r6, r6, #63
    lsl     r6, r6, #4
    add     r6, r6, #336                @ diagnostic width
    .else
    mov     r6, #320
    .endif
    mov     r7, #240
    strh    r6, [r4, #14]               @ final width
    strh    r7, [r4, #16]               @ final height
    mov     r0, #1
    strb    r0, [r4, #4]                @ same as shared tail at 0xf6c8
    mov     r0, #1440
    strh    r0, [r4, #6]                @ crop 1440 x 1080
    strh    r9, [r4, #8]
    strh    r0, [r4, #10]               @ first scaler output 1440 x 1080
    strh    r9, [r4, #12]
    b       PHOTO_PATH
    .ltorg

    .org    DIAG
    .word   0
