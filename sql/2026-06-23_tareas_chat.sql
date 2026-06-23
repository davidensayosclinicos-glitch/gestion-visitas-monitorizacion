-- Migracion: sistema de tareas de monitor en formato chat
-- Fecha: 2026-06-23

begin;

create table if not exists public.tareas (
  id bigserial primary key,
  titulo text not null,
  descripcion text default '',
  monitor_id bigint not null references public.monitores(id) on delete cascade,
  estado text not null default 'abierta',
  creado_en timestamptz default now(),
  actualizado_en timestamptz default now(),
  constraint tareas_estado_check check (estado in ('abierta', 'en_coordinacion', 'cerrada'))
);

create table if not exists public.tareas_mensajes (
  id bigserial primary key,
  tarea_id bigint not null references public.tareas(id) on delete cascade,
  usuario_id bigint not null references public.usuarios(id) on delete set null,
  contenido text not null,
  tipo text not null default 'mensaje',
  creado_en timestamptz default now(),
  constraint tareas_mensajes_tipo_check check (tipo in ('mensaje', 'sistema'))
);

create index if not exists tareas_monitor_id_idx
  on public.tareas(monitor_id);

create index if not exists tareas_estado_idx
  on public.tareas(estado);

create index if not exists tareas_creado_en_idx
  on public.tareas(creado_en desc);

create index if not exists tareas_mensajes_tarea_id_idx
  on public.tareas_mensajes(tarea_id);

create index if not exists tareas_mensajes_usuario_id_idx
  on public.tareas_mensajes(usuario_id);

create index if not exists tareas_mensajes_creado_en_idx
  on public.tareas_mensajes(creado_en asc);

commit;
