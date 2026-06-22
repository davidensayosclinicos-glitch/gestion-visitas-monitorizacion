-- Politicas RLS estrictas por rol (admin/monitor)
-- Requisito: public.usuarios.auth_uid debe mapear al usuario de Supabase Auth (auth.users.id)

begin;

-- Funciones helper
create or replace function public.app_current_usuario()
returns public.usuarios
language sql
stable
security definer
set search_path = public
as $$
  select u.*
  from public.usuarios u
  where u.auth_uid = auth.uid()
    and coalesce(u.activo, 0) = 1
  limit 1
$$;

create or replace function public.app_is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.usuarios u
    where u.auth_uid = auth.uid()
      and coalesce(u.activo, 0) = 1
      and u.rol = 'admin'
  )
$$;

create or replace function public.app_monitor_id()
returns bigint
language sql
stable
security definer
set search_path = public
as $$
  select u.monitor_id
  from public.usuarios u
  where u.auth_uid = auth.uid()
    and coalesce(u.activo, 0) = 1
    and u.rol = 'monitor'
  limit 1
$$;

create or replace function public.app_ensayo_id()
returns bigint
language sql
stable
security definer
set search_path = public
as $$
  select m.ensayo_id
  from public.usuarios u
  join public.monitores m on m.id = u.monitor_id
  where u.auth_uid = auth.uid()
    and coalesce(u.activo, 0) = 1
    and u.rol = 'monitor'
  limit 1
$$;

-- Permisos de ejecucion para roles de Supabase
grant execute on function public.app_current_usuario() to authenticated;
grant execute on function public.app_is_admin() to authenticated;
grant execute on function public.app_monitor_id() to authenticated;
grant execute on function public.app_ensayo_id() to authenticated;

-- Activar RLS
alter table public.ensayos enable row level security;
alter table public.monitores enable row level security;
alter table public.visitas enable row level security;
alter table public.dias_bloqueados enable row level security;
alter table public.usuarios enable row level security;

-- Limpiar politicas antiguas si existieran
-- ENSAYOS
drop policy if exists ensayos_select_admin_monitor on public.ensayos;
drop policy if exists ensayos_write_admin on public.ensayos;

create policy ensayos_select_admin_monitor
on public.ensayos
for select
to authenticated
using (
  public.app_is_admin()
  or id = public.app_ensayo_id()
);

create policy ensayos_write_admin
on public.ensayos
for all
to authenticated
using (public.app_is_admin())
with check (public.app_is_admin());

-- MONITORES
drop policy if exists monitores_select_admin_monitor on public.monitores;
drop policy if exists monitores_write_admin on public.monitores;

create policy monitores_select_admin_monitor
on public.monitores
for select
to authenticated
using (
  public.app_is_admin()
  or ensayo_id = public.app_ensayo_id()
);

create policy monitores_write_admin
on public.monitores
for all
to authenticated
using (public.app_is_admin())
with check (public.app_is_admin());

-- VISITAS
drop policy if exists visitas_select_admin_monitor on public.visitas;
drop policy if exists visitas_insert_admin_monitor on public.visitas;
drop policy if exists visitas_update_admin_monitor on public.visitas;
drop policy if exists visitas_delete_admin_monitor on public.visitas;

create policy visitas_select_admin_monitor
on public.visitas
for select
to authenticated
using (
  public.app_is_admin()
  or ensayo_id = public.app_ensayo_id()
);

create policy visitas_insert_admin_monitor
on public.visitas
for insert
to authenticated
with check (
  public.app_is_admin()
  or (
    ensayo_id = public.app_ensayo_id()
    and monitor_id = public.app_monitor_id()
  )
);

create policy visitas_update_admin_monitor
on public.visitas
for update
to authenticated
using (
  public.app_is_admin()
  or (
    ensayo_id = public.app_ensayo_id()
    and monitor_id = public.app_monitor_id()
  )
)
with check (
  public.app_is_admin()
  or (
    ensayo_id = public.app_ensayo_id()
    and monitor_id = public.app_monitor_id()
  )
);

create policy visitas_delete_admin_monitor
on public.visitas
for delete
to authenticated
using (
  public.app_is_admin()
  or (
    ensayo_id = public.app_ensayo_id()
    and monitor_id = public.app_monitor_id()
  )
);

-- DIAS BLOQUEADOS
-- Monitor: solo lectura (para saber si hay hueco)
-- Admin: lectura y escritura
drop policy if exists dias_bloqueados_select_authenticated on public.dias_bloqueados;
drop policy if exists dias_bloqueados_write_admin on public.dias_bloqueados;

create policy dias_bloqueados_select_authenticated
on public.dias_bloqueados
for select
to authenticated
using (true);

create policy dias_bloqueados_write_admin
on public.dias_bloqueados
for all
to authenticated
using (public.app_is_admin())
with check (public.app_is_admin());

-- USUARIOS
-- Admin ve todo y gestiona todo
-- Monitor solo puede verse a si mismo
drop policy if exists usuarios_select_admin_or_self on public.usuarios;
drop policy if exists usuarios_write_admin on public.usuarios;

create policy usuarios_select_admin_or_self
on public.usuarios
for select
to authenticated
using (
  public.app_is_admin()
  or auth_uid = auth.uid()
);

create policy usuarios_write_admin
on public.usuarios
for all
to authenticated
using (public.app_is_admin())
with check (public.app_is_admin());

commit;
