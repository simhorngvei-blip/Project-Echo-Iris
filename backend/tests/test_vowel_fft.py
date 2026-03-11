"""Diagnose FFT vowel estimation - writes to file directly"""
import numpy as np

SAMPLE_RATE = 44100
FFT_SIZE = 256

def hann_window(n):
    return 0.5 * (1 - np.cos(2 * np.pi * np.arange(n) / (n - 1)))

WINDOW = hann_window(FFT_SIZE)

def estimate_vowels(samples):
    windowed = samples[:FFT_SIZE] * WINDOW
    spectrum = np.fft.fft(windowed)
    mag = np.abs(spectrum[:FFT_SIZE // 2])
    def be(lo, hi): return np.sum(mag[lo:hi+1])
    b1 = be(1, 3); b2 = be(3, 6); b3 = be(5, 10); b4 = be(10, 24)
    total = b1 + b2 + b3 + b4 + 0.0001
    r1, r2, r3, r4 = b1/total, b2/total, b3/total, b4/total
    rawA = r2 * 2.0
    rawI = r4 * 3.0 * (1.0 - r2 * 0.5)
    rawU = r1 * 2.0 * (1.0 - r4)
    rawE = (r2 + r4) * 1.2 * (1.0 - r1)
    rawO = r2 * r3 * 4.0 * (1.0 - r4)
    s = rawA + rawI + rawU + rawE + rawO + 0.0001
    return rawA/s, rawI/s, rawU/s, rawE/s, rawO/s, r1, r2, r3, r4

def tone(formants, dur=0.01):
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    sig = sum(a * np.sin(2*np.pi*f*t) for f, a in formants)
    return sig / (np.max(np.abs(sig)) + 0.001) * 0.5

VOWELS = [
    ('A', [(800,1.0),(1200,0.7),(2500,0.3)]),
    ('I', [(300,1.0),(2300,0.8),(3000,0.4)]),
    ('U', [(300,1.0),(800,0.6),(2200,0.2)]),
    ('E', [(500,1.0),(1800,0.7),(2500,0.4)]),
    ('O', [(500,1.0),(800,0.7),(2500,0.2)]),
]

lines = []
lines.append("FFT VOWEL DIAGNOSTIC")
lines.append(f"SR={SAMPLE_RATE} FFT={FFT_SIZE} BinWidth={SAMPLE_RATE/FFT_SIZE:.0f}Hz")
lines.append("")

for name, formants in VOWELS:
    sig = tone(formants)
    a, i, u, e, o, r1, r2, r3, r4 = estimate_vowels(sig)
    lines.append(f"--- Vowel {name} (formants: {[f for f,amp in formants]}) ---")
    lines.append(f"  r1={r1:.3f} r2={r2:.3f} r3={r3:.3f} r4={r4:.3f}")
    lines.append(f"  A={a:.3f}  I={i:.3f}  U={u:.3f}  E={e:.3f}  O={o:.3f}")
    vals = {'A':a,'I':i,'U':u,'E':e,'O':o}
    winner = max(vals, key=vals.get)
    lines.append(f"  Winner={winner} Expected={name} {'OK' if winner==name else 'WRONG!!!'}")
    lines.append("")

lines.append("PURE TONE TESTS")
for freq in [300, 500, 800, 1200, 1800, 2300, 3000]:
    t = np.linspace(0, 0.01, int(SAMPLE_RATE*0.01), endpoint=False)
    sig = np.sin(2*np.pi*freq*t) * 0.5
    a, i, u, e, o, r1, r2, r3, r4 = estimate_vowels(sig)
    lines.append(f"  {freq}Hz: A={a:.3f} I={i:.3f} U={u:.3f} E={e:.3f} O={o:.3f} r1={r1:.3f} r2={r2:.3f} r3={r3:.3f} r4={r4:.3f}")

with open('d:/Vtuber/vowel_results.txt', 'w', encoding='ascii', errors='replace') as f:
    f.write('\n'.join(lines))
print("Done - results in vowel_results.txt")
