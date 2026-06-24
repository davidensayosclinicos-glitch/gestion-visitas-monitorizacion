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
    authenticate_user, list_usuarios_monitor, create_usuario_monitor, set_usuario_activo, reset_usuario_password, update_usuario_username,
    documentos_feature_available, create_documento, set_documento_visible_para_usuarios,
    list_documentos, get_documento_bytes, get_usuarios_monitor_activos, delete_documento,
    tareas_feature_available, create_tarea, get_tareas_por_monitor, get_todas_tareas, get_tarea_by_id,
    add_mensaje_tarea, get_mensajes_tarea, update_estado_tarea, delete_tarea,
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


def current_user():
    return st.session_state.get("auth_user")


def is_admin():
    u = current_user() or {}
    return u.get("rol") == "admin"


def is_monitor():
    u = current_user() or {}
    return u.get("rol") == "monitor"


def scope_ensayo_id():
    u = current_user() or {}
    return u.get("ensayo_id")


def scope_monitor_id():
    u = current_user() or {}
    return u.get("monitor_id")


def do_logout():
    st.session_state.pop("auth_user", None)
    st.rerun()


def require_login():
    if current_user():
        return

    st.title("🔐 Acceso a Monitorización")
    st.caption("Inicia sesión para ver solo la información permitida según tu rol.")
    with st.form("form_login"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")
        if submitted:
            user = authenticate_user(username, password)
            if not user:
                st.error("Usuario o contraseña incorrectos, o cuenta inactiva.")
            else:
                st.session_state["auth_user"] = user
                st.rerun()
    st.stop()


def elabel(e):
    return f"{e['codigo']} — {e['nombre']}"


def mlabel(m):
    extra = f" ({m['empresa']})" if m['empresa'] else ""
    return f"{m['nombre']} {m['apellidos']}{extra}"


def render_month_calendar(year: int, month: int, visitas_por_dia: dict, bloqueados: dict, ensayos_por_dia: dict):
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
            ensayo_label = ensayos_por_dia.get(f, "")
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
                chip = ensayo_label if (n == 2 and ensayo_label) else f"{n} visitas"
            elif n == 1:
                cls = "gvm-state-mid"
                chip = ensayo_label if ensayo_label else "1 visita"
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


def format_file_size(num_bytes: int):
    if num_bytes is None:
        return "0 B"
    if num_bytes < 1024:
        return f"{num_bytes} B"
    units = ["KB", "MB", "GB"]
    value = float(num_bytes)
    for unit in units:
        value /= 1024.0
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
    return f"{num_bytes} B"


def render_tab_documentos(tipo: str, tab_key: str):
    docs = []
    current_id = current_user().get("id")
    if is_admin():
        docs = list_documentos(tipo=tipo)
    else:
        if current_id is None:
            st.warning("No se puede resolver tu usuario para mostrar documentos visibles.")
            return
        docs = list_documentos(tipo=tipo, solo_visibles_para_usuario_id=current_id)

    if is_admin():
        st.caption("Solo administrador puede subir y asignar visibilidad.")
        usuarios = get_usuarios_monitor_activos()
        usuario_opts = {int(u.get("id")): f"{u.get('username', '')} ({u.get('monitor_nombre', '')} {u.get('monitor_apellidos', '')})" for u in usuarios}

        with st.form(f"form_upload_{tab_key}"):
            archivo = st.file_uploader(
                "Selecciona archivo",
                type=["pdf", "doc", "docx", "png", "jpg", "jpeg"],
                key=f"upload_{tab_key}",
            )
            visibles = st.multiselect(
                "Usuarios que pueden verlo",
                options=list(usuario_opts.keys()),
                format_func=lambda x: usuario_opts.get(x, str(x)),
                key=f"vis_{tab_key}",
                placeholder="Selecciona usuarios",
            )
            submit = st.form_submit_button("Subir documento", type="primary", use_container_width=True)
            if submit:
                if archivo is None:
                    st.error("Debes seleccionar un archivo.")
                elif not visibles:
                    st.error("Debes asignar al menos un usuario visible.")
                else:
                    try:
                        contenido = archivo.read()
                        doc_id = create_documento(
                            tipo=tipo,
                            nombre_archivo=archivo.name,
                            mime_type=getattr(archivo, "type", "application/octet-stream") or "application/octet-stream",
                            contenido_bytes=contenido,
                            subido_por_user_id=current_id,
                        )
                        set_documento_visible_para_usuarios(doc_id, visibles)
                        st.success("Documento subido y visibilidad asignada.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"No se pudo subir el documento: {ex}")
    else:
        st.caption("Aquí solo ves los documentos que el administrador te haya asignado.")

    st.divider()
    st.subheader("Documentos")
    if not docs:
        st.info("No hay documentos para este tipo.")
        return

    for d in docs:
        doc_id = int(d.get("id"))
        nombre = d.get("nombre_archivo", "archivo")
        mime_type = d.get("mime_type", "application/octet-stream")
        contenido = None
        try:
            contenido = get_documento_bytes(doc_id)
        except Exception:
            contenido = None
        size_bytes = len(contenido or b"")

        visible_para = d.get("visible_para", "")
        total_visibles = int(d.get("total_visibles") or 0)
        creado_en = d.get("creado_en", "")

        with st.container(border=True):
            h1, h2, h3 = st.columns([5, 2, 2])
            h1.markdown(f"**{nombre}**")
            h1.caption(f"{mime_type} · {format_file_size(size_bytes)}")
            if creado_en:
                h2.caption(f"Subido: {str(creado_en)[:19].replace('T', ' ')}")
            if is_admin():
                h2.caption(f"Visible para: {total_visibles} usuario(s)")
                if visible_para:
                    h2.caption(visible_para)

            if contenido:
                h3.download_button(
                    "Descargar",
                    data=contenido,
                    file_name=nombre,
                    mime=mime_type,
                    key=f"dl_{tab_key}_{doc_id}",
                    use_container_width=True,
                )
            else:
                h3.warning("Sin contenido")

            if is_admin():
                usuarios = get_usuarios_monitor_activos()
                usuario_opts = {
                    int(u.get("id")): f"{u.get('username', '')} ({u.get('monitor_nombre', '')} {u.get('monitor_apellidos', '')})"
                    for u in usuarios
                }
                current_vis = [int(uid) for uid in (d.get("visible_user_ids") or []) if uid is not None]

                e1, e2 = st.columns([4, 1])
                nuevos_vis = e1.multiselect(
                    f"Visibilidad ({nombre})",
                    options=list(usuario_opts.keys()),
                    default=current_vis,
                    format_func=lambda x: usuario_opts.get(x, str(x)),
                    key=f"edit_vis_{tab_key}_{doc_id}",
                )
                if e2.button("Guardar", key=f"save_vis_{tab_key}_{doc_id}", use_container_width=True):
                    try:
                        set_documento_visible_para_usuarios(doc_id, nuevos_vis)
                        st.success("Visibilidad actualizada.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"No se pudo actualizar visibilidad: {ex}")

                if e2.button("Eliminar", key=f"del_doc_{tab_key}_{doc_id}", use_container_width=True):
                    try:
                        delete_documento(doc_id)
                        st.success("Documento eliminado.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"No se pudo eliminar: {ex}")


def render_calendario_general(section_key: str, can_manage_blocks: bool = False):
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
        visitas_por_dia = {}
        ensayos_por_dia = {}

        if is_admin():
            df_scope = get_visitas_df(desde=desde_grid, hasta=hasta_grid)
        else:
            # En perfil monitor, el calendario muestra solo visitas de su ensayo.
            ensayo_scope = scope_ensayo_id()
            df_scope = pd.DataFrame()
            if ensayo_scope is not None:
                df_scope = get_visitas_df(ensayo_id=ensayo_scope, desde=desde_grid, hasta=hasta_grid)

        if not df_scope.empty:
            for fecha_key, group in df_scope.groupby("fecha"):
                if not fecha_key:
                    continue
                visitas_por_dia[fecha_key] = int(len(group))

                codigos = [str(c).strip() for c in group["ensayo_codigo"].fillna("") if str(c).strip()]
                codigos_unique = list(dict.fromkeys(codigos))
                if not codigos_unique:
                    continue

                if is_admin():
                    if len(codigos_unique) == 1:
                        ensayos_por_dia[fecha_key] = codigos_unique[0]
                    elif len(codigos_unique) == 2:
                        ensayos_por_dia[fecha_key] = f"{codigos_unique[0]} / {codigos_unique[1]}"
                    else:
                        ensayos_por_dia[fecha_key] = f"{codigos_unique[0]} +{len(codigos_unique) - 1}"
                else:
                    ensayos_por_dia[fecha_key] = codigos_unique[0]

        bloqueados_rows = get_dias_bloqueados(desde=desde_grid, hasta=hasta_grid)
        bloqueados_map = {r.get("fecha"): r.get("motivo", "") for r in bloqueados_rows}
        render_month_calendar(anio, mes, visitas_por_dia, bloqueados_map, ensayos_por_dia)
    except Exception as ex:
        st.error(
            "No se pudo cargar el calendario de bloqueos. "
            "Verifica que exista la tabla public.dias_bloqueados en Supabase."
        )
        st.caption(f"Detalle técnico: {ex}")
        bloqueados_rows = []

    st.caption("Leyenda: Libre (sin bloqueo), Bloqueado (0 visitas), Solo 1 visita, Normal (2 visitas).")

    st.divider()
    st.subheader("🔎 Detalle del día")
    fecha_detalle = st.date_input("Selecciona un día", value=date.today(), key=f"{section_key}_detalle_fecha")
    fecha_detalle_iso = fecha_detalle.isoformat()

    if is_admin():
        df_dia = get_visitas_df(desde=fecha_detalle_iso, hasta=fecha_detalle_iso)
    else:
        ensayo_scope = scope_ensayo_id()
        if ensayo_scope is None:
            st.error("Tu usuario no tiene ensayo asignado.")
            df_dia = pd.DataFrame()
        else:
            df_dia = get_visitas_df(ensayo_id=ensayo_scope, desde=fecha_detalle_iso, hasta=fecha_detalle_iso)

    if df_dia.empty:
        if is_admin():
            st.info("No hay visitas registradas en ese día.")
        else:
            st.info("No hay visitas de tu ensayo en ese día.")
    else:
        if is_admin():
            st.caption("Ensayos con visitas en el día seleccionado")
            df_ensayos_dia = (
                df_dia[["ensayo_codigo", "ensayo_nombre"]]
                .drop_duplicates()
                .sort_values(["ensayo_codigo", "ensayo_nombre"], ascending=[True, True])
                .rename(columns={"ensayo_codigo": "Código", "ensayo_nombre": "Ensayo"})
            )
            st.dataframe(df_ensayos_dia, use_container_width=True, hide_index=True)
        else:
            ensayo_scope = scope_ensayo_id()
            ensayo = get_ensayo_by_id(ensayo_scope) if ensayo_scope is not None else None
            if ensayo:
                st.caption(f"Mostrando solo tu ensayo: {ensayo.get('codigo', '')} — {ensayo.get('nombre', '')}")

        cols_show = ["fecha", "hora", "tipo", "estado", "monitor_nombre", "notas"]
        if is_admin():
            cols_show = ["fecha", "hora", "ensayo_codigo", "monitor_nombre", "tipo", "estado", "notas"]

        df_detalle = df_dia[cols_show].copy()
        df_detalle["fecha"] = pd.to_datetime(df_detalle["fecha"]).dt.strftime("%d/%m/%Y")
        df_detalle["estado"] = df_detalle["estado"].map(ESTADO_LABEL)

        if is_admin():
            df_detalle.columns = ["Fecha", "Hora", "Ensayo", "Monitor", "Tipo", "Estado", "Notas"]
        else:
            df_detalle.columns = ["Fecha", "Hora", "Tipo", "Estado", "Monitor", "Notas"]

        st.dataframe(df_detalle, use_container_width=True, hide_index=True)

    if not can_manage_blocks:
        return

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


# ── AUTENTICACIÓN ─────────────────────────────────────────────────────────────
require_login()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 Monitorización")
    st.caption("Coordinación de Ensayos Clínicos")
    backend = get_backend_name()
    if backend == "postgres":
        st.caption("Backend: 🐘 PostgreSQL (DATABASE_URL)")
    else:
        st.caption("Backend: ☁️ Supabase API")
    st.caption(f"Usuario: **{current_user().get('username', '')}**")
    rol_text = "Administrador" if is_admin() else "Monitor"
    st.caption(f"Rol: {rol_text}")
    st.divider()

    nav_options = ["🏠 Inicio", "📅 Visitas"]
    if is_admin():
        nav_options.extend(["👥 Monitores", "📋 Ensayos", "📁 Documentos", "💬 Tareas", "🔑 Usuarios"])
    else:
        nav_options.extend(["📁 Documentos", "💬 Tareas"])

    nav = st.radio(
        "Navegación",
        nav_options,
        label_visibility="collapsed",
    )

    st.divider()
    if st.button("Cerrar sesión", use_container_width=True):
        do_logout()

    with st.expander("💾 Copia de seguridad"):
        st.info("Los datos se guardan directamente en Supabase.")


# ── DIALOGS: VISITAS ──────────────────────────────────────────────────────────

@st.dialog("Nueva Visita", width="large")
def dialog_nueva_visita():
    if is_admin():
        ensayos = get_ensayos()
    else:
        ensayo_id_scope = scope_ensayo_id()
        ensayos = [e for e in get_ensayos() if e.get("id") == ensayo_id_scope]

    if not ensayos:
        st.warning("⚠️ Primero debes crear al menos un **Ensayo** en la sección correspondiente.")
        return

    with st.form("form_nueva_visita"):
        if is_admin():
            ei = st.selectbox("Ensayo *", range(len(ensayos)), format_func=lambda i: elabel(ensayos[i]))
            ensayo_id_sel = ensayos[ei]["id"]
        else:
            ensayo_id_sel = ensayos[0]["id"]
            st.info(f"Ensayo asignado: **{elabel(ensayos[0])}**")
        
        monitores = get_monitores(ensayo_id=ensayo_id_sel)
        if not monitores:
            st.warning(f"⚠️ No hay monitores asociados a este ensayo. Crea uno en la sección **Monitores**.")
            return

        monitor_id_sel = monitores[0]["id"]
        if is_monitor():
            own_monitor_id = scope_monitor_id()
            propios = [m for m in monitores if m.get("id") == own_monitor_id]
            if not propios:
                st.error("Tu usuario no está vinculado a un monitor válido en este ensayo.")
                return
            monitor_id_sel = propios[0]["id"]
            st.info(f"Monitor asignado: **{mlabel(propios[0])}**")
        elif len(monitores) == 1:
            st.info(f"📍 Monitor asignado: **{mlabel(monitores[0])}**")
        else:
            mi = st.selectbox("Monitor *", range(len(monitores)), format_func=lambda i: mlabel(monitores[i]))
            monitor_id_sel = monitores[mi]["id"]

        c3, c4 = st.columns(2)
        fecha_desde = c3.date_input("Fecha de inicio *", value=date.today(), key="visita_desde")
        fecha_hasta = c4.date_input("Fecha de fin *", value=date.today(), key="visita_hasta")
        hora_val = st.time_input("Hora", value=datetime.strptime("09:00", "%H:%M").time(), step=900)

        c5, c6 = st.columns(2)
        tipo   = c5.selectbox("Tipo de visita *", TIPOS_VISITA)
        
        # Monitores solo pueden crear visitas pendientes
        if is_monitor():
            estado = "pendiente"
            st.info("📝 Tu visita se registrará como **PENDIENTE** y deberá ser confirmada por el administrador.")
        else:
            # Admin puede elegir el estado
            estado = c6.selectbox("Estado", ESTADOS_VISITA, format_func=lambda x: ESTADO_LABEL.get(x, x))

        notas = st.text_area("Notas", height=80,
                             placeholder="Observaciones, documentos solicitados, incidencias...")

        if st.form_submit_button("💾 Guardar visita(s)", use_container_width=True, type="primary"):
            try:
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

                if count == 1:
                    st.success("✅ Visita registrada correctamente.")
                else:
                    st.success(f"✅ {count} visita(s) registrada(s) correctamente.")
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

    if is_monitor():
        if v.get("ensayo_id") != scope_ensayo_id() or v.get("monitor_id") != scope_monitor_id():
            st.error("No tienes permiso para editar esta visita.")
            return

    if is_admin():
        ensayos = get_ensayos()
    else:
        ensayos = [e for e in get_ensayos() if e.get("id") == scope_ensayo_id()]

    e_ids = [e["id"] for e in ensayos]
    e_idx = e_ids.index(v["ensayo_id"])  if v["ensayo_id"]  in e_ids else 0
    
    monitores = get_monitores(ensayo_id=v["ensayo_id"])
    m_ids = [m["id"] for m in monitores]
    m_idx = m_ids.index(v["monitor_id"]) if v["monitor_id"] in m_ids else 0
    hora_default = datetime.strptime(v["hora"], "%H:%M").time() if v["hora"] else datetime.strptime("09:00", "%H:%M").time()

    with st.form("form_editar_visita"):
        if is_admin():
            ei = st.selectbox("Ensayo *", range(len(ensayos)), index=e_idx, format_func=lambda i: elabel(ensayos[i]))
            ensayo_sel = ensayos[ei]["id"]
        else:
            ei = 0
            ensayo_sel = ensayos[0]["id"]
            st.info(f"Ensayo asignado: **{elabel(ensayos[0])}**")
        
        monitores_new = get_monitores(ensayo_id=ensayo_sel)
        m_idx_new = 0
        if monitores_new:
            m_ids_new = [m["id"] for m in monitores_new]
            m_idx_new = m_ids_new.index(v["monitor_id"]) if v["monitor_id"] in m_ids_new else 0

        if is_monitor():
            own_monitor_id = scope_monitor_id()
            propios = [m for m in monitores_new if m.get("id") == own_monitor_id]
            if not propios:
                st.error("Tu usuario no está vinculado a un monitor válido en este ensayo.")
                return
            st.info(f"Monitor asignado: **{mlabel(propios[0])}**")
            mi = 0
            monitores_new = propios
        elif len(monitores_new) == 1:
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


@st.dialog("Crear usuario de monitor", width="large")
def dialog_crear_usuario_monitor():
    if not is_admin():
        st.error("No tienes permiso para esta operación.")
        return

    monitores = get_monitores()
    if not monitores:
        st.warning("No hay monitores disponibles.")
        return

    with st.form("form_crear_usuario_monitor"):
        mi = st.selectbox("Monitor", range(len(monitores)), format_func=lambda i: mlabel(monitores[i]))
        username = st.text_input("Usuario", placeholder="ej: monitor.maria")
        password = st.text_input("Contraseña", type="password")
        activo = st.checkbox("Cuenta activa", value=True)

        if st.form_submit_button("💾 Crear usuario", use_container_width=True, type="primary"):
            try:
                create_usuario_monitor(
                    username=username,
                    password=password,
                    monitor_id=monitores[mi]["id"],
                    activo=activo,
                )
            except ValueError as ex:
                st.error(str(ex))
                return
            st.success("✅ Usuario de monitor creado.")
            st.rerun()


@st.dialog("Gestionar usuario", width="large")
def dialog_gestionar_usuario(user_id: int, username: str, activo_actual: bool):
    if not is_admin():
        st.error("No tienes permiso para esta operación.")
        return

    st.markdown(f"**Usuario:** {username}")
    c1, c2 = st.columns(2)
    if c1.button("Activar" if not activo_actual else "Desactivar", use_container_width=True):
        set_usuario_activo(user_id, not activo_actual)
        st.success("Estado actualizado.")
        st.rerun()

    with c2.popover("Reset contraseña", use_container_width=True):
        new_password = st.text_input("Nueva contraseña", type="password", key=f"pwd_reset_{user_id}")
        if st.button("Guardar nueva contraseña", key=f"btn_reset_{user_id}", use_container_width=True):
            try:
                reset_usuario_password(user_id, new_password)
            except ValueError as ex:
                st.error(str(ex))
                return
            st.success("Contraseña actualizada.")
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
    if is_monitor() and entity_type != "visita":
        st.error("No tienes permiso para esta operación.")
        return
    if is_monitor() and entity_type == "visita":
        v = get_visita_by_id(entity_id)
        if not v or v.get("ensayo_id") != scope_ensayo_id() or v.get("monitor_id") != scope_monitor_id():
            st.error("No tienes permiso para eliminar esta visita.")
            return

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

    if is_admin():
        stats = get_stats()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📅 Visitas este mes", stats["total_mes"])
        c2.metric("⏳ Pendientes / Confirmadas", stats["pendientes"])
        c3.metric("✅ Realizadas (total)", stats["realizadas"])
        c4.metric("🔬 Ensayos activos", stats["ensayos_activos"])

        st.divider()
        
        # ⚠️ ALERTAS DE VISITAS PENDIENTES DE CONFIRMACIÓN
        df_visitas = get_visitas_df()
        visitas_pendientes = df_visitas[df_visitas["estado"] == "pendiente"].copy()
        
        if not visitas_pendientes.empty:
            visitas_pendientes = visitas_pendientes.sort_values("fecha", ascending=True)
            st.warning(f"⚠️ **{len(visitas_pendientes)} visita(s) PENDIENTE(S) de confirmación**")
            
            # Tabla de visitas pendientes
            pendientes_show = visitas_pendientes[["id", "fecha", "hora", "monitor_nombre", "ensayo_codigo", "tipo", "notas"]].copy()
            pendientes_show["fecha"] = pd.to_datetime(pendientes_show["fecha"]).dt.strftime("%d/%m/%Y")
            pendientes_show.columns = ["ID", "Fecha", "Hora", "Monitor", "Ensayo", "Tipo", "Notas"]
            
            event_pend = st.dataframe(
                pendientes_show,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun",
                key="sel_visitas_pendientes",
            )
            
            sel_pend = event_pend.selection.rows
            if sel_pend:
                row_idx = sel_pend[0]
                visita_id = int(visitas_pendientes.iloc[row_idx]["id"])
                visita_info = visitas_pendientes.iloc[row_idx]
                
                col_a, col_b, col_c = st.columns(3)
                
                with col_a:
                    if st.button("✅ Confirmar", use_container_width=True, type="primary"):
                        try:
                            update_visita(visita_id, {"estado": "confirmada"})
                            st.success("✅ Visita confirmada")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {e}")
                
                with col_b:
                    if st.button("❌ Rechazar", use_container_width=True):
                        try:
                            update_visita(visita_id, {"estado": "cancelada"})
                            st.success("❌ Visita rechazada")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {e}")
                
                with col_c:
                    if st.button("✏️ Editar", use_container_width=True):
                        dialog_editar_visita(visita_id)

        st.divider()
        render_calendario_general("home", can_manage_blocks=True)

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
        return

    ensayo_id = scope_ensayo_id()
    monitor_id = scope_monitor_id()
    df_own = get_visitas_df(ensayo_id=ensayo_id)
    mes = date.today().strftime("%Y-%m")

    total_mes = int(df_own["fecha"].fillna("").str.startswith(mes).sum()) if not df_own.empty else 0
    pendientes = int(df_own["estado"].isin(["pendiente", "confirmada"]).sum()) if not df_own.empty else 0
    propias = df_own[df_own["monitor_id"] == monitor_id] if not df_own.empty else pd.DataFrame()
    propias_pend = int(propias["estado"].isin(["pendiente", "confirmada"]).sum()) if not propias.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("📅 Visitas de tu ensayo (mes)", total_mes)
    c2.metric("⏳ Pendientes en tu ensayo", pendientes)
    c3.metric("👤 Pendientes tuyas", propias_pend)

    st.divider()
    st.subheader("🗓️ Disponibilidad general")
    st.caption("Solo se muestra disponibilidad del calendario (hueco o no).")
    render_calendario_general("home_monitor", can_manage_blocks=False)

    st.divider()
    st.subheader("📅 Tus próximas visitas")
    if propias.empty:
        st.info("No tienes visitas próximas programadas.")
        return

    hoy = date.today().isoformat()
    prox = propias[(propias["fecha"].fillna("") >= hoy) & (~propias["estado"].isin(["cancelada", "realizada"]))].copy()
    if prox.empty:
        st.info("No tienes visitas próximas programadas.")
        return

    prox = prox.sort_values(["fecha", "hora"], ascending=[True, True]).head(10)
    prox_show = prox[["fecha", "hora", "tipo", "estado", "notas"]].copy()
    prox_show["fecha"] = pd.to_datetime(prox_show["fecha"]).dt.strftime("%d/%m/%Y")
    prox_show["estado"] = prox_show["estado"].map(ESTADO_LABEL)
    prox_show.columns = ["Fecha", "Hora", "Tipo", "Estado", "Notas"]
    st.dataframe(prox_show, use_container_width=True, hide_index=True)


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
        if is_admin():
            ensayos_list = get_ensayos()
            ensayo_opts  = {e["id"]: elabel(e) for e in ensayos_list}
            f_ensayo_id  = c3.selectbox(
                "Ensayo", [None] + list(ensayo_opts.keys()),
                format_func=lambda x: ensayo_opts.get(x, "Todos los ensayos"),
                label_visibility="collapsed",
            )
        else:
            f_ensayo_id = scope_ensayo_id()
            c3.info("Ensayo asignado")
        f_desde = c4.date_input("Desde", value=None, label_visibility="collapsed")
        f_hasta = c5.date_input("Hasta", value=None, label_visibility="collapsed")

    df = get_visitas_df(
        texto=f_texto,
        estado=f_estado,
        ensayo_id=f_ensayo_id,
        desde=f_desde.isoformat() if f_desde else "",
        hasta=f_hasta.isoformat() if f_hasta else "",
    )

    if is_monitor() and not df.empty:
        df = df[df["monitor_id"] == scope_monitor_id()].copy()

    if df.empty:
        st.info("No hay visitas que coincidan con los filtros.")
        return

    # Exportar CSV
    c_info, c_exp = st.columns([4, 1])
    c_info.caption(f"**{len(df)}** visita(s) encontradas.")
    if is_admin():
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
    if is_monitor():
        display_cols = ["id", "fecha", "hora", "tipo", "estado", "notas"]
    df_show = df[display_cols].copy()
    df_show["fecha"]  = pd.to_datetime(df_show["fecha"]).dt.strftime("%d/%m/%Y")
    df_show["estado"] = df_show["estado"].map(ESTADO_LABEL)
    df_show["notas"]  = df_show["notas"].str[:60]
    if is_admin():
        df_show.columns = ["ID", "Fecha", "Hora", "Monitor", "Ensayo", "Tipo", "Estado", "Notas"]
    else:
        df_show.columns = ["ID", "Fecha", "Hora", "Tipo", "Estado", "Notas"]

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
    if not is_admin():
        st.error("No tienes permiso para acceder a esta pantalla.")
        return

    col_h, col_btn = st.columns([5, 1])
    col_h.header("👥 Monitores")
    if col_btn.button("➕ Nuevo Monitor", use_container_width=True, type="primary"):
        dialog_nuevo_monitor()

    st.divider()
    cu1, cu2 = st.columns([5, 1])
    cu1.subheader("🔐 Usuarios de monitores")
    if cu2.button("➕ Crear usuario", use_container_width=True):
        dialog_crear_usuario_monitor()

    usuarios = list_usuarios_monitor()
    if not usuarios:
        st.info("No hay usuarios creados para monitores.")
    else:
        rows = []
        for u in usuarios:
            monitor_nom = (f"{u.get('monitor_nombre', '')} {u.get('monitor_apellidos', '')}").strip()
            ensayo_txt = (f"{u.get('ensayo_codigo', '')} {u.get('ensayo_nombre', '')}").strip()
            rows.append(
                {
                    "_id": u.get("id"),
                    "Usuario": u.get("username", ""),
                    "Rol": u.get("rol", ""),
                    "Estado": "Activo" if int(u.get("activo") or 0) else "Inactivo",
                    "Monitor": monitor_nom,
                    "Ensayo": ensayo_txt,
                }
            )

        df_u = pd.DataFrame(rows)
        event_u = st.dataframe(
            df_u.drop(columns=["_id"]),
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="sel_usuarios",
        )

        sel_u = event_u.selection.rows
        if sel_u:
            idx = sel_u[0]
            user_id = int(df_u.iloc[idx]["_id"])
            username = df_u.iloc[idx]["Usuario"]
            activo = df_u.iloc[idx]["Estado"] == "Activo"
            if st.button("⚙️ Gestionar usuario seleccionado", use_container_width=True):
                dialog_gestionar_usuario(user_id, username, activo)

    st.divider()

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
    if not is_admin():
        st.error("No tienes permiso para acceder a esta pantalla.")
        return

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


# ── DIALOGS: USUARIOS ─────────────────────────────────────────────────────────

@st.dialog("Editar Usuario", width="large")
def dialog_editar_usuario(user_id, username_actual):
    """Diálogo para editar username y contraseña de un usuario."""
    st.subheader("Editar Usuario")
    
    with st.form("form_editar_usuario"):
        new_username = st.text_input("Nuevo usuario", value=username_actual, placeholder="usuario")
        new_password = st.text_input("Nueva contraseña (opcional)", type="password", placeholder="Dejar vacío para no cambiar")
        
        if st.form_submit_button("💾 Guardar cambios", use_container_width=True, type="primary"):
            try:
                # Actualizar usuario si cambió
                if new_username.strip() != username_actual.strip():
                    update_usuario_username(user_id, new_username)
                    st.success("✅ Usuario actualizado")
                
                # Actualizar contraseña si se ingresó
                if new_password.strip():
                    reset_usuario_password(user_id, new_password)
                    st.success("✅ Contraseña actualizada")
                
                st.rerun()
            except ValueError as e:
                st.error(f"❌ Error: {e}")
            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")


# ── PÁGINA: USUARIOS ──────────────────────────────────────────────────────────

def page_usuarios():
    """Página de gestión de usuarios (solo para admin)."""
    if not is_admin():
        st.error("❌ No tienes permiso para acceder a esta pantalla.")
        return
    
    st.header("🔑 Gestión de Usuarios")
    st.caption("Visualiza, edita usuarios y contraseñas de todos los monitores.")
    st.divider()
    
    # Obtener lista de usuarios
    usuarios = list_usuarios_monitor()
    
    if not usuarios:
        st.info("📭 No hay usuarios creados.")
        return
    
    # Preparar datos para mostrar
    rows = []
    for u in usuarios:
        monitor_nom = (f"{u.get('monitor_nombre', '')} {u.get('monitor_apellidos', '')}").strip() or "(Admin)"
        ensayo_txt = u.get('ensayo_codigo', '') or "(N/A)"
        activo = "🟢 Activo" if int(u.get("activo") or 0) else "🔴 Inactivo"
        
        rows.append({
            "_id": u.get("id"),
            "_username": u.get("username", ""),
            "Usuario": u.get("username", ""),
            "Rol": u.get("rol", "").upper(),
            "Monitor": monitor_nom,
            "Ensayo": ensayo_txt,
            "Estado": activo,
        })
    
    # Convertir a DataFrame
    df = pd.DataFrame(rows)
    
    # Mostrar tabla
    st.subheader("📋 Lista de Usuarios")
    event = st.dataframe(
        df[["Usuario", "Rol", "Monitor", "Ensayo", "Estado"]],
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="sel_usuarios_page",
    )
    
    # Si hay usuario seleccionado, mostrar opciones
    selected = event.selection.rows
    if selected:
        row_idx = selected[0]
        user_id = int(df.iloc[row_idx]["_id"])
        username = df.iloc[row_idx]["_username"]
        rol = df.iloc[row_idx]["Rol"]
        monitor = df.iloc[row_idx]["Monitor"]
        estado = df.iloc[row_idx]["Estado"]
        
        st.divider()
        st.subheader(f"Opciones para: **{username}**")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        # Información del usuario
        with col1:
            st.text(f"👤 Usuario: {username}")
            st.text(f"📊 Rol: {rol}")
            st.text(f"🏥 Monitor: {monitor}")
            st.text(f"📌 Estado: {estado}")
        
        # Botón para editar
        with col2:
            if st.button("✏️ Editar", use_container_width=True, type="primary"):
                dialog_editar_usuario(user_id, username)
        
        # Botón para cambiar estado
        with col3:
            estado_actual = int(df.iloc[row_idx]["Estado"].count("🟢"))
            texto_btn = "Desactivar" if estado_actual else "Activar"
            if st.button(f"{'🔴' if estado_actual else '🟢'} {texto_btn}", use_container_width=True):
                try:
                    set_usuario_activo(user_id, not bool(estado_actual))
                    st.success(f"✅ Usuario {'desactivado' if estado_actual else 'activado'}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")
    
    st.divider()
    st.info(
        "💡 **Cambiar credenciales de usuario:**\n\n"
        "1. Selecciona un usuario de la tabla\n"
        "2. Haz clic en '✏️ Editar'\n"
        "3. Modifica el usuario y/o contraseña\n"
        "4. Haz clic en 'Guardar cambios'\n\n"
        "**Nota:** La contraseña debe tener mínimo 8 caracteres."
    )


# ── PÁGINA: DOCUMENTOS ───────────────────────────────────────────────────────

def page_documentos():
    st.header("📁 Documentos")
    st.caption("Pestañas de documentación: CV, GCP y certificados de calibración.")

    if not documentos_feature_available():
        st.error("Falta migración SQL para documentos. Aplica el script en la carpeta sql y recarga la app.")
        return

    tab_cv, tab_gcp, tab_cal = st.tabs([
        "CV",
        "GCP",
        "Certificados de calibración",
    ])

    with tab_cv:
        render_tab_documentos("cv", "cv")
    with tab_gcp:
        render_tab_documentos("gcp", "gcp")
    with tab_cal:
        render_tab_documentos("calibracion", "calibracion")


# ── PÁGINA: TAREAS (CHAT) ─────────────────────────────────────────────────────

def page_tareas():
    st.header("💬 Tareas y Coordinación")
    st.caption("Sistema de tareas en formato chat entre monitores y administrador.")
    
    if not tareas_feature_available():
        st.error("Falta migración SQL para tareas. Aplica el script en la carpeta sql y recarga la app.")
        return
    
    if is_admin():
        st.subheader("Todas las tareas")
        tareas = get_todas_tareas()
        
        if not tareas:
            st.info("No hay tareas registradas.")
            return
        
        # Crear tabs por estado
        tab_abiertas, tab_coordinacion, tab_cerradas = st.tabs(["🟠 Abiertas", "🔵 En coordinación", "🟢 Cerradas"])
        
        with tab_abiertas:
            tareas_abiertas = [t for t in tareas if t.get("estado") == "abierta"]
            if not tareas_abiertas:
                st.info("No hay tareas abiertas.")
            else:
                for tarea in tareas_abiertas:
                    render_tarea_chat(tarea, is_admin=True)
        
        with tab_coordinacion:
            tareas_coord = [t for t in tareas if t.get("estado") == "en_coordinacion"]
            if not tareas_coord:
                st.info("No hay tareas en coordinación.")
            else:
                for tarea in tareas_coord:
                    render_tarea_chat(tarea, is_admin=True)
        
        with tab_cerradas:
            tareas_cerradas = [t for t in tareas if t.get("estado") == "cerrada"]
            if not tareas_cerradas:
                st.info("No hay tareas cerradas.")
            else:
                for tarea in tareas_cerradas:
                    render_tarea_chat(tarea, is_admin=True)
    else:
        st.subheader("Mis tareas")
        monitor_id = scope_monitor_id()
        if monitor_id is None:
            st.error("Tu usuario no está vinculado a un monitor válido.")
            return
        
        tareas = get_tareas_por_monitor(monitor_id)
        if not tareas:
            st.info("No tienes tareas. Crea una nueva.")
        else:
            for tarea in tareas:
                render_tarea_chat(tarea, is_admin=False, monitor_id=monitor_id)
        
        st.divider()
        st.subheader("➕ Nueva tarea")
        with st.form("form_nueva_tarea"):
            titulo = st.text_input("Título *", placeholder="Descripción breve de la tarea")
            descripcion = st.text_area("Descripción detallada", height=80, placeholder="Explica el problema o solicitud")
            
            if st.form_submit_button("Crear tarea", type="primary", use_container_width=True):
                if not titulo.strip():
                    st.error("El título es obligatorio.")
                else:
                    try:
                        tarea_id = create_tarea(titulo, descripcion, monitor_id)
                        st.success(f"Tarea creada. ID: {tarea_id}")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"No se pudo crear la tarea: {ex}")


def render_tarea_chat(tarea, is_admin=False, monitor_id=None):
    tarea_id = int(tarea.get("id"))
    titulo = tarea.get("titulo", "")
    descripcion = tarea.get("descripcion", "")
    estado = tarea.get("estado", "abierta")
    creado_en = tarea.get("creado_en", "")
    monitor_nombre = f"{tarea.get('monitor_nombre', '')} {tarea.get('monitor_apellidos', '')}".strip() if is_admin else "Tú"
    
    with st.container(border=True):
        col_h, col_e = st.columns([4, 1])
        col_h.markdown(f"**{titulo}**")
        if descripcion:
            col_h.caption(f"📝 {descripcion[:120]}...")
        fecha_creacion = str(creado_en)[:10] if creado_en else 'sin fecha'
        col_h.caption(f"👤 {monitor_nombre} · {fecha_creacion}")
        
        # Estado badge
        estado_labels = {"abierta": "🟠 Abierta", "en_coordinacion": "🔵 En coordinación", "cerrada": "🟢 Cerrada"}
        col_e.markdown(f"**{estado_labels.get(estado, estado)}**")
        
        # Mensajes (chat)
        mensajes = get_mensajes_tarea(tarea_id)
        st.markdown("**Conversación:**")
        if not mensajes:
            st.caption("*(Sin mensajes aún)*")
        else:
            for msg in mensajes:
                usuario = msg.get("username", "Sistema")
                contenido = msg.get("contenido", "")
                tipo = msg.get("tipo", "mensaje")
                timestamp = msg.get("creado_en", "")
                timestamp_str = str(timestamp)[:10] if timestamp else ""
                
                if tipo == "sistema":
                    st.info(f"📌 **[Sistema]** {contenido}")
                else:
                    st.markdown(f"**{usuario}** ({timestamp_str}): {contenido}")
        
        # Agregar respuesta
        col_m, col_b = st.columns([5, 1])
        nuevo_msg = col_m.text_input(
            f"Nuevo mensaje (Tarea {tarea_id})",
            placeholder="Escribe tu respuesta...",
            key=f"msg_{tarea_id}",
            label_visibility="collapsed",
        )
        if col_b.button("Enviar", key=f"send_{tarea_id}", use_container_width=True):
            if nuevo_msg.strip():
                try:
                    current_user_id = current_user().get("id")
                    add_mensaje_tarea(tarea_id, current_user_id, nuevo_msg)
                    st.success("Mensaje enviado.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")
        
        # Opciones (solo admin)
        if is_admin:
            st.divider()
            col_a, col_b, col_c = st.columns(3)
            
            # Cambiar estado
            nuevo_estado = col_a.selectbox(
                "Cambiar estado",
                ["abierta", "en_coordinacion", "cerrada"],
                index=["abierta", "en_coordinacion", "cerrada"].index(estado),
                key=f"estado_{tarea_id}",
            )
            if col_b.button("Actualizar", key=f"update_estado_{tarea_id}", use_container_width=True):
                try:
                    update_estado_tarea(tarea_id, nuevo_estado)
                    st.success("Estado actualizado.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")
            
            if col_c.button("🗑️ Eliminar", key=f"del_tarea_{tarea_id}", use_container_width=True):
                try:
                    delete_tarea(tarea_id)
                    st.success("Tarea eliminada.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")
        
        st.divider()


# ── ROUTER ────────────────────────────────────────────────────────────────────
pages = {
    "🏠 Inicio":    page_dashboard,
    "📅 Visitas":   page_visitas,
    "👥 Monitores": page_monitores,
    "📋 Ensayos":   page_ensayos,
    "📁 Documentos": page_documentos,
    "💬 Tareas":    page_tareas,
    "🔑 Usuarios":  page_usuarios,
}
pages[nav]()
