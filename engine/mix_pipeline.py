"""Orchestration du mixage multipiste — Phase 2.

    analyser chaque piste  →  Claude décide le mix  →  sommer & traiter  →  ré-analyser

Deux entrées possibles :
  - un dossier de stems fournis par l'artiste ;
  - un mixdown 2-pistes, séparé en stems via Demucs (si installé).
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

from mix_engineer import propose_mix, propose_mix_offline
from mixing import analyze_stems, mix_master
from schema import AudioProfile, MixDecision

_AUDIO_EXT = (".wav", ".flac", ".aif", ".aiff", ".mp3", ".ogg")


def stems_from_dir(directory: str) -> dict[str, str]:
    """Construit {nom: chemin} à partir des fichiers audio d'un dossier."""
    paths = [
        p for p in sorted(glob.glob(os.path.join(directory, "*")))
        if p.lower().endswith(_AUDIO_EXT)
    ]
    return {os.path.splitext(os.path.basename(p))[0]: p for p in paths}


@dataclass
class MixResult:
    before: dict[str, AudioProfile]
    decision: MixDecision
    after: AudioProfile
    output_path: str

    def to_dict(self) -> dict:
        return {
            "before": {k: v.model_dump() for k, v in self.before.items()},
            "decision": self.decision.model_dump(exclude_none=True),
            "after": self.after.model_dump(),
            "output_path": self.output_path,
        }


def mix(
    stem_paths: dict[str, str],
    output_path: str,
    intent: str = "",
    target_lufs: float = -14.0,
    offline: bool | None = None,
) -> MixResult:
    """Exécute le loop de mixage complet sur des stems déjà séparés."""
    if offline is None:
        offline = not os.environ.get("ANTHROPIC_API_KEY")

    before = analyze_stems(stem_paths)                      # 1. mesure par piste
    if offline:                                             # 2. décision de mix
        decision = propose_mix_offline(before, intent, target_lufs)
    else:
        decision = propose_mix(before, intent, target_lufs)
    after = mix_master(stem_paths, decision, output_path)   # 3+4. sommation & contrôle
    return MixResult(before=before, decision=decision, after=after, output_path=output_path)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Mixage multipiste augmenté IA.")
    parser.add_argument("stems_dir", help="Dossier contenant les stems (un fichier par piste)")
    parser.add_argument("-o", "--output", default="mix.wav", help="Fichier de sortie")
    parser.add_argument("-i", "--intent", default="", help="Intention en langage naturel")
    parser.add_argument("-t", "--target-lufs", type=float, default=-14.0, help="Loudness cible")
    parser.add_argument("--offline", action="store_true", help="Décision par règles, sans clé API")
    args = parser.parse_args()

    stem_paths = stems_from_dir(args.stems_dir)
    if not stem_paths:
        raise SystemExit(f"Aucun stem trouvé dans {args.stems_dir}")

    result = mix(stem_paths, args.output, args.intent, args.target_lufs,
                 offline=args.offline or None)

    print(f"\n=== PISTES ({len(result.before)}) ===")
    for name, p in result.before.items():
        print(f"  {name:<10} {p.integrated_lufs} LUFS")
    print(f"\n=== DÉCISION DE MIX : {result.decision.summary} ===")
    for s in result.decision.stems:
        print(f"  {s.name:<10} gain {s.gain_db:+.1f} dB · pan {s.pan:+.2f} · "
              f"{len(s.chain)} traitement(s)")
    print(f"\n=== MIX FINAL ===")
    print(f"  {result.after.integrated_lufs} LUFS · true-peak {result.after.true_peak_dbtp} dBTP")
    print(f"\n→ Écrit dans {result.output_path}\n")
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
