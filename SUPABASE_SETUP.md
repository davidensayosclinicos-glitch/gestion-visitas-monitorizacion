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

## 5) Solucionar problemas de conexión

### Error: `OperationalError` o "Error de autenticación"

**Causas comunes:**

1. **Contraseña incorrecta o usuario incorrecto**
   - Ve a tu servidor PostgreSQL y verifica credenciales
   - Para Supabase: Settings → Database → Connection string → URI
   - Copia la string completa (incluye usuario y contraseña)

2. **DATABASE_URL mal configurado en Streamlit Cloud**
   - En tu app en streamlit.app: **Manage app** → **Secrets**
   - Verifica que esté exactamente: `DATABASE_URL="postgresql://..."`
   - Sin comillas adicionales ni espacios
   - Formato correcto: `postgresql://usuario:contrasena@host:puerto/nombrebd`

3. **Host no accesible desde Streamlit Cloud**
   - Streamlit Cloud necesita que tu base de datos sea accesible desde internet
   - Si tu PostgreSQL está en localhost o privado, no funcionará
   - Opciones:
     - Usa Supabase Cloud (público y accesible)
     - Usa otro proveedor cloud (AWS RDS, Heroku Postgres, Railway, etc.)
     - Configura un firewall que permita IPs de Streamlit Cloud (difícil)

4. **Contraseña expirada o reseteada**
   - Si cambias la contraseña en PostgreSQL, actualiza DATABASE_URL en Secrets
   - En Supabase: Settings → Database → Reset database password

### Error: "Falta DATABASE_URL"

**Solución:**
- Verifica en **Secrets** que esté configurado: `DATABASE_URL="..."`
- Refuerza la app (reload)
- Espera 30 segundos para que los secrets se sincronicen

### Verificar localmente primero

Antes de subir a Streamlit Cloud, prueba en tu máquina:

```bash
# Instala dependencias
pip install -r requirements.txt

# Copia tu DATABASE_URL
export DATABASE_URL="postgresql://usuario:pass@host:5432/bd"

# Prueba la app
streamlit run streamlit_app.py
```

Si funciona localmente pero no en Streamlit Cloud, el problema es la configuración de Secrets.

Si no estan las variables necesarias, la app mostrara un error de configuracion al iniciar.
