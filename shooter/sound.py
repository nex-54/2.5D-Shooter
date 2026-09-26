"""
Procedural sound synthesis — generates all game audio at startup.
"""

from __future__ import annotations

import array
import math
import random
from collections.abc import Callable

import pygame

from shooter.constants import SAMPLE_RATE
from shooter.types import Sfx, SoundName

# Footsteps alternate between these two slightly different thuds.
FOOTSTEP_SOUNDS: tuple[SoundName, SoundName] = ("step0", "step1")


def _make_sound(samples: list[float]) -> pygame.mixer.Sound:
    """Create a pygame Sound from a list of 16-bit signed samples (mono)."""
    buf = array.array("h", [max(-32767, min(32767, int(s))) for s in samples])
    return pygame.mixer.Sound(buffer=buf)


def _synth_noise(duration: float, volume: float = 0.3, decay: bool = True) -> list[float]:
    """Generate noise burst (for footsteps, impacts)."""
    n = int(SAMPLE_RATE * duration)
    samples: list[float] = []
    for i in range(n):
        t = i / n
        env = (1 - t) if decay else 1
        samples.append(random.uniform(-1, 1) * volume * env * 32767)
    return samples


def _synth_tone(
    freq: float, duration: float, volume: float = 0.3, decay: bool = True
) -> list[float]:
    """Generate a sine tone."""
    n = int(SAMPLE_RATE * duration)
    samples: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = (1 - i / n) if decay else 1
        samples.append(math.sin(2 * math.pi * freq * t) * volume * env * 32767)
    return samples


def _synth_voice(
    duration: float,
    pitch: Callable[[float, float], float],
    tone: float,
    noise: float,
    fade: float = 1.0,
) -> list[float]:
    """Mix a sine tone of changing pitch with noise, both fading out together.

    pitch(t, progress) gives the frequency at t seconds, where progress runs
    from 0 to 1 over the sound. The envelope is 1 - progress**fade.
    """
    n = int(SAMPLE_RATE * duration)
    samples: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        progress = i / n
        env = 1 - progress**fade
        samples.append(
            math.sin(2 * math.pi * pitch(t, progress) * t) * tone * env * 32767
            + random.uniform(-1, 1) * noise * env * 32767
        )
    return samples


def init_sounds() -> Sfx:
    """Generate all game sounds. Call after pygame.mixer.init()."""
    sounds: Sfx = {}

    # --- Footsteps (2 alternating) ---
    for j, name in enumerate(FOOTSTEP_SOUNDS):
        s = _synth_noise(0.08, volume=0.12, decay=True)
        for i in range(len(s)):
            t = i / SAMPLE_RATE
            env = 1 - i / len(s)
            s[i] += math.sin(2 * math.pi * (60 + j * 10) * t) * 0.15 * env * 32767
        sounds[name] = _make_sound(s)

    # --- Pistol shot ---
    s = _synth_noise(0.15, volume=0.5, decay=True)
    for i in range(min(400, len(s))):
        t = i / SAMPLE_RATE
        s[i] += math.sin(2 * math.pi * 800 * t) * 0.3 * (1 - i / 400) * 32767
    sounds["pistol"] = _make_sound(s)

    # --- Gatling shot (shorter, sharper) ---
    s = _synth_noise(0.05, volume=0.35, decay=True)
    for i in range(min(200, len(s))):
        t = i / SAMPLE_RATE
        s[i] += math.sin(2 * math.pi * 1200 * t) * 0.2 * (1 - i / 200) * 32767
    sounds["gatling"] = _make_sound(s)

    # --- Shotgun blast (big boom) ---
    s = _synth_noise(0.25, volume=0.7, decay=True)
    for i in range(len(s)):
        t = i / SAMPLE_RATE
        env = 1 - i / len(s)
        s[i] += math.sin(2 * math.pi * 120 * t) * 0.5 * env * 32767
        s[i] += math.sin(2 * math.pi * 300 * t) * 0.2 * env * 32767
    sounds["shotgun"] = _make_sound(s)

    # --- Rocket launch (whoosh with downward freq sweep) ---
    s = _synth_voice(
        0.35, lambda _, progress: 900 - progress * 700, tone=0.25, noise=0.35, fade=1.5
    )
    sounds["rocket_fire"] = _make_sound(s)

    # --- Explosion (low boom + big noise burst) ---
    dur = 0.6
    n = int(SAMPLE_RATE * dur)
    s = list[float]()
    for i in range(n):
        t = i / SAMPLE_RATE
        env = (1 - i / n) ** 0.7
        boom = math.sin(2 * math.pi * max(30, 140 - t * 180) * t) * 0.55 * env
        rumble = math.sin(2 * math.pi * 60 * t) * 0.25 * env
        noise = random.uniform(-1, 1) * 0.55 * env * (1 - (i / n) ** 0.4)
        s.append((boom + rumble + noise) * 32767)
    sounds["explosion"] = _make_sound(s)

    # --- Enemy hurt grunt ---
    s = _synth_voice(0.2, lambda t, _: 150 + math.sin(t * 30) * 50, tone=0.3, noise=0.1)
    sounds["enemy_hurt"] = _make_sound(s)

    # --- Enemy die ---
    s = _synth_voice(0.4, lambda t, _: max(200 - t * 300, 50), tone=0.35, noise=0.15)
    sounds["enemy_die"] = _make_sound(s)

    # --- Enemy attack ---
    s = _synth_voice(0.15, lambda t, _: 180 + math.sin(t * 50) * 80, tone=0.25, noise=0.08)
    sounds["enemy_attack"] = _make_sound(s)

    # --- Pickup ---
    s = _synth_tone(600, 0.08, volume=0.2) + _synth_tone(900, 0.1, volume=0.2)
    sounds["pickup"] = _make_sound(s)

    # --- Empty click ---
    s = _synth_noise(0.03, volume=0.15, decay=True)
    sounds["empty"] = _make_sound(s)

    # --- Boss roar ---
    s = _synth_voice(0.6, lambda t, _: 80 + math.sin(t * 15) * 30, tone=0.5, noise=0.25, fade=0.5)
    sounds["boss_roar"] = _make_sound(s)

    # --- Boss die ---
    s = _synth_voice(0.8, lambda t, _: max(100 - t * 80, 30), tone=0.5, noise=0.3, fade=0.7)
    sounds["boss_die"] = _make_sound(s)

    # --- Spider hiss ---
    s = _synth_voice(
        0.25, lambda t, _: 3000 + math.sin(t * 80) * 1500, tone=0.1, noise=0.2, fade=0.6
    )
    sounds["spider_hiss"] = _make_sound(s)

    # --- Spider die ---
    s = _synth_voice(0.35, lambda t, _: max(800 - t * 600, 100), tone=0.15, noise=0.25)
    sounds["spider_die"] = _make_sound(s)

    # --- Door open creak ---
    s = _synth_voice(
        0.4, lambda t, _: 200 + math.sin(t * 25) * 100 + t * 300, tone=0.2, noise=0.1, fade=0.5
    )
    sounds["door_open"] = _make_sound(s)

    # --- Door close thud ---
    s = _synth_voice(0.3, lambda t, _: max(120 - t * 60, 50), tone=0.25, noise=0.15, fade=0.4)
    sounds["door_close"] = _make_sound(s)

    # --- Looping background music ---
    sounds["music"] = _make_sound(_synth_music())

    return sounds


# ---------------------------------------------------------------------------
# Background music
# ---------------------------------------------------------------------------
def _synth_music() -> list[float]:
    """Procedurally generate a Doom-inspired E-minor metal riff that loops.

    Layers: palm-muted square-wave bass pedal, distorted lead riff, kick/snare drums.
    Two alternating 2-bar riffs fill 4 bars so the loop point is musically natural.
    """
    BPM = 138
    BEAT = 60.0 / BPM
    EIGHTH = BEAT / 2
    BARS = 4

    total_dur = BARS * 4 * BEAT
    n = int(SAMPLE_RATE * total_dur)
    samples = [0.0] * n

    # --- Per-note synthesis (pre-computed, then blitted into the mix) ---
    def _note_buf(freq: float, dur: float, vol: float = 0.3, staccato: bool = False) -> list[float]:
        m = int(SAMPLE_RATE * dur)
        buf = [0.0] * m
        attack = min(m // 40, 120)
        release = int(0.04 * SAMPLE_RATE) if staccato else int(0.09 * SAMPLE_RATE)
        sustain_end = max(attack + 1, m - release)
        for i in range(m):
            t = i / SAMPLE_RATE
            if i < attack:
                env = i / attack
            elif i >= sustain_end:
                env = max(0.0, (m - i) / release)
            else:
                env = 1.0
            # Distorted square = fundamental + odd-harmonic saw-ish + soft clip
            ph = (freq * t) % 1.0
            v = 1.0 if ph < 0.5 else -1.0
            v += 0.35 * math.sin(2 * math.pi * freq * 2 * t)
            v += 0.2 * math.sin(2 * math.pi * freq * 3 * t)
            v *= 1.4
            if v > 0.9:
                v = 0.9 + (v - 0.9) * 0.2
            elif v < -0.9:
                v = -0.9 + (v + 0.9) * 0.2
            buf[i] = v * vol * env
        return buf

    def _kick_buf() -> list[float]:
        dur = 0.13
        m = int(SAMPLE_RATE * dur)
        buf = [0.0] * m
        for i in range(m):
            t = i / SAMPLE_RATE
            f = 130 - 85 * (t / dur)
            env = (1 - t / dur) ** 0.6
            buf[i] = math.sin(2 * math.pi * f * t) * 0.55 * env
            buf[i] += random.uniform(-1, 1) * 0.08 * env * (1 - t / dur) ** 2
        return buf

    def _snare_buf() -> list[float]:
        dur = 0.09
        m = int(SAMPLE_RATE * dur)
        buf = [0.0] * m
        for i in range(m):
            t = i / SAMPLE_RATE
            env = (1 - i / m) ** 0.8
            noise = random.uniform(-1, 1) * 0.5
            tone = math.sin(2 * math.pi * 220 * t) * 0.2
            buf[i] = (noise + tone) * env
        return buf

    def _hat_buf() -> list[float]:
        dur = 0.025
        m = int(SAMPLE_RATE * dur)
        buf = [0.0] * m
        for i in range(m):
            env = (1 - i / m) ** 0.4
            buf[i] = random.uniform(-1, 1) * 0.18 * env
        return buf

    def _blit(buf: list[float], start_t: float, gain: float = 1.0) -> None:
        i_start = int(start_t * SAMPLE_RATE)
        end = min(len(buf), n - i_start)
        for i in range(end):
            samples[i_start + i] += buf[i] * gain

    # --- E-minor pitches ---
    E2, G2 = 82.41, 98.00
    E3, G3, A3, Bb3, B3, D4 = 164.81, 196.00, 220.00, 233.08, 246.94, 293.66

    # --- Pre-synth palette ---
    BASS_E = _note_buf(E2, EIGHTH, vol=0.40, staccato=True)
    BASS_G = _note_buf(G2, EIGHTH, vol=0.40, staccato=True)
    L_E3 = _note_buf(E3, EIGHTH * 0.95, vol=0.22)
    L_G3 = _note_buf(G3, EIGHTH * 0.95, vol=0.22)
    L_A3 = _note_buf(A3, EIGHTH * 0.95, vol=0.22)
    L_Bb3 = _note_buf(Bb3, EIGHTH * 0.95, vol=0.22)
    L_B3 = _note_buf(B3, EIGHTH * 0.95, vol=0.22)
    L_D4 = _note_buf(D4, EIGHTH * 0.95, vol=0.22)
    KICK = _kick_buf()
    SNARE = _snare_buf()
    HAT = _hat_buf()

    # --- Composition: 4 bars, alternating riff A / riff B ---
    lead_A = [L_E3, L_E3, L_G3, L_A3, L_G3, L_E3, L_D4, L_E3]
    lead_B = [L_E3, L_E3, L_G3, L_A3, L_Bb3, L_A3, L_G3, L_B3]
    bass_A = [BASS_E] * 8
    bass_B = [BASS_E] * 6 + [BASS_G, BASS_E]
    bars = [(lead_A, bass_A), (lead_B, bass_B), (lead_A, bass_A), (lead_B, bass_B)]

    for bar_i, (lead, bass) in enumerate(bars):
        bar_start = bar_i * 4 * BEAT
        for eighth_i in range(8):
            t = bar_start + eighth_i * EIGHTH
            _blit(lead[eighth_i], t, gain=1.0)
            _blit(bass[eighth_i], t, gain=1.0)
            _blit(HAT, t, gain=0.9)
        for beat_i in range(4):
            beat_t = bar_start + beat_i * BEAT
            if beat_i % 2 == 0:
                _blit(KICK, beat_t, gain=1.0)
            else:
                _blit(SNARE, beat_t, gain=1.0)

    # --- Convert to 16-bit signed samples (master gain + clip) ---
    OVERALL = 0.55
    return [s * OVERALL * 32767 for s in samples]
