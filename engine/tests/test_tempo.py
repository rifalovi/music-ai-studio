"""Tests du moteur tempo — time-stretch (durée) et détection de BPM.

Nécessite librosa. Si librosa est absent, le test est ignoré proprement.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SR = 22050


def _has_librosa() -> bool:
    try:
        import librosa  # noqa: F401
        return True
    except Exception:
        return False


def test_time_stretch_changes_length():
    if not _has_librosa():
        print("librosa absent — test tempo ignoré.")
        return
    from tempo import time_stretch

    t = np.arange(int(2.0 * SR)) / SR
    sig = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    stereo = np.vstack([sig, sig])

    faster = time_stretch(stereo, rate=2.0)   # 2x plus rapide -> ~2x plus court
    ratio = faster.shape[1] / stereo.shape[1]
    assert 0.4 < ratio < 0.6, ratio

    slower = time_stretch(stereo, rate=0.5)   # 2x plus lent -> ~2x plus long
    ratio2 = slower.shape[1] / stereo.shape[1]
    assert 1.7 < ratio2 < 2.3, ratio2


def test_detect_bpm_runs():
    if not _has_librosa():
        return
    from tempo import detect_bpm

    # Train de clics à 120 BPM (2 clics/seconde).
    n = int(4.0 * SR)
    sig = np.zeros(n, dtype=np.float32)
    step = int(SR * 0.5)
    for i in range(0, n, step):
        sig[i : i + 200] = 1.0
    bpm = detect_bpm(np.vstack([sig, sig]), SR)
    assert bpm > 0  # une estimation plausible est renvoyée


if __name__ == "__main__":
    test_time_stretch_changes_length()
    test_detect_bpm_runs()
    print("✓ Tests tempo réussis (ou ignorés si librosa absent).")
