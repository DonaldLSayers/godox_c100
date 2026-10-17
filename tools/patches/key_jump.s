@ Point the center button handler's post of message 0x7041 (bl 0x42c at
@ 0x1ddf8 in FUN_0001dd6c, ap_peripheral_F_key_exe; reached once per press)
@ at center_hook in lcd_cave.s, which steps the preset mode and then posts
@ the message itself. The BL is encoded by hand: llvm-mc would
@ leave a relocation for `bl` (see docs/c100-firmware.md).

    .syntax unified
    .arm
    .org    0x1ddf8
    .word   0xeb000000 | (((HOOK - 0x1ddf8 - 8) >> 2) & 0xffffff)   @ bl center_hook
