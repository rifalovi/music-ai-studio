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

## Ce que ce POC prouve — et ne prouve pas

- ✅ La boucle mastering **et** la boucle mixage multipiste **tournent de bout en
  bout et atteignent la loudness cible** (vérifié par `tests/test_loop.py` et
  `tests/test_mix.py`).
- ✅ Claude produit une chaîne / une décision de mix cohérente à partir des seules mesures.
- ⚠️ Le jugement final reste **à l'oreille** : prévoir un A/B à l'aveugle.
- ⚠️ Qualité source : travailler en **WAV / sans perte** pour un vrai master.
- ⚠️ Pas de temps réel via l'IA : la décision est ponctuelle, le DSP fait le reste.

## Tests

```bash
python tests/test_loop.py    # loop mastering (2-pistes)
python tests/test_mix.py     # loop mixage multipiste
# ou : pytest tests/
```

## Prochaines phases

1. **MVP web** — UI intégrée à une vraie app (Next.js), comparaison A/B, export.
2. **Assistant conversationnel** — dialoguer avec le mix (« voix plus devant »).
3. **Reference matching** — approcher le son d'un morceau de référence.
