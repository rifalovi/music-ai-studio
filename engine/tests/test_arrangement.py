"""Test du seam de génération/arrangement.

Prouve la chaîne : brief (hors-ligne) -> génération (placeholder) -> placement
sur la timeline. Le générateur est un bouche-trou synthétique — le test valide
l'ARRANGEMENT (durée, sommation), pas la qualité musicale (qui vient d'un vrai
modèle branché).
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generation import PlaceholderGenerator, brief_duration_s, propose_brief_offline  # noqa: E402
from timeline import Timeline  # noqa: E402

SR = 44100


def test_brief_then_generate_then_place():
    brief = propose_brief_offline("une nappe chaude", bpm=90.0, key="Am")
    assert brief.bpm == 90.0 and brief.key == "Am"

    gen = PlaceholderGenerator()
    audio = gen.generate(brief, sr=SR)
    assert audio.ndim == 2 and audio.shape[0] == 2
    expected = int(round(brief_duration_s(brief) * SR))
    assert abs(audio.shape[1] - expected) <= 1, (audio.shape[1], expected)

    # Placement : on superpose l'instrumentale sur un fond existant à 1 s.
    base = Timeline(np.zeros((2, 2 * SR), np.float32), SR)  # 2 s de silence
    clip = Timeline(audio, SR)
    arranged = base.overlay(1.0, clip, gain_db=-3.0)

    # La durée finale couvre au moins jusqu'à la fin de l'instrumentale placée.
    assert arranged.duration_s >= 1.0 + clip.duration_s - 1e-3
    # Il y a bien du signal après le point de placement.
    assert np.max(np.abs(arranged.audio[:, int(1.1 * SR):])) > 0.0


if __name__ == "__main__":
    test_brief_then_generate_then_place()
    print("✓ Test d'arrangement (brief → génération placeholder → placement) réussi.")
