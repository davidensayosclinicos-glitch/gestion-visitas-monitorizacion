"""
database.py — Capa de acceso a datos (Supabase)
Gestion de Visitas de Monitorizacion — Ensayos Clinicos
"""
import os
from datetime import date, datetime

import pandas as pd

try:
    from supabase import create_client
except Exception:
    create_client = None

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
_SUPABASE_CLIENT = None
MAX_VISITAS_POR_DIA = 2


def get_backend_name():
    return "supabase"


def _norm_text(value):
    return (value or "").strip().lower()


def _sb():
    global _SUPABASE_CLIENT
    if create_client is None:
        raise RuntimeError("Falta la dependencia 'supabase'. Ejecuta: pip install supabase")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "Faltan variables de entorno de Supabase. Define SUPABASE_URL y SUPABASE_KEY. "
            "Consulta SUPABASE_SETUP.md."
        )
    if _SUPABASE_CLIENT is None:
        _SUPABASE_CLIENT = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _SUPABASE_CLIENT


def _supabase_fetch_all(table_name):
    res = _sb().table(table_name).select("*").execute()
    return res.data or []


def _supabase_get_by_id(table_name, entity_id):
    res = _sb().table(table_name).select("*").eq("id", entity_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else None


def get_dias_bloqueados(desde='', hasta=''):
    query = _sb().table("dias_bloqueados").select("fecha,motivo")
    if desde:
        query = query.gte("fecha", desde)
    if hasta:
        query = query.lte("fecha", hasta)
    rows = query.execute().data or []
    rows.sort(key=lambda r: _norm_text(r.get("fecha")))
    return rows


def bloquear_dia(fecha, motivo=''):
    _sb().table("dias_bloqueados").upsert(
        {
            "fecha": fecha,
            "motivo": (motivo or "").strip(),
        },
        on_conflict="fecha",
    ).execute()


def desbloquear_dia(fecha):
    _sb().table("dias_bloqueados").delete().eq("fecha", fecha).execute()


def get_visitas_count_by_date(desde='', hasta=''):
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

    rows = _sb().table("visitas").select("id").eq("fecha", fecha).execute().data or []
    if exclude_visita_id is not None:
        rows = [r for r in rows if r.get("id") != exclude_visita_id]

    if len(rows) >= MAX_VISITAS_POR_DIA:
        raise ValueError(f"No se puede registrar la visita: maximo {MAX_VISITAS_POR_DIA} visitas por dia.")


def init_db():
    # Verifica conectividad y tablas requeridas.
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
    rows = _supabase_fetch_all("ensayos")
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
    return _supabase_get_by_id("ensayos", eid)


def create_ensayo(data):
    _sb().table("ensayos").insert(data).execute()


def update_ensayo(eid, data):
    _sb().table("ensayos").update(data).eq("id", eid).execute()


def delete_ensayo(eid):
    _sb().table("ensayos").delete().eq("id", eid).execute()


# ── MONITORES ─────────────────────────────────────────────────────────────────

def get_monitores(texto=''):
    rows = _supabase_fetch_all("monitores")
    texto_n = _norm_text(texto)

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
    return _supabase_get_by_id("monitores", mid)


def create_monitor(data):
    _sb().table("monitores").insert(data).execute()


def update_monitor(mid, data):
    _sb().table("monitores").update(data).eq("id", mid).execute()


def delete_monitor(mid):
    _sb().table("monitores").delete().eq("id", mid).execute()


# ── VISITAS ───────────────────────────────────────────────────────────────────

def get_visitas_df(texto='', estado='', ensayo_id=None, desde='', hasta=''):
    visitas = pd.DataFrame(_supabase_fetch_all("visitas"))
    ensayos = pd.DataFrame(_supabase_fetch_all("ensayos"))
    monitores = pd.DataFrame(_supabase_fetch_all("monitores"))

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
    return _supabase_get_by_id("visitas", vid)


def create_visita(data):
    _validar_limites_visita(data.get("fecha", ""))
    _sb().table("visitas").insert(data).execute()


def update_visita(vid, data):
    _validar_limites_visita(data.get("fecha", ""), exclude_visita_id=vid)
    data = dict(data)
    data["actualizado_en"] = datetime.utcnow().isoformat()
    _sb().table("visitas").update(data).eq("id", vid).execute()


def delete_visita(vid):
    _sb().table("visitas").delete().eq("id", vid).execute()


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
