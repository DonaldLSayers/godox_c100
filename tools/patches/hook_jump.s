@ Redirect the photo frame/strip callback FUN_00015448 to our hook.
@ Replaces its first instruction (str lr, [sp, #-4]!), which the hook
@ re-executes before jumping back to 0x1544c.

    .syntax unified
    .arm
base:
    .set    HOOK, base + 0xbab6c
    .org    0x15448
    b       HOOK
