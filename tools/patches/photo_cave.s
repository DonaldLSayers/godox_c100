@ EXPERIMENT 1: proven per-row loop, luma = rowindex*4 (cheap, no match),
@ chroma neutral. Tests whether cheap per-row writes cover ALL rows.
    .syntax unified
    .arm
base:
    .set    RESUME,      base + 0x1544c
    .set    PHOTO_PATH,  base + 0xf188
    .set    CACHE_INV,   base + 0x401ac
    .set    CACHE_CLEAN, base + 0x401b8
    .equ    PHOTO,       0x1317ac
    .equ    STRIP_BYTES, 0x13155c

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
1:  ldr     r5, [r4, #0x18]            @ base = A
    mov     r7, r6, lsr #5            @ stride
    ldr     r2, =0xAAAAAAAB
    umull   r0, r3, r7, r2
    mov     r8, r3, lsr #1           @ third
    add     r6, r5, r6, lsl #1        @ end = A + 2*STRIP
    mov     r0, r5
    sub     r1, r6, r5
    mov     lr, pc
    b       CACHE_INV
    mov     r9, r5                    @ rowbase
    mov     r10, #0                   @ rowidx
rowloop:
    @ luma block + chroma block by parity
    tst     r10, #1
    moveq   r12, r9                   @ even luma start
    addeq   r0, r9, r8, lsl #1        @ even chroma start
    addne   r12, r9, r8               @ odd luma start
    movne   r0, r9                    @ odd chroma start
    @ fill chroma third = 128 (neutral)
    add     r2, r0, r8
    mov     r3, #128
cz:
    strb    r3, [r0], #1
    cmp     r0, r2
    blo     cz
    @ fill luma third = rowidx*4
    add     r1, r12, r8, lsl #1       @ luma end
    mov     r3, r10, lsl #2           @ luma value = rowidx*4
lz:
    strb    r3, [r12], #1
    cmp     r12, r1
    blo     lz
    add     r10, r10, #1
    add     r9, r9, r7
    add     r0, r9, r7
    cmp     r0, r6
    bls     rowloop
    mov     r0, r5
    sub     r1, r6, r5
    mov     lr, pc
    b       CACHE_CLEAN
done:
    pop     {r0-r11, lr}                  @ restore args before resuming callback
    str     lr, [sp, #-4]!
    b       RESUME

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
