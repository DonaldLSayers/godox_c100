@ Photo jump table entries 3 (4:3) and 10..12 point at 0xf74c (the code for
@ unused 4032x3024 etc. cases); jump from there to photo43 in the code cave.

    .syntax unified
    .arm
base:
    .set    PHOTO43, base + 0xbad00
    .org    0xf74c
    b       PHOTO43
