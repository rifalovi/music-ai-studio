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

Affiche le profil **avant**, la **décision de Claude** (chaîne + justifications),
le profil **après**, et écrit `master.wav`.

### Étapes séparées

```bash
python analysis.py    ../samples/Morceau_choix.mp3     # profil chiffré seul
python ai_engineer.py ../samples/Morceau_choix.mp3 "plus chaud"   # décision seule
```

### Via l'API + l'UI web (valide la direction « application web »)

```bash
uvicorn server:app --reload --port 8000     # depuis engine/
```

Puis ouvrez `web/index.html` (double-clic, ou servez-le) : upload d'un fichier,
intention en langage naturel, cible de loudness → avant / décision / après +
lecteur du résultat.

## Ce que ce POC prouve — et ne prouve pas

- ✅ La boucle mesure → décision IA structurée → rendu → contrôle est viable.
- ✅ Claude produit une chaîne cohérente à partir des seules mesures.
- ⚠️ Le jugement final reste **à l'oreille** : prévoir un A/B à l'aveugle.
- ⚠️ Qualité source : travailler en **WAV / sans perte** pour un vrai master.
- ⚠️ Pas de temps réel via l'IA : la décision est ponctuelle, le DSP fait le reste.

## Prochaines phases

1. **MVP mastering web** — l'UI de `web/` intégrée à une vraie app (Next.js),
   comparaison A/B, export normalisé.
2. **Mixage multipiste** — import de stems ou séparation de sources (Demucs),
   traitement par piste.
3. **Assistant conversationnel + reference matching**.
