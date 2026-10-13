    .syntax unified
    .arm
base:
    .set    STUB, base + 0xbb2c0
    .org    0x187c4
    b       STUB
