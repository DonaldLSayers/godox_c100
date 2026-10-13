    .syntax unified
    .arm
base:
    .set    PHOTO43, base + 0xbb080
    .org    0xf74c
    b       PHOTO43
