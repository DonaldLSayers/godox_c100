@ Redirect FUN_00018d14 (video frame -> H.264 encoder) to the video cave.
@ Replaces its first instruction (ldr r3, [r0]), which the hook re-executes
@ before jumping back to 0x18d18.

    .syntax unified
    .arm
base:
    .set    TARGET, base + HOOK           @ vhook (address from build.sh)
    .org    0x18d14
    b       TARGET
