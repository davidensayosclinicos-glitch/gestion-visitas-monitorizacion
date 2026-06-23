-- Migracion: documentos por tipo + visibilidad por usuario
-- Fecha: 2026-06-23

begin;

create table if not exists public.documentos (
  id bigserial primary key,
  tipo text not null,
  nombre_archivo text not null,
  mime_type text not null default 'application/octet-stream',
  contenido_b64 text not null,
  subido_por_user_id bigint references public.usuarios(id) on delete set null,
  creado_en timestamptz default now(),
  constraint documentos_tipo_check check (tipo in ('cv', 'gcp', 'calibracion'))
);

create table if not exists public.documentos_visibilidad (
  documento_id bigint not null references public.documentos(id) on delete cascade,
  usuario_id bigint not null references public.usuarios(id) on delete cascade,
  creado_en timestamptz default now(),
  primary key (documento_id, usuario_id)
);

create index if not exists documentos_tipo_idx
  on public.documentos(tipo);

create index if not exists documentos_creado_en_idx
  on public.documentos(creado_en desc);

create index if not exists documentos_visibilidad_usuario_idx
  on public.documentos_visibilidad(usuario_id);

commit;
