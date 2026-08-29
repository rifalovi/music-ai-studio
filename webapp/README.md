# Studio web — app Next.js + Supabase (multi-utilisateurs)

L'interface hébergée du studio : comptes, projets sauvegardés, éditeur DAW dans
le navigateur, et mastering IA branché sur le moteur Python.

## Pile

- **Next.js 14** (App Router) — front + API légère.
- **Supabase** — auth (lien magique), base Postgres (projets, pistes), stockage
  audio privé (bucket `audio`), le tout protégé par RLS par utilisateur.
- **Moteur audio Python** (`../engine`) — worker séparé appelé en HTTP pour le
  mastering/mix IA (les libs audio ne tournent pas sur du serverless).

## Mise en route

1. **Créer un projet Supabase DÉDIÉ** (ne pas réutiliser un projet existant).
2. Appliquer le schéma : `supabase/migrations/0001_init.sql`
   (via l'éditeur SQL Supabase, ou `supabase db push`).
3. Copier les clés :
   ```bash
   cp .env.example .env.local
   # NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
   # NEXT_PUBLIC_ENGINE_URL=http://localhost:8000   (worker Python, optionnel)
   ```
4. Lancer :
   ```bash
   npm install
   npm run dev            # http://localhost:3000
   ```

## Ce qui marche

- Connexion par lien magique ; routes `/dashboard` et `/project/*` protégées.
- Création de projets ; chaque utilisateur ne voit que les siens (RLS).
- Éditeur : import audio → **stockage privé** + ligne `tracks`, forme d'onde,
  sélection, couper/rogner/copier/coller/fondus, annuler/rétablir, lecture,
  **Enregistrer** (upload master), **Masteriser (IA)** (via le worker Python).

## Déploiement

- **Front** : Vercel (variables `NEXT_PUBLIC_*`).
- **Worker audio** : conteneur séparé (Fly.io / Render / Railway) exposant
  l'API FastAPI de `../engine` ; renseigner son URL dans `NEXT_PUBLIC_ENGINE_URL`.
- **Génération d'instrumentale** : voir `../engine` (Stable Audio recommandé).

## Vérification locale

```bash
npm run typecheck      # tsc --noEmit
npm run build
```
