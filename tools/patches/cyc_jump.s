    .syntax unified
    .arm
base:
    .set    TARGET, base + STUB           @ idx_stub (address from build.sh)
    .org    0x187c4
    b       TARGET
