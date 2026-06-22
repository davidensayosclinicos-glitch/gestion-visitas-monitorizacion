-- Migracion: usuarios por monitor + soporte para RLS con Supabase Auth
-- Fecha: 2026-06-22

begin;

create table if not exists public.ensayos (
  id bigserial primary key,
  codigo text not null,
  nombre text not null,
  promotor text default '',
  fase text default '',
  ip text default '',
  estado text default 'activo',
  fecha_inicio text default '',
  fecha_fin text default '',
  notas text default '',
  creado_en timestamptz default now()
);

create table if not exists public.monitores (
  id bigserial primary key,
  ensayo_id bigint references public.ensayos(id) on delete set null,
  nombre text not null,
  apellidos text not null,
  empresa text default '',
  email text default '',
  telefono text default '',
  activo integer default 1,
  notas text default '',
  creado_en timestamptz default now()
);

create table if not exists public.visitas (
  id bigserial primary key,
  ensayo_id bigint references public.ensayos(id) on delete set null,
  monitor_id bigint references public.monitores(id) on delete set null,
  fecha text not null,
  hora text default '',
  tipo text not null,
  estado text default 'pendiente',
  notas text default '',
  creado_en timestamptz default now(),
  actualizado_en timestamptz default now()
);

create table if not exists public.dias_bloqueados (
  fecha text primary key,
  motivo text default '',
  creado_en timestamptz default now()
);

create table if not exists public.usuarios (
  id bigserial primary key,
  username text unique not null,
  password_hash text not null,
  rol text not null default 'monitor',
  monitor_id bigint references public.monitores(id) on delete set null,
  activo integer default 1,
  -- Opcional: vínculo con Supabase Auth para aplicar RLS por usuario autenticado
  auth_uid uuid unique,
  creado_en timestamptz default now()
);

alter table public.monitores
  add column if not exists ensayo_id bigint references public.ensayos(id) on delete set null;

alter table public.usuarios
  add column if not exists auth_uid uuid unique;

create unique index if not exists usuarios_monitor_unique
  on public.usuarios(monitor_id)
  where monitor_id is not null;

create index if not exists usuarios_auth_uid_idx
  on public.usuarios(auth_uid)
  where auth_uid is not null;

-- Integridad basica de roles
alter table public.usuarios
  drop constraint if exists usuarios_rol_check;

alter table public.usuarios
  add constraint usuarios_rol_check
  check (rol in ('admin', 'monitor'));

commit;
