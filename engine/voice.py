"""« Voix » — synthèse vocale (TTS) réaliste.

Comme chez Mureka : produire de la parole à partir d'un texte. Claude rédige /
nettoie le script ; un modèle TTS dédié synthétise l'audio via `SpeechSynthesizer`.

Claude ne synthétise pas de voix — il écrit le texte. Le TTS est un service
externe (ElevenLabs recommandé pour la qualité, ou un modèle open-source).
"""

from __future__ import annotations

import os
from typing import Protocol

import numpy as np


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, sr: int = 44100) -> np.ndarray:
        """Renvoie un buffer (canaux, N) parlant le texte."""
        ...


class ElevenLabsVoice:
    """Adaptateur ElevenLabs (API). Nécessite ELEVENLABS_API_KEY.

    Point de branchement ; l'endpoint/paramètres exacts sont à confirmer dans la
    doc ElevenLabs au moment de l'intégration.
    """

    def __init__(self, voice_id: str = "Rachel", api_key: str | None = None) -> None:
        self.voice_id = voice_id
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY manquante pour la synthèse vocale.")

    def synthesize(self, text: str, sr: int = 44100) -> np.ndarray:
        import io

        import requests
        import soundfile as sf

        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            headers={"xi-api-key": self.api_key, "accept": "audio/mpeg"},
            json={"text": text, "model_id": "eleven_multilingual_v2"},
            timeout=120,
        )
        resp.raise_for_status()
        audio, model_sr = sf.read(io.BytesIO(resp.content), always_2d=True, dtype="float32")
        wav = audio.T
        if model_sr != sr:
            ratio = sr / model_sr
            idx = np.clip(np.arange(int(wav.shape[1] * ratio)) / ratio, 0, wav.shape[1] - 1)
            wav = np.stack([np.interp(idx, np.arange(wav.shape[1]), ch) for ch in wav])
        return wav.astype(np.float32)


MODEL = os.environ.get("AI_MODEL", "claude-opus-5")


def propose_script(intent: str, client=None) -> str:
    """Claude rédige un script parlé propre à partir d'une intention (texte)."""
    import anthropic

    client = client or anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=(
            "Tu es scénariste audio. Rédige un script PARLÉ, naturel et prêt à être "
            "lu par une voix de synthèse : phrases courtes, ponctuation claire, sans "
            "didascalies ni mise en forme. Renvoie uniquement le texte à dire."
        ),
        messages=[{"role": "user", "content": intent}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()
