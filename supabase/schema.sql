-- Cape Monitor accounts: run once in the Supabase SQL editor (Dashboard > SQL Editor > New query > paste > Run).
-- Then add your own e-mail address as owner in Table Editor > owners > Insert row.

-- Owners: the addresses allowed to read the activity log. Each signed-in user can read only their own row, so the app
-- can tell whether to show the owner view; nobody can add rows except through the dashboard.
create table if not exists public.owners (email text primary key);
alter table public.owners enable row level security;
drop policy if exists "own row" on public.owners;
create policy "own row" on public.owners for select to authenticated using (email = auth.jwt() ->> 'email');

-- Activity log: one row per key action of a signed-in user. Users may only add rows for themselves; only owners may read.
create table if not exists public.user_activity (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  email text not null default (auth.jwt() ->> 'email'),
  action text not null check (char_length(action) <= 40),
  detail jsonb not null default '{}'::jsonb check (pg_column_size(detail) <= 2000),
  district text check (char_length(district) <= 60),
  at timestamptz not null default now()
);
create index if not exists user_activity_at on public.user_activity (at desc);
alter table public.user_activity enable row level security;
drop policy if exists "insert own" on public.user_activity;
create policy "insert own" on public.user_activity for insert to authenticated with check (user_id = auth.uid());
drop policy if exists "owners read" on public.user_activity;
create policy "owners read" on public.user_activity for select to authenticated
  using (exists (select 1 from public.owners o where o.email = auth.jwt() ->> 'email'));

-- Retention: delete activity older than 12 months, nightly. Needs the pg_cron extension
-- (Dashboard > Database > Extensions > pg_cron > Enable) before this statement is run.
-- select cron.schedule('cape-monitor-activity-retention', '17 2 * * *', $$delete from public.user_activity where at < now() - interval '12 months'$$);
