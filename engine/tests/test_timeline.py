"""Tests du moteur d'édition (timeline) — couper, coller, insérer, superposer."""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from timeline import Timeline, concatenate  # noqa: E402

SR = 44100


def _tone(seconds: float, level: float = 0.5) -> Timeline:
    n = int(seconds * SR)
    sig = (level * np.ones(n)).astype(np.float32)
    return Timeline(np.vstack([sig, sig]), SR)


def test_split_and_delete():
    tl = _tone(2.0)                       # 2 s
    a, b = tl.split(0.5)
    assert abs(a.duration_s - 0.5) < 1e-3
    assert abs(b.duration_s - 1.5) < 1e-3

    cut = tl.delete_range(0.5, 1.0)       # retire 0.5 s
    assert abs(cut.duration_s - 1.5) < 1e-3


def test_copy_paste_insert():
    base = _tone(1.0, level=0.2)
    clip = _tone(0.5, level=0.9)          # « presse-papier »
    pasted = base.insert(0.25, clip)      # coller à 0.25 s
    assert abs(pasted.duration_s - 1.5) < 1e-3
    # La région insérée doit porter le niveau du clip.
    mid = pasted.audio[0, int(0.4 * SR)]
    assert abs(mid - 0.9) < 1e-3


def test_overlay_extends_and_sums():
    base = _tone(1.0, level=0.2)
    layer = _tone(1.0, level=0.2)
    mixed = base.overlay(0.5, layer)      # superpose au-delà de la fin
    assert abs(mixed.duration_s - 1.5) < 1e-3
    # Zone de recouvrement : somme des deux (~0.4).
    overlap = mixed.audio[0, int(0.75 * SR)]
    assert abs(overlap - 0.4) < 1e-2


def test_concatenate_and_fade():
    joined = concatenate([_tone(0.5), _tone(0.5)])
    assert abs(joined.duration_s - 1.0) < 1e-3
    faded = _tone(1.0).fade(fade_in_s=0.1, fade_out_s=0.1)
    assert faded.audio[0, 0] == 0.0            # début à zéro
    assert abs(faded.audio[0, -1]) < 1e-3      # fin à ~zéro


if __name__ == "__main__":
    test_split_and_delete()
    test_copy_paste_insert()
    test_overlay_extends_and_sums()
    test_concatenate_and_fade()
    print("✓ Tests d'édition (timeline) réussis.")
