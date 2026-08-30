"""Couche DÉCISION du mixage multipiste.

Deux moteurs, comme pour le mastering :
  - `propose_mix`         : Claude, l'ingénieur de mix (sorties structurées).
  - `propose_mix_offline` : baseline par règles, sans réseau (balance + nettoyage).

Claude raisonne sur les profils de TOUTES les pistes à la fois : c'est ce qui
distingue le mixage du mastering — équilibrer les pistes les unes par rapport
aux autres, pas traiter un master 2-pistes.
"""

from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING

from schema import AudioProfile, EQBand, MixDecision, Processor, StemDecision

if TYPE_CHECKING:
    import anthropic

MODEL = os.environ.get("AI_MODEL", "claude-opus-5")

SYSTEM_PROMPT = """\
Tu es un ingénieur de MIXAGE de niveau professionnel.

On te fournit le PROFIL MESURÉ de chaque piste (stem) d'un morceau — loudness,
dynamique, équilibre spectral, image stéréo — et l'INTENTION de l'artiste. Tu ne
peux pas écouter : tu raisonnes sur ces mesures.

Ta tâche : produire une décision de mix complète. Pour CHAQUE piste :
- un gain de balance (son niveau relatif dans le mix),
- un panoramique (-1 gauche, 0 centre, +1 droite),
- une chaîne de traitement propre à la piste.
Puis une chaîne de BUS master (glue + limiter) après sommation.

Règles de métier :
- Équilibre d'abord les niveaux entre pistes : voix intelligible au premier plan,
  basse et grosse caisse solidaires et centrées.
- Garde basse et voix lead au centre ; élargis les éléments d'accompagnement.
- Nettoie chaque piste (passe-haut sur ce qui n'a pas de grave utile) avant
  d'ajouter du caractère.
- Chaque `reason` cite la mesure qui le motive.
- Termine le bus par un limiter pour tenir la cible true-peak.
- N'utilise que les traitements listés dans le schéma.
"""


def _stems_message(profiles: dict[str, AudioProfile], intent: str, target_lufs: float) -> str:
    blocks = "\n".join(
        f"### Piste « {name} »\n{p.model_dump_json(indent=2)}" for name, p in profiles.items()
    )
    return (
        f"PROFILS DES PISTES ({len(profiles)}) :\n{blocks}\n\n"
        f"INTENTION DE L'ARTISTE : {intent or 'Mix équilibré, moderne, prêt pour le streaming.'}\n"
        f"CIBLE DE LOUDNESS DU MIX : {target_lufs} LUFS\n\n"
        "Propose la décision de mix complète."
    )


def propose_mix(
    profiles: dict[str, AudioProfile],
    intent: str = "",
    target_lufs: float = -14.0,
    client: "anthropic.Anthropic | None" = None,
) -> MixDecision:
    """profils des pistes + intention -> MixDecision validé (via Claude)."""
    import anthropic

    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=12000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _stems_message(profiles, intent, target_lufs)}],
        output_format=MixDecision,
    )
    decision = response.parsed_output
    if decision is None:
        raise RuntimeError("Claude n'a pas renvoyé de décision de mix exploitable.")
    decision.target_lufs = target_lufs
    return decision


# --------------------------------------------------------------------------- #
#  Baseline HORS-LIGNE (par règles)
# --------------------------------------------------------------------------- #

# Niveau cible par type de piste, en LUFS (référence de balance).
_STEM_TARGET_LUFS = {
    "vocals": -16.0,
    "vocal": -16.0,
    "voix": -16.0,
    "drums": -17.0,
    "batterie": -17.0,
    "bass": -18.0,
    "basse": -18.0,
    "other": -20.0,
    "autres": -20.0,
}
# Panoramique et passe-haut par défaut selon le type.
_STEM_PAN = {"other": 0.2, "autres": 0.2}
_STEM_HPF = {"vocals": 90.0, "voix": 90.0, "other": 100.0, "autres": 100.0, "drums": 40.0}


def _balance_gain(profile: AudioProfile, target: float) -> float:
    if not math.isfinite(profile.integrated_lufs):
        return 0.0
    return round(max(min(target - profile.integrated_lufs, 12.0), -24.0), 1)


def propose_mix_offline(
    profiles: dict[str, AudioProfile],
    intent: str = "",
    target_lufs: float = -14.0,
) -> MixDecision:
    """Décision de mix sûre, déterministe, sans appel réseau."""
    stems: list[StemDecision] = []
    for name, profile in profiles.items():
        key = name.lower()
        target = _STEM_TARGET_LUFS.get(key, -19.0)
        gain = _balance_gain(profile, target)
        pan = _STEM_PAN.get(key, 0.0)

        chain: list[Processor] = []
        hpf = _STEM_HPF.get(key)
        if hpf:
            chain.append(
                Processor(
                    type="eq",
                    reason=f"Passe-haut à {hpf:.0f} Hz : nettoie le grave inutile de « {name} ».",
                    bands=[EQBand(filter_type="high_pass", freq_hz=hpf)],
                )
            )

        stems.append(
            StemDecision(
                name=name,
                gain_db=gain,
                pan=pan,
                chain=chain,
            )
        )

    # Bus master : glue douce + limiter final.
    bus = [
        Processor(
            type="compressor",
            reason="Glue de bus : compression très douce 1.5:1 pour souder le mix.",
            threshold_db=-12.0,
            ratio=1.5,
            attack_ms=30.0,
            release_ms=200.0,
        ),
        Processor(
            type="limiter",
            reason="Limiter de bus : tient le true-peak et la loudness cible.",
            threshold_db=-1.0,
            release_ms=100.0,
        ),
    ]

    return MixDecision(
        summary="Mix de base (mode hors-ligne, sans IA) : balance des pistes, nettoyage, bus.",
        target_lufs=target_lufs,
        target_true_peak_db=-1.0,
        stems=stems,
        bus_chain=bus,
    )
