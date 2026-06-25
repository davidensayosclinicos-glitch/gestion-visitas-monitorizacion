"""
database.py — Capa de acceso a datos (PostgreSQL/Supabase)
Gestion de Visitas de Monitorizacion — Ensayos Clinicos
"""
import os
import hashlib
import hmac
import secrets
import base64
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import pandas as pd

try:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
except Exception:
    psycopg = None
    sql = None
    dict_row = None

try:
    from supabase import create_client
except Exception:
    create_client = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY", "").strip()
    or os.getenv("SUPABASE_ANON_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)
_SUPABASE_CLIENT = None
_PG_CONN = None
_ACTIVE_BACKEND = None
MAX_VISITAS_POR_DIA = 2
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 150_000
TIPOS_DOCUMENTO = ("cv", "gcp", "calibracion")

ADMIN_USER = os.getenv("ADMIN_USER", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()


def _can_use_supabase_api():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _get_backend_name():
    global _ACTIVE_BACKEND
    if _ACTIVE_BACKEND:
        return _ACTIVE_BACKEND
    if DATABASE_URL:
        _ACTIVE_BACKEND = "postgres"
    else:
        _ACTIVE_BACKEND = "supabase"
    return _ACTIVE_BACKEND


def get_backend_name():
    return _get_backend_name()


def _norm_text(value):
    return (value or "").strip().lower()


def _hash_password(password, salt=None):
    if not password:
        raise ValueError("La contraseña no puede estar vacía.")
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${digest}"


def _verify_password(password, stored_hash):
    if not password or not stored_hash:
        return False
    try:
        scheme, iterations_s, salt, expected = stored_hash.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_s)
    except Exception:
        return False

    check = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(check, expected)


def _using_postgres():
    return _get_backend_name() == "postgres"


def _activate_supabase_fallback():
    global _ACTIVE_BACKEND, _PG_CONN
    if not _can_use_supabase_api():
        return False
    _ACTIVE_BACKEND = "supabase"
    _PG_CONN = None
    return True


def _validate_database_url():
    if not DATABASE_URL:
        return

    url_lower = DATABASE_URL.lower()
    if "[your-password]" in url_lower or "[password]" in url_lower:
        raise RuntimeError(
            "❌ DATABASE_URL inválido: contiene un placeholder de contraseña sin reemplazar.\n\n"
            "Reemplaza [YOUR-PASSWORD] o [PASSWORD] por tu contraseña real de PostgreSQL en Supabase."
        )

    try:
        parsed = urlparse(DATABASE_URL)
    except Exception as ex:
        raise RuntimeError(
            "❌ DATABASE_URL inválido: no se pudo interpretar la URL.\n"
            "Asegúrate de usar el formato postgresql://usuario:password@host:5432/base_de_datos"
        ) from ex

    if parsed.scheme not in ("postgresql", "postgres"):
        raise RuntimeError(
            "❌ DATABASE_URL inválido: el esquema debe ser postgresql:// o postgres://"
        )

    hostname = (parsed.hostname or "").lower()
    username = parsed.username or ""

    # En Supabase pooler normalmente el usuario es postgres.<project_ref>.
    if "pooler.supabase.com" in hostname and "." not in username:
        raise RuntimeError(
            "❌ DATABASE_URL inválido para pooler de Supabase.\n\n"
            "Cuando usas host pooler.supabase.com, el usuario debe tener este formato:\n"
            "postgres.<project-ref>\n\n"
            "Opciones recomendadas:\n"
            "1. Usar conexión directa: postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres\n"
            "2. O usar pooler con usuario postgres.<project-ref>"
        )

    if "supabase.co" in hostname and (parsed.password is None or parsed.password == ""):
        raise RuntimeError(
            "❌ DATABASE_URL inválido: falta la contraseña en la URL.\n"
            "Asegúrate de incluir usuario y contraseña en el formato postgresql://usuario:password@host:puerto/base"
        )


def _pg_conn():
    global _PG_CONN
    if not DATABASE_URL:
        raise RuntimeError("Falta DATABASE_URL para conexion PostgreSQL.")
    _validate_database_url()
    if psycopg is None:
        raise RuntimeError("Falta la dependencia 'psycopg'. Ejecuta: pip install psycopg[binary]")
    if _PG_CONN is None or _PG_CONN.closed:
        try:
            # PgBouncer/Supabase pooler puede fallar con prepared statements automáticos.
            # Desactivarlos evita errores como DuplicatePreparedStatement.
            _PG_CONN = psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row,
                autocommit=True,
                prepare_threshold=None,
            )
        except psycopg.OperationalError as ex:
            error_msg = str(ex).lower()
            parsed = urlparse(DATABASE_URL)
            host = (parsed.hostname or "").lower()
            user = parsed.username or ""
            
            # Errores específicos de Supabase
            if "enotfound" in error_msg and "tenant" in error_msg:
                raise RuntimeError(
                    "❌ Error de conexión Supabase: tenant/usuario no encontrado.\n\n"
                    "📋 Para obtener el DATABASE_URL correcto de Supabase:\n"
                    "1. Ve a https://supabase.com → Tu proyecto → Connect → Direct\n"
                    "2. Type: URI\n"
                    "3. Copia la cadena completa (postgresql://...)\n"
                    "4. Reemplaza [YOUR-PASSWORD] por tu contraseña real\n\n"
                    "🔎 Validaciones rápidas:\n"
                    f"- Host actual: {host or '(vacío)'}\n"
                    f"- Usuario actual: {user or '(vacío)'}\n"
                    "- Si usas host pooler.supabase.com, el usuario debe ser postgres.<project-ref>\n"
                    "- Si usas host db.<project-ref>.supabase.co, el usuario suele ser postgres"
                ) from ex
            elif "authentication failed" in error_msg or "password authentication" in error_msg:
                raise RuntimeError(
                    "❌ Error de autenticación: Contraseña o usuario incorrecto.\n\n"
                    "Pasos para verificar DATABASE_URL:\n"
                    "1. En Supabase: Settings → Database → Connection string → URI\n"
                    "2. Copia la cadena completa\n"
                    "3. Reemplaza [YOUR-PASSWORD] con tu contraseña de PostgreSQL\n"
                    "4. Pega en Streamlit Cloud: Manage app → Secrets → DATABASE_URL"
                ) from ex
            elif "could not translate host name" in error_msg or "nodename nor servname provided" in error_msg:
                raise RuntimeError(
                    "❌ Error de conexión: No se puede resolver el host de PostgreSQL.\n"
                    "Verifica que el DATABASE_URL sea válido y el servidor sea accesible."
                ) from ex
            elif "cannot assign requested address" in error_msg or "network is unreachable" in error_msg:
                raise RuntimeError(
                    "❌ Error de red al conectar con PostgreSQL directo (IPv6).\n\n"
                    "En Streamlit Cloud suele funcionar mejor el pooler (IPv4).\n"
                    "Usa en DATABASE_URL este formato:\n"
                    "postgresql://postgres.<project-ref>:<password>@aws-1-eu-west-1.pooler.supabase.com:6543/postgres\n\n"
                    "Pasos:\n"
                    "1. Supabase → Connect → Direct\n"
                    "2. Connection method: Transaction pooler\n"
                    "3. Type: URI\n"
                    "4. Copia la URL completa y pégala en Streamlit Cloud → Manage app → Secrets"
                ) from ex
            elif "connection refused" in error_msg:
                raise RuntimeError(
                    "❌ Conexión rechazada: El servidor PostgreSQL no responde.\n"
                    "Verifica que el servidor esté ejecutándose y accesible."
                ) from ex
            else:
                raise RuntimeError(
                    f"❌ Error al conectar a PostgreSQL: {error_msg}\n\n"
                    "Verifica tu DATABASE_URL en Streamlit Cloud:\n"
                    "1. Manage app → Secrets\n"
                    "2. Copia la cadena completa de Supabase (Settings → Database → Connection string → URI)\n"
                    "3. Reemplaza [YOUR-PASSWORD] con tu contraseña\n"
                    "4. Salva y refuerza (reload) la app"
                ) from ex
    return _PG_CONN


def _sb():
    global _SUPABASE_CLIENT
    if create_client is None:
        raise RuntimeError("Falta la dependencia 'supabase'. Ejecuta: pip install supabase")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "No hay backend configurado. Define DATABASE_URL para PostgreSQL directo, "
            "o SUPABASE_URL y SUPABASE_KEY para API de Supabase."
        )
    if _SUPABASE_CLIENT is None:
        _SUPABASE_CLIENT = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _SUPABASE_CLIENT


def _fetch_all(table_name):
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(sql.SQL("select * from {}" ).format(sql.Identifier(table_name)))
            return cur.fetchall() or []
    res = _sb().table(table_name).select("*").execute()
    return res.data or []


def _table_exists(table_name):
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                select 1
                from information_schema.tables
                where table_schema = 'public' and table_name = %s
                limit 1
                """,
                [table_name],
            )
            return bool(cur.fetchone())
    try:
        _sb().table(table_name).select("id").limit(1).execute()
        return True
    except Exception:
        return False


def _get_by_id(table_name, entity_id):
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                sql.SQL("select * from {} where id = %s limit 1").format(sql.Identifier(table_name)),
                [entity_id],
            )
            row = cur.fetchone()
            return row if row else None
    res = _sb().table(table_name).select("*").eq("id", entity_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else None


def _insert_row(table_name, data):
    if _using_postgres():
        keys = list(data.keys())
        with _pg_conn().cursor() as cur:
            cur.execute(
                sql.SQL("insert into {} ({}) values ({})").format(
                    sql.Identifier(table_name),
                    sql.SQL(", ").join(sql.Identifier(k) for k in keys),
                    sql.SQL(", ").join(sql.Placeholder() for _ in keys),
                ),
                [data[k] for k in keys],
            )
        return
    _sb().table(table_name).insert(data).execute()


def _update_row_by_id(table_name, entity_id, data):
    if _using_postgres():
        keys = list(data.keys())
        with _pg_conn().cursor() as cur:
            cur.execute(
                sql.SQL("update {} set {} where id = %s").format(
                    sql.Identifier(table_name),
                    sql.SQL(", ").join(
                        sql.SQL("{} = {}").format(sql.Identifier(k), sql.Placeholder()) for k in keys
                    ),
                ),
                [data[k] for k in keys] + [entity_id],
            )
        return
    _sb().table(table_name).update(data).eq("id", entity_id).execute()


def _delete_row_by_id(table_name, entity_id):
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                sql.SQL("delete from {} where id = %s").format(sql.Identifier(table_name)),
                [entity_id],
            )
        return
    _sb().table(table_name).delete().eq("id", entity_id).execute()


def get_dias_bloqueados(desde='', hasta=''):
    if _using_postgres():
        where = []
        params = []
        if desde:
            where.append("fecha >= %s")
            params.append(desde)
        if hasta:
            where.append("fecha <= %s")
            params.append(hasta)

        query = "select fecha, motivo from dias_bloqueados"
        if where:
            query += " where " + " and ".join(where)
        with _pg_conn().cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall() or []
    else:
        query = _sb().table("dias_bloqueados").select("fecha,motivo")
        if desde:
            query = query.gte("fecha", desde)
        if hasta:
            query = query.lte("fecha", hasta)
        rows = query.execute().data or []
    rows.sort(key=lambda r: _norm_text(r.get("fecha")))
    return rows


def bloquear_rango(fecha_desde, fecha_hasta, motivo=''):
    """Bloquea un rango de fechas (inclusive)"""
    from_date = datetime.fromisoformat(fecha_desde).date() if isinstance(fecha_desde, str) else fecha_desde
    to_date = datetime.fromisoformat(fecha_hasta).date() if isinstance(fecha_hasta, str) else fecha_hasta
    
    current_date = from_date
    while current_date <= to_date:
        bloquear_dia(current_date.isoformat(), motivo)
        current_date += timedelta(days=1)


def desbloquear_rango(fecha_desde, fecha_hasta):
    """Desbloquea un rango de fechas (inclusive)"""
    from_date = datetime.fromisoformat(fecha_desde).date() if isinstance(fecha_desde, str) else fecha_desde
    to_date = datetime.fromisoformat(fecha_hasta).date() if isinstance(fecha_hasta, str) else fecha_hasta
    
    current_date = from_date
    while current_date <= to_date:
        desbloquear_dia(current_date.isoformat())
        current_date += timedelta(days=1)


def bloquear_dia(fecha, motivo=''):
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                insert into dias_bloqueados (fecha, motivo)
                values (%s, %s)
                on conflict (fecha) do update set motivo = excluded.motivo
                """,
                [fecha, (motivo or "").strip()],
            )
        return

    _sb().table("dias_bloqueados").upsert(
        {
            "fecha": fecha,
            "motivo": (motivo or "").strip(),
        },
        on_conflict="fecha",
    ).execute()


def desbloquear_dia(fecha):
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute("delete from dias_bloqueados where fecha = %s", [fecha])
        return
    _sb().table("dias_bloqueados").delete().eq("fecha", fecha).execute()


def get_visitas_count_by_date(desde='', hasta=''):
    if _using_postgres():
        where = []
        params = []
        if desde:
            where.append("fecha >= %s")
            params.append(desde)
        if hasta:
            where.append("fecha <= %s")
            params.append(hasta)

        query = "select fecha, count(*) as total from visitas"
        if where:
            query += " where " + " and ".join(where)
        query += " group by fecha"

        with _pg_conn().cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall() or []
        return {row.get("fecha"): int(row.get("total", 0)) for row in rows if row.get("fecha")}

    query = _sb().table("visitas").select("fecha")
    if desde:
        query = query.gte("fecha", desde)
    if hasta:
        query = query.lte("fecha", hasta)
    rows = query.execute().data or []

    out = {}
    for row in rows:
        f = row.get("fecha")
        if not f:
            continue
        out[f] = out.get(f, 0) + 1
    return out


def _validar_limites_visita(fecha, monitor_id, exclude_visita_id=None):
    if not fecha:
        raise ValueError("La fecha de la visita es obligatoria.")
    if monitor_id is None:
        raise ValueError("El monitor de la visita es obligatorio.")

    # Buscar bloqueos personalizados para este día (con máximo de visitas)
    dias_bloq = get_dias_bloqueados(desde=fecha, hasta=fecha)
    max_visitas_dia = MAX_VISITAS_POR_DIA  # default global
    
    for bloqueo in dias_bloq:
        if bloqueo.get("fecha") == fecha:
            motivo = bloqueo.get("motivo", "")
            # Parsear formato "max:X" o "max:X - comentario"
            if motivo.startswith("max:"):
                try:
                    max_visitas_dia = int(motivo.split(":")[1].split()[0].split("-")[0])
                except (ValueError, IndexError):
                    max_visitas_dia = 0  # Si no se puede parsear, bloquear completamente
            else:
                # Bloqueo total (sin especificar max, asumir 0)
                max_visitas_dia = 0
            break

    # Si max_visitas_dia es 0, día bloqueado completamente
    if max_visitas_dia == 0:
        raise ValueError("No se puede registrar la visita: el día está bloqueado.")

    # Contar visitas en el día
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute("select id from visitas where fecha = %s", [fecha])
            rows = cur.fetchall() or []
    else:
        rows = _sb().table("visitas").select("id").eq("fecha", fecha).execute().data or []
    if exclude_visita_id is not None:
        rows = [r for r in rows if r.get("id") != exclude_visita_id]

    # Comprobar límite de visitas del día
    if len(rows) >= max_visitas_dia:
        raise ValueError(f"No se puede registrar la visita: máximo {max_visitas_dia} visita(s) por día.")

    # Bloqueo parcial: un mismo monitor no puede tener más de una visita por día.
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                "select id from visitas where fecha = %s and monitor_id = %s",
                [fecha, monitor_id],
            )
            same_monitor_rows = cur.fetchall() or []
    else:
        same_monitor_rows = (
            _sb()
            .table("visitas")
            .select("id")
            .eq("fecha", fecha)
            .eq("monitor_id", monitor_id)
            .execute()
            .data
            or []
        )

    if exclude_visita_id is not None:
        same_monitor_rows = [r for r in same_monitor_rows if r.get("id") != exclude_visita_id]

    if same_monitor_rows:
        raise ValueError(
            "No se puede registrar la visita: este monitor ya tiene una visita asignada en esa fecha."
        )

def init_db():
    # Verifica conectividad y tablas requeridas.
    required = ["ensayos", "monitores", "visitas", "dias_bloqueados", "usuarios"]

    if _using_postgres():
        try:
            missing = []
            with _pg_conn().cursor() as cur:
                cur.execute(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = 'public' and table_name = any(%s)
                    """,
                    [required],
                )
                existing = {r.get("table_name") for r in (cur.fetchall() or [])}

            for table_name in required:
                if table_name not in existing:
                    missing.append(table_name)
                    continue
                try:
                    with _pg_conn().cursor() as cur:
                        cur.execute(sql.SQL("select 1 from {} limit 1").format(sql.Identifier(table_name)))
                except Exception:
                    missing.append(table_name)

            if missing:
                names = ", ".join(missing)
                raise RuntimeError(
                    f"PostgreSQL configurado pero faltan tablas o permisos: {names}. "
                    "Revisa SUPABASE_SETUP.md."
                )
            return
        except RuntimeError:
            if not _activate_supabase_fallback():
                raise

    missing = []
    probe_columns = {
        "ensayos": "id",
        "monitores": "id",
        "visitas": "id",
        "dias_bloqueados": "fecha",
        "usuarios": "id",
    }
    for table_name, col in probe_columns.items():
        try:
            _sb().table(table_name).select(col).limit(1).execute()
        except Exception:
            missing.append(table_name)
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Supabase configurado pero faltan tablas o permisos: {names}. "
            "Revisa SUPABASE_SETUP.md y las politicas RLS."
        )


# ── AUTENTICACION Y USUARIOS ────────────────────────────────────────────────

def get_usuario_by_username(username):
    username_n = _norm_text(username)
    if not username_n:
        return None

    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                select id, username, rol, monitor_id, password_hash, activo
                from usuarios
                where lower(username) = %s
                limit 1
                """,
                [username_n],
            )
            row = cur.fetchone()
            return row if row else None

    res = (
        _sb()
        .table("usuarios")
        .select("id,username,rol,monitor_id,password_hash,activo")
        .ilike("username", username_n)
        .limit(1)
        .execute()
    )
    data = res.data or []
    if not data:
        return None
    # ilike puede devolver coincidencias no exactas; validamos exactitud en Python.
    for row in data:
        if _norm_text(row.get("username")) == username_n:
            return row
    return None


def list_usuarios_monitor():
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                select u.id, u.username, u.rol, u.activo, u.monitor_id,
                       m.nombre as monitor_nombre,
                       m.apellidos as monitor_apellidos,
                       e.codigo as ensayo_codigo,
                       e.nombre as ensayo_nombre
                from usuarios u
                left join monitores m on m.id = u.monitor_id
                left join ensayos e on e.id = m.ensayo_id
                order by lower(u.username)
                """
            )
            return cur.fetchall() or []

    users = _sb().table("usuarios").select("id,username,rol,activo,monitor_id").execute().data or []
    if not users:
        return []
    monitores = {m.get("id"): m for m in _fetch_all("monitores")}
    ensayos = {e.get("id"): e for e in _fetch_all("ensayos")}
    out = []
    for u in users:
        m = monitores.get(u.get("monitor_id")) or {}
        e = ensayos.get(m.get("ensayo_id")) or {}
        item = dict(u)
        item["monitor_nombre"] = m.get("nombre", "")
        item["monitor_apellidos"] = m.get("apellidos", "")
        item["ensayo_codigo"] = e.get("codigo", "")
        item["ensayo_nombre"] = e.get("nombre", "")
        out.append(item)
    out.sort(key=lambda r: _norm_text(r.get("username")))
    return out


def set_usuario_activo(user_id, activo):
    _update_row_by_id("usuarios", user_id, {"activo": 1 if bool(activo) else 0})


def create_usuario_monitor(username, password, monitor_id, activo=True):
    username_clean = (username or "").strip()
    if not username_clean:
        raise ValueError("El usuario es obligatorio.")
    if len(password or "") < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    if monitor_id is None:
        raise ValueError("Debes seleccionar un monitor.")

    existing = get_usuario_by_username(username_clean)
    if existing:
        raise ValueError("Ese nombre de usuario ya existe.")

    # Asegura un usuario por monitor.
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute("select id from usuarios where monitor_id = %s limit 1", [monitor_id])
            if cur.fetchone():
                raise ValueError("Ese monitor ya tiene un usuario creado.")
    else:
        rows = _sb().table("usuarios").select("id").eq("monitor_id", monitor_id).limit(1).execute().data or []
        if rows:
            raise ValueError("Ese monitor ya tiene un usuario creado.")

    _insert_row(
        "usuarios",
        {
            "username": username_clean,
            "password_hash": _hash_password(password),
            "rol": "monitor",
            "monitor_id": monitor_id,
            "activo": 1 if bool(activo) else 0,
        },
    )


def reset_usuario_password(user_id, new_password):
    if len(new_password or "") < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    _update_row_by_id("usuarios", user_id, {"password_hash": _hash_password(new_password)})


def update_usuario_username(user_id, new_username):
    """Actualiza el nombre de usuario (username)."""
    new_username_clean = (new_username or "").strip()
    if not new_username_clean:
        raise ValueError("El usuario es obligatorio.")
    
    # Verificar que no exista otro usuario con el mismo nombre
    existing = get_usuario_by_username(new_username_clean)
    if existing and int(existing.get("id") or 0) != int(user_id or 0):
        raise ValueError("Ese nombre de usuario ya existe.")
    
    _update_row_by_id("usuarios", user_id, {"username": new_username_clean})


def _ensure_admin_user_record():
    if not ADMIN_USER or not ADMIN_PASSWORD:
        return None

    admin_user = get_usuario_by_username(ADMIN_USER)
    if admin_user:
        if _norm_text(admin_user.get("rol")) != "admin":
            raise RuntimeError(
                "El usuario definido en ADMIN_USER ya existe, pero no tiene rol admin. "
                "Corrige ese usuario o cambia ADMIN_USER."
            )
        if not int(admin_user.get("activo") or 0):
            set_usuario_activo(admin_user.get("id"), True)
            admin_user["activo"] = 1
        return admin_user

    _insert_row(
        "usuarios",
        {
            "username": ADMIN_USER,
            "password_hash": _hash_password(ADMIN_PASSWORD),
            "rol": "admin",
            "monitor_id": None,
            "activo": 1,
        },
    )
    return get_usuario_by_username(ADMIN_USER)


def authenticate_user(username, password):
    username_clean = (username or "").strip()

    # Admin por variables de entorno (recomendado para el propietario de la app).
    if ADMIN_USER and ADMIN_PASSWORD:
        if _norm_text(username_clean) == _norm_text(ADMIN_USER) and password == ADMIN_PASSWORD:
            admin_user = _ensure_admin_user_record() or {}
            return {
                "id": admin_user.get("id"),
                "username": admin_user.get("username") or ADMIN_USER,
                "rol": "admin",
                "monitor_id": None,
                "ensayo_id": None,
            }

    user = get_usuario_by_username(username_clean)
    if not user:
        return None
    if not int(user.get("activo") or 0):
        return None
    if not _verify_password(password, user.get("password_hash", "")):
        return None

    role = _norm_text(user.get("rol") or "monitor")
    if role not in ("admin", "monitor"):
        role = "monitor"

    ensayo_id = None
    monitor_id = user.get("monitor_id")
    if role == "monitor":
        monitor = get_monitor_by_id(monitor_id) if monitor_id is not None else None
        if not monitor or monitor.get("ensayo_id") is None:
            return None
        ensayo_id = monitor.get("ensayo_id")

    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "rol": role,
        "monitor_id": monitor_id,
        "ensayo_id": ensayo_id,
    }


# ── ENSAYOS ───────────────────────────────────────────────────────────────────

def get_ensayos(texto='', estado=''):
    rows = _fetch_all("ensayos")
    estado_n = _norm_text(estado)
    texto_n = _norm_text(texto)

    if estado_n:
        rows = [r for r in rows if _norm_text(r.get("estado")) == estado_n]

    if texto_n:
        def match_row(r):
            return (
                texto_n in _norm_text(r.get("codigo"))
                or texto_n in _norm_text(r.get("nombre"))
                or texto_n in _norm_text(r.get("promotor"))
            )

        rows = [r for r in rows if match_row(r)]

    rows.sort(key=lambda r: _norm_text(r.get("codigo")))
    return rows


def get_ensayo_by_id(eid):
    return _get_by_id("ensayos", eid)


def create_ensayo(data):
    _insert_row("ensayos", data)


def update_ensayo(eid, data):
    _update_row_by_id("ensayos", eid, data)


def delete_ensayo(eid):
    _delete_row_by_id("ensayos", eid)


# ── MONITORES ─────────────────────────────────────────────────────────────────

def get_monitores(texto='', ensayo_id=None):
    rows = _fetch_all("monitores")
    texto_n = _norm_text(texto)

    if ensayo_id is not None:
        rows = [r for r in rows if r.get("ensayo_id") == ensayo_id]

    if texto_n:
        def match_row(r):
            return (
                texto_n in _norm_text(r.get("nombre"))
                or texto_n in _norm_text(r.get("apellidos"))
                or texto_n in _norm_text(r.get("empresa"))
                or texto_n in _norm_text(r.get("email"))
            )

        rows = [r for r in rows if match_row(r)]

    rows.sort(key=lambda r: (_norm_text(r.get("apellidos")), _norm_text(r.get("nombre"))))
    return rows


def get_monitor_by_id(mid):
    return _get_by_id("monitores", mid)


def create_monitor(data):
    _insert_row("monitores", data)


def update_monitor(mid, data):
    # No permitir cambiar ensayo_id
    original = _get_by_id("monitores", mid)
    if original and data.get("ensayo_id") != original.get("ensayo_id"):
        raise ValueError("No se puede cambiar el ensayo de un monitor una vez creado.")
    _update_row_by_id("monitores", mid, data)


def delete_monitor(mid):
    _delete_row_by_id("monitores", mid)


# ── VISITAS ───────────────────────────────────────────────────────────────────

def get_visitas_df(texto='', estado='', ensayo_id=None, desde='', hasta=''):
    visitas = pd.DataFrame(_fetch_all("visitas"))
    ensayos = pd.DataFrame(_fetch_all("ensayos"))
    monitores = pd.DataFrame(_fetch_all("monitores"))

    cols = [
        "id", "ensayo_id", "monitor_id", "fecha", "hora", "tipo", "estado", "notas",
        "ensayo_codigo", "ensayo_nombre", "monitor_nombre", "monitor_empresa",
    ]
    if visitas.empty:
        return pd.DataFrame(columns=cols)

    if not ensayos.empty:
        ensayos = ensayos.rename(columns={"id": "ensayo_id_ref", "codigo": "ensayo_codigo", "nombre": "ensayo_nombre"})
        visitas = visitas.merge(
            ensayos[["ensayo_id_ref", "ensayo_codigo", "ensayo_nombre"]],
            left_on="ensayo_id",
            right_on="ensayo_id_ref",
            how="left",
        ).drop(columns=["ensayo_id_ref"])
    else:
        visitas["ensayo_codigo"] = ""
        visitas["ensayo_nombre"] = ""

    if not monitores.empty:
        monitores = monitores.rename(columns={"id": "monitor_id_ref", "empresa": "monitor_empresa"})
        if "nombre" not in monitores.columns:
            monitores["nombre"] = ""
        if "apellidos" not in monitores.columns:
            monitores["apellidos"] = ""
        monitores["monitor_nombre"] = (
            monitores["nombre"].fillna("") + " " + monitores["apellidos"].fillna("")
        ).str.strip()
        visitas = visitas.merge(
            monitores[["monitor_id_ref", "monitor_nombre", "monitor_empresa"]],
            left_on="monitor_id",
            right_on="monitor_id_ref",
            how="left",
        ).drop(columns=["monitor_id_ref"])
    else:
        visitas["monitor_nombre"] = ""
        visitas["monitor_empresa"] = ""

    estado_n = _norm_text(estado)
    texto_n = _norm_text(texto)

    if estado_n:
        visitas = visitas[visitas["estado"].fillna("").str.lower() == estado_n]

    if ensayo_id:
        visitas = visitas[visitas["ensayo_id"] == ensayo_id]

    if desde:
        visitas = visitas[visitas["fecha"].fillna("") >= desde]

    if hasta:
        visitas = visitas[visitas["fecha"].fillna("") <= hasta]

    if texto_n:
        text_block = (
            visitas["monitor_nombre"].fillna("") + " "
            + visitas["ensayo_codigo"].fillna("") + " "
            + visitas["ensayo_nombre"].fillna("") + " "
            + visitas["tipo"].fillna("")
        ).str.lower()
        visitas = visitas[text_block.str.contains(texto_n, regex=False)]

    if "hora" not in visitas.columns:
        visitas["hora"] = ""

    visitas = visitas.sort_values(["fecha", "hora"], ascending=[False, False])
    for c in cols:
        if c not in visitas.columns:
            visitas[c] = ""
    return visitas[cols]


def get_visita_by_id(vid):
    return _get_by_id("visitas", vid)


def create_visitas_rango(data, fecha_desde, fecha_hasta):
    """Crea visitas para un rango de fechas (inclusive).
    
    data: diccionario con los datos de la visita (sin fecha)
    fecha_desde: fecha inicial (YYYY-MM-DD o date object)
    fecha_hasta: fecha final (YYYY-MM-DD o date object)
    """
    from_date = datetime.fromisoformat(fecha_desde).date() if isinstance(fecha_desde, str) else fecha_desde
    to_date = datetime.fromisoformat(fecha_hasta).date() if isinstance(fecha_hasta, str) else fecha_hasta
    
    current_date = from_date
    created_count = 0
    while current_date <= to_date:
        visit_data = dict(data)
        visit_data["fecha"] = current_date.isoformat()
        create_visita(visit_data)
        created_count += 1
        current_date += timedelta(days=1)
    
    return created_count


def create_visita(data):
    _validar_limites_visita(data.get("fecha", ""), data.get("monitor_id"))
    _insert_row("visitas", data)


def update_visita(vid, data):
    data = dict(data)

    # Para actualizaciones parciales (p.ej. solo estado), no exigir fecha/monitor.
    # Validamos límites solo cuando se intenta cambiar fecha y/o monitor.
    if "fecha" in data or "monitor_id" in data:
        actual = get_visita_by_id(vid)
        if not actual:
            raise ValueError("La visita no existe.")
        fecha_val = data.get("fecha", actual.get("fecha", ""))
        monitor_val = data.get("monitor_id", actual.get("monitor_id"))
        _validar_limites_visita(
            fecha_val,
            monitor_val,
            exclude_visita_id=vid,
        )

    data["actualizado_en"] = datetime.utcnow().isoformat()
    _update_row_by_id("visitas", vid, data)


def delete_visita(vid):
    _delete_row_by_id("visitas", vid)


# ── ESTADISTICAS ──────────────────────────────────────────────────────────────

def get_stats():
    df = get_visitas_df()
    ensayos = get_ensayos(estado="activo")
    mes = date.today().strftime('%Y-%m')

    if df.empty:
        total_mes = 0
        pendientes = 0
        realizadas = 0
    else:
        total_mes = int(df["fecha"].fillna("").str.startswith(mes).sum())
        pendientes = int(df["estado"].isin(["pendiente", "confirmada"]).sum())
        realizadas = int((df["estado"] == "realizada").sum())

    return {
        'total_mes': total_mes,
        'pendientes': pendientes,
        'realizadas': realizadas,
        'ensayos_activos': len(ensayos),
    }


def get_proximas_visitas(limit=10):
    hoy = date.today().isoformat()
    df = get_visitas_df()
    if df.empty:
        return pd.DataFrame(columns=["fecha", "hora", "tipo", "estado", "monitor", "ensayo"])

    base = df[
        (df["fecha"].fillna("") >= hoy)
        & (~df["estado"].isin(["cancelada", "realizada"]))
    ].copy()
    if base.empty:
        return pd.DataFrame(columns=["fecha", "hora", "tipo", "estado", "monitor", "ensayo"])

    base["monitor"] = base["monitor_nombre"].fillna("")
    base["ensayo"] = (
        base["ensayo_codigo"].fillna("") + " - " + base["ensayo_nombre"].fillna("")
    ).str.strip(" -")
    base = base.sort_values(["fecha", "hora"], ascending=[True, True]).head(limit)
    return base[["fecha", "hora", "tipo", "estado", "monitor", "ensayo"]]


def get_resumen_por_ensayo():
    ensayos = pd.DataFrame(get_ensayos())
    visitas = get_visitas_df()
    if ensayos.empty:
        return pd.DataFrame(columns=[
            "codigo", "nombre", "estado_ensayo", "total", "pendientes", "realizadas", "canceladas"
        ])

    if visitas.empty:
        ensayos["total"] = 0
        ensayos["pendientes"] = 0
        ensayos["realizadas"] = 0
        ensayos["canceladas"] = 0
        ensayos = ensayos.rename(columns={"estado": "estado_ensayo"})
        return ensayos[["codigo", "nombre", "estado_ensayo", "total", "pendientes", "realizadas", "canceladas"]]

    grp = visitas.groupby("ensayo_id", dropna=False).agg(
        total=("id", "count"),
        pendientes=("estado", lambda s: int(s.isin(["pendiente", "confirmada"]).sum())),
        realizadas=("estado", lambda s: int((s == "realizada").sum())),
        canceladas=("estado", lambda s: int((s == "cancelada").sum())),
    ).reset_index()

    out = ensayos.merge(grp, left_on="id", right_on="ensayo_id", how="left")
    for c in ["total", "pendientes", "realizadas", "canceladas"]:
        out[c] = out[c].fillna(0).astype(int)
    out = out.rename(columns={"estado": "estado_ensayo"})
    out = out.sort_values("codigo")
    return out[["codigo", "nombre", "estado_ensayo", "total", "pendientes", "realizadas", "canceladas"]]


# ── DOCUMENTOS ───────────────────────────────────────────────────────────────

def documentos_feature_available():
    return _table_exists("documentos") and _table_exists("documentos_visibilidad")


def _validar_tipo_documento(tipo):
    t = _norm_text(tipo)
    if t not in TIPOS_DOCUMENTO:
        raise ValueError("Tipo de documento no válido.")
    return t


def _encode_bytes_to_b64(content_bytes):
    return base64.b64encode(content_bytes).decode("ascii")


def _decode_b64_to_bytes(content_b64):
    return base64.b64decode((content_b64 or "").encode("ascii"))


def create_documento(tipo, nombre_archivo, mime_type, contenido_bytes, subido_por_user_id=None):
    if not documentos_feature_available():
        raise RuntimeError("La funcionalidad de documentos no está disponible. Falta aplicar migración SQL.")

    tipo_n = _validar_tipo_documento(tipo)
    nombre_clean = (nombre_archivo or "").strip()
    if not nombre_clean:
        raise ValueError("El nombre del archivo es obligatorio.")
    if not contenido_bytes:
        raise ValueError("El archivo está vacío.")

    payload = {
        "tipo": tipo_n,
        "nombre_archivo": nombre_clean,
        "mime_type": (mime_type or "application/octet-stream").strip(),
        "contenido_b64": _encode_bytes_to_b64(contenido_bytes),
        "subido_por_user_id": subido_por_user_id,
    }

    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                insert into documentos (tipo, nombre_archivo, mime_type, contenido_b64, subido_por_user_id)
                values (%s, %s, %s, %s, %s)
                returning id
                """,
                [
                    payload["tipo"],
                    payload["nombre_archivo"],
                    payload["mime_type"],
                    payload["contenido_b64"],
                    payload["subido_por_user_id"],
                ],
            )
            row = cur.fetchone() or {}
            return row.get("id")

    res = _sb().table("documentos").insert(payload).execute()
    data = res.data or []
    if not data:
        raise RuntimeError("No se pudo crear el documento.")
    return data[0].get("id")


def set_documento_visible_para_usuarios(documento_id, user_ids):
    if not documentos_feature_available():
        raise RuntimeError("La funcionalidad de documentos no está disponible. Falta aplicar migración SQL.")

    ids = []
    for uid in (user_ids or []):
        if uid is None:
            continue
        try:
            ids.append(int(uid))
        except (TypeError, ValueError):
            continue
    ids = sorted(set(ids))

    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute("delete from documentos_visibilidad where documento_id = %s", [documento_id])
            for uid in ids:
                cur.execute(
                    """
                    insert into documentos_visibilidad (documento_id, usuario_id)
                    values (%s, %s)
                    on conflict (documento_id, usuario_id) do nothing
                    """,
                    [documento_id, uid],
                )
        return

    _sb().table("documentos_visibilidad").delete().eq("documento_id", documento_id).execute()
    if ids:
        rows = [{"documento_id": documento_id, "usuario_id": uid} for uid in ids]
        _sb().table("documentos_visibilidad").insert(rows).execute()


def list_documentos(tipo=None, solo_visibles_para_usuario_id=None):
    if not documentos_feature_available():
        return []

    tipo_n = _norm_text(tipo)
    if tipo_n and tipo_n not in TIPOS_DOCUMENTO:
        return []

    if _using_postgres():
        where = []
        params = []
        if tipo_n:
            where.append("d.tipo = %s")
            params.append(tipo_n)
        if solo_visibles_para_usuario_id is not None:
            where.append(
                "exists (select 1 from documentos_visibilidad dv2 where dv2.documento_id = d.id and dv2.usuario_id = %s)"
            )
            params.append(int(solo_visibles_para_usuario_id))

        query = """
            select
                d.id,
                d.tipo,
                d.nombre_archivo,
                d.mime_type,
                d.contenido_b64,
                d.subido_por_user_id,
                d.creado_en,
                coalesce(string_agg(distinct u.username, ', ' order by u.username), '') as visible_para,
                coalesce(array_agg(distinct dv.usuario_id) filter (where dv.usuario_id is not null), '{}') as visible_user_ids,
                count(distinct dv.usuario_id) as total_visibles
            from documentos d
            left join documentos_visibilidad dv on dv.documento_id = d.id
            left join usuarios u on u.id = dv.usuario_id
        """
        if where:
            query += " where " + " and ".join(where)
        query += " group by d.id order by d.creado_en desc, d.id desc"

        with _pg_conn().cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall() or []

    docs = _sb().table("documentos").select("*").execute().data or []
    vis = _sb().table("documentos_visibilidad").select("documento_id,usuario_id").execute().data or []
    users = _sb().table("usuarios").select("id,username").execute().data or []

    user_map = {u.get("id"): u.get("username", "") for u in users}
    vis_by_doc = {}
    for row in vis:
        doc_id = row.get("documento_id")
        user_id = row.get("usuario_id")
        if doc_id is None or user_id is None:
            continue
        vis_by_doc.setdefault(doc_id, set()).add(user_id)

    out = []
    for d in docs:
        if tipo_n and _norm_text(d.get("tipo")) != tipo_n:
            continue
        visible_set = vis_by_doc.get(d.get("id"), set())
        if solo_visibles_para_usuario_id is not None and int(solo_visibles_para_usuario_id) not in visible_set:
            continue
        usernames = sorted([user_map.get(uid, "") for uid in visible_set if user_map.get(uid, "")])
        item = dict(d)
        item["visible_para"] = ", ".join(usernames)
        item["visible_user_ids"] = sorted(list(visible_set))
        item["total_visibles"] = len(visible_set)
        out.append(item)

    out.sort(key=lambda r: (_norm_text(r.get("creado_en")), int(r.get("id") or 0)), reverse=True)
    return out


def get_documento_by_id(documento_id):
    if not documentos_feature_available():
        return None
    return _get_by_id("documentos", documento_id)


def delete_documento(documento_id):
    if not documentos_feature_available():
        raise RuntimeError("La funcionalidad de documentos no está disponible. Falta aplicar migración SQL.")
    _delete_row_by_id("documentos", documento_id)


def get_usuarios_monitor_activos():
    rows = list_usuarios_monitor()
    out = []
    for r in rows:
        if _norm_text(r.get("rol")) != "monitor":
            continue
        if int(r.get("activo") or 0) != 1:
            continue
        out.append(r)
    return out


def get_documento_bytes(documento_id):
    row = get_documento_by_id(documento_id)
    if not row:
        return None
    return _decode_b64_to_bytes(row.get("contenido_b64", ""))


# ── TAREAS (CHAT) ─────────────────────────────────────────────────────────────

def tareas_feature_available():
    return _table_exists("tareas") and _table_exists("tareas_mensajes")


def create_tarea(titulo, descripcion, monitor_id):
    if not tareas_feature_available():
        raise RuntimeError("La funcionalidad de tareas no está disponible. Falta aplicar migración SQL.")
    
    titulo_clean = (titulo or "").strip()
    descripcion_clean = (descripcion or "").strip()
    if not titulo_clean:
        raise ValueError("El título de la tarea es obligatorio.")
    if monitor_id is None:
        raise ValueError("El monitor es obligatorio.")
    
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                insert into tareas (titulo, descripcion, monitor_id, estado)
                values (%s, %s, %s, %s)
                returning id
                """,
                [titulo_clean, descripcion_clean, monitor_id, "abierta"],
            )
            row = cur.fetchone() or {}
            return row.get("id")
    
    res = _sb().table("tareas").insert({
        "titulo": titulo_clean,
        "descripcion": descripcion_clean,
        "monitor_id": monitor_id,
        "estado": "abierta",
    }).execute()
    data = res.data or []
    if not data:
        raise RuntimeError("No se pudo crear la tarea.")
    return data[0].get("id")


def get_tareas_por_monitor(monitor_id):
    if not tareas_feature_available():
        return []
    
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                select t.id, t.titulo, t.descripcion, t.monitor_id, t.estado, t.creado_en, t.actualizado_en,
                       m.nombre as monitor_nombre, m.apellidos as monitor_apellidos
                from tareas
                join monitores m on m.id = tareas.monitor_id
                where m.ensayo_id = (
                    select ensayo_id
                    from monitores
                    where id = %s
                    limit 1
                )
                order by t.actualizado_en desc, t.creado_en desc
                """,
                [monitor_id],
            )
            return cur.fetchall() or []
    
    monitor = _get_by_id("monitores", monitor_id)
    ensayo_id = monitor.get("ensayo_id") if monitor else None
    if ensayo_id is None:
        return []

    rows = _sb().table("tareas").select("*").order("actualizado_en", desc=True).execute().data or []
    monitores = {m.get("id"): m for m in _fetch_all("monitores")}
    rows = [row for row in rows if (monitores.get(row.get("monitor_id")) or {}).get("ensayo_id") == ensayo_id]

    for row in rows:
        monitor_row = monitores.get(row.get("monitor_id")) or {}
        row["monitor_nombre"] = monitor_row.get("nombre", "")
        row["monitor_apellidos"] = monitor_row.get("apellidos", "")

    return rows


def get_todas_tareas():
    if not tareas_feature_available():
        return []
    
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                select t.id, t.titulo, t.descripcion, t.monitor_id, t.estado, t.creado_en, t.actualizado_en,
                       m.nombre as monitor_nombre, m.apellidos as monitor_apellidos
                from tareas t
                left join monitores m on m.id = t.monitor_id
                order by t.actualizado_en desc, t.creado_en desc
                """
            )
            return cur.fetchall() or []
    
    tareas = _sb().table("tareas").select("*").order("actualizado_en", desc=True).execute().data or []
    monitores = {m.get("id"): m for m in _fetch_all("monitores")}
    
    for tarea in tareas:
        monitor_id = tarea.get("monitor_id")
        monitor = monitores.get(monitor_id) or {}
        tarea["monitor_nombre"] = monitor.get("nombre", "")
        tarea["monitor_apellidos"] = monitor.get("apellidos", "")
    
    return tareas


def get_tarea_by_id(tarea_id):
    if not tareas_feature_available():
        return None
    return _get_by_id("tareas", tarea_id)


def update_estado_tarea(tarea_id, nuevo_estado):
    if not tareas_feature_available():
        raise RuntimeError("La funcionalidad de tareas no está disponible. Falta aplicar migración SQL.")
    
    estados_validos = ("abierta", "en_coordinacion", "cerrada")
    if nuevo_estado not in estados_validos:
        raise ValueError(f"Estado no válido. Debe ser uno de: {', '.join(estados_validos)}")
    
    _update_row_by_id("tareas", tarea_id, {
        "estado": nuevo_estado,
        "actualizado_en": datetime.utcnow().isoformat(),
    })


def add_mensaje_tarea(tarea_id, usuario_id, contenido, tipo="mensaje"):
    if not tareas_feature_available():
        raise RuntimeError("La funcionalidad de tareas no está disponible. Falta aplicar migración SQL.")
    
    tarea = get_tarea_by_id(tarea_id)
    if not tarea:
        raise ValueError("La tarea no existe.")
    
    contenido_clean = (contenido or "").strip()
    if not contenido_clean:
        raise ValueError("El contenido del mensaje no puede estar vacío.")
    
    tipos_validos = ("mensaje", "sistema")
    if tipo not in tipos_validos:
        tipo = "mensaje"
    
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                insert into tareas_mensajes (tarea_id, usuario_id, contenido, tipo)
                values (%s, %s, %s, %s)
                returning id
                """,
                [tarea_id, usuario_id, contenido_clean, tipo],
            )
            row = cur.fetchone() or {}
            msg_id = row.get("id")
    else:
        res = _sb().table("tareas_mensajes").insert({
            "tarea_id": tarea_id,
            "usuario_id": usuario_id,
            "contenido": contenido_clean,
            "tipo": tipo,
        }).execute()
        data = res.data or []
        msg_id = data[0].get("id") if data else None
    
    # Actualizar timestamp de tarea
    _update_row_by_id("tareas", tarea_id, {"actualizado_en": datetime.utcnow().isoformat()})
    
    return msg_id


def get_mensajes_tarea(tarea_id):
    if not tareas_feature_available():
        return []
    
    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute(
                """
                select m.id, m.tarea_id, m.usuario_id, m.contenido, m.tipo, m.creado_en,
                       u.username
                from tareas_mensajes m
                left join usuarios u on u.id = m.usuario_id
                where m.tarea_id = %s
                order by m.creado_en asc
                """,
                [tarea_id],
            )
            return cur.fetchall() or []
    
    mensajes = _sb().table("tareas_mensajes").select("*").eq("tarea_id", tarea_id).order("creado_en", desc=False).execute().data or []
    usuarios = {u.get("id"): u.get("username", "") for u in _fetch_all("usuarios")}
    
    for msg in mensajes:
        msg["username"] = usuarios.get(msg.get("usuario_id"), "")
    
    return mensajes


def delete_tarea(tarea_id):
    if not tareas_feature_available():
        raise RuntimeError("La funcionalidad de tareas no está disponible. Falta aplicar migración SQL.")
    _delete_row_by_id("tareas", tarea_id)
