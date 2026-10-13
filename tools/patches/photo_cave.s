@ EXPERIMENT 3 / OPTION B: true nearest-palette colour matching, per 2x2 block
@ (one chroma pair per block in 4:2:0), with 4x4 Bayer ordered dithering on the
@ block's representative luma. Single palette (riso6). Built on the proven
@ band/pixel-pair write structure from the colour-bars experiment.
    .syntax unified
    .arm
base:
    .set    RESUME,      base + 0x1544c
    .set    PHOTO_PATH,  base + 0xf188
    .set    CACHE_INV,   base + 0x401ac
    .set    CACHE_CLEAN, base + 0x401b8
    .equ    PHOTO,       0x1317ac
    .equ    STRIP_BYTES, 0x13155c
    .equ    BAYER_ADDR,  0x000bb040
    .equ    PAL_ADDR,    0x000bb058

    .org    0xbab6c
hook:
    push    {r0-r11, lr}                  @ r0-r3 are the callback's live args
    sub     r3, r0, #0x200000
    cmp     r3, #0xe00000
    bhs     done
    ldr     r4, =PHOTO
    ldr     r6, =STRIP_BYTES
    ldr     r6, [r6]
    cmp     r6, #96
    bls     done
    ldr     r5, [r4, #0x18]
    cmp     r1, r5
    beq     1f
    add     r5, r5, r6
    cmp     r1, r5
    bne     done
1:  ldr     r5, [r4, #0x18]              @ r5 = buffer A (base)
    mov     r7, r6, lsr #5              @ r7 = stride = 480
    ldr     r2, =0xAAAAAAAB
    umull   r0, r3, r7, r2
    mov     r8, r3, lsr #1             @ r8 = third = 160
    mov     r0, r5                      @ invalidate the 64-row span
    mov     r1, r7, lsl #6
    mov     lr, pc
    b       CACHE_INV

    mov     r11, r5                     @ r11 = even_base (row 2b)
    mov     r10, #0                    @ r10 = band index b (0..31)
bandloop:
    mov     r9, #0                     @ r9 = block index c (0..159), x = 2c
pixloop:
    @ ---- representative luma = average of the 4 block pixels ----
    add     r6, r11, r9, lsl #1         @ even luma addr (x, x+1)
    ldrb    r0, [r6]
    ldrb    r1, [r6, #1]
    add     r0, r0, r1
    add     r6, r11, r7                 @ odd_base
    add     r6, r6, r8                  @ + third (odd luma starts at +160)
    add     r6, r6, r9, lsl #1          @ + x
    ldrb    r1, [r6]
    ldrb    r2, [r6, #1]
    add     r0, r0, r1
    add     r0, r0, r2                  @ sum of 4 luma
    mov     r0, r0, lsr #2             @ repY
    @ ---- Bayer dither: repY += (BAYER[b&3][c&3] - 8) * 4 ----
    ldr     lr, =BAYER_ADDR
    and     r6, r10, #3
    add     lr, lr, r6, lsl #2
    and     r6, r9, #3
    ldrb    r6, [lr, r6]
    sub     r6, r6, #8
    add     r0, r0, r6, lsl #2
    cmp     r0, #0
    movlt   r0, #0
    cmp     r0, #255
    movgt   r0, #255                    @ r0 = Yp
    @ ---- chroma U,V of this block ----
    cmp     r9, #80
    addlo   r6, r11, #320
    addlo   r6, r6, r9, lsl #1
    subhs   r1, r9, #80
    addhs   r6, r11, r7
    addhs   r6, r6, r1, lsl #1
    ldrb    r1, [r6]                    @ U
    ldrb    r2, [r6, #1]                @ V
    @ ---- nearest of 6 palette colours (Manhattan Y+U+V) ----
    ldr     r4, =PAL_ADDR               @ r4 = palette base
    mov     r3, #0                     @ best offset
    mvn     r12, #0                    @ best distance
    ldrb    r6, [r4, #0]
    subs    r6, r0, r6
    rsbmi   r6, r6, #0
    mov     lr, r6
    ldrb    r6, [r4, #1]
    subs    r6, r1, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    ldrb    r6, [r4, #2]
    subs    r6, r2, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    cmp     lr, r12
    movlo   r12, lr
    movlo   r3, #0
    ldrb    r6, [r4, #3]
    subs    r6, r0, r6
    rsbmi   r6, r6, #0
    mov     lr, r6
    ldrb    r6, [r4, #4]
    subs    r6, r1, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    ldrb    r6, [r4, #5]
    subs    r6, r2, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    cmp     lr, r12
    movlo   r12, lr
    movlo   r3, #3
    ldrb    r6, [r4, #6]
    subs    r6, r0, r6
    rsbmi   r6, r6, #0
    mov     lr, r6
    ldrb    r6, [r4, #7]
    subs    r6, r1, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    ldrb    r6, [r4, #8]
    subs    r6, r2, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    cmp     lr, r12
    movlo   r12, lr
    movlo   r3, #6
    ldrb    r6, [r4, #9]
    subs    r6, r0, r6
    rsbmi   r6, r6, #0
    mov     lr, r6
    ldrb    r6, [r4, #10]
    subs    r6, r1, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    ldrb    r6, [r4, #11]
    subs    r6, r2, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    cmp     lr, r12
    movlo   r12, lr
    movlo   r3, #9
    ldrb    r6, [r4, #12]
    subs    r6, r0, r6
    rsbmi   r6, r6, #0
    mov     lr, r6
    ldrb    r6, [r4, #13]
    subs    r6, r1, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    ldrb    r6, [r4, #14]
    subs    r6, r2, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    cmp     lr, r12
    movlo   r12, lr
    movlo   r3, #12
    ldrb    r6, [r4, #15]
    subs    r6, r0, r6
    rsbmi   r6, r6, #0
    mov     lr, r6
    ldrb    r6, [r4, #16]
    subs    r6, r1, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    ldrb    r6, [r4, #17]
    subs    r6, r2, r6
    rsbmi   r6, r6, #0
    add     lr, lr, r6
    cmp     lr, r12
    movlo   r12, lr
    movlo   r3, #15
    @ ---- write the winning palette colour to the whole 2x2 block ----
    add     r4, r4, r3                  @ palptr = palbase + best offset
    ldrb    r0, [r4]                    @ pY
    ldrb    r1, [r4, #1]                @ pU
    ldrb    r2, [r4, #2]                @ pV
    add     r6, r11, r9, lsl #1         @ even luma (x, x+1)
    strb    r0, [r6]
    strb    r0, [r6, #1]
    add     r6, r11, r7                 @ odd luma (x, x+1)
    add     r6, r6, r8
    add     r6, r6, r9, lsl #1
    strb    r0, [r6]
    strb    r0, [r6, #1]
    cmp     r9, #80                     @ chroma pair
    addlo   r6, r11, #320
    addlo   r6, r6, r9, lsl #1
    subhs   r3, r9, #80
    addhs   r6, r11, r7
    addhs   r6, r6, r3, lsl #1
    strb    r1, [r6]                    @ pU
    strb    r2, [r6, #1]                @ pV
    add     r9, r9, #1
    cmp     r9, #160
    blo     pixloop
    add     r11, r11, r7, lsl #1        @ even_base += 2*stride
    add     r10, r10, #1
    cmp     r10, #32
    blo     bandloop

    sub     r0, r11, r7, lsl #6         @ base = even_base - 64*stride
    mov     r1, r7, lsl #6
    mov     lr, pc
    b       CACHE_CLEAN
done:
    pop     {r0-r11, lr}
    str     lr, [sp, #-4]!
    b       RESUME
    .ltorg

    .org    BAYER_ADDR
BAYER:
    .byte   0, 8, 2, 10
    .byte   12, 4, 14, 6
    .byte   3, 11, 1, 9
    .byte   15, 7, 13, 5
    .org    PAL_ADDR
PAL:                                    @ riso6, JPEG/JFIF YCbCr (Y,U,V) x6
    .byte   30, 144, 125                @ 1a1a3a navy
    .byte   115, 114, 206               @ e0405a pink-red
    .byte   164, 72, 183                @ f09040 orange
    .byte   125, 148, 69                @ 2aa0a0 teal
    .byte   225, 109, 139               @ f0e0c0 cream
    .byte   255, 128, 128               @ ffffff white

    .org    0xbb080
photo43:
    mov     r6, #320
    mov     r7, #240
    strh    r6, [r4, #14]
    strh    r7, [r4, #16]
    mov     r0, #1
    strb    r0, [r4, #4]
    mov     r0, #1440
    strh    r0, [r4, #6]
    strh    r9, [r4, #8]
    strh    r0, [r4, #10]
    strh    r9, [r4, #12]
    b       PHOTO_PATH
    .ltorg
