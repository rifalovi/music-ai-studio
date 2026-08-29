"""Tests des outils créatifs — Modifier (régénérer une région) et Étendre.

Utilise le générateur placeholder : on valide la LOGIQUE d'arrangement
(remplacement de région à durée préservée, continuation), pas la qualité
musicale (qui vient d'un vrai modèle branché).
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generation import PlaceholderGenerator, brief_duration_s, propose_brief_offline  # noqa: E402
from timeline import Timeline  # noqa: E402
from tools import extend, insert_generated, regenerate_region  # noqa: E402

SR = 44100


def _tone(seconds: float, level: float = 0.5) -> Timeline:
    n = int(seconds * SR)
    sig = (level * np.ones(n)).astype(np.float32)
    return Timeline(np.vstack([sig, sig]), SR)


def test_regenerate_region_preserves_duration():
    base = _tone(4.0, level=0.3)
    brief = propose_brief_offline("nouveau passage", bpm=120.0, key="C")
    out = regenerate_region(base, 1.0, 2.0, brief, generator=PlaceholderGenerator())

    # Durée totale inchangée (région remplacée par un clip de même longueur).
    assert abs(out.duration_s - base.duration_s) < 1e-3, out.duration_s
    # La région modifiée n'est plus le niveau plat d'origine (du contenu généré y est).
    mid = out.audio[0, int(1.5 * SR)]
    assert abs(mid - 0.3) > 1e-3


def test_extend_lengthens():
    base = _tone(2.0)
    brief = propose_brief_offline("outro douce", bpm=90.0, key="Am")
    out = extend(base, brief, generator=PlaceholderGenerator())
    expected = base.duration_s + brief_duration_s(brief)
    assert abs(out.duration_s - expected) < 0.05, (out.duration_s, expected)


def test_insert_generated_overlay():
    base = _tone(3.0, level=0.0)  # silence
    brief = propose_brief_offline("nappe", bpm=100.0, key="F")
    out = insert_generated(base, 0.5, brief, overlay=True, gain_db=-3.0)
    # Overlay : durée au moins jusqu'à la fin de la couche placée.
    assert out.duration_s >= 0.5 + brief_duration_s(brief) - 1e-3
    assert np.max(np.abs(out.audio[:, int(0.6 * SR):])) > 0.0


if __name__ == "__main__":
    test_regenerate_region_preserves_duration()
    test_extend_lengthens()
    test_insert_generated_overlay()
    print("✓ Tests outils créatifs (Modifier / Étendre / Insérer) réussis.")
