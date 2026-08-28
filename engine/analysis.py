"""Couche 1 — MESURE.

Transforme un fichier audio en `AudioProfile` : un ensemble de chiffres.
C'est la seule chose que Claude verra du morceau. Aucune décision de mix
n'est prise ici — on décrit, on ne juge pas.

Dépendances : numpy, soundfile, librosa, pyloudnorm.
"""

from __future__ import annotations

import numpy as np
import soundfile as sf

from schema import AudioProfile, SpectralBand

# Limites des sept bandes spectrales (Hz). Doit rester aligné sur schema.SpectralBand.
_BAND_EDGES: dict[SpectralBand, tuple[float, float]] = {
    "sub": (20, 60),
    "low": (60, 150),
    "low_mid": (150, 500),
    "mid": (500, 2000),
    "high_mid": (2000, 5000),
    "high": (5000, 10000),
    "air": (10000, 20000),
}

_EPS = 1e-12


def _db(x: float) -> float:
    return float(20.0 * np.log10(max(abs(x), _EPS)))


def _load(path: str) -> tuple[np.ndarray, int]:
    """Charge l'audio en float32, forme (canaux, échantillons)."""
    data, sr = sf.read(path, always_2d=True, dtype="float32")
    return data.T, sr  # (canaux, N)


def _spectral_balance(mono: np.ndarray, sr: int) -> tuple[dict[SpectralBand, float], float]:
    """Énergie par bande, en dB relatifs à l'énergie large bande, + centroïde."""
    # STFT magnitude moyenne sur toute la durée.
    n_fft = 4096
    hop = n_fft // 4
    window = np.hanning(n_fft)
    mags = []
    for start in range(0, max(1, len(mono) - n_fft), hop):
        frame = mono[start : start + n_fft]
        if len(frame) < n_fft:
            break
        spec = np.abs(np.fft.rfft(frame * window))
        mags.append(spec)
    if not mags:
        mags = [np.abs(np.fft.rfft(np.zeros(n_fft)))]
    avg = np.mean(mags, axis=0)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)

    total_energy = float(np.sum(avg**2)) + _EPS
    balance: dict[SpectralBand, float] = {}
    for band, (lo, hi) in _BAND_EDGES.items():
        mask = (freqs >= lo) & (freqs < hi)
        band_energy = float(np.sum(avg[mask] ** 2))
        # dB de la bande relatif à l'énergie totale — 0 dB ≈ bande « moyenne ».
        balance[band] = round(10.0 * np.log10((band_energy / total_energy) + _EPS), 2)

    centroid = float(np.sum(freqs * avg) / (np.sum(avg) + _EPS))
    return balance, centroid


def _loudness(mono: np.ndarray, sr: int) -> tuple[float, float, float]:
    """LUFS intégré, LRA (approx), true-peak (approx par sur-échantillonnage x4)."""
    import pyloudnorm as pyln

    meter = pyln.Meter(sr)
    integrated = float(meter.integrated_loudness(mono))

    # LRA approximée : écart entre 95e et 10e percentile du loudness court terme.
    win = int(sr * 0.4)
    if win > 0 and len(mono) > win:
        blocks = [
            mono[i : i + win] for i in range(0, len(mono) - win, win)
        ]
        st = np.array([
            -0.691 + 10 * np.log10(np.mean(b**2) + _EPS) for b in blocks
        ])
        st = st[np.isfinite(st)]
        lra = float(np.percentile(st, 95) - np.percentile(st, 10)) if st.size else 0.0
    else:
        lra = 0.0

    # True-peak : sur-échantillonnage x4 pour approcher les crêtes inter-échantillons.
    up = np.interp(
        np.linspace(0, len(mono), len(mono) * 4, endpoint=False),
        np.arange(len(mono)),
        mono,
    )
    true_peak = _db(float(np.max(np.abs(up))))
    return integrated, max(lra, 0.0), true_peak


def _tempo(mono: np.ndarray, sr: int) -> float:
    try:
        import librosa

        tempo, _ = librosa.beat.beat_track(y=mono, sr=sr)
        return round(float(np.atleast_1d(tempo)[0]), 1)
    except Exception:
        return 0.0


def analyze(path: str) -> AudioProfile:
    """Point d'entrée : chemin de fichier -> AudioProfile validé."""
    audio, sr = _load(path)
    channels = audio.shape[0]
    mono = np.mean(audio, axis=0)

    peak = _db(float(np.max(np.abs(audio))))
    rms = _db(float(np.sqrt(np.mean(mono**2) + _EPS)))
    integrated, lra, true_peak = _loudness(mono, sr)
    balance, centroid = _spectral_balance(mono, sr)

    if channels >= 2:
        left, right = audio[0], audio[1]
        # Corrélation de phase L/R.
        denom = (np.std(left) * np.std(right)) + _EPS
        correlation = float(np.clip(np.mean((left - left.mean()) * (right - right.mean())) / denom, -1, 1))
        # Largeur : énergie du canal « side » relative au canal « mid ».
        mid = (left + right) / 2
        side = (left - right) / 2
        width = float(np.clip(
            np.sqrt(np.mean(side**2)) / (np.sqrt(np.mean(mid**2)) + _EPS), 0, 1
        ))
    else:
        correlation, width = 1.0, 0.0

    return AudioProfile(
        duration_s=round(audio.shape[1] / sr, 2),
        sample_rate=sr,
        channels=channels,
        integrated_lufs=round(integrated, 2),
        loudness_range_lu=round(lra, 2),
        true_peak_dbtp=round(true_peak, 2),
        peak_dbfs=round(peak, 2),
        rms_dbfs=round(rms, 2),
        crest_factor_db=round(peak - rms, 2),
        clipping_detected=bool(np.max(np.abs(audio)) >= 0.999),
        spectral_balance=balance,
        spectral_centroid_hz=round(centroid, 1),
        stereo_width=round(width, 3),
        phase_correlation=round(correlation, 3),
        tempo_bpm=_tempo(mono, sr),
    )


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("usage: python analysis.py <fichier_audio>")
    print(json.dumps(analyze(sys.argv[1]).model_dump(), indent=2, ensure_ascii=False))
