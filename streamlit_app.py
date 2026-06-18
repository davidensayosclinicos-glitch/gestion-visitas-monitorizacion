"""
streamlit_app.py — Gestión de Visitas de Monitorización
Coordinación de Ensayos Clínicos
"""
import calendar
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta

from database import (
    init_db, get_backend_name,
    get_ensayos, get_ensayo_by_id, create_ensayo, update_ensayo, delete_ensayo,
    get_monitores, get_monitor_by_id, create_monitor, update_monitor, delete_monitor,
    get_visitas_df, get_visita_by_id, create_visita, create_visitas_rango, update_visita, delete_visita,
    get_stats, get_proximas_visitas, get_resumen_por_ensayo,
    get_dias_bloqueados, bloquear_dia, bloquear_rango, desbloquear_dia, desbloquear_rango, get_visitas_count_by_date,
)

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Visitas de Monitorización",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Gestión de Visitas de Monitorización — Ensayos Clínicos"},
)

try:
    init_db()
except RuntimeError as ex:
    st.error(str(ex))
    st.divider()
    st.subheader("Cómo configurar")
    with st.expander("📋 Para PostgreSQL directo (DATABASE_URL)", expanded=True):
        st.markdown("""
        **En Streamlit Cloud:**
        1. Abre tu app → **Manage app** (esquina inferior derecha)
        2. Ve a **Secrets** 
        3. Agrega:
        ```
        DATABASE_URL="postgresql://usuario:contraseña@host:5432/nombre_bd"
        ```
        4. Haz refresh de la app
        """)
    with st.expander("☁️ Para Supabase API (SUPABASE_URL + SUPABASE_KEY)"):
        st.markdown("""
        **En Streamlit Cloud → Secrets:**
        ```
        SUPABASE_URL="https://xxxx.supabase.co"
        SUPABASE_KEY="your-api-key"
        ```

        También se aceptan estos nombres habituales para la clave:
        - `SUPABASE_ANON_KEY`
        - `SUPABASE_SERVICE_ROLE_KEY`

        Si PostgreSQL directo o el pooler fallan en Streamlit Cloud, esta opción evita el problema de red/autenticación del conector PostgreSQL.
        """)
    st.stop()

# ── CONSTANTES ────────────────────────────────────────────────────────────────
ESTADOS_VISITA = ["pendiente", "confirmada", "realizada", "cancelada"]
TIPOS_VISITA = [
    "Visita de Inicio", "Visita de Monitorización", "Visita de Cierre",
    "Auditoría", "Inspección", "Teleconferencia", "Otra",
]
FASES_ENSAYO  = ["", "Fase I", "Fase II", "Fase III", "Fase IV", "Observacional"]
ESTADOS_ENSAYO = ["activo", "en_pausa", "cerrado"]

ESTADO_LABEL = {
    "pendiente": "🟡 Pendiente", "confirmada": "🔵 Confirmada",
    "realizada":  "🟢 Realizada",  "cancelada": "🔴 Cancelada",
    "activo":     "🟢 Activo",    "en_pausa":  "🟡 En pausa",  "cerrado": "⚫ Cerrado",
}


def elabel(e):
    return f"{e['codigo']} — {e['nombre']}"


def mlabel(m):
    extra = f" ({m['empresa']})" if m['empresa'] else ""
    return f"{m['nombre']} {m['apellidos']}{extra}"


def render_month_calendar(year: int, month: int, visitas_por_dia: dict, bloqueados: dict):
    week_names = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)
    # Cuadricula fija de 6 semanas para mantener consistencia visual todos los meses.
    while len(weeks) < 6:
        last_day = weeks[-1][-1]
        weeks.append([last_day + timedelta(days=i) for i in range(1, 8)])

    html = """
    <style>
    .gvm-cal { width: 100%; border-collapse: collapse; table-layout: fixed; }
    .gvm-cal th { text-align: center; padding: 6px; font-size: 0.85rem; color: #444; }
    .gvm-cal td { border: 1px solid #e6e6e6; vertical-align: top; height: 86px; padding: 6px; border-radius: 8px; }
    .gvm-day { font-weight: 700; margin-bottom: 6px; }
    .gvm-outside { background: #fafafa; color: #888; }
    .gvm-state-ok { background: #f7fbf7; }
    .gvm-state-mid { background: #fff8e8; }
    .gvm-state-full { background: #ffe9e9; }
    .gvm-state-locked { background: #eceff3; }
    .gvm-chip { display: inline-block; font-size: 0.78rem; padding: 2px 6px; border-radius: 999px; background: #fff; border: 1px solid #d9d9d9; }
    </style>
    """

    html += "<table class='gvm-cal'><thead><tr>"
    for w in week_names:
        html += f"<th>{w}</th>"
    html += "</tr></thead><tbody>"

    for week in weeks:
        html += "<tr>"
        for day in week:
            f = day.isoformat()
            n = int(visitas_por_dia.get(f, 0))
            is_blocked = f in bloqueados
            in_current_month = day.month == month

            # Determinar máximo de visitas permitidas para este día
            max_visitas_dia = 2  # default global
            if is_blocked:
                motivo = bloqueados[f]
                # Parsear "max:X" o "max:X - comentario"
                if motivo.startswith("max:"):
                    try:
                        max_visitas_dia = int(motivo.split(":")[1].split()[0].split("-")[0])
                    except (ValueError, IndexError):
                        max_visitas_dia = 0  # Si no se puede parsear, bloqueo total

            # Asignar clase CSS según estado
            if is_blocked and max_visitas_dia == 0:
                cls = "gvm-state-locked"
                chip = "Bloqueado"
            elif is_blocked and max_visitas_dia == 1:
                cls = "gvm-state-mid"
                chip = "Max 1 visita"
            elif n >= max_visitas_dia and max_visitas_dia > 0:
                cls = "gvm-state-full"
                chip = f"{n} visitas"
            elif n == 1:
                cls = "gvm-state-mid"
                chip = "1 visita"
            else:
                cls = "gvm-state-ok"
                chip = "Libre"

            if not in_current_month:
                cls = "gvm-outside"

            html += (
                f"<td class='{cls}'>"
                f"<div class='gvm-day'>{day.day}</div>"
                f"<span class='gvm-chip'>{chip}</span>"
                "</td>"
            )
        html += "</tr>"
    html += "</tbody></table>"

    st.markdown(html, unsafe_allow_html=True)


def render_calendario_general(section_key: str):
    st.subheader("🗓️ Calendario general de visitas")
    s1, s2, s3 = st.columns([1, 1, 3])
    anio = s1.selectbox("Año", list(range(2024, 2036)), index=date.today().year - 2024, key=f"{section_key}_anio")
    mes = s2.selectbox("Mes", list(range(1, 13)), index=date.today().month - 1, key=f"{section_key}_mes",
                       format_func=lambda x: calendar.month_name[x])
    s3.caption("Regla: maximo 2 visitas por dia. Los dias bloqueados no aceptan visitas.")

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(anio, mes)
    while len(weeks) < 6:
        last_day = weeks[-1][-1]
        weeks.append([last_day + timedelta(days=i) for i in range(1, 8)])

    desde_grid = weeks[0][0].isoformat()
    hasta_grid = weeks[-1][-1].isoformat()

    try:
        visitas_por_dia = get_visitas_count_by_date(desde=desde_grid, hasta=hasta_grid)
        bloqueados_rows = get_dias_bloqueados(desde=desde_grid, hasta=hasta_grid)
        bloqueados_map = {r.get("fecha"): r.get("motivo", "") for r in bloqueados_rows}
        render_month_calendar(anio, mes, visitas_por_dia, bloqueados_map)
    except Exception as ex:
        st.error(
            "No se pudo cargar el calendario de bloqueos. "
            "Verifica que exista la tabla public.dias_bloqueados en Supabase."
        )
        st.caption(f"Detalle técnico: {ex}")
        bloqueados_rows = []

    st.caption("Leyenda: Libre (sin bloqueo), Bloqueado (0 visitas), Solo 1 visita, Normal (2 visitas).")

    # Opción de rango de fechas para bloqueos
    col_rango_bloqueo = st.columns(1)[0]
    es_rango_bloqueo = col_rango_bloqueo.checkbox("Bloquear un rango de fechas", value=False, key=f"{section_key}_rango_check")
    
    if es_rango_bloqueo:
        b1, b2 = st.columns(2)
        fecha_bloqueo_desde = b1.date_input("Desde", value=date.today(), key=f"{section_key}_fecha_desde")
        fecha_bloqueo_hasta = b2.date_input("Hasta", value=date.today(), key=f"{section_key}_fecha_hasta")
    else:
        b1 = st.columns(1)[0]
        fecha_bloqueo = b1.date_input("Día a bloquear", value=date.today(), key=f"{section_key}_fecha_bloqueo")
    
    b_cols = st.columns([2, 1, 1, 1])
    max_visitas = b_cols[0].selectbox(
        "Máximo de visitas",
        [2, 1, 0],
        format_func=lambda x: f"{x} visita(s)" if x > 0 else "Bloqueado",
        key=f"{section_key}_max_visitas"
    )
    motivo_bloqueo = st.text_input("Motivo", placeholder="Opcional", key=f"{section_key}_motivo_bloqueo")
    
    col_btn = st.columns([1, 1])
    if col_btn[0].button("Bloquear", use_container_width=True, key=f"{section_key}_bloquear"):
        try:
            # Guardar max_visitas en el campo motivo como "max:X"
            motivo = f"max:{max_visitas}"
            if motivo_bloqueo.strip():
                motivo += f" - {motivo_bloqueo.strip()}"
            
            if es_rango_bloqueo:
                if fecha_bloqueo_desde > fecha_bloqueo_hasta:
                    st.error("La fecha inicial no puede ser mayor que la fecha final.")
                else:
                    bloquear_rango(fecha_bloqueo_desde.isoformat(), fecha_bloqueo_hasta.isoformat(), motivo)
                    dias_bloqueados = (fecha_bloqueo_hasta - fecha_bloqueo_desde).days + 1
                    st.success(f"Rango de {dias_bloqueados} días bloqueado.")
                    st.rerun()
            else:
                bloquear_dia(fecha_bloqueo.isoformat(), motivo)
                st.success(f"Día bloqueado (máximo {max_visitas} visita(s)).")
                st.rerun()
        except Exception as ex:
            st.error(f"No se pudo bloquear: {ex}")
    
    if col_btn[1].button("Desbloquear", use_container_width=True, key=f"{section_key}_desbloquear"):
        try:
            if es_rango_bloqueo:
                if fecha_bloqueo_desde > fecha_bloqueo_hasta:
                    st.error("La fecha inicial no puede ser mayor que la fecha final.")
                else:
                    desbloquear_rango(fecha_bloqueo_desde.isoformat(), fecha_bloqueo_hasta.isoformat())
                    dias_desbloqueados = (fecha_bloqueo_hasta - fecha_bloqueo_desde).days + 1
                    st.success(f"Rango de {dias_desbloqueados} días desbloqueado.")
                    st.rerun()
            else:
                desbloquear_dia(fecha_bloqueo.isoformat())
                st.success("Día desbloqueado.")
                st.rerun()
        except Exception as ex:
            st.error(f"No se pudo desbloquear: {ex}")

    bloqueados_mes = [r for r in bloqueados_rows if r.get("fecha", "").startswith(f"{anio:04d}-{mes:02d}-")]
    if bloqueados_mes:
        df_b = pd.DataFrame(bloqueados_mes)
        # Parsear máximo de visitas del motivo
        def parse_max_visitas(motivo):
            if not motivo or not motivo.startswith("max:"):
                return "Bloqueado"
            try:
                max_v = int(motivo.split(":")[1].split()[0].split("-")[0])
                if max_v == 0:
                    return "Bloqueado (0)"
                elif max_v == 1:
                    return "Reducido (1)"
                else:
                    return "Normal (2)"
            except (ValueError, IndexError):
                return "Bloqueado"
        
        df_b["max_visitas"] = df_b["motivo"].apply(parse_max_visitas)
        df_b = df_b.rename(columns={"fecha": "Fecha", "motivo": "Detalle", "max_visitas": "Máximo"})
        st.dataframe(df_b[["Fecha", "Máximo", "Detalle"]], use_container_width=True, hide_index=True)
    else:
        st.info("No hay dias bloqueados en este mes.")


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 Monitorización")
    st.caption("Coordinación de Ensayos Clínicos")
    backend = get_backend_name()
    if backend == "postgres":
        st.caption("Backend: 🐘 PostgreSQL (DATABASE_URL)")
    else:
        st.caption("Backend: ☁️ Supabase API")
    st.divider()

    nav = st.radio(
        "Navegación",
        ["🏠 Inicio", "📅 Visitas", "👥 Monitores", "📋 Ensayos"],
        label_visibility="collapsed",
    )

    st.divider()

    with st.expander("💾 Copia de seguridad"):
        st.info("Los datos se guardan directamente en Supabase.")


# ── DIALOGS: VISITAS ──────────────────────────────────────────────────────────

@st.dialog("Nueva Visita", width="large")
def dialog_nueva_visita():
    ensayos   = get_ensayos()
    if not ensayos:
        st.warning("⚠️ Primero debes crear al menos un **Ensayo** en la sección correspondiente.")
        return

    with st.form("form_nueva_visita"):
        ei = st.selectbox("Ensayo *", range(len(ensayos)), format_func=lambda i: elabel(ensayos[i]))
        ensayo_id_sel = ensayos[ei]["id"]
        
        monitores = get_monitores(ensayo_id=ensayo_id_sel)
        if not monitores:
            st.warning(f"⚠️ No hay monitores asociados a este ensayo. Crea uno en la sección **Monitores**.")
            return
        
        monitor_id_sel = monitores[0]["id"]
        if len(monitores) == 1:
            st.info(f"📍 Monitor asignado: **{mlabel(monitores[0])}**")
        else:
            mi = st.selectbox("Monitor *", range(len(monitores)), format_func=lambda i: mlabel(monitores[i]))
            monitor_id_sel = monitores[mi]["id"]

        # Opción de rango de fechas
        col_rango = st.columns(1)[0]
        es_rango = col_rango.checkbox("Crear visitas para un rango de fechas", value=False, key="visita_rango_check")
        
        if es_rango:
            c3, c4 = st.columns(2)
            fecha_desde = c3.date_input("Desde *", value=date.today(), key="visita_desde")
            fecha_hasta = c4.date_input("Hasta *", value=date.today(), key="visita_hasta")
            hora_val = st.time_input("Hora", value=datetime.strptime("09:00", "%H:%M").time(), step=900)
        else:
            c3, c4 = st.columns(2)
            fecha = c3.date_input("Fecha *", value=date.today())
            hora_val = c4.time_input("Hora", value=datetime.strptime("09:00", "%H:%M").time(), step=900)

        c5, c6 = st.columns(2)
        tipo   = c5.selectbox("Tipo de visita *", TIPOS_VISITA)
        estado = c6.selectbox("Estado", ESTADOS_VISITA, format_func=lambda x: ESTADO_LABEL.get(x, x))

        notas = st.text_area("Notas", height=80,
                             placeholder="Observaciones, documentos solicitados, incidencias...")

        if st.form_submit_button("💾 Guardar visita(s)", use_container_width=True, type="primary"):
            try:
                if es_rango:
                    if fecha_desde > fecha_hasta:
                        st.error("La fecha inicial no puede ser mayor que la fecha final.")
                        return
                    count = create_visitas_rango({
                        "ensayo_id":  ensayo_id_sel,
                        "monitor_id": monitor_id_sel,
                        "hora":       hora_val.strftime("%H:%M"),
                        "tipo":       tipo,
                        "estado":     estado,
                        "notas":      notas.strip(),
                    }, fecha_desde.isoformat(), fecha_hasta.isoformat())
                    st.success(f"✅ {count} visita(s) registrada(s) correctamente.")
                else:
                    create_visita({
                        "ensayo_id":  ensayo_id_sel,
                        "monitor_id": monitor_id_sel,
                        "fecha":      fecha.isoformat(),
                        "hora":       hora_val.strftime("%H:%M"),
                        "tipo":       tipo,
                        "estado":     estado,
                        "notas":      notas.strip(),
                    })
                    st.success("✅ Visita registrada correctamente.")
            except ValueError as ex:
                st.error(str(ex))
                return
            st.rerun()


@st.dialog("Editar Visita", width="large")
def dialog_editar_visita(visita_id: int):
    v = get_visita_by_id(visita_id)
    if not v:
        st.error("Visita no encontrada.")
        return

    ensayos   = get_ensayos()
    e_ids = [e["id"] for e in ensayos]
    e_idx = e_ids.index(v["ensayo_id"])  if v["ensayo_id"]  in e_ids else 0
    
    monitores = get_monitores(ensayo_id=v["ensayo_id"])
    m_ids = [m["id"] for m in monitores]
    m_idx = m_ids.index(v["monitor_id"]) if v["monitor_id"] in m_ids else 0
    hora_default = datetime.strptime(v["hora"], "%H:%M").time() if v["hora"] else datetime.strptime("09:00", "%H:%M").time()

    with st.form("form_editar_visita"):
        ei = st.selectbox("Ensayo *",   range(len(ensayos)),   index=e_idx, format_func=lambda i: elabel(ensayos[i]))
        
        monitores_new = get_monitores(ensayo_id=ensayos[ei]["id"])
        m_idx_new = 0
        if monitores_new:
            m_ids_new = [m["id"] for m in monitores_new]
            m_idx_new = m_ids_new.index(v["monitor_id"]) if v["monitor_id"] in m_ids_new else 0
        
        if len(monitores_new) == 1:
            st.info(f"📍 Monitor asignado: **{mlabel(monitores_new[0])}**")
            mi = 0
        else:
            mi = st.selectbox("Monitor *",  range(len(monitores_new)), index=m_idx_new, format_func=lambda i: mlabel(monitores_new[i]))
        
        monitores = monitores_new

        c3, c4 = st.columns(2)
        fecha    = c3.date_input("Fecha *", value=date.fromisoformat(v["fecha"]))
        hora_val = c4.time_input("Hora", value=hora_default, step=900)

        c5, c6 = st.columns(2)
        tipo_idx = TIPOS_VISITA.index(v["tipo"]) if v["tipo"] in TIPOS_VISITA else 0
        tipo     = c5.selectbox("Tipo de visita *", TIPOS_VISITA, index=tipo_idx)
        est_idx  = ESTADOS_VISITA.index(v["estado"]) if v["estado"] in ESTADOS_VISITA else 0
        estado   = c6.selectbox("Estado", ESTADOS_VISITA, index=est_idx,
                                format_func=lambda x: ESTADO_LABEL.get(x, x))

        notas = st.text_area("Notas", value=v["notas"], height=80)

        if st.form_submit_button("💾 Guardar cambios", use_container_width=True, type="primary"):
            try:
                update_visita(visita_id, {
                    "ensayo_id":  ensayos[ei]["id"],
                    "monitor_id": monitores[mi]["id"],
                    "fecha":      fecha.isoformat(),
                    "hora":       hora_val.strftime("%H:%M"),
                    "tipo":       tipo,
                    "estado":     estado,
                    "notas":      notas.strip(),
                })
            except ValueError as ex:
                st.error(str(ex))
                return
            st.success("✅ Visita actualizada.")
            st.rerun()


# ── DIALOGS: MONITORES ────────────────────────────────────────────────────────

@st.dialog("Nuevo Monitor", width="large")
def dialog_nuevo_monitor():
    ensayos = get_ensayos()
    if not ensayos:
        st.warning("⚠️ Primero debes crear al menos un **Ensayo**.")
        return

    with st.form("form_nuevo_monitor"):
        ei = st.selectbox("Ensayo *", range(len(ensayos)), format_func=lambda i: elabel(ensayos[i]))

        c1, c2 = st.columns(2)
        nombre    = c1.text_input("Nombre *")
        apellidos = c2.text_input("Apellidos *")

        c3, c4 = st.columns(2)
        empresa  = c3.text_input("CRO / Empresa")
        email    = c4.text_input("Email")

        c5, c6 = st.columns(2)
        telefono = c5.text_input("Teléfono")
        activo   = c6.selectbox("Estado", [True, False],
                                format_func=lambda x: "Activo" if x else "Inactivo")
        notas = st.text_area("Notas", height=60)

        if st.form_submit_button("💾 Guardar", use_container_width=True, type="primary"):
            if not nombre.strip() or not apellidos.strip():
                st.error("Nombre y apellidos son obligatorios.")
                return
            if email.strip() and "@" not in email:
                st.error("El formato del email no es válido.")
                return
            create_monitor({
                "nombre": nombre.strip(), "apellidos": apellidos.strip(),
                "empresa": empresa.strip(), "email": email.strip(),
                "telefono": telefono.strip(), "activo": 1 if activo else 0,
                "notas": notas.strip(),
                "ensayo_id": ensayos[ei]["id"],
            })
            st.success("✅ Monitor creado.")
            st.rerun()


@st.dialog("Editar Monitor", width="large")
def dialog_editar_monitor(monitor_id: int):
    m = get_monitor_by_id(monitor_id)
    if not m:
        st.error("Monitor no encontrado.")
        return

    ensayos = get_ensayos()
    ensayo_nombre = ""
    for e in ensayos:
        if e["id"] == m.get("ensayo_id"):
            ensayo_nombre = elabel(e)
            break

    with st.form("form_editar_monitor"):
        st.info(f"Asociado a: **{ensayo_nombre}** (no se puede cambiar)")

        c1, c2 = st.columns(2)
        nombre    = c1.text_input("Nombre *",    value=m["nombre"])
        apellidos = c2.text_input("Apellidos *", value=m["apellidos"])

        c3, c4 = st.columns(2)
        empresa  = c3.text_input("CRO / Empresa", value=m["empresa"])
        email    = c4.text_input("Email",          value=m["email"])

        c5, c6 = st.columns(2)
        telefono = c5.text_input("Teléfono", value=m["telefono"])
        activo   = c6.selectbox("Estado", [True, False],
                                index=0 if bool(m["activo"]) else 1,
                                format_func=lambda x: "Activo" if x else "Inactivo")
        notas = st.text_area("Notas", value=m["notas"], height=60)

        if st.form_submit_button("💾 Guardar cambios", use_container_width=True, type="primary"):
            if not nombre.strip() or not apellidos.strip():
                st.error("Nombre y apellidos son obligatorios.")
                return
            if email.strip() and "@" not in email:
                st.error("El formato del email no es válido.")
                return
            update_monitor(monitor_id, {
                "nombre": nombre.strip(), "apellidos": apellidos.strip(),
                "empresa": empresa.strip(), "email": email.strip(),
                "telefono": telefono.strip(), "activo": 1 if activo else 0,
                "notas": notas.strip(),
                "ensayo_id": m.get("ensayo_id"),  # Mantener el ensayo original
            })
            st.success("✅ Monitor actualizado.")
            st.rerun()


# ── DIALOGS: ENSAYOS ──────────────────────────────────────────────────────────

@st.dialog("Nuevo Ensayo", width="large")
def dialog_nuevo_ensayo():
    with st.form("form_nuevo_ensayo"):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código / Protocolo *", placeholder="Ej: ABC-2024-001")
        nombre = c2.text_input("Nombre del ensayo *")

        c3, c4 = st.columns(2)
        promotor = c3.text_input("Promotor")
        fase     = c4.selectbox("Fase", FASES_ENSAYO)

        c5, c6 = st.columns(2)
        ip     = c5.text_input("Investigador Principal")
        estado = c6.selectbox("Estado", ESTADOS_ENSAYO,
                              format_func=lambda x: ESTADO_LABEL.get(x, x))

        c7, c8 = st.columns(2)
        fecha_inicio = c7.date_input("Fecha inicio",        value=None)
        fecha_fin    = c8.date_input("Fecha fin prevista",  value=None)

        notas = st.text_area("Notas", height=60)

        if st.form_submit_button("💾 Guardar", use_container_width=True, type="primary"):
            if not codigo.strip() or not nombre.strip():
                st.error("Código y nombre son obligatorios.")
                return
            create_ensayo({
                "codigo": codigo.strip(), "nombre": nombre.strip(),
                "promotor": promotor.strip(), "fase": fase, "ip": ip.strip(),
                "estado": estado,
                "fecha_inicio": fecha_inicio.isoformat() if fecha_inicio else "",
                "fecha_fin":    fecha_fin.isoformat()    if fecha_fin    else "",
                "notas": notas.strip(),
            })
            st.success("✅ Ensayo creado.")
            st.rerun()


@st.dialog("Editar Ensayo", width="large")
def dialog_editar_ensayo(ensayo_id: int):
    e = get_ensayo_by_id(ensayo_id)
    if not e:
        st.error("Ensayo no encontrado.")
        return

    with st.form("form_editar_ensayo"):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código / Protocolo *", value=e["codigo"])
        nombre = c2.text_input("Nombre del ensayo *",  value=e["nombre"])

        c3, c4 = st.columns(2)
        promotor  = c3.text_input("Promotor", value=e["promotor"])
        fase_idx  = FASES_ENSAYO.index(e["fase"]) if e["fase"] in FASES_ENSAYO else 0
        fase      = c4.selectbox("Fase", FASES_ENSAYO, index=fase_idx)

        c5, c6 = st.columns(2)
        ip      = c5.text_input("Investigador Principal", value=e["ip"])
        est_idx = ESTADOS_ENSAYO.index(e["estado"]) if e["estado"] in ESTADOS_ENSAYO else 0
        estado  = c6.selectbox("Estado", ESTADOS_ENSAYO, index=est_idx,
                               format_func=lambda x: ESTADO_LABEL.get(x, x))

        c7, c8 = st.columns(2)
        fi_val = date.fromisoformat(e["fecha_inicio"]) if e["fecha_inicio"] else None
        ff_val = date.fromisoformat(e["fecha_fin"])    if e["fecha_fin"]    else None
        fecha_inicio = c7.date_input("Fecha inicio",       value=fi_val)
        fecha_fin    = c8.date_input("Fecha fin prevista", value=ff_val)

        notas = st.text_area("Notas", value=e["notas"], height=60)

        if st.form_submit_button("💾 Guardar cambios", use_container_width=True, type="primary"):
            if not codigo.strip() or not nombre.strip():
                st.error("Código y nombre son obligatorios.")
                return
            update_ensayo(ensayo_id, {
                "codigo": codigo.strip(), "nombre": nombre.strip(),
                "promotor": promotor.strip(), "fase": fase, "ip": ip.strip(),
                "estado": estado,
                "fecha_inicio": fecha_inicio.isoformat() if fecha_inicio else "",
                "fecha_fin":    fecha_fin.isoformat()    if fecha_fin    else "",
                "notas": notas.strip(),
            })
            st.success("✅ Ensayo actualizado.")
            st.rerun()


# ── DIALOG: CONFIRMAR BORRADO ─────────────────────────────────────────────────

@st.dialog("Confirmar eliminación")
def dialog_confirmar_delete(entity_type: str, entity_id: int, entity_name: str):
    st.warning(f"¿Eliminar **{entity_name}**?\n\nEsta acción **no se puede deshacer**.")
    c1, c2 = st.columns(2)
    if c1.button("🗑️ Sí, eliminar", type="primary", use_container_width=True):
        if entity_type == "visita":
            delete_visita(entity_id)
        elif entity_type == "monitor":
            delete_monitor(entity_id)
        elif entity_type == "ensayo":
            delete_ensayo(entity_id)
        st.rerun()
    if c2.button("Cancelar", use_container_width=True):
        st.rerun()


# ── PÁGINA: INICIO ────────────────────────────────────────────────────────────

def page_dashboard():
    st.header("🏠 Panel de Control")

    stats = get_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📅 Visitas este mes",          stats["total_mes"])
    c2.metric("⏳ Pendientes / Confirmadas",   stats["pendientes"])
    c3.metric("✅ Realizadas (total)",         stats["realizadas"])
    c4.metric("🔬 Ensayos activos",            stats["ensayos_activos"])

    st.divider()
    render_calendario_general("home")

    st.divider()

    col_a, col_b = st.columns([3, 2])

    with col_a:
        st.subheader("📅 Próximas Visitas")
        df_prox = get_proximas_visitas(10)
        if df_prox.empty:
            st.info("No hay visitas próximas programadas.")
        else:
            df_prox["fecha"] = pd.to_datetime(df_prox["fecha"]).dt.strftime("%d/%m/%Y")
            df_prox["estado"] = df_prox["estado"].map(ESTADO_LABEL)
            df_prox.columns = ["Fecha", "Hora", "Tipo", "Estado", "Monitor", "Ensayo"]
            st.dataframe(df_prox, use_container_width=True, hide_index=True)

    with col_b:
        st.subheader("📋 Resumen por Ensayo")
        df_res = get_resumen_por_ensayo()
        if df_res.empty:
            st.info("Sin datos.")
        else:
            df_res["estado_ensayo"] = df_res["estado_ensayo"].map(ESTADO_LABEL)
            df_res.columns = ["Código", "Nombre", "Estado", "Total", "Pend.", "Realiz.", "Cancel."]
            st.dataframe(df_res, use_container_width=True, hide_index=True)


# ── PÁGINA: VISITAS ───────────────────────────────────────────────────────────

def page_visitas():
    col_h, col_btn = st.columns([5, 1])
    col_h.header("📅 Visitas de Monitorización")
    if col_btn.button("➕ Nueva Visita", use_container_width=True, type="primary"):
        dialog_nueva_visita()

    st.caption("El calendario y bloqueos se gestionan desde la pantalla Inicio.")

    # Filtros
    with st.expander("🔍 Filtros", expanded=True):
        c1, c2, c3, c4, c5 = st.columns([2, 1, 2, 1, 1])
        f_texto  = c1.text_input("Buscar", placeholder="Monitor, ensayo, tipo...",
                                 label_visibility="collapsed")
        f_estado = c2.selectbox("Estado", [""] + ESTADOS_VISITA,
                                format_func=lambda x: ESTADO_LABEL.get(x, "Todos los estados"),
                                label_visibility="collapsed")
        ensayos_list = get_ensayos()
        ensayo_opts  = {e["id"]: elabel(e) for e in ensayos_list}
        f_ensayo_id  = c3.selectbox(
            "Ensayo", [None] + list(ensayo_opts.keys()),
            format_func=lambda x: ensayo_opts.get(x, "Todos los ensayos"),
            label_visibility="collapsed",
        )
        f_desde = c4.date_input("Desde", value=None, label_visibility="collapsed")
        f_hasta = c5.date_input("Hasta", value=None, label_visibility="collapsed")

    df = get_visitas_df(
        texto=f_texto,
        estado=f_estado,
        ensayo_id=f_ensayo_id,
        desde=f_desde.isoformat() if f_desde else "",
        hasta=f_hasta.isoformat() if f_hasta else "",
    )

    if df.empty:
        st.info("No hay visitas que coincidan con los filtros.")
        return

    # Exportar CSV
    c_info, c_exp = st.columns([4, 1])
    c_info.caption(f"**{len(df)}** visita(s) encontradas.")
    csv_data = df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
    c_exp.download_button(
        "⬇️ Exportar CSV",
        data=csv_data,
        file_name=f"visitas_{date.today()}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # Tabla
    display_cols = ["id", "fecha", "hora", "monitor_nombre", "ensayo_codigo", "tipo", "estado", "notas"]
    df_show = df[display_cols].copy()
    df_show["fecha"]  = pd.to_datetime(df_show["fecha"]).dt.strftime("%d/%m/%Y")
    df_show["estado"] = df_show["estado"].map(ESTADO_LABEL)
    df_show["notas"]  = df_show["notas"].str[:60]
    df_show.columns   = ["ID", "Fecha", "Hora", "Monitor", "Ensayo", "Tipo", "Estado", "Notas"]

    event = st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="sel_visitas",
    )

    selected = event.selection.rows
    if selected:
        row_idx = selected[0]
        sel_id   = int(df.iloc[row_idx]["id"])
        sel_tipo = df.iloc[row_idx]["tipo"]

        st.divider()
        ca, cb, _ = st.columns([1, 1, 4])
        if ca.button("✏️ Editar seleccionada", use_container_width=True):
            dialog_editar_visita(sel_id)
        if cb.button("🗑️ Eliminar seleccionada", use_container_width=True):
            dialog_confirmar_delete("visita", sel_id, sel_tipo)


# ── PÁGINA: MONITORES ─────────────────────────────────────────────────────────

def page_monitores():
    col_h, col_btn = st.columns([5, 1])
    col_h.header("👥 Monitores")
    if col_btn.button("➕ Nuevo Monitor", use_container_width=True, type="primary"):
        dialog_nuevo_monitor()

    ensayos = get_ensayos()
    c1, c2 = st.columns([2, 3])
    
    if ensayos:
        ensayo_opts = {e["id"]: elabel(e) for e in ensayos}
        ensayo_id = c1.selectbox(
            "Filtrar por ensayo",
            [None] + list(ensayo_opts.keys()),
            format_func=lambda x: ensayo_opts.get(x, "Todos los ensayos"),
            label_visibility="collapsed",
        )
    else:
        c1.warning("No hay ensayos. Crea uno primero.")
        ensayo_id = None

    f_texto = c2.text_input("🔍 Buscar", placeholder="Nombre, apellidos, empresa...",
                             label_visibility="collapsed")
    monitores = get_monitores(texto=f_texto, ensayo_id=ensayo_id)

    if not monitores:
        msg = "No hay monitores registrados." if not f_texto else "No hay monitores que coincidan."
        st.info(msg)
        return

    # Conteo de visitas por monitor (una sola consulta)
    df_v = get_visitas_df()

    cols_per_row = 2
    for i in range(0, len(monitores), cols_per_row):
        row_items = monitores[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for j, m in enumerate(row_items):
            with cols[j]:
                mv = df_v[df_v["monitor_id"] == m["id"]] if not df_v.empty else pd.DataFrame()
                total      = len(mv)
                pendientes = len(mv[mv["estado"].isin(["pendiente", "confirmada"])]) if total > 0 else 0

                with st.container(border=True):
                    h_col, btn_col = st.columns([4, 1])
                    with h_col:
                        badge = "🟢" if m["activo"] else "⚫"
                        st.markdown(f"**{badge} {m['nombre']} {m['apellidos']}**")
                        if m["empresa"]:  st.caption(f"🏢 {m['empresa']}")
                        if m["email"]:    st.caption(f"✉️ {m['email']}")
                        if m["telefono"]: st.caption(f"📞 {m['telefono']}")
                        pend_txt = f" · ⏳ {pendientes} pendientes" if pendientes else ""
                        st.caption(f"📅 {total} visitas{pend_txt}")
                    with btn_col:
                        if st.button("✏️", key=f"em_{m['id']}", help="Editar monitor"):
                            dialog_editar_monitor(m["id"])
                        if st.button("🗑️", key=f"dm_{m['id']}", help="Eliminar monitor"):
                            dialog_confirmar_delete("monitor", m["id"],
                                                    f"{m['nombre']} {m['apellidos']}")


# ── PÁGINA: ENSAYOS ───────────────────────────────────────────────────────────

def page_ensayos():
    col_h, col_btn = st.columns([5, 1])
    col_h.header("📋 Ensayos Clínicos")
    if col_btn.button("➕ Nuevo Ensayo", use_container_width=True, type="primary"):
        dialog_nuevo_ensayo()

    c1, c2 = st.columns([3, 1])
    f_texto  = c1.text_input("🔍 Buscar", placeholder="Código, nombre, promotor...",
                              label_visibility="collapsed")
    f_estado = c2.selectbox("Estado", [""] + ESTADOS_ENSAYO,
                            format_func=lambda x: ESTADO_LABEL.get(x, "Todos"),
                            label_visibility="collapsed")

    ensayos = get_ensayos(texto=f_texto, estado=f_estado)
    if not ensayos:
        msg = "No hay ensayos registrados." if not f_texto else "No hay ensayos que coincidan."
        st.info(msg)
        return

    df_v = get_visitas_df()

    rows = []
    for e in ensayos:
        ev    = df_v[df_v["ensayo_id"] == e["id"]] if not df_v.empty else pd.DataFrame()
        rows.append({
            "_id":          e["id"],
            "Código":       e["codigo"],
            "Nombre":       e["nombre"],
            "Promotor":     e["promotor"] or "—",
            "Fase":         e["fase"]     or "—",
            "IP":           e["ip"]       or "—",
            "Estado":       ESTADO_LABEL.get(e["estado"], e["estado"]),
            "Visitas":      len(ev),
            "Inicio":       e["fecha_inicio"] or "—",
            "Fin previsto": e["fecha_fin"]    or "—",
        })

    df_ens = pd.DataFrame(rows)

    event = st.dataframe(
        df_ens.drop(columns=["_id"]),
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="sel_ensayos",
    )

    selected = event.selection.rows
    if selected:
        row_idx   = selected[0]
        sel_id     = int(df_ens.iloc[row_idx]["_id"])
        sel_codigo = df_ens.iloc[row_idx]["Código"]

        st.divider()
        ca, cb, _ = st.columns([1, 1, 4])
        if ca.button("✏️ Editar seleccionado", use_container_width=True):
            dialog_editar_ensayo(sel_id)
        if cb.button("🗑️ Eliminar seleccionado", use_container_width=True):
            dialog_confirmar_delete("ensayo", sel_id, sel_codigo)


# ── ROUTER ────────────────────────────────────────────────────────────────────
pages = {
    "🏠 Inicio":    page_dashboard,
    "📅 Visitas":   page_visitas,
    "👥 Monitores": page_monitores,
    "📋 Ensayos":   page_ensayos,
}
pages[nav]()
