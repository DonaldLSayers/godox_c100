#!/usr/bin/env python3
"""Generate a short sine beep as 16-bit mono PCM WAV (the C100's sound format).

Usage: make_beep.py OUT.wav [FREQ_HZ] [DURATION_S]
"""
import math, struct, sys

RATE = 11025
FADE_S = 0.005  # short fade in/out so the beep doesn't click

def beep(freq, dur, amp=0.5):
    n = int(RATE * dur)
    fade = int(RATE * FADE_S)
    for i in range(n):
        env = min(1.0, i / fade, (n - 1 - i) / fade)
        yield int(32767 * amp * env * math.sin(2 * math.pi * freq * i / RATE))

def write_wav(path, samples):
    data = struct.pack(f'<{len(samples)}h', *samples)
    hdr = b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVE'
    hdr += b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, RATE, RATE * 2, 2, 16)
    hdr += b'data' + struct.pack('<I', len(data))
    open(path, 'wb').write(hdr + data)
    return len(hdr) + len(data)

if __name__ == '__main__':
    out = sys.argv[1]
    freq = float(sys.argv[2]) if len(sys.argv) > 2 else 1320.0
    dur = float(sys.argv[3]) if len(sys.argv) > 3 else 0.2
    size = write_wav(out, list(beep(freq, dur)))
    print(f'{out}: {freq:g} Hz, {dur:g} s, {size} bytes')
