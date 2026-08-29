# Console de mixage augmentée IA — POC (Phase 0)

Preuve de concept d'un outil de **mastering / mixage assisté par Claude**.
L'objectif de cette phase est de valider **une seule chose** : la boucle complète

```
analyser  →  Claude décide  →  DSP applique  →  ré-analyser (conformité)
```

tourne proprement sur un morceau réel. Si cette boucle tient, tout le reste est
de l'ingénierie.

## Le postulat

**Claude ne traite pas le signal.** Un modèle de langage ne touche jamais à la
forme d'onde : pas d'EQ, pas de compression, pas d'écoute. Son rôle ici est celui
d'un **ingénieur du son-conseil** : il lit un profil *chiffré* du morceau, raisonne,
et produit une **chaîne de traitement structurée** que le moteur DSP exécute.

## Architecture (3 couches)

| Couche | Fichier | Rôle | Touche le son ? |
|---|---|---|---|
| **Mesure** | `engine/analysis.py` | audio → `AudioProfile` (LUFS, dynamique, équilibre spectral, stéréo, tempo) | lecture seule |
| **Décision** | `engine/ai_engineer.py` | `AudioProfile` + intention → `ProcessingChain` (via Claude, sorties structurées) | non |
| **Exécution** | `engine/dsp.py` | applique le `ProcessingChain` avec `pedalboard`, normalise, plafonne | **oui** |

Le contrat entre les couches est défini dans `engine/schema.py`. Claude n'émet
jamais d'audio — il émet un `ProcessingChain`, objet déterministe et rejouable.

## Installation

```bash
cd music-ai-studio/engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # puis renseigner ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)
```

> `pedalboard` fournit le moteur DSP. Aucun `ffmpeg` requis pour le WAV ;
> pour lire du MP3, installez `ffmpeg` sur le système (ou convertissez en WAV).

## Utilisation

### Le loop complet en une commande (CLI)

```bash
python pipeline.py ../samples/Morceau_choix.mp3 \
  -o master.wav \
  -i "voix plus présente, plus chaud, prêt pour le streaming" \
  -t -14
```

Affiche le profil **avant**, la **décision** (chaîne + justifications), le profil
**après**, et écrit `master.wav`.

### Mode hors-ligne (sans clé API)

La couche décision a deux moteurs :

- **Claude** (par défaut si `ANTHROPIC_API_KEY` est définie) — l'ingénieur du son IA.
- **Règles** (`--offline`, ou automatique si aucune clé) — une baseline déterministe
  qui nettoie, équilibre et amène à la loudness cible sans réseau. Sert aussi de
  point de comparaison A/B face aux décisions de Claude.

```bash
python pipeline.py entree.wav -o master.wav --offline
```

### Étapes séparées

```bash
python analysis.py    ../samples/Morceau_choix.mp3     # profil chiffré seul
python ai_engineer.py --offline ../samples/Morceau_choix.mp3 "plus chaud"   # décision seule
```

### Via l'API + l'UI web (valide la direction « application web »)

```bash
uvicorn server:app --reload --port 8000     # depuis engine/
```

Puis ouvrez `web/index.html` (double-clic, ou servez-le) : upload d'un fichier,
intention en langage naturel, cible de loudness → avant / décision / après +
lecteur du résultat.

## Mixage multipiste (Phase 2)

Le mastering ci-dessus traite un master 2-pistes. Le **mixage** travaille piste
par piste : Claude raisonne sur les profils de **toutes les pistes à la fois** et
produit, pour chacune, un gain de balance, un panoramique et une chaîne de
traitement, plus un bus master.

| Couche | Fichier | Rôle |
|---|---|---|
| Séparation *(optionnelle)* | `engine/separation.py` | mixdown → stems via Demucs (si tu n'as pas les pistes) |
| Décision | `engine/mix_engineer.py` | profils des pistes → `MixDecision` (Claude ou règles) |
| Exécution | `engine/mixing.py` | traitement + gain + pan par piste → sommation → bus |
| Orchestration | `engine/mix_pipeline.py` | loop complet + CLI |

```bash
# À partir d'un dossier de stems (un fichier par piste : vocals.wav, drums.wav, …)
python mix_pipeline.py ./mes_stems -o mix.wav -i "voix devant, mix large" -t -14

# Sans clé API (balance + nettoyage déterministes)
python mix_pipeline.py ./mes_stems -o mix.wav --offline
```

> Pas de stems ? `pip install demucs` puis sépare le mixdown via `separation.py`.
> Demucs (PyTorch) est une dépendance **optionnelle**, lourde, non requise pour
> mixer des stems déjà fournis.

## Production : édition, tempo, génération (Phase 3)

Vers une vraie DAW augmentée : les briques de **montage**, de **tempo** et de
**génération** d'instrumentale.

| Fonction | Fichier | Rôle |
|---|---|---|
| Édition | `engine/timeline.py` | `Timeline` : couper, coller, insérer, supprimer une région, superposer, fondus, concaténer (montage non destructif) |
| Tempo | `engine/tempo.py` | détection de BPM, time-stretch (durée sans changer la hauteur), calage d'un extrait sur un tempo cible |
| Génération | `engine/generation.py` | Claude rédige un `GenerationBrief` ; un `MusicGenerator` branché réalise l'audio |

```python
from timeline import Timeline
tl = Timeline.from_file("voix.wav")
tl = tl.delete_range(12.0, 16.0)          # couper un passage
tl = tl.insert(4.0, Timeline.from_file("refrain.wav"))  # coller
tl = tl.overlay(0.0, Timeline.from_file("nappe.wav"), gain_db=-6)  # ajouter une couche
tl.write("montage.wav")
```

### ⚠️ La génération d'audio nécessite un modèle externe

**Claude ne génère pas de musique** — il rédige le brief (instrument, style,
tonalité, tempo, prompt). L'audio est produit par un **modèle de génération
musicale dédié**, branché via l'interface `MusicGenerator` :

- `PlaceholderGenerator` — bouche-trou **synthétique** (pas de la vraie musique),
  fourni pour exécuter et tester l'arrangement sans modèle externe.
- `MusicGenGenerator` — adaptateur d'exemple pour MusicGen/AudioCraft (`pip install
  audiocraft`). D'autres cibles possibles : Stable Audio, Suno/Udio (via API).

> **Décision produit à trancher** : quel modèle de génération (coût, licence,
> droits commerciaux d'usage des instrumentales générées) ?

## Ce que ce POC prouve — et ne prouve pas

- ✅ Mastering, mixage multipiste, **montage** (couper/coller), **tempo**
  (time-stretch) et **arrangement** (brief → placement) **tournent de bout en
  bout** (vérifié par les tests).
- ✅ Claude produit chaîne de mix / brief de génération à partir des seules mesures / intentions.
- ⚠️ **Claude ne génère pas d'audio** : la génération d'instrumentale passe par un modèle externe.
- ⚠️ Le jugement final reste **à l'oreille** : prévoir un A/B à l'aveugle.
- ⚠️ Qualité source : travailler en **WAV / sans perte**.
- ⚠️ Pas de temps réel via l'IA : la décision est ponctuelle, le DSP fait le reste.

## Tests

```bash
python tests/test_loop.py         # mastering (2-pistes)
python tests/test_mix.py          # mixage multipiste
python tests/test_timeline.py     # montage (couper/coller/superposer)
python tests/test_tempo.py        # tempo (time-stretch, BPM)
python tests/test_arrangement.py  # brief → génération placeholder → placement
# ou : pytest tests/
```

## Prochaines phases

1. **MVP web** — UI intégrée à une vraie app (Next.js) : timeline visuelle,
   édition, mix, écoute A/B, export.
2. **Génération réelle** — brancher un modèle de génération (décision produit).
3. **Assistant conversationnel** — dialoguer avec le projet (« voix plus devant »,
   « ajoute un pont de 8 mesures »).
