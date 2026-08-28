"""Couche 3 — EXÉCUTION (DSP).

Le seul maillon qui touche réellement le signal. Prend un `ProcessingChain`
produit par Claude et l'applique sur l'audio avec pedalboard, puis normalise
au loudness cible et plafonne le true-peak.

Dépendances : numpy, soundfile, pedalboard, pyloudnorm.
"""

from __future__ import annotations

import numpy as np
import soundfile as sf
from pedalboard import (
    Compressor,
    Distortion,
    Gain,
    HighpassFilter,
    HighShelfFilter,
    Limiter,
    LowpassFilter,
    LowShelfFilter,
    PeakFilter,
    Pedalboard,
    Reverb,
)

from schema import Processor, ProcessingChain

_EPS = 1e-12


def _eq_plugins(proc: Processor) -> list:
    plugins = []
    for band in proc.bands or []:
        q = band.q or 0.7
        gain = band.gain_db or 0.0
        if band.filter_type == "peak":
            plugins.append(PeakFilter(cutoff_frequency_hz=band.freq_hz, gain_db=gain, q=q))
        elif band.filter_type == "low_shelf":
            plugins.append(LowShelfFilter(cutoff_frequency_hz=band.freq_hz, gain_db=gain, q=q))
        elif band.filter_type == "high_shelf":
            plugins.append(HighShelfFilter(cutoff_frequency_hz=band.freq_hz, gain_db=gain, q=q))
        elif band.filter_type == "high_pass":
            plugins.append(HighpassFilter(cutoff_frequency_hz=band.freq_hz))
        elif band.filter_type == "low_pass":
            plugins.append(LowpassFilter(cutoff_frequency_hz=band.freq_hz))
    return plugins


def _build_board(chain: ProcessingChain) -> Pedalboard:
    """Traduit le ProcessingChain (décision de Claude) en chaîne pedalboard."""
    board = Pedalboard()
    for proc in chain.chain:
        if proc.type == "eq":
            for plugin in _eq_plugins(proc):
                board.append(plugin)
        elif proc.type == "compressor":
            board.append(
                Compressor(
                    threshold_db=proc.threshold_db if proc.threshold_db is not None else -18.0,
                    ratio=proc.ratio or 2.0,
                    attack_ms=proc.attack_ms or 15.0,
                    release_ms=proc.release_ms or 120.0,
                )
            )
            if proc.makeup_db:
                board.append(Gain(gain_db=proc.makeup_db))
        elif proc.type == "saturation":
            board.append(Distortion(drive_db=proc.drive_db or 6.0))
        elif proc.type == "reverb":
            board.append(
                Reverb(
                    room_size=proc.room_size if proc.room_size is not None else 0.3,
                    wet_level=proc.wet_level if proc.wet_level is not None else 0.15,
                    dry_level=proc.dry_level if proc.dry_level is not None else 0.85,
                )
            )
        elif proc.type == "limiter":
            board.append(
                Limiter(
                    threshold_db=proc.threshold_db if proc.threshold_db is not None else -1.0,
                    release_ms=proc.release_ms or 100.0,
                )
            )
        elif proc.type == "gain":
            board.append(Gain(gain_db=proc.gain_db or 0.0))
    return board


def _normalize_loudness(audio: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    """Ramène le loudness intégré vers la cible (gain global)."""
    import pyloudnorm as pyln

    mono = np.mean(audio, axis=0)
    meter = pyln.Meter(sr)
    current = meter.integrated_loudness(mono)
    if not np.isfinite(current):
        return audio
    gain_db = target_lufs - current
    return audio * (10.0 ** (gain_db / 20.0))


def _peak_ceiling(audio: np.ndarray, ceiling_db: float) -> np.ndarray:
    """Garantit que le crête ne dépasse pas le plafond (sécurité anti-écrêtage)."""
    ceiling = 10.0 ** (ceiling_db / 20.0)
    peak = float(np.max(np.abs(audio))) + _EPS
    if peak > ceiling:
        audio = audio * (ceiling / peak)
    return audio


def apply_chain(input_path: str, chain: ProcessingChain, output_path: str) -> str:
    """Applique la chaîne, normalise au loudness cible, écrit le fichier de sortie."""
    audio, sr = sf.read(input_path, always_2d=True, dtype="float32")
    audio = audio.T  # (canaux, N) pour pedalboard

    board = _build_board(chain)
    processed = board(audio, sr)

    processed = _normalize_loudness(processed, sr, chain.target_lufs)
    processed = _peak_ceiling(processed, chain.target_true_peak_db)

    sf.write(output_path, processed.T, sr)
    return output_path
