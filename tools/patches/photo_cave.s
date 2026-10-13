@ OPTION B + palette cycling: true nearest-palette colour matching, per 2x2
@ block (one chroma pair per block in 4:2:0), with 4x4 Bayer ordered dithering
@ on the block's representative luma. A persistent index (PAL_IDX) selects one
@ of NPAL palettes, advanced once per photo by idx_stub (hooks FUN_000187c4).
    .syntax unified
    .arm
base:
    .set    RESUME,      base + 0x1544c
    .set    PHOTO_PATH,  base + 0xf188
    .set    RESUME187,   base + 0x187c8
    .set    CACHE_INV,   base + 0x401ac
    .set    CACHE_CLEAN, base + 0x401b8
    .equ    PHOTO,       0x1317ac
    .equ    STRIP_BYTES, 0x13155c
    .equ    NPAL,        7
    .equ    BAYER_ADDR,    0x000bb040
    .equ    PAL_IDX_ADDR,  0x000bb054
    .equ    SEEDED_ADDR,   0x000bb058
    .equ    PALETTES_ADDR, 0x000bb0c0

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
    @ ---- seed PAL_IDX once per boot from sensor pixel entropy ----
    ldr     r4, =SEEDED_ADDR
    ldrb    r0, [r4]
    cmp     r0, #0
    bne     2f
    ldrb    r0, [r11, #0]
    ldrb    r1, [r11, #64]
    add     r0, r0, r1
    ldrb    r1, [r11, #128]
    add     r0, r0, r1
    ldrb    r1, [r11, #192]
    add     r0, r0, r1                  @ sum of 4 luma samples (noisy low bits)
3:  cmp     r0, #NPAL                   @ reduce mod NPAL (runs once per boot)
    subhs   r0, r0, #NPAL
    bhs     3b
    ldr     r1, =PAL_IDX_ADDR
    strb    r0, [r1]
    mov     r0, #1
    strb    r0, [r4]                    @ mark seeded
2:  @ ---- select palette base from the current index ----
    ldr     r4, =PAL_IDX_ADDR
    ldrb    r0, [r4]
    cmp     r0, #NPAL
    movhs   r0, #0
    ldr     r5, =PALETTES_ADDR
    add     r1, r0, r0, lsl #3          @ idx*9
    add     r1, r1, r1                  @ idx*18
    add     r5, r5, r1                  @ r5 = palbase (18 bytes/palette)
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
    @ ---- contrast / brightness pre-map (assemble-time constants) ----
    @ Y' = (Y-128)*CONTRAST/128 + 128 + (BRIGHT_FIX-128).  CONTRAST_FIX = pct*128/100.
    sub     r0, r0, #128
    mov     r1, #CONTRAST_FIX
    mul     r0, r1, r0
    mov     r0, r0, asr #7
    add     r0, r0, #128
    add     r0, r0, #BRIGHT_FIX        @ BRIGHT_FIX = BRIGHT + 128 ...
    sub     r0, r0, #128               @ ... so this nets +BRIGHT with no negative imm
    @ ---- Bayer dither: repY += (BAYER[b&3][c&3] - 8) * 4 (clamps 0..255 below) ----
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
    @ ---- chroma U,V of this block (split at third/2, even chroma at +2*third) ----
    cmp     r9, r8, lsr #1
    addlo   r6, r11, r8, lsl #1
    addlo   r6, r6, r9, lsl #1
    subhs   r1, r9, r8, lsr #1
    addhs   r6, r11, r7
    addhs   r6, r6, r1, lsl #1
    ldrb    r1, [r6]                    @ U
    ldrb    r2, [r6, #1]                @ V
    @ ---- nearest of 6 palette colours (Manhattan Y+U+V) ----
    mov     r4, r5                      @ r4 = palette base
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
    add     r4, r5, r3                  @ palptr = palbase + best offset
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
    cmp     r9, r8, lsr #1              @ chroma pair
    addlo   r6, r11, r8, lsl #1
    addlo   r6, r6, r9, lsl #1
    subhs   r3, r9, r8, lsr #1
    addhs   r6, r11, r7
    addhs   r6, r6, r3, lsl #1
    strb    r1, [r6]                    @ pU
    strb    r2, [r6, #1]                @ pV
    add     r9, r9, #1
    cmp     r9, r8                      @ third chroma pairs (= width/2) per band
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

    .org    PAL_IDX_ADDR
PAL_IDX:
    .byte   6, 0, 0, 0                   @ init 6; overridden by the random seed
    .org    SEEDED_ADDR
SEEDED:
    .byte   0, 0, 0, 0                   @ 0 until the per-boot seed has run

    .org    0xbb080
photo43:                                @ 4:3  crop 1440x1080 -> 640x480
    mov     r6, #640
    mov     r7, #480
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

    .org    PALETTES_ADDR
PALETTES:                               @ NPAL x 6 colours, JPEG/JFIF (Y,U,V)
    .byte 30,144,125, 115,114,206, 164,72,183, 125,148,69, 225,109,139, 255,128,128   @ riso6
    .byte 82,137,113, 235,103,135, 167,76,160, 85,108,177, 39,120,153, 39,120,153     @ dark_sunset
    .byte 130,105,196, 198,58,159, 164,77,110, 131,174,87, 108,162,138, 108,162,138   @ vibrant_summer
    .byte 187,57,166, 138,74,190, 106,130,216, 88,196,152, 127,192,90, 127,192,90     @ fiesta
    .byte 99,105,197, 89,123,106, 185,114,111, 235,106,132, 41,118,137, 41,118,137    @ vibrant_nature
    .byte 108,138,215, 83,192,155, 52,187,133, 103,207,108, 178,159,88, 178,159,88    @ bold_hues
    .byte 199,145,105, 128,156,89, 37,145,113, 193,54,162, 155,65,183, 155,65,183     @ refreshing

@ Aspect-ratio shrink stubs, reached directly from the resolution jump table
@ (ldrls pc,[pc,idx,lsl#2] @ 0xf3c8, table @ 0xf3d0). Each keeps the native crop
@ and first-scaler size (so the sensor is scaled, not cropped) and sets a small
@ 320-wide final size at that aspect. r4 = size struct, r9 = 1080 at entry.
    .org    0xbb140
stub169:                                @ 16:9  crop 1920x1080 -> 640x360
    mov     r6, #640
    mov     r7, #360
    strh    r6, [r4, #14]
    strh    r7, [r4, #16]
    mov     r0, #1
    strb    r0, [r4, #4]
    mov     r0, #1920
    strh    r0, [r4, #6]
    strh    r9, [r4, #8]
    strh    r0, [r4, #10]
    strh    r9, [r4, #12]
    b       PHOTO_PATH

    .org    0xbb180
stub32:                                 @ 3:2  crop 1616x1080 -> 640x428
    mov     r6, #640
    mov     r7, #428
    strh    r6, [r4, #14]
    strh    r7, [r4, #16]
    mov     r0, #1
    strb    r0, [r4, #4]
    mov     r0, #1616
    strh    r0, [r4, #6]
    strh    r9, [r4, #8]
    strh    r0, [r4, #10]
    strh    r9, [r4, #12]
    b       PHOTO_PATH

    .org    0xbb1c0
stub11:                                 @ 1:1  crop 1024x1024 -> 640x640
    mov     r6, #640
    mov     r7, #640
    strh    r6, [r4, #14]
    strh    r7, [r4, #16]
    mov     r0, #1
    strb    r0, [r4, #4]
    mov     r0, #1024
    strh    r0, [r4, #6]
    strh    r0, [r4, #8]
    strh    r0, [r4, #10]
    strh    r0, [r4, #12]
    b       PHOTO_PATH

    .org    0xbb2c0
idx_stub:                               @ hooks FUN_000187c4 (once per photo)
    ldr     r12, =PAL_IDX_ADDR
    ldrb    r0, [r12]
    add     r0, r0, #1
    cmp     r0, #NPAL
    movhs   r0, #0
    strb    r0, [r12]
    push    {r3, r4, r5, r6, r7, lr}    @ replaced instruction from 0x187c4
    b       RESUME187
    .ltorg
