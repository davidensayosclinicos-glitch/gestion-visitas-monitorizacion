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
  creado_en timestamptz default now()
);

create unique index if not exists usuarios_monitor_unique
  on public.usuarios(monitor_id)
  where monitor_id is not null;
```

## 2) Politicas RLS (entorno de prueba)

Si no usas autenticacion de usuarios en esta app, para pruebas puedes:

- Ir a cada tabla
- Desactivar RLS, o crear politicas que permitan `select/insert/update/delete`

Nota: para produccion conviene mantener RLS activado y autenticar usuarios.

## 2.1) RLS estricto (produccion)

Si quieres blindar permisos en base de datos (ademas del control en la app), usa estos scripts:

1. `sql/2026-06-22_migracion_auth_roles.sql`
2. `sql/2026-06-22_rls_policies.sql`

Orden recomendado en Supabase SQL Editor:

1. Ejecuta primero `sql/2026-06-22_migracion_auth_roles.sql`.
2. Verifica que la tabla `usuarios` tiene datos y que el monitor esta enlazado.
3. Si usas Supabase Auth, rellena `usuarios.auth_uid` con el `auth.users.id` correspondiente.
4. Ejecuta `sql/2026-06-22_rls_policies.sql`.

Notas importantes:
- Con RLS estricto, un monitor solo puede leer su ensayo y operar visitas de su propio monitor.
- `dias_bloqueados` queda en solo lectura para monitor y escritura solo para admin.
- Si usas la app con `service_role`, recuerda que ese rol puede bypass de RLS.
- Si quieres que RLS aplique en runtime, usa JWT de usuarios autenticados (`authenticated`) y mapea `auth_uid`.

## 3) Variables de entorno

### Variables de acceso de administrador (nueva)

Define también estas variables para tu acceso de administrador en la app:

```bash
export ADMIN_USER="tu_usuario_admin"
export ADMIN_PASSWORD="tu_password_admin_segura"
```

En Streamlit Cloud añádelas en **Manage app → Secrets**.

Notas:
- El rol `admin` puede ver todos los ensayos, bloquear días y gestionar usuarios.
- Los usuarios `monitor` se crean desde la propia app (pantalla Monitores) y quedan limitados a su ensayo.

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

## 6) Script SQL de migracion

Tambien tienes un script unico de migracion y soporte de roles en:

- `sql/2026-06-22_migracion_auth_roles.sql`

Este script crea/actualiza tablas e indices necesarios para:

- Usuario por monitor
- Restriccion de un usuario por monitor
- Soporte opcional de RLS con `auth_uid`

## 7) Checklist de validacion

Para validar admin vs monitor paso a paso, usa:

- `TEST_CHECKLIST_ROLES.md`

## 8) Rangos de Fechas (Visitas y Bloqueos)

### Crear Visitas en Rango

En la sección "Visitas", puedes activar el checkbox **"Crear visitas para un rango de fechas"** para:
- Especificar una fecha inicial ("Desde") y una fecha final ("Hasta")
- Crear automáticamente una visita por cada día en el rango
- Las validaciones se aplican a cada día (máximo de visitas, bloqueo parcial del monitor)

**Ejemplo**: Para crear visitas de lunes a viernes (5 días) para el monitor X en el Ensayo Y, solo necesitas:
1. Seleccionar el Ensayo y Monitor
2. Activar el checkbox "Crear visitas para un rango de fechas"
3. Especificar desde el lunes hasta el viernes
4. Click en "Guardar visita(s)"

### Bloquear/Desbloquear Rangos

En la sección "Bloqueos", puedes activar el checkbox **"Bloquear un rango de fechas"** para:
- Especificar una fecha inicial ("Desde") y una fecha final ("Hasta")
- Bloquear automáticamente todos los días en el rango con el mismo máximo de visitas
- El máximo de visitas se configura en el selectbox:
  - **0 visitas**: Día completamente bloqueado (no se puede registrar ninguna visita)
  - **1 visita**: Día con límite reducido (máximo 1 visita en lugar del global de 2)
  - **2 visitas**: Día sin restricción especial (usa el máximo global de 2)

**Ejemplo**: Para reducir a 1 visita por día toda una semana de baja demanda:
1. Activar "Bloquear un rango de fechas"
2. Especificar desde el lunes hasta el domingo
3. Seleccionar "1 visita(s)" en el máximo
4. Agregar motivo: "Baja demanda"
5. Click en "Bloquear"

### Almacenamiento en Base de Datos

Los rangos se almacenan como registros individuales por día en la tabla `dias_bloqueados`:
- Cada día del rango obtiene su propio registro
- El campo `motivo` contiene el formato: `max:X - comentario_opcional`
- Ejemplo: Un bloqueo de 3 días crea 3 registros (uno por día) en la tabla

### Funciones en Backend

**Database.py**:
- `create_visitas_rango(data, fecha_desde, fecha_hasta)`: Crea visitas para múltiples días
- `bloquear_rango(fecha_desde, fecha_hasta, motivo)`: Bloquea múltiples días
- `desbloquear_rango(fecha_desde, fecha_hasta)`: Desbloquea múltiples días

Las funciones manejan fechas en formato ISO (YYYY-MM-DD) o como objetos `datetime.date`.
