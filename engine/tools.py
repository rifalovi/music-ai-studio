"""Outils créatifs — équivalents des outils Mureka, câblés sur notre moteur.

Ces fonctions composent la timeline (montage) et le générateur (génération) :
Claude rédige le brief, un modèle de génération réalise l'audio, la timeline
place/remplace. On prouve ici la LOGIQUE d'arrangement avec le générateur
placeholder ; brancher un vrai modèle ne change pas cette logique.

Outils déjà couverts ailleurs :
  - « Découper »   -> timeline.py (split / trim / delete_range)
  - « Séparateur » -> separation.py (Demucs)
  - « Créer »      -> generation.py (Stable Audio / MusicGen)
"""

from __future__ import annotations

import numpy as np

from generation import MusicGenerator, PlaceholderGenerator
from schema import GenerationBrief
from timeline import Timeline


def _fit(audio: np.ndarray, target_len: int) -> np.ndarray:
    """Ajuste un buffer (canaux, N) à exactement `target_len` échantillons."""
    ch = audio.shape[0]
    if target_len <= 0:
        return np.zeros((ch, 0), dtype=np.float32)
    if audio.shape[1] >= target_len:
        return audio[:, :target_len]
    pad = np.zeros((ch, target_len - audio.shape[1]), dtype=np.float32)
    return np.concatenate([audio, pad], axis=1)


def regenerate_region(
    tl: Timeline,
    from_s: float,
    to_s: float,
    brief: GenerationBrief,
    generator: MusicGenerator | None = None,
    crossfade_s: float = 0.02,
) -> Timeline:
    """« Modifier » — remplace la région [from, to] par de l'audio généré.

    La durée totale est préservée : on retire la région et on insère un clip
    de même longueur, avec de courts fondus pour éviter les clics aux raccords.
    """
    generator = generator or PlaceholderGenerator()
    region_len = tl._t(to_s) - tl._t(from_s)
    gen = _fit(generator.generate(brief, sr=tl.sr), region_len)
    clip = Timeline(gen, tl.sr).fade(crossfade_s, crossfade_s)
    return tl.delete_range(from_s, to_s).insert(from_s, clip)


def extend(
    tl: Timeline,
    brief: GenerationBrief,
    generator: MusicGenerator | None = None,
    crossfade_s: float = 0.02,
) -> Timeline:
    """« Étendre » — prolonge le morceau par une continuation générée."""
    generator = generator or PlaceholderGenerator()
    clip = Timeline(generator.generate(brief, sr=tl.sr), tl.sr).fade(crossfade_s, 0.0)
    return tl.append(clip)


def insert_generated(
    tl: Timeline,
    at_s: float,
    brief: GenerationBrief,
    generator: MusicGenerator | None = None,
    overlay: bool = False,
    gain_db: float = 0.0,
) -> Timeline:
    """Ajoute une instrumentale générée : en insertion (décale) ou en couche (overlay)."""
    generator = generator or PlaceholderGenerator()
    clip = Timeline(generator.generate(brief, sr=tl.sr), tl.sr)
    return tl.overlay(at_s, clip, gain_db) if overlay else tl.insert(at_s, clip)
