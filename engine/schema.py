"""Contrat de données partagé entre les trois couches.

Ces modèles sont la frontière stricte du POC :

    analysis.py  -->  AudioProfile      (ce que le moteur MESURE)
    ai_engineer  -->  ProcessingChain   (ce que Claude DÉCIDE)
    dsp.py       consomme ProcessingChain (ce que le moteur EXÉCUTE)

Claude n'émet jamais d'audio : il émet un ProcessingChain, un objet
déterministe que le moteur DSP sait rejouer à l'identique. Tous les
traitements listés ici sont réellement rendus par pedalboard — on ne
met pas dans le schéma ce que le moteur ne sait pas appliquer.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
#  Profil mesuré (sortie de la couche d'analyse)
# --------------------------------------------------------------------------- #

# Bandes spectrales exprimées en dB relatifs à l'énergie large bande.
# Sept bandes suffisent à décrire un équilibre tonal pour une décision de mix.
SpectralBand = Literal[
    "sub",       # 20–60 Hz
    "low",       # 60–150 Hz
    "low_mid",   # 150–500 Hz
    "mid",       # 500–2000 Hz
    "high_mid",  # 2–5 kHz
    "high",      # 5–10 kHz
    "air",       # 10–20 kHz
]


class AudioProfile(BaseModel):
    """Description chiffrée d'un morceau — le seul langage que Claude « entend »."""

    duration_s: float
    sample_rate: int
    channels: int

    # Loudness / dynamique
    integrated_lufs: float = Field(..., description="Loudness intégré (norme EBU R128)")
    loudness_range_lu: float = Field(..., description="Plage de loudness (LRA)")
    true_peak_dbtp: float = Field(..., description="Vrai crête estimé, dBTP")
    peak_dbfs: float
    rms_dbfs: float
    crest_factor_db: float = Field(..., description="peak - rms : marqueur de dynamique")
    clipping_detected: bool

    # Équilibre tonal : bande -> niveau relatif en dB
    spectral_balance: Dict[SpectralBand, float]
    spectral_centroid_hz: float

    # Image stéréo
    stereo_width: float = Field(..., description="0 = mono, 1 = large ; 0 si source mono")
    phase_correlation: float = Field(..., description="-1..1 ; <0 = risque de mono")

    # Rythme
    tempo_bpm: float


# --------------------------------------------------------------------------- #
#  Chaîne de traitement (sortie de Claude, entrée du DSP)
# --------------------------------------------------------------------------- #

class EQBand(BaseModel):
    filter_type: Literal["peak", "low_shelf", "high_shelf", "high_pass", "low_pass"]
    freq_hz: float
    gain_db: Optional[float] = Field(
        None, description="Requis pour peak/shelf ; ignoré pour les filtres passe-*"
    )
    q: Optional[float] = Field(None, description="Facteur de qualité ; défaut 0.7")


class Processor(BaseModel):
    """Un maillon de la chaîne. Les champs non pertinents pour `type` restent nuls."""

    type: Literal["eq", "compressor", "saturation", "reverb", "limiter", "gain"]
    reason: str = Field(..., description="Justification courte, ancrée sur une mesure du profil")

    # eq
    bands: Optional[List[EQBand]] = None

    # compressor / limiter
    threshold_db: Optional[float] = None
    ratio: Optional[float] = None
    attack_ms: Optional[float] = None
    release_ms: Optional[float] = None
    makeup_db: Optional[float] = None

    # saturation
    drive_db: Optional[float] = None

    # reverb
    room_size: Optional[float] = None
    wet_level: Optional[float] = None
    dry_level: Optional[float] = None

    # gain
    gain_db: Optional[float] = None


class ProcessingChain(BaseModel):
    """Décision complète de l'ingénieur du son IA pour ce morceau."""

    summary: str = Field(..., description="Résumé en une phrase de l'intention du traitement")
    target_lufs: float = Field(-14.0, description="Loudness cible (streaming = -14)")
    target_true_peak_db: float = Field(-1.0, description="Plafond true-peak, dBTP")
    chain: List[Processor]
