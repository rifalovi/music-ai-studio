"""Gestion du TEMPO — détection de BPM et étirement temporel.

- `detect_bpm`  : estime le tempo d'un buffer audio.
- `time_stretch`: change la durée sans changer la hauteur (phase vocoder).
- `stretch_to_bpm` : ré-aligne un extrait d'un tempo à un autre.

S'appuie sur librosa. Le time-stretch conserve la hauteur (utile pour caler
une boucle ou une instrumentale sur le tempo du morceau).
"""

from __future__ import annotations

import numpy as np


def detect_bpm(audio: np.ndarray, sr: int) -> float:
    """Estime le tempo (BPM) d'un buffer (canaux, N) ou mono."""
    import librosa

    mono = np.mean(audio, axis=0) if audio.ndim == 2 else audio
    tempo, _ = librosa.beat.beat_track(y=np.ascontiguousarray(mono), sr=sr)
    return round(float(np.atleast_1d(tempo)[0]), 1)


def time_stretch(audio: np.ndarray, rate: float) -> np.ndarray:
    """Étire le temps par `rate` (>1 = plus rapide/court), hauteur conservée.

    Applique le phase vocoder canal par canal pour préserver l'image stéréo.
    """
    import librosa

    if rate <= 0:
        raise ValueError("rate doit être > 0")
    if abs(rate - 1.0) < 1e-6:
        return audio.copy()

    if audio.ndim == 1:
        return librosa.effects.time_stretch(np.ascontiguousarray(audio), rate=rate)

    stretched = [
        librosa.effects.time_stretch(np.ascontiguousarray(ch), rate=rate) for ch in audio
    ]
    n = min(s.shape[0] for s in stretched)  # aligne les longueurs des canaux
    return np.vstack([s[:n] for s in stretched]).astype(np.float32)


def stretch_to_bpm(audio: np.ndarray, from_bpm: float, to_bpm: float) -> np.ndarray:
    """Ré-aligne un extrait de `from_bpm` vers `to_bpm` (hauteur conservée)."""
    if from_bpm <= 0 or to_bpm <= 0:
        raise ValueError("Les tempos doivent être > 0")
    # Pour accélérer vers un BPM plus élevé, rate = to/from (>1).
    return time_stretch(audio, rate=to_bpm / from_bpm)
