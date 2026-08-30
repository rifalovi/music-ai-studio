"""Couche EXÉCUTION du mixage multipiste.

Applique une `MixDecision` sur un ensemble de stems :
  pour chaque piste  ->  traitement + gain (balance) + panoramique
  puis               ->  sommation en un bus stéréo
  puis               ->  traitements de bus + normalisation loudness + plafond

C'est l'équivalent multipiste de `dsp.py`. Le seul maillon qui touche le son.
"""

from __future__ import annotations

import numpy as np
import soundfile as sf

from analysis import analyze
from dsp import _normalize_loudness, _peak_ceiling, build_board_from_processors
from schema import AudioProfile, MixDecision, StemDecision


def analyze_stems(stem_paths: dict[str, str]) -> dict[str, AudioProfile]:
    """Profil chiffré de chaque piste (entrée de la couche décision)."""
    return {name: analyze(path) for name, path in stem_paths.items()}


def _load_stereo(path: str) -> tuple[np.ndarray, int]:
    """Charge une piste en stéréo (2, N) ; un mono est dupliqué L=R."""
    data, sr = sf.read(path, always_2d=True, dtype="float32")
    audio = data.T
    if audio.shape[0] == 1:
        audio = np.vstack([audio[0], audio[0]])
    elif audio.shape[0] > 2:
        audio = audio[:2]
    return audio, sr


def _pan_gains(pan: float) -> tuple[float, float]:
    """Loi de panoramique à puissance constante : renvoie (gain_L, gain_R)."""
    theta = (np.clip(pan, -1.0, 1.0) + 1.0) / 2.0 * (np.pi / 2.0)
    return float(np.cos(theta)), float(np.sin(theta))


def mix_master(
    stem_paths: dict[str, str],
    decision: MixDecision,
    output_path: str,
) -> AudioProfile:
    """Applique la décision de mix et écrit le master ; renvoie son profil."""
    dec_by_name = {s.name: s for s in decision.stems}
    sr: int | None = None
    layers: list[np.ndarray] = []

    for name, path in stem_paths.items():
        audio, this_sr = _load_stereo(path)
        sr = this_sr if sr is None else sr
        if this_sr != sr:
            raise ValueError(
                f"Sample rate hétérogène ({name}: {this_sr} Hz vs {sr} Hz) — "
                "rééchantillonne les stems au même taux."
            )

        d = dec_by_name.get(name, StemDecision(name=name))

        board = build_board_from_processors(d.chain)
        if len(board) > 0:
            audio = board(audio, sr)

        audio = audio * (10.0 ** (d.gain_db / 20.0))       # balance
        lg, rg = _pan_gains(d.pan)                          # panoramique
        audio = np.vstack([audio[0] * lg, audio[1] * rg])
        layers.append(audio)

    if not layers or sr is None:
        raise ValueError("Aucune piste à mixer.")

    # Sommation (les pistes peuvent différer en longueur : on aligne sur la plus longue).
    max_len = max(a.shape[1] for a in layers)
    mix = np.zeros((2, max_len), dtype=np.float32)
    for a in layers:
        mix[:, : a.shape[1]] += a

    # Bus master.
    bus = build_board_from_processors(decision.bus_chain)
    if len(bus) > 0:
        mix = bus(mix, sr)

    mix = _normalize_loudness(mix, sr, decision.target_lufs)
    mix = _peak_ceiling(mix, decision.target_true_peak_db)

    sf.write(output_path, mix.T, sr)
    return analyze(output_path)
