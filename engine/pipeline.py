"""Orchestration du loop complet — le cœur du POC Phase 0.

    analyser  →  Claude décide  →  DSP applique  →  ré-analyser (conformité)

C'est le test qui prouve la viabilité du produit : si cette boucle tourne
proprement sur un morceau, tout le reste est de l'ingénierie.
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis import analyze
from ai_engineer import propose_chain
from dsp import apply_chain
from schema import AudioProfile, ProcessingChain


@dataclass
class MasterResult:
    before: AudioProfile
    chain: ProcessingChain
    after: AudioProfile
    output_path: str

    def to_dict(self) -> dict:
        return {
            "before": self.before.model_dump(),
            "chain": self.chain.model_dump(exclude_none=True),
            "after": self.after.model_dump(),
            "output_path": self.output_path,
        }


def master(
    input_path: str,
    output_path: str,
    intent: str = "",
    target_lufs: float = -14.0,
) -> MasterResult:
    """Exécute le loop complet et renvoie le avant / la décision / l'après."""
    before = analyze(input_path)                      # 1. mesure
    chain = propose_chain(before, intent, target_lufs)  # 2. décision (Claude)
    apply_chain(input_path, chain, output_path)         # 3. exécution (DSP)
    after = analyze(output_path)                       # 4. contrôle de conformité
    return MasterResult(before=before, chain=chain, after=after, output_path=output_path)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="POC mastering augmenté IA — loop complet.")
    parser.add_argument("input", help="Fichier audio d'entrée (WAV de préférence)")
    parser.add_argument("-o", "--output", default="out.wav", help="Fichier de sortie")
    parser.add_argument("-i", "--intent", default="", help="Intention en langage naturel")
    parser.add_argument("-t", "--target-lufs", type=float, default=-14.0, help="Loudness cible")
    args = parser.parse_args()

    result = master(args.input, args.output, args.intent, args.target_lufs)

    print("\n=== AVANT ===")
    print(f"  {result.before.integrated_lufs} LUFS · dyn {result.before.loudness_range_lu} LU "
          f"· true-peak {result.before.true_peak_dbtp} dBTP")
    print(f"\n=== DÉCISION DE CLAUDE : {result.chain.summary} ===")
    for i, proc in enumerate(result.chain.chain, 1):
        print(f"  {i}. {proc.type:<11} — {proc.reason}")
    print("\n=== APRÈS ===")
    print(f"  {result.after.integrated_lufs} LUFS · dyn {result.after.loudness_range_lu} LU "
          f"· true-peak {result.after.true_peak_dbtp} dBTP")
    print(f"\n→ Écrit dans {result.output_path}")
    print("\n(JSON complet ci-dessous)\n")
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
