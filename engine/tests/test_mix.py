"""Auto-test du loop de mixage multipiste, sans clé API ni fichier externe.

Génère trois stems synthétiques (bass, drums, vocals) à des niveaux volontairement
déséquilibrés, exécute analyse par piste → décision (règles) → sommation & bus →
ré-analyse, et vérifie que :
  1. le loop produit un mix ;
  2. la décision couvre chaque piste + finit le bus par un limiter ;
  3. la balance rapproche les pistes de niveaux cohérents (l'écart de niveau se réduit) ;
  4. le mix final atteint la loudness cible et respecte le plafond true-peak.
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mix_pipeline import mix  # noqa: E402


def _write(path: str, mono: np.ndarray, sr: int) -> None:
    sf.write(path, np.stack([mono, mono], axis=1), sr)


def _make_stems(directory: str, sr: int = 44100, seconds: float = 3.0) -> dict[str, str]:
    n = int(sr * seconds)
    t = np.arange(n) / sr
    rng = np.random.default_rng(7)

    # Basse : sinus grave, niveau fort.
    bass = 0.5 * np.sin(2 * np.pi * 70 * t)
    # Batterie : salves de bruit périodiques, niveau moyen.
    pulse = (np.sin(2 * np.pi * 2 * t) > 0.8).astype(float)
    drums = 0.25 * rng.standard_normal(n) * pulse
    # Voix : ton médium, niveau volontairement TROP FAIBLE (à remonter par la balance).
    vocals = 0.05 * np.sin(2 * np.pi * 500 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t))

    paths = {}
    for name, sig in {"bass": bass, "drums": drums, "vocals": vocals}.items():
        p = os.path.join(directory, f"{name}.wav")
        _write(p, sig.astype(np.float32), sr)
        paths[name] = p
    return paths


def test_multitrack_loop_offline():
    with tempfile.TemporaryDirectory() as tmp:
        stem_paths = _make_stems(tmp)
        out = os.path.join(tmp, "mix.wav")
        target = -14.0

        result = mix(stem_paths, out, intent="mix de test", target_lufs=target, offline=True)

        # 1. Un mix a été produit.
        assert os.path.isfile(out)

        # 2. Décision complète : une entrée par piste, bus terminé par un limiter.
        assert {s.name for s in result.decision.stems} == set(stem_paths)
        assert result.decision.bus_chain[-1].type == "limiter"

        # 3. La balance réduit l'écart de niveau entre pistes.
        raw_levels = [p.integrated_lufs for p in result.before.values()]
        balanced = [
            p.integrated_lufs + s.gain_db
            for s, p in zip(result.decision.stems, result.before.values())
        ]
        assert (max(balanced) - min(balanced)) < (max(raw_levels) - min(raw_levels)), (
            "la balance devrait resserrer les niveaux entre pistes"
        )

        # 4. Le mix final atteint la cible et respecte le plafond.
        assert abs(result.after.integrated_lufs - target) <= 1.5, result.after.integrated_lufs
        assert result.after.true_peak_dbtp <= result.decision.target_true_peak_db + 0.5

        return result


if __name__ == "__main__":
    res = test_multitrack_loop_offline()
    print("✓ Auto-test multipiste réussi.")
    print("  Pistes (niveau brut → gain de balance) :")
    for s, (name, p) in zip(res.decision.stems, res.before.items()):
        print(f"    {name:<8} {p.integrated_lufs:>7.1f} LUFS  →  gain {s.gain_db:+.1f} dB · pan {s.pan:+.2f}")
    print(f"  Décision : {res.decision.summary}")
    print(f"  Mix final : {res.after.integrated_lufs} LUFS · true-peak {res.after.true_peak_dbtp} dBTP")
