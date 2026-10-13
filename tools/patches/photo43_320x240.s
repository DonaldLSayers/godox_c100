@ 4:3 photo setting -> 320x240, downscaled from the full 4:3 sensor area.
@
@ Lives in FUN_0000f004's code for the unused 4032x3024 / 3648x2736 /
@ 3264x2448 photo cases (0xf74c..0xf787). Photo jump table entries 3 (4:3)
@ and 10..12 point here.
@
@ Capture-size struct (r4), as used by FUN_0001109c:
@   +6/+8    crop window, centred on the sensor
@   +0xa/+0xc first scaler output
@   +0xe/+0x10 final JPEG size
@ Stock 4:3 is 1440x1080 for all three. We keep the 1440x1080 crop and only
@ shrink the final size, then continue at the photo path (0xf188), which
@ re-reads everything from the struct. r9 = sensor height (1080).

    .syntax unified
    .arm
    .org 0xf74c
photo43:
    mov     r6, #320
    mov     r7, #240
    strh    r6, [r4, #14]       @ final width
    strh    r7, [r4, #16]       @ final height
    mov     r0, #1
    strb    r0, [r4, #4]        @ same as shared tail at 0xf6c8
    mov     r0, #1440
    strh    r0, [r4, #6]        @ crop 1440 x 1080
    strh    r9, [r4, #8]
    strh    r0, [r4, #10]       @ first scaler output 1440 x 1080
    strh    r9, [r4, #12]
    b       . + (0xf188 - 0xf778)
