"""Auto-test du loop complet, sans clé API ni fichier externe.

Génère un signal WAV synthétique, exécute analyse → décision (règles) → DSP →
ré-analyse, et vérifie que :
  1. le loop s'exécute de bout en bout et produit un fichier ;
  2. la décision est un ProcessingChain valide (schéma) se terminant par un limiter ;
  3. le master atteint (à ±1.5 LU) la loudness cible, alors que l'entrée en était loin ;
  4. le true-peak final respecte le plafond.

Exécutable directement (`python tests/test_loop.py`) ou via pytest.
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import soundfile as sf

# Permet l'exécution directe depuis engine/ ou depuis la racine du repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import master  # noqa: E402


def _make_test_wav(path: str, sr: int = 44100, seconds: float = 3.0) -> None:
    """Signal stéréo volontairement bas et dynamique (loin de la cible)."""
    n = int(sr * seconds)
    t = np.arange(n) / sr
    rng = np.random.default_rng(42)

    # Mélange de tons (basse + médium + aigu) + un peu de bruit, faible niveau.
    tone = (
        0.5 * np.sin(2 * np.pi * 90 * t)      # basse
        + 0.3 * np.sin(2 * np.pi * 700 * t)   # médium
        + 0.15 * np.sin(2 * np.pi * 6000 * t)  # aigu
    )
    tone += 0.05 * rng.standard_normal(n)

    # Enveloppe qui crée de la dynamique (crest factor élevé).
    env = 0.2 + 0.8 * (0.5 * (1 + np.sin(2 * np.pi * 0.5 * t)))
    mono = tone * env * 0.15  # niveau global bas

    stereo = np.stack([mono, mono * 0.98], axis=1)  # léger décalage L/R
    sf.write(path, stereo, sr)


def test_full_loop_offline() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.wav")
        out = os.path.join(tmp, "out.wav")
        _make_test_wav(src)

        target = -14.0
        result = master(src, out, intent="master de test", target_lufs=target, offline=True)

        # 1. Le loop a produit un fichier.
        assert os.path.isfile(out), "aucun fichier de sortie écrit"

        # 2. Décision valide, se terminant par un limiter.
        assert len(result.chain.chain) >= 1
        assert result.chain.chain[-1].type == "limiter", "la chaîne doit finir par un limiter"

        # 3. La loudness s'est rapprochée de la cible.
        before_err = abs(result.before.integrated_lufs - target)
        after_err = abs(result.after.integrated_lufs - target)
        assert after_err < before_err, (
            f"loudness pas rapprochée : avant {result.before.integrated_lufs}, "
            f"après {result.after.integrated_lufs}, cible {target}"
        )
        assert after_err <= 1.5, f"cible loudness manquée : {result.after.integrated_lufs} LUFS"

        # 4. True-peak sous le plafond (petite tolérance de mesure).
        assert result.after.true_peak_dbtp <= result.chain.target_true_peak_db + 0.5

        return result


if __name__ == "__main__":
    res = test_full_loop_offline()
    print("✓ Auto-test réussi.")
    print(f"  Avant : {res.before.integrated_lufs} LUFS · crest {res.before.crest_factor_db} dB")
    print(f"  Décision ({len(res.chain.chain)} maillons) : {res.chain.summary}")
    for i, proc in enumerate(res.chain.chain, 1):
        print(f"    {i}. {proc.type} — {proc.reason}")
    print(f"  Après : {res.after.integrated_lufs} LUFS · "
          f"true-peak {res.after.true_peak_dbtp} dBTP")
