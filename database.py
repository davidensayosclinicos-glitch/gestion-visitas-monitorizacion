"""
database.py — Capa de acceso a datos (PostgreSQL/Supabase)
Gestion de Visitas de Monitorizacion — Ensayos Clinicos
"""
import os
from datetime import date, datetime
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
            _PG_CONN = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)
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


def _validar_limites_visita(fecha, exclude_visita_id=None):
    if not fecha:
        raise ValueError("La fecha de la visita es obligatoria.")

    bloqueados = {d.get("fecha") for d in get_dias_bloqueados(desde=fecha, hasta=fecha)}
    if fecha in bloqueados:
        raise ValueError("No se puede registrar la visita: el dia esta bloqueado.")

    if _using_postgres():
        with _pg_conn().cursor() as cur:
            cur.execute("select id from visitas where fecha = %s", [fecha])
            rows = cur.fetchall() or []
    else:
        rows = _sb().table("visitas").select("id").eq("fecha", fecha).execute().data or []
    if exclude_visita_id is not None:
        rows = [r for r in rows if r.get("id") != exclude_visita_id]

    if len(rows) >= MAX_VISITAS_POR_DIA:
        raise ValueError(f"No se puede registrar la visita: maximo {MAX_VISITAS_POR_DIA} visitas por dia.")


def init_db():
    # Verifica conectividad y tablas requeridas.
    required = ["ensayos", "monitores", "visitas", "dias_bloqueados"]

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


def create_visita(data):
    _validar_limites_visita(data.get("fecha", ""))
    _insert_row("visitas", data)


def update_visita(vid, data):
    _validar_limites_visita(data.get("fecha", ""), exclude_visita_id=vid)
    data = dict(data)
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
