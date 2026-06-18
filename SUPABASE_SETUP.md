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

### Opcion A: PostgreSQL directo via DATABASE_URL (Recomendado)

#### Para Supabase: Obtener DATABASE_URL correcto

**⚠️ IMPORTANTE: Prioriza conexión directa (5432). Si tu entorno no soporta IPv6, usa pooler.**

**Pasos:**

1. Ve a tu proyecto en https://supabase.com
2. En la esquina inferior izquierda, haz clic en el nombre de tu proyecto
3. Selecciona **Settings**
4. Ve a la pestaña **Database**
5. En **Connection string**, selecciona **URI** del dropdown
6. Verifica uno de estos formatos:
  - Directa: `postgresql://postgres:[PASSWORD]@db.[PROJECT_ID].supabase.co:5432/postgres`
  - Pooler: `postgresql://postgres.[PROJECT_ID]:[PASSWORD]@aws-...pooler.supabase.com:6543/postgres`
7. Copia la cadena completa
8. Si no sabes la contraseña, ve a **Database** → **Reset database password**
9. En tu terminal local, prueba:

```bash
export DATABASE_URL="postgresql://postgres:TU_PASSWORD@db.XXXX.supabase.co:5432/postgres"
streamlit run streamlit_app.py
```

**En Streamlit Cloud:**

1. Ve a tu app: https://streamlit.io → **My workspace** → Tu app
2. Haz clic en **⋯ (Manage app)** (esquina inferior derecha)
3. Ve a **Secrets**
4. Agrega:
```
DATABASE_URL="postgresql://postgres:TU_PASSWORD@db.XXXX.supabase.co:5432/postgres"
```
5. Haz clic **Save**
6. Espera 30 segundos y recarga tu app

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

1. **Error Supabase: "tenant/user ... not found"**
   - ❌ Usuario/host no corresponde al tipo de conexión (directa vs pooler) o contraseña incorrecta
   - ✅ **Solución:**
     - Copia el CONNECTION STRING de Supabase desde Connect → Direct → Type: URI
     - Si usas **directa**: usuario `postgres` + host `db.[PROJECT_ID].supabase.co` + puerto 5432
     - Si usas **pooler**: usuario `postgres.[PROJECT_ID]` + host `...pooler.supabase.com` + puerto 6543
     - Si olvidaste la contraseña: Settings → Database → Reset database password
     - Reemplaza `[PASSWORD]` con tu contraseña real (sin corchetes)

2. **Contraseña incorrecta o usuario incorrecto (PostgreSQL)**
   - ❌ Tu DATABASE_URL tiene credenciales inválidas
   - ✅ **Solución:**
     - Para Supabase: Settings → Database → Connection string → URI
     - Copia la string completa (incluye usuario y contraseña)
     - Reemplaza [PASSWORD] con tu contraseña real

3. **DATABASE_URL mal configurado en Streamlit Cloud**
   - ❌ El valor en Secrets tiene typos, espacios, o comillas extras
   - ✅ **Solución:**
     - En tu app en streamlit.io: **Manage app** → **Secrets**
     - Verifica que sea exactamente: `DATABASE_URL="postgresql://..."`
     - Sin comillas adicionales ni espacios extra

4. **Host no accesible desde Streamlit Cloud**
   - ❌ Tu PostgreSQL está en localhost o en una red privada
   - ✅ **Solución:**
     - Streamlit Cloud necesita una BD pública accesible desde internet
     - Usa Supabase Cloud (automáticamente accesible)
     - O usa otro proveedor cloud (AWS RDS, Railway, etc.)

5. **Contraseña expirada o reseteada**
   - ❌ Cambiaste la contraseña en PostgreSQL pero no actualizaste DATABASE_URL
   - ✅ **Solución:**
     - En Supabase: Settings → Database → Reset database password
     - Copia el nuevo DATABASE_URL
     - Actualiza en Streamlit Cloud → Secrets
     - Refuerza (reload) la app

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
