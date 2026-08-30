"""Séparation de sources (mixdown -> stems), optionnelle.

Quand l'utilisateur n'a que le mixdown 2-pistes, on reconstruit des stems
approximatifs (voix / batterie / basse / autres) avec Demucs. Quand il a déjà
ses stems, on saute cette étape.

Demucs est lourd (PyTorch + poids du modèle) et donc une dépendance optionnelle :
    pip install demucs
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys


def is_available() -> bool:
    """Vrai si Demucs est installé et importable."""
    try:
        import demucs  # noqa: F401

        return True
    except Exception:
        return False


def separate(mixdown_path: str, out_dir: str, model: str = "htdemucs") -> dict[str, str]:
    """mixdown -> {nom_de_piste: chemin_wav}. Nécessite Demucs installé.

    Lève RuntimeError avec un message clair si Demucs est absent, plutôt que de
    faire échouer le reste du pipeline de façon obscure.
    """
    if not is_available():
        raise RuntimeError(
            "Demucs n'est pas installé. Installe-le (`pip install demucs`) pour "
            "séparer un mixdown, ou fournis directement tes stems."
        )

    os.makedirs(out_dir, exist_ok=True)
    # Demucs écrit dans out_dir/<model>/<nom_du_fichier>/{vocals,drums,bass,other}.wav
    subprocess.run(
        [sys.executable, "-m", "demucs", "-n", model, "-o", out_dir, mixdown_path],
        check=True,
    )

    base = os.path.splitext(os.path.basename(mixdown_path))[0]
    stem_dir = os.path.join(out_dir, model, base)
    stems = {
        os.path.splitext(os.path.basename(p))[0]: p
        for p in sorted(glob.glob(os.path.join(stem_dir, "*.wav")))
    }
    if not stems:
        raise RuntimeError(f"Aucun stem produit dans {stem_dir}.")
    return stems
