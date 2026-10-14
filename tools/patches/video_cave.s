@ Video frame diagnostics (VIDDIAG=1 build). Hooks FUN_00018d14, the call
@ that hands each video frame to the H.264 encoder (camera task context, so
@ not an interrupt). Its first instruction (ldr r3, [r0]) is replaced with a
@ branch here; we re-run it and return to 0x18d18.
@
@ r0 = video encode struct (0x131490): [0] = 1 on the front-camera path,
@ +0x101 = pixel format ('#' = 0x23), [2] = frame address tagged with
@ 0x30000000 (0x50000000 = no frame), +0xdc / +0xe0 = width / height.
@ Test 1 (IMG_0309-0312) confirmed the photo strip layout per row (stride
@ 1.5 * width, luma at [0, W) on even rows, [W/2, 1.5W) on odd rows), but
@ every 64-row strip of the output showed the luma written to rows 0-63.
@ Test 2 (this one) writes a barcode of runtime values into the luma of rows
@ 0-63 only (one 64-row strip, 61440 bytes at 640 wide), to see per output
@ strip which call wrote it and from where. 8 lines of 8 rows (7 + a grey
@ gap), each a 32-bit value as 32 cells of 20 px, MSB left, white = 1:
@   0  0xA5A5F00F (marker, to check the decoding)
@   1  call counter          2  venc[2], frame address (tagged)
@   3  xTickCount (ms)       4  r1, the timestamp argument
@   5  venc+0xc8             6  venc+0xec      7  venc+0x164
@ Chroma is left untouched.
@ Writes nothing unless every check passes, so wrong guesses about the
@ struct leave the video untouched rather than corrupting memory.
    .syntax unified
    .arm
base:
    .set    RESUME,      base + 0x18d18
    .set    CACHE_INV,   base + 0x401ac
    .set    CACHE_CLEAN, base + 0x401b8
    .equ    VW,          640              @ only 640-wide frames are touched
    .equ    STRIDE,      VW * 3 / 2
    .equ    ROWS,        64
    .equ    TICK,        0x126b80         @ FreeRTOS xTickCount

    .org    0xbb774
vhook:
    push    {r0-r12, lr}                  @ r0-r1 are FUN_00018d14's live args
    ldr     r1, [r0]
    cmp     r1, #1                        @ front camera path
    bne     vdone
    ldrb    r1, [r0, #0x101]
    cmp     r1, #0x23                     @ '#'
    bne     vdone
    ldr     r1, [r0, #0xdc]
    cmp     r1, #VW
    bne     vdone
    ldr     r1, [r0, #0xe0]
    cmp     r1, #ROWS
    blo     vdone
    ldr     r5, [r0, #8]                  @ r5 = frame
    cmp     r5, #0x50000000
    cmpne   r5, #0
    beq     vdone
    bic     r5, r5, #0x30000000           @ strip the tag (FUN_00047228)
    ldr     r7, =VARS - base              @ VARS[i] = value for barcode line i
    ldr     r1, [r7, #32]                 @ call counter (persists across calls)
    add     r1, r1, #1
    str     r1, [r7, #32]
    str     r1, [r7, #4]                  @ 1: call counter
    ldr     r1, =0xA5A5F00F
    str     r1, [r7, #0]                  @ 0: marker
    ldr     r1, [sp]                      @ saved r0 = venc
    ldr     r2, [r1, #8]
    str     r2, [r7, #8]                  @ 2: frame address, tagged
    ldr     r2, =TICK
    ldr     r2, [r2]
    str     r2, [r7, #12]                 @ 3: xTickCount
    ldr     r2, [sp, #4]                  @ saved r1 = timestamp argument
    str     r2, [r7, #16]                 @ 4: timestamp
    ldr     r2, [r1, #0xc8]
    str     r2, [r7, #20]                 @ 5: venc+0xc8
    ldr     r2, [r1, #0xec]
    str     r2, [r7, #24]                 @ 6: venc+0xec
    ldr     r2, [r1, #0x164]
    str     r2, [r7, #28]                 @ 7: venc+0x164
    mov     r0, r5
    ldr     r1, =STRIDE * ROWS
    mov     lr, pc
    b       CACHE_INV
    mov     r4, #0                        @ r4 = row
rowloop:
    ldr     r6, =STRIDE
    mla     r8, r4, r6, r5                @ r8 = row start
    tst     r4, #1
    moveq   r9, r8                        @ r9 = luma
    addne   r9, r8, #VW / 2
    and     r0, r4, #7
    cmp     r0, #7                        @ last row of each line: mid grey gap
    moveq   r3, #128
    beq     fill
    ldr     r7, =VARS - base
    mov     r0, r4, lsr #3                @ r0 = line 0..7
    ldr     r10, [r7, r0, lsl #2]         @ r10 = VARS[line]
    mov     r0, #0                        @ r0 = x
1:  mov     r1, #0                        @ r1 = cell = x / 20
    mov     r2, r0
2:  subs    r2, r2, #20
    addpl   r1, r1, #1
    bpl     2b
    rsb     r1, r1, #31
    mov     r2, r10, lsr r1
    tst     r2, #1
    moveq   r3, #16                       @ 0 = black
    movne   r3, #235                      @ 1 = white
    strb    r3, [r9, r0]
    add     r0, r0, #1
    cmp     r0, #VW
    blo     1b
    b       nextrow
fill:
    mov     r0, #0
3:  strb    r3, [r9, r0]
    add     r0, r0, #1
    cmp     r0, #VW
    blo     3b
nextrow:
    add     r4, r4, #1
    cmp     r4, #ROWS
    blo     rowloop
    mov     r0, r5
    ldr     r1, =STRIDE * ROWS
    mov     lr, pc
    b       CACHE_CLEAN
vdone:
    pop     {r0-r12, lr}
    ldr     r3, [r0]                      @ the instruction we replaced
    b       RESUME
    .ltorg
    .align  2
VARS:                                     @ [0..7] barcode line values, [8] counter
    .space  36
