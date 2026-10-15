@ Redirect FUN_0001ff10 (ISO readout on the see-through display) to the
@ display cave. Replaces its first instruction (ldr r3, [pc, #68], which
@ loads 0xe3279); lcd_hook redoes it before jumping back to 0x1ff14.

    .syntax unified
    .arm
base:
    .set    TARGET, base + HOOK           @ lcd_hook (address from build.sh)
    .org    0x1ff10
    b       TARGET
