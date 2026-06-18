# Configuracion de Base de Datos

La app soporta dos backends automaticamente:

- PostgreSQL directo con `DATABASE_URL` (recomendado si quieres igual que tu otra app)
- API de Supabase con `SUPABASE_URL` + `SUPABASE_KEY`

## 1) Crear tablas en Supabase

En el SQL Editor de Supabase, ejecuta:

```sql
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
```

## 2) Politicas RLS (entorno de prueba)

Si no usas autenticacion de usuarios en esta app, para pruebas puedes:

- Ir a cada tabla
- Desactivar RLS, o crear politicas que permitan `select/insert/update/delete`

Nota: para produccion conviene mantener RLS activado y autenticar usuarios.

## 3) Variables de entorno

### Opcion A: PostgreSQL directo (igual que tu otra app)

Define `DATABASE_URL`:

```bash
export DATABASE_URL="postgresql://usuario:password@host:6543/postgres"
streamlit run streamlit_app.py
```

### Opcion B: API de Supabase

Define estas variables:

- `SUPABASE_URL`
- `SUPABASE_KEY` (recomendado usar `service_role` solo en backend seguro)

Ejemplo rapido:

```bash
export SUPABASE_URL="https://TU-PROYECTO.supabase.co"
export SUPABASE_KEY="TU_SUPABASE_KEY"
streamlit run streamlit_app.py
```

## 4) Verificar en la app

En el sidebar debe aparecer:

- `Backend: 🐘 PostgreSQL (DATABASE_URL)` si usas `DATABASE_URL`
- `Backend: ☁️ Supabase API` si usas `SUPABASE_URL` y `SUPABASE_KEY`

Si no estan las variables necesarias, la app mostrara un error de configuracion al iniciar.
