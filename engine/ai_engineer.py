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

import anthropic

from schema import AudioProfile, ProcessingChain

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
    client: anthropic.Anthropic | None = None,
) -> ProcessingChain:
    """profil + intention -> ProcessingChain validé (sorties structurées)."""
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


if __name__ == "__main__":
    import json
    import sys

    from analysis import analyze

    if len(sys.argv) < 2:
        raise SystemExit('usage: python ai_engineer.py <fichier> ["intention"]')
    prof = analyze(sys.argv[1])
    intent = sys.argv[2] if len(sys.argv) > 2 else ""
    result = propose_chain(prof, intent)
    print(json.dumps(result.model_dump(exclude_none=True), indent=2, ensure_ascii=False))
