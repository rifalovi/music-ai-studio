"""Moteur d'ÉDITION — la partie « couper / coller / arranger » de la DAW.

Une `Timeline` enveloppe un buffer audio (canaux, N) à un sample rate donné et
offre les opérations d'édition non destructives usuelles. Chaque opération
renvoie une NOUVELLE Timeline (immuable) — pratique pour l'undo/redo et pour
que Claude enchaîne des éditions de façon déterministe.

Toutes les positions sont en secondes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import soundfile as sf

_EPS = 1e-12


@dataclass(frozen=True)
class Timeline:
    audio: np.ndarray  # (canaux, N), float32
    sr: int

    # ---- construction / IO ------------------------------------------------- #

    @staticmethod
    def from_file(path: str) -> "Timeline":
        data, sr = sf.read(path, always_2d=True, dtype="float32")
        return Timeline(audio=data.T, sr=sr)

    @staticmethod
    def silence(seconds: float, sr: int, channels: int = 2) -> "Timeline":
        n = int(round(seconds * sr))
        return Timeline(audio=np.zeros((channels, n), dtype=np.float32), sr=sr)

    def write(self, path: str) -> str:
        sf.write(path, self.audio.T, self.sr)
        return path

    @property
    def duration_s(self) -> float:
        return self.audio.shape[1] / self.sr

    def _t(self, seconds: float) -> int:
        """Seconde -> index d'échantillon, borné au buffer."""
        return int(np.clip(round(seconds * self.sr), 0, self.audio.shape[1]))

    def _match_channels(self, other: np.ndarray) -> np.ndarray:
        """Adapte le nombre de canaux d'un buffer à celui de la timeline."""
        ch = self.audio.shape[0]
        if other.shape[0] == ch:
            return other
        if other.shape[0] == 1:
            return np.repeat(other, ch, axis=0)
        if other.shape[0] > ch:
            return other[:ch]
        return np.vstack([other, np.zeros((ch - other.shape[0], other.shape[1]), np.float32)])

    # ---- opérations d'édition --------------------------------------------- #

    def trim(self, start_s: float, end_s: float) -> "Timeline":
        """Garde uniquement [start, end] (rogner)."""
        a, b = sorted((self._t(start_s), self._t(end_s)))
        return Timeline(self.audio[:, a:b].copy(), self.sr)

    def split(self, at_s: float) -> tuple["Timeline", "Timeline"]:
        """Coupe la timeline en deux à `at_s` (coupure)."""
        i = self._t(at_s)
        return Timeline(self.audio[:, :i].copy(), self.sr), Timeline(self.audio[:, i:].copy(), self.sr)

    def delete_range(self, start_s: float, end_s: float) -> "Timeline":
        """Supprime la région [start, end] et recolle (couper au sens 'ôter')."""
        a, b = sorted((self._t(start_s), self._t(end_s)))
        kept = np.concatenate([self.audio[:, :a], self.audio[:, b:]], axis=1)
        return Timeline(kept, self.sr)

    def copy_range(self, start_s: float, end_s: float) -> "Timeline":
        """Renvoie la région [start, end] comme timeline (copier)."""
        return self.trim(start_s, end_s)

    def insert(self, at_s: float, clip: "Timeline") -> "Timeline":
        """Insère `clip` à la position `at_s`, en décalant la suite (coller)."""
        i = self._t(at_s)
        other = self._match_channels(clip.audio)
        out = np.concatenate([self.audio[:, :i], other, self.audio[:, i:]], axis=1)
        return Timeline(out, self.sr)

    def append(self, clip: "Timeline") -> "Timeline":
        """Ajoute `clip` à la fin."""
        return self.insert(self.duration_s, clip)

    def overlay(self, at_s: float, clip: "Timeline", gain_db: float = 0.0) -> "Timeline":
        """Superpose `clip` par-dessus, à `at_s` (ajouter une couche / de la musique)."""
        i = self._t(at_s)
        other = self._match_channels(clip.audio) * (10.0 ** (gain_db / 20.0))
        end = i + other.shape[1]
        out = self.audio.copy()
        if end > out.shape[1]:  # agrandit le buffer si la couche dépasse
            pad = np.zeros((out.shape[0], end - out.shape[1]), np.float32)
            out = np.concatenate([out, pad], axis=1)
        out[:, i:end] += other
        return Timeline(out, self.sr)

    def fade(self, fade_in_s: float = 0.0, fade_out_s: float = 0.0) -> "Timeline":
        """Applique un fondu d'entrée/sortie (évite les clics aux points de coupe)."""
        out = self.audio.copy()
        n = out.shape[1]
        fi = min(self._t(fade_in_s), n)
        fo = min(self._t(fade_out_s), n)
        if fi > 0:
            out[:, :fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
        if fo > 0:
            out[:, n - fo :] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)
        return Timeline(out, self.sr)


def concatenate(clips: list[Timeline]) -> Timeline:
    """Colle plusieurs timelines bout à bout (même sr requis)."""
    if not clips:
        raise ValueError("Aucun clip à concaténer.")
    sr = clips[0].sr
    for c in clips:
        if c.sr != sr:
            raise ValueError("Sample rate hétérogène entre les clips.")
    return Timeline(np.concatenate([c.audio for c in clips], axis=1), sr)
