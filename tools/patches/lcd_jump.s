@ Point the display refresh's tail call to 0x20fd0 (video icon + SS
@ readout, photo and video mode, at 0x21218 in FUN_00021318) at lcd_hook,
@ which calls it and then draws the preset code on the SS cells.

    .syntax unified
    .arm
base:
    .set    TARGET, base + HOOK           @ lcd_hook (address from build.sh)
    .org    0x21218
    b       TARGET
