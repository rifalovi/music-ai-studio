"""Génération d'instrumentale — le SEAM entre Claude et un modèle de musique.

Rappel du postulat : **Claude ne génère pas d'audio.** Ici, Claude produit un
`GenerationBrief` (instrument, style, tonalité, tempo, longueur, prompt). Un
modèle de génération musicale DÉDIÉ réalise l'audio via l'interface
`MusicGenerator`. On fournit :

  - `propose_brief` / `propose_brief_offline` : Claude (ou règles) -> brief.
  - `MusicGenerator` : le contrat qu'un modèle branché doit remplir.
  - `PlaceholderGenerator` : un bouche-trou SYNTHÉTIQUE (pas de la vraie musique)
    pour faire tourner l'arrangement de bout en bout sans modèle externe.

Brancher un vrai modèle (MusicGen/AudioCraft, Stable Audio, Suno/Udio via API)
est une décision produit (coût, licence, droits commerciaux) : voir le README.
"""

from __future__ import annotations

import os
from typing import Protocol

import numpy as np

from schema import GenerationBrief

_EPS = 1e-9
_BEATS_PER_BAR = 4  # 4/4 par défaut


def brief_duration_s(brief: GenerationBrief) -> float:
    return brief.bars * _BEATS_PER_BAR * (60.0 / max(brief.bpm, 1.0))


# --------------------------------------------------------------------------- #
#  Le contrat de génération
# --------------------------------------------------------------------------- #

class MusicGenerator(Protocol):
    """Tout modèle de génération branché doit implémenter ceci."""

    def generate(self, brief: GenerationBrief, sr: int = 44100) -> np.ndarray:
        """Renvoie un buffer (canaux, N) réalisant le brief."""
        ...


class PlaceholderGenerator:
    """Bouche-trou SYNTHÉTIQUE — PAS de la vraie musique.

    Rend un accord soutenu à la tonalité/longueur demandées, uniquement pour que
    la chaîne d'arrangement (placer, caler, mixer) soit exécutable et testable
    sans modèle externe. À remplacer par un vrai `MusicGenerator`.
    """

    _NOTE_HZ = {  # fréquence de la fondamentale par tonique (octave médium)
        "C": 261.63, "C#": 277.18, "D": 293.66, "D#": 311.13, "E": 329.63,
        "F": 349.23, "F#": 369.99, "G": 392.00, "G#": 415.30, "A": 440.00,
        "A#": 466.16, "B": 493.88,
    }

    def generate(self, brief: GenerationBrief, sr: int = 44100) -> np.ndarray:
        root_name = "".join(c for c in brief.key if c in "ABCDEFG#") or "C"
        root_name = root_name[:2] if len(root_name) > 1 and root_name[1] == "#" else root_name[:1]
        f0 = self._NOTE_HZ.get(root_name, 261.63)

        n = int(round(brief_duration_s(brief) * sr))
        t = np.arange(n) / sr
        minor = "m" in brief.key.lower().replace("maj", "")
        third = f0 * (2 ** (3 / 12)) if minor else f0 * (2 ** (4 / 12))
        fifth = f0 * (2 ** (7 / 12))
        chord = (
            0.4 * np.sin(2 * np.pi * f0 * t)
            + 0.3 * np.sin(2 * np.pi * third * t)
            + 0.3 * np.sin(2 * np.pi * fifth * t)
        )
        env = np.minimum(1.0, np.minimum(t / 0.05, (t[-1] - t + _EPS) / 0.2)) if n else chord
        mono = (chord * env * 0.2).astype(np.float32)
        return np.vstack([mono, mono])


# --------------------------------------------------------------------------- #
#  Adaptateur pour un vrai modèle (exemple : MusicGen / AudioCraft)
# --------------------------------------------------------------------------- #

class MusicGenGenerator:
    """Adaptateur MusicGen (Meta AudioCraft). Dépendance lourde, optionnelle.

        pip install audiocraft

    Non exécuté par défaut : sert de patron pour brancher un vrai modèle.
    """

    def __init__(self, model_name: str = "facebook/musicgen-small") -> None:
        from audiocraft.models import MusicGen  # import paresseux

        self.model = MusicGen.get_pretrained(model_name)

    def generate(self, brief: GenerationBrief, sr: int = 44100) -> np.ndarray:
        self.model.set_generation_params(duration=brief_duration_s(brief))
        prompt = (
            f"{brief.style} {brief.instrument}, key {brief.key}, {brief.bpm:.0f} BPM. "
            f"{brief.description}"
        )
        wav = self.model.generate([prompt])[0].cpu().numpy()  # (canaux, N) au sr du modèle
        model_sr = int(self.model.sample_rate)
        if model_sr != sr:  # rééchantillonnage simple vers le sr cible
            import numpy as _np

            ratio = sr / model_sr
            idx = _np.clip((_np.arange(int(wav.shape[1] * ratio)) / ratio), 0, wav.shape[1] - 1)
            wav = _np.stack([_np.interp(idx, _np.arange(wav.shape[1]), ch) for ch in wav])
        return wav.astype(np.float32)


class StableAudioGenerator:
    """Adaptateur Stable Audio (Stability AI), via API — RECOMMANDÉ pour un SaaS.

    Pas d'infra GPU à opérer, licence commerciale claire sur l'audio généré.
    Nécessite la variable d'environnement STABILITY_API_KEY.

        adapter = StableAudioGenerator()
        audio = adapter.generate(brief, sr=44100)

    L'appel HTTP réel est laissé volontairement minimal (endpoint à confirmer
    dans la doc Stability au moment de l'intégration) : c'est le point de
    branchement, pas encore le câblage final.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("STABILITY_API_KEY")
        if not self.api_key:
            raise RuntimeError("STABILITY_API_KEY manquante pour Stable Audio.")

    def generate(self, brief: GenerationBrief, sr: int = 44100) -> np.ndarray:
        import io

        import requests  # dépendance légère, à ajouter aux requirements si activé
        import soundfile as sf

        prompt = (
            f"{brief.style} {brief.instrument}, key {brief.key}, {brief.bpm:.0f} BPM. "
            f"{brief.description}"
        )
        resp = requests.post(
            "https://api.stability.ai/v2beta/audio/generations",
            headers={"authorization": f"Bearer {self.api_key}", "accept": "audio/*"},
            files={"none": ""},
            data={"prompt": prompt, "duration": int(brief_duration_s(brief))},
            timeout=120,
        )
        resp.raise_for_status()
        audio, model_sr = sf.read(io.BytesIO(resp.content), always_2d=True, dtype="float32")
        wav = audio.T
        if model_sr != sr:  # rééchantillonnage simple
            ratio = sr / model_sr
            idx = np.clip(np.arange(int(wav.shape[1] * ratio)) / ratio, 0, wav.shape[1] - 1)
            wav = np.stack([np.interp(idx, np.arange(wav.shape[1]), ch) for ch in wav])
        return wav.astype(np.float32)


# --------------------------------------------------------------------------- #
#  Le BRIEF : produit par Claude (le cerveau), pas par un modèle audio
# --------------------------------------------------------------------------- #

MODEL = os.environ.get("AI_MODEL", "claude-opus-5")

_BRIEF_SYSTEM = """\
Tu es directeur artistique et arrangeur. On te donne le contexte d'un morceau
(tempo, tonalité) et une intention. Produis un brief de génération pour UNE
instrumentale à ajouter : instrument, style, tonalité et tempo cohérents avec le
morceau, longueur en mesures, et un prompt riche destiné à un modèle de
génération musicale. Tu ne génères pas l'audio — tu rédiges le cahier des charges.
"""


def propose_brief(
    intent: str,
    bpm: float = 120.0,
    key: str = "C",
    client=None,
) -> GenerationBrief:
    """Intention + contexte -> GenerationBrief (via Claude, sorties structurées)."""
    import anthropic

    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=_BRIEF_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"CONTEXTE : {bpm:.0f} BPM, tonalité {key}.\n"
                f"INTENTION : {intent or 'une nappe discrète pour épaissir le fond'}.\n"
                "Rédige le brief."
            ),
        }],
        output_format=GenerationBrief,
    )
    brief = response.parsed_output
    if brief is None:
        raise RuntimeError("Claude n'a pas renvoyé de brief exploitable.")
    return brief


def propose_brief_offline(intent: str, bpm: float = 120.0, key: str = "C") -> GenerationBrief:
    """Brief par défaut, sans réseau."""
    return GenerationBrief(
        instrument="nappe de synthé",
        style="ambiant discret",
        key=key,
        bpm=bpm,
        bars=8,
        description=(
            f"Nappe douce et soutenue en {key}, {bpm:.0f} BPM, pour épaissir le fond "
            f"sans masquer la voix. Intention : {intent or 'accompagnement neutre'}."
        ),
    )
