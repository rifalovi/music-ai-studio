"""Couche 2 — DÉCISION (Claude / Anthropic).

L'ingénieur du son-conseil. Reçoit un `AudioProfile` chiffré + l'intention
de l'utilisateur en langage naturel, et renvoie un `ProcessingChain` validé.

Point clé : Claude ne traite pas le signal. Il raisonne sur des mesures et
produit une décision structurée que la couche DSP exécutera. On utilise les
sorties structurées de l'API (client.messages.parse) pour garantir que la
réponse est un ProcessingChain valide, jamais du texte libre.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from schema import AudioProfile, EQBand, Processor, ProcessingChain

if TYPE_CHECKING:  # évite d'exiger le paquet `anthropic` en mode hors-ligne
    import anthropic

# Modèle par défaut : le plus capable. Surchargeable pour ajuster coût/latence.
MODEL = os.environ.get("AI_MODEL", "claude-opus-5")

SYSTEM_PROMPT = """\
Tu es un ingénieur du son de mastering et de mixage de niveau professionnel.

On te fournit le PROFIL MESURÉ d'un morceau (loudness, dynamique, équilibre
spectral par bandes, image stéréo, tempo) et l'INTENTION de l'artiste en langage
naturel. Tu ne peux pas écouter l'audio : tu raisonnes uniquement sur ces mesures.

Ta tâche : proposer une chaîne de traitement précise et sobre qui rapproche le
morceau de l'intention et de la cible de loudness, sans le dénaturer.

Règles de métier :
- Corrige d'abord les problèmes que les mesures révèlent (déséquilibre tonal,
  dynamique excessive ou écrasée, crêtes, corrélation de phase négative) avant
  d'ajouter du caractère.
- Chaque maillon doit citer, dans son `reason`, la mesure qui le motive
  (ex. « low_mid à +4 dB : on dégage 250 Hz »).
- Reste conservateur : préfère quelques gestes justes à une longue chaîne.
- Termine toujours par un limiter pour tenir la cible true-peak.
- L'ordre de la chaîne compte : EQ correctif → compression → saturation →
  EQ de finition → limiter.
- Ne mets dans la chaîne que des traitements réellement listés dans le schéma.
"""


def _profile_message(profile: AudioProfile, intent: str, target_lufs: float) -> str:
    return (
        "PROFIL MESURÉ (JSON) :\n"
        f"{profile.model_dump_json(indent=2)}\n\n"
        f"INTENTION DE L'ARTISTE : {intent or 'Master propre, prêt pour le streaming.'}\n"
        f"CIBLE DE LOUDNESS : {target_lufs} LUFS\n\n"
        "Propose la chaîne de traitement."
    )


def propose_chain(
    profile: AudioProfile,
    intent: str = "",
    target_lufs: float = -14.0,
    client: "anthropic.Anthropic | None" = None,
) -> ProcessingChain:
    """profil + intention -> ProcessingChain validé (sorties structurées, via Claude)."""
    import anthropic  # import paresseux : requis seulement en mode en ligne

    client = client or anthropic.Anthropic()

    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": _profile_message(profile, intent, target_lufs)}
        ],
        output_format=ProcessingChain,
    )

    chain = response.parsed_output
    if chain is None:
        raise RuntimeError("Claude n'a pas renvoyé de chaîne exploitable.")
    # On force la cible demandée : l'utilisateur décide du loudness final.
    chain.target_lufs = target_lufs
    return chain


# --------------------------------------------------------------------------- #
#  Décision HORS-LIGNE (par règles) — baseline déterministe, sans clé API.
#
#  Ce n'est pas l'ingénieur IA : c'est un garde-fou raisonnable qui permet de
#  faire tourner le loop sans réseau, et de servir de point de comparaison A/B
#  face aux décisions de Claude.
# --------------------------------------------------------------------------- #

def propose_chain_offline(
    profile: AudioProfile,
    intent: str = "",
    target_lufs: float = -14.0,
) -> ProcessingChain:
    """profil -> ProcessingChain sûr, sans appel réseau."""
    chain: list[Processor] = []

    # 1. Nettoyage du sub-sonique : un passe-haut doux libère du headroom.
    chain.append(
        Processor(
            type="eq",
            reason="Passe-haut à 30 Hz : retire le sub-sonique inutile et gagne du headroom.",
            bands=[EQBand(filter_type="high_pass", freq_hz=30.0)],
        )
    )

    # 2. Correction tonale légère si le bas-médium domine la région médium.
    balance = profile.spectral_balance
    if balance.get("low_mid", -99) > balance.get("mid", -99) + 3:
        chain.append(
            Processor(
                type="eq",
                reason=(
                    f"low_mid ({balance['low_mid']} dB) domine mid ({balance['mid']} dB) : "
                    "léger creux à 250 Hz pour dégager la boue."
                ),
                bands=[EQBand(filter_type="peak", freq_hz=250.0, gain_db=-2.5, q=1.0)],
            )
        )

    # 3. Compression seulement si la dynamique est large (crest factor élevé).
    if profile.crest_factor_db > 16:
        chain.append(
            Processor(
                type="compressor",
                reason=(
                    f"Crest factor {profile.crest_factor_db} dB (large) : compression douce "
                    "2:1 pour resserrer sans écraser."
                ),
                threshold_db=round(profile.rms_dbfs + 2, 1),
                ratio=2.0,
                attack_ms=20.0,
                release_ms=150.0,
                makeup_db=0.0,
            )
        )

    # 4. Un peu d'air si la bande haute est la plus faible (manque de brillance).
    if balance.get("air", 0) == min(balance.values()):
        chain.append(
            Processor(
                type="eq",
                reason="La bande 'air' est la plus faible : high-shelf +1.5 dB à 10 kHz.",
                bands=[EQBand(filter_type="high_shelf", freq_hz=10000.0, gain_db=1.5, q=0.7)],
            )
        )

    # 5. Limiter final : tient la cible true-peak. Toujours présent.
    chain.append(
        Processor(
            type="limiter",
            reason=f"Limiter à {target_lufs + 12:.0f} dB pour tenir le true-peak et la loudness cible.",
            threshold_db=-1.0,
            release_ms=100.0,
        )
    )

    return ProcessingChain(
        summary="Master de base (mode hors-ligne, sans IA) : nettoyage, équilibre, loudness.",
        target_lufs=target_lufs,
        target_true_peak_db=-1.0,
        chain=chain,
    )


if __name__ == "__main__":
    import json
    import sys

    from analysis import analyze

    args = [a for a in sys.argv[1:] if a != "--offline"]
    offline = "--offline" in sys.argv or not os.environ.get("ANTHROPIC_API_KEY")
    if not args:
        raise SystemExit('usage: python ai_engineer.py [--offline] <fichier> ["intention"]')

    prof = analyze(args[0])
    intent = args[1] if len(args) > 1 else ""
    result = (
        propose_chain_offline(prof, intent) if offline else propose_chain(prof, intent)
    )
    mode = "HORS-LIGNE (règles)" if offline else f"CLAUDE ({MODEL})"
    print(f"# Décision — {mode}")
    print(json.dumps(result.model_dump(exclude_none=True), indent=2, ensure_ascii=False))
