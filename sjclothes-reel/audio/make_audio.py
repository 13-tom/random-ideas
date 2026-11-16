#!/usr/bin/env python3
"""Builds the SJClothes reel soundtrack: a synthesized 120 BPM minimal fashion beat,
transition whooshes/impacts, and the voiceover placed on the shot timeline with ducking.

  python3 audio/make_audio.py            -> out/soundtrack.wav (+ stems in out/stems/)

To use a real voice artist: replace audio/vo/l1.wav … l8.wav (any sample rate, same line split
as VO_LINES below) and re-run. To use licensed music instead, drop it at audio/music.wav.
"""
import os, subprocess, numpy as np, wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'out'); os.makedirs(os.path.join(OUT, 'stems'), exist_ok=True)
SR, DUR, BPM = 44100, 28.0, 120
N = int(SR * DUR); BEAT = 60 / BPM
rng = np.random.default_rng(7)

# Voiceover lines and where they start (seconds) — matches reel.html shot timing
VO_LINES = [('l1', 0.30), ('l2', 4.15), ('l3', 7.75), ('l4', 11.75),
            ('l5', 16.35), ('l6', 19.95), ('l7', 22.25), ('l8', 24.75)]

def tvec(sec): return np.arange(int(SR * sec)) / SR
def place(buf, x, at, gain=1.0):
    i = int(at * SR); j = min(len(buf), i + len(x))
    if j > i: buf[i:j] += x[:j - i] * gain
def fft_filter(x, lo=None, hi=None):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); g = np.ones_like(f)
    if lo: g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1)) ** 4)
    if hi: g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    return np.fft.irfft(X * g, len(x))
def norm(x, peak=0.9): m = np.max(np.abs(x)); return x * (peak / m) if m > 0 else x
def saw(freq, t): return 2 * ((t * freq) % 1) - 1

# ---------------- drums ----------------
def kick():
    t = tvec(0.42); f = 48 + 110 * np.exp(-t * 38)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 7.5) + 0.25 * np.sin(ph * 2) * np.exp(-t * 30)
def hat(open_=False):
    t = tvec(0.25 if open_ else 0.06); return rng.standard_normal(len(t)) * np.exp(-t * (14 if open_ else 70))
def clap():
    t = tvec(0.3); env = np.exp(-t * 18)
    for d in (0.0, 0.012, 0.024): env += np.where(t >= d, np.exp(-(t - d) * 120), 0) * 0.6
    return rng.standard_normal(len(t)) * env
def impact():
    t = tvec(1.6); f = 32 + 70 * np.exp(-t * 6)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2)
    return boom + 0.35 * rng.standard_normal(len(t)) * np.exp(-t * 9)
def whoosh(length=0.45):
    t = tvec(length); n = rng.standard_normal(len(t))
    env = np.sin(np.pi * t / length) ** 2
    return n * env

kicks, hats, claps, fx_lo, fx_hi = (np.zeros(N) for _ in range(5))
k = kick()
beats = np.arange(0, DUR, BEAT)
for b in beats:
    if b < 21.9 or b >= 24.5:
        place(kicks, k, b, 1.0 if b < 21.9 else 0.7)
    if b < 21.9 or b >= 24.5:
        place(hats, hat(), b + BEAT / 2, 0.55)                      # offbeat closed hat
        place(hats, hat(), b + BEAT / 4, 0.18); place(hats, hat(), b + 3 * BEAT / 4, 0.18)
        if 16.25 <= b < 21.9: place(hats, hat(True), b + BEAT / 2, 0.35)   # collage lift
    beat_in_bar = round(b / BEAT) % 4
    if beat_in_bar in (1, 3) and (4.0 <= b < 21.9 or b >= 24.5): place(claps, clap(), b, 0.8)
hats = fft_filter(hats, lo=7000); claps = fft_filter(claps, lo=900, hi=5000)

# transitions: whooshes on wipes/whips, impacts on the big moments
for at in (3.82, 7.33, 10.40, 11.58, 16.08, 17.52, 18.60):
    place(fx_hi, whoosh(0.42), at - 0.15, 0.55)
for at, g in ((4.0, 0.9), (22.0, 1.0), (27.5, 0.55)):
    place(fx_lo, impact(), at, g)
# riser into the end card
t = tvec(1.6); rise = rng.standard_normal(len(t)) * (t / 1.6) ** 2.2
place(fx_hi, fft_filter(rise, lo=1500) * 0.8, 20.4)
fx_hi = fft_filter(fx_hi, lo=500, hi=9000)

# ---------------- bass + pad (A minor: Am F C G, one chord per bar) ----------------
CH = [(55.00, [220.0, 261.63, 329.63]), (43.65, [174.61, 220.0, 261.63]),
      (65.41, [261.63, 329.63, 392.0]), (49.00, [196.0, 246.94, 293.66])]
bass, padL, padR = np.zeros(N), np.zeros(N), np.zeros(N)
bar = 4 * BEAT
for bi, bstart in enumerate(np.arange(0, DUR, bar)):
    root, notes = CH[bi % 4]
    for e in range(8):                                   # offbeat 8th-note bass pulses
        if e % 2 == 1:
            tt = tvec(BEAT * 0.45); env = np.exp(-tt * 6) * np.minimum(1, tt * 200)
            place(bass, (np.sin(2 * np.pi * root * tt) + 0.3 * saw(root * 2, tt)) * env, bstart + e * BEAT / 2)
    tt = tvec(bar + 0.3); env = np.minimum(1, tt / 0.6) * np.minimum(1, (bar + 0.3 - tt) / 0.4)
    for f in notes:
        place(padL, saw(f * 0.997, tt) * env, bstart, 0.33); place(padR, saw(f * 1.003, tt) * env, bstart, 0.33)
bass = fft_filter(bass, hi=260)
padL, padR = fft_filter(padL, lo=150, hi=1700), fft_filter(padR, lo=150, hi=1700)
# drop the bass out for the end-card breath, then bring it back with the kick
gate = np.ones(N); i0, i1 = int(21.95 * SR), int(24.5 * SR); gate[i0:i1] = 0.0
bass *= gate

def stereo(m, pan=0.0): return np.stack([m * (1 - max(0, pan)), m * (1 + min(0, pan))], 1)
music = (stereo(norm(kicks), 0) * 0.9 + stereo(norm(bass), 0) * 0.55 + stereo(norm(hats), 0.25) * 0.28 +
         stereo(norm(claps), -0.15) * 0.35 + np.stack([norm(padL), norm(padR)], 1) * 0.22 +
         stereo(norm(fx_hi), 0) * 0.30 + stereo(norm(fx_lo), 0) * 0.75)
custom = os.path.join(ROOT, 'audio', 'music.wav')
if os.path.exists(custom):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', custom, '-t', str(DUR), '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    m = np.frombuffer(raw, np.float32).reshape(-1, 2); music = np.zeros((N, 2)); music[:len(m)] = m[:N]
fade = np.ones(N); fade[-int(0.5 * SR):] = np.linspace(1, 0, int(0.5 * SR)); music *= fade[:, None]

# ---------------- voiceover ----------------
vo = np.zeros(N)
for name, at in VO_LINES:
    path = os.path.join(ROOT, 'audio', 'vo', name + '.wav')
    if not os.path.exists(path): continue
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(SR), '-af',
                          'highpass=f=90,acompressor=threshold=-20dB:ratio=3:attack=5:release=60', '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    place(vo, np.frombuffer(raw, np.float32).astype(np.float64), at)
vo = norm(vo, 0.95)

# duck music under the voice (smoothed envelope)
env = np.abs(vo); w = int(0.12 * SR); env = np.convolve(env, np.ones(w) / w, 'same')
env = np.clip(env / (env.max() + 1e-9) * 6, 0, 1)
duck = 1 - 0.45 * env
mix = norm(music, 0.9) * duck[:, None] * 0.55 + stereo(vo, 0) * 0.95

def write(path, x):
    x = np.clip(x, -1, 1); x = (x * 32767).astype(np.int16)
    if x.ndim == 1: x = np.stack([x, x], 1)
    with wave.open(path, 'wb') as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR); f.writeframes(x.tobytes())

write(os.path.join(OUT, 'stems', 'music.wav'), norm(music, 0.9))
write(os.path.join(OUT, 'stems', 'voiceover.wav'), vo)
tmp = os.path.join(OUT, 'stems', 'mix_raw.wav'); write(tmp, norm(mix, 0.9))
# loudness-normalise for Instagram/Reels (~ -14 LUFS, -1 dBTP)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', tmp, '-af', 'loudnorm=I=-14:TP=-1.0:LRA=9', '-ar', str(SR),
                os.path.join(OUT, 'soundtrack.wav')], check=True)
os.remove(tmp)
print('soundtrack ->', os.path.join(OUT, 'soundtrack.wav'))
