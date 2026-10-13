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
hook:
    push    {r0-r8, lr}

    sub     r3, r0, #0x200000           @ accept only frame-ready status
    cmp     r3, #0xe00000
    bhs     done

    ldr     r4, =PHOTO
    ldr     r8, [r4, #4]                @ W = photo width (e.g. 320)
    cmp     r8, #16                     @ sanity: 16..2047
    bls     done
    cmp     r8, #2048
    bhs     done

    ldr     r5, [r4, #0x14]             @ buffer must be the full frame ...
    cmp     r1, r5
    beq     2f
    ldr     r5, [r4, #0x18]             @ ... or scaler strip A / B
    ldr     r6, =STRIP_BYTES
    ldr     r6, [r6]
    cmp     r1, r5
    addne   r5, r5, r6
    cmpne   r1, r5
    bne     done

2:  mov     r5, r1                      @ r5 = buffer start
    ldr     r6, =STRIP_BYTES            @ r6 = total bytes in this buffer
    ldr     r6, [r6]
    ldr     r3, [r4, #0x14]             @ full frame is width*height*3/2
    cmp     r1, r3
    bne     3f
    ldr     r3, [r4, #8]
    mul     r2, r8, r3
    add     r6, r2, r2, lsr #1          @ W*H*3/2
3:  add     r6, r5, r6                  @ r6 = buffer end

    mov     r0, r5                      @ flush cache for the whole buffer
    mov     r1, r6
    sub     r1, r1, r5
    mov     lr, pc
    b       CACHE_INV

    add     r1, r8, r8, lsr #1          @ row stride = W + W/2
    mov     r3, #0x80
    mov     r7, r5                      @ r7 = row base
rowloop:
    add     r12, r7, r8                 @ chroma = row + W
    add     r2, r7, r1                  @ row end
chromaloop:
    strb    r3, [r12], #1
    cmp     r12, r2
    blo     chromaloop
    add     r7, r7, r1
    cmp     r7, r6                      @ stop before a partial row
    add     r0, r7, r1
    cmpls   r0, r6
    bls     rowloop

    mov     r0, r5                      @ write cache back to RAM
    sub     r1, r6, r5
    mov     lr, pc
    b       CACHE_CLEAN

done:
    pop     {r0-r8, lr}
    str     lr, [sp, #-4]!              @ replaced instruction from 0x15448
    b       RESUME
    .ltorg

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
