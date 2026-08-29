"""« Partition » — transcription audio -> notation.

Comme chez Mureka : transformer une chanson en partition. La chaîne réaliste :

    audio  --(basic-pitch)-->  MIDI  --(music21 / MuseScore)-->  partition (MusicXML/PDF)

`basic-pitch` (Spotify) est une dépendance ML optionnelle :  pip install basic-pitch

Claude n'extrait pas les notes (c'est un modèle audio) mais peut ensuite
annoter/corriger la partition (accords, structure) à partir du MIDI.
"""

from __future__ import annotations

import os


def is_available() -> bool:
    try:
        import basic_pitch  # noqa: F401

        return True
    except Exception:
        return False


def transcribe_to_midi(audio_path: str, out_dir: str) -> str:
    """audio -> fichier MIDI. Nécessite basic-pitch installé."""
    if not is_available():
        raise RuntimeError(
            "basic-pitch n'est pas installé. `pip install basic-pitch` pour la "
            "transcription, ou fournis directement un MIDI."
        )
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict_and_save

    os.makedirs(out_dir, exist_ok=True)
    predict_and_save(
        [audio_path],
        out_dir,
        save_midi=True,
        sonify_midi=False,
        save_model_outputs=False,
        save_notes=False,
        model_or_model_path=ICASSP_2022_MODEL_PATH,
    )
    base = os.path.splitext(os.path.basename(audio_path))[0]
    midi = os.path.join(out_dir, f"{base}_basic_pitch.mid")
    if not os.path.isfile(midi):
        raise RuntimeError(f"MIDI non produit dans {out_dir}.")
    return midi


def midi_to_score(midi_path: str, out_path: str) -> str:
    """MIDI -> partition (MusicXML). Nécessite music21 :  pip install music21."""
    from music21 import converter

    score = converter.parse(midi_path)
    score.write("musicxml", fp=out_path)
    return out_path
