"""
database.py — Capa de acceso a datos SQLite
Gestión de Visitas de Monitorización — Ensayos Clínicos
"""
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).parent / "data" / "gvm.db"


def _get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ensayos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo       TEXT NOT NULL,
            nombre       TEXT NOT NULL,
            promotor     TEXT DEFAULT '',
            fase         TEXT DEFAULT '',
            ip           TEXT DEFAULT '',
            estado       TEXT DEFAULT 'activo',
            fecha_inicio TEXT DEFAULT '',
            fecha_fin    TEXT DEFAULT '',
            notas        TEXT DEFAULT '',
            creado_en    TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS monitores (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT NOT NULL,
            apellidos TEXT NOT NULL,
            empresa   TEXT DEFAULT '',
            email     TEXT DEFAULT '',
            telefono  TEXT DEFAULT '',
            activo    INTEGER DEFAULT 1,
            notas     TEXT DEFAULT '',
            creado_en TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS visitas (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ensayo_id      INTEGER REFERENCES ensayos(id),
            monitor_id     INTEGER REFERENCES monitores(id),
            fecha          TEXT NOT NULL,
            hora           TEXT DEFAULT '',
            tipo           TEXT NOT NULL,
            estado         TEXT DEFAULT 'pendiente',
            notas          TEXT DEFAULT '',
            creado_en      TEXT DEFAULT (datetime('now','localtime')),
            actualizado_en TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    conn.close()


# ── ENSAYOS ───────────────────────────────────────────────────────────────────

def get_ensayos(texto='', estado=''):
    conn = _get_conn()
    q = "SELECT * FROM ensayos WHERE 1=1"
    params = []
    if estado:
        q += " AND estado = ?"
        params.append(estado)
    if texto:
        q += " AND (LOWER(codigo) LIKE LOWER(?) OR LOWER(nombre) LIKE LOWER(?) OR LOWER(promotor) LIKE LOWER(?))"
        t = f"%{texto}%"
        params.extend([t, t, t])
    q += " ORDER BY codigo"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ensayo_by_id(eid):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM ensayos WHERE id = ?", (eid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_ensayo(data):
    conn = _get_conn()
    conn.execute("""
        INSERT INTO ensayos (codigo, nombre, promotor, fase, ip, estado, fecha_inicio, fecha_fin, notas)
        VALUES (:codigo, :nombre, :promotor, :fase, :ip, :estado, :fecha_inicio, :fecha_fin, :notas)
    """, data)
    conn.commit()
    conn.close()


def update_ensayo(eid, data):
    conn = _get_conn()
    conn.execute("""
        UPDATE ensayos SET codigo=:codigo, nombre=:nombre, promotor=:promotor, fase=:fase,
        ip=:ip, estado=:estado, fecha_inicio=:fecha_inicio, fecha_fin=:fecha_fin, notas=:notas
        WHERE id=:id
    """, {**data, 'id': eid})
    conn.commit()
    conn.close()


def delete_ensayo(eid):
    conn = _get_conn()
    conn.execute("DELETE FROM ensayos WHERE id = ?", (eid,))
    conn.commit()
    conn.close()


# ── MONITORES ─────────────────────────────────────────────────────────────────

def get_monitores(texto=''):
    conn = _get_conn()
    q = "SELECT * FROM monitores WHERE 1=1"
    params = []
    if texto:
        q += """ AND (LOWER(nombre) LIKE LOWER(?) OR LOWER(apellidos) LIKE LOWER(?)
                  OR LOWER(empresa) LIKE LOWER(?) OR LOWER(email) LIKE LOWER(?))"""
        t = f"%{texto}%"
        params.extend([t, t, t, t])
    q += " ORDER BY apellidos, nombre"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monitor_by_id(mid):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM monitores WHERE id = ?", (mid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_monitor(data):
    conn = _get_conn()
    conn.execute("""
        INSERT INTO monitores (nombre, apellidos, empresa, email, telefono, activo, notas)
        VALUES (:nombre, :apellidos, :empresa, :email, :telefono, :activo, :notas)
    """, data)
    conn.commit()
    conn.close()


def update_monitor(mid, data):
    conn = _get_conn()
    conn.execute("""
        UPDATE monitores SET nombre=:nombre, apellidos=:apellidos, empresa=:empresa,
        email=:email, telefono=:telefono, activo=:activo, notas=:notas
        WHERE id=:id
    """, {**data, 'id': mid})
    conn.commit()
    conn.close()


def delete_monitor(mid):
    conn = _get_conn()
    conn.execute("DELETE FROM monitores WHERE id = ?", (mid,))
    conn.commit()
    conn.close()


# ── VISITAS ───────────────────────────────────────────────────────────────────

def get_visitas_df(texto='', estado='', ensayo_id=None, desde='', hasta=''):
    conn = _get_conn()
    q = """
        SELECT v.id, v.ensayo_id, v.monitor_id, v.fecha, v.hora, v.tipo, v.estado, v.notas,
               e.codigo AS ensayo_codigo, e.nombre AS ensayo_nombre,
               m.nombre || ' ' || m.apellidos AS monitor_nombre,
               m.empresa AS monitor_empresa
        FROM visitas v
        LEFT JOIN ensayos  e ON v.ensayo_id  = e.id
        LEFT JOIN monitores m ON v.monitor_id = m.id
        WHERE 1=1
    """
    params = []
    if estado:
        q += " AND v.estado = ?"
        params.append(estado)
    if ensayo_id:
        q += " AND v.ensayo_id = ?"
        params.append(ensayo_id)
    if desde:
        q += " AND v.fecha >= ?"
        params.append(desde)
    if hasta:
        q += " AND v.fecha <= ?"
        params.append(hasta)
    if texto:
        q += """ AND (LOWER(m.nombre || ' ' || m.apellidos) LIKE LOWER(?)
                  OR LOWER(e.codigo) LIKE LOWER(?) OR LOWER(e.nombre) LIKE LOWER(?)
                  OR LOWER(v.tipo) LIKE LOWER(?))"""
        t = f"%{texto}%"
        params.extend([t, t, t, t])
    q += " ORDER BY v.fecha DESC, v.hora DESC"
    try:
        df = pd.read_sql_query(q, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_visita_by_id(vid):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM visitas WHERE id = ?", (vid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_visita(data):
    conn = _get_conn()
    conn.execute("""
        INSERT INTO visitas (ensayo_id, monitor_id, fecha, hora, tipo, estado, notas)
        VALUES (:ensayo_id, :monitor_id, :fecha, :hora, :tipo, :estado, :notas)
    """, data)
    conn.commit()
    conn.close()


def update_visita(vid, data):
    conn = _get_conn()
    conn.execute("""
        UPDATE visitas SET ensayo_id=:ensayo_id, monitor_id=:monitor_id, fecha=:fecha,
        hora=:hora, tipo=:tipo, estado=:estado, notas=:notas,
        actualizado_en=datetime('now','localtime')
        WHERE id=:id
    """, {**data, 'id': vid})
    conn.commit()
    conn.close()


def delete_visita(vid):
    conn = _get_conn()
    conn.execute("DELETE FROM visitas WHERE id = ?", (vid,))
    conn.commit()
    conn.close()


# ── ESTADÍSTICAS ──────────────────────────────────────────────────────────────

def get_stats():
    conn = _get_conn()
    mes = date.today().strftime('%Y-%m')
    stats = {
        'total_mes': conn.execute(
            "SELECT COUNT(*) FROM visitas WHERE fecha LIKE ?", (f"{mes}%",)).fetchone()[0],
        'pendientes': conn.execute(
            "SELECT COUNT(*) FROM visitas WHERE estado IN ('pendiente','confirmada')").fetchone()[0],
        'realizadas': conn.execute(
            "SELECT COUNT(*) FROM visitas WHERE estado = 'realizada'").fetchone()[0],
        'ensayos_activos': conn.execute(
            "SELECT COUNT(*) FROM ensayos WHERE estado = 'activo'").fetchone()[0],
    }
    conn.close()
    return stats


def get_proximas_visitas(limit=10):
    conn = _get_conn()
    hoy = date.today().isoformat()
    q = """
        SELECT v.fecha, v.hora, v.tipo, v.estado,
               m.nombre || ' ' || m.apellidos AS monitor,
               e.codigo || ' — ' || e.nombre   AS ensayo
        FROM visitas v
        LEFT JOIN ensayos  e ON v.ensayo_id  = e.id
        LEFT JOIN monitores m ON v.monitor_id = m.id
        WHERE v.fecha >= ? AND v.estado NOT IN ('cancelada', 'realizada')
        ORDER BY v.fecha, v.hora
        LIMIT ?
    """
    try:
        df = pd.read_sql_query(q, conn, params=(hoy, limit))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_resumen_por_ensayo():
    conn = _get_conn()
    q = """
        SELECT e.codigo, e.nombre, e.estado AS estado_ensayo,
               COUNT(v.id) AS total,
               SUM(CASE WHEN v.estado IN ('pendiente','confirmada') THEN 1 ELSE 0 END) AS pendientes,
               SUM(CASE WHEN v.estado = 'realizada'  THEN 1 ELSE 0 END) AS realizadas,
               SUM(CASE WHEN v.estado = 'cancelada'  THEN 1 ELSE 0 END) AS canceladas
        FROM ensayos e
        LEFT JOIN visitas v ON e.id = v.ensayo_id
        GROUP BY e.id
        ORDER BY e.codigo
    """
    try:
        df = pd.read_sql_query(q, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


# ── BACKUP / RESTORE ──────────────────────────────────────────────────────────

def get_db_bytes():
    if not DB_PATH.exists():
        return None
    with open(DB_PATH, 'rb') as f:
        return f.read()


def restore_db_bytes(data: bytes):
    DB_PATH.parent.mkdir(exist_ok=True)
    with open(DB_PATH, 'wb') as f:
        f.write(data)
