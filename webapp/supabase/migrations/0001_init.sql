-- Schéma initial du studio : projets, pistes, stockage audio — avec RLS par utilisateur.
-- Chaque utilisateur ne voit et ne modifie QUE ses propres projets/pistes/fichiers.

create extension if not exists "pgcrypto";

-- ------------------------------------------------------------------ projets
create table if not exists public.projects (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  name       text not null default 'Nouveau projet',
  bpm        numeric,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ------------------------------------------------------------------ pistes
create table if not exists public.tracks (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references public.projects(id) on delete cascade,
  name         text not null default 'piste',
  kind         text not null default 'audio',   -- audio | stem | master | generated
  storage_path text,                            -- chemin dans le bucket 'audio'
  created_at   timestamptz not null default now()
);

create index if not exists tracks_project_idx on public.tracks(project_id);

-- ------------------------------------------------------------------ RLS
alter table public.projects enable row level security;
alter table public.tracks   enable row level security;

create policy "projects_select_own" on public.projects for select using (auth.uid() = user_id);
create policy "projects_insert_own" on public.projects for insert with check (auth.uid() = user_id);
create policy "projects_update_own" on public.projects for update using (auth.uid() = user_id);
create policy "projects_delete_own" on public.projects for delete using (auth.uid() = user_id);

create policy "tracks_select_own" on public.tracks for select
  using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));
create policy "tracks_insert_own" on public.tracks for insert
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));
create policy "tracks_update_own" on public.tracks for update
  using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));
create policy "tracks_delete_own" on public.tracks for delete
  using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));

-- ------------------------------------------------------------------ stockage
insert into storage.buckets (id, name, public)
  values ('audio', 'audio', false)
  on conflict (id) do nothing;

-- Chaque utilisateur gère les fichiers rangés sous un dossier nommé par son uid.
create policy "audio_read_own" on storage.objects for select
  using (bucket_id = 'audio' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "audio_insert_own" on storage.objects for insert
  with check (bucket_id = 'audio' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "audio_update_own" on storage.objects for update
  using (bucket_id = 'audio' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "audio_delete_own" on storage.objects for delete
  using (bucket_id = 'audio' and (storage.foldername(name))[1] = auth.uid()::text);
