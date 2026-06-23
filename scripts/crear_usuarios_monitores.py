#!/usr/bin/env python3
"""
Script para crear usuarios de monitores desde la CLI.

Uso:
    ADMIN_USER=... ADMIN_PASSWORD=... python scripts/crear_usuarios_monitores.py

Comportamiento:
1. Se conecta a la BD
2. Lee todos los monitores existentes
3. Crea un usuario para cada monitor si todavía no existe
4. Crea el usuario ADMIN si se han definido ADMIN_USER y ADMIN_PASSWORD
"""

import os
import sys
import unicodedata

import psycopg

# Agregar el directorio padre al path para importar database.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import _hash_password

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_USER = os.getenv("ADMIN_USER", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()

def get_db_conn():
    """Conexión directa a PostgreSQL."""
    if not DATABASE_URL:
        raise ValueError("Falta DATABASE_URL")
    return psycopg.connect(DATABASE_URL)


def normalizar_username(value, fallback):
    """Genera un username estable y legible."""
    raw = (value or "").strip()
    if not raw:
        return fallback

    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()

    cleaned = []
    previous_dot = False
    for char in normalized:
        if char.isalnum():
            cleaned.append(char)
            previous_dot = False
        else:
            if not previous_dot:
                cleaned.append(".")
                previous_dot = True

    username = "".join(cleaned).strip(".")
    return username or fallback

def crear_usuario_admin():
    """
    Crea el usuario ADMIN si no existe.
    """
    if not ADMIN_USER or not ADMIN_PASSWORD:
        print("⚠️  ADMIN_USER/ADMIN_PASSWORD no definidos, se omite el usuario ADMIN.")
        return

    print("\n👤 Configurando usuario ADMIN...")

    admin_user = ADMIN_USER
    admin_password = ADMIN_PASSWORD
    
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                # Verificar si ya existe
                cur.execute(
                    "SELECT id FROM public.usuarios WHERE username = %s",
                    (admin_user,)
                )
                if cur.fetchone():
                    print(f"⏭️  Usuario {admin_user} ya existe, saltando...")
                    return
                
                password_hash = _hash_password(admin_password)
                
                # Insertar
                cur.execute(
                    """INSERT INTO public.usuarios 
                       (username, password_hash, rol, monitor_id, activo) 
                       VALUES (%s, %s, %s, %s, %s)""",
                    (admin_user, password_hash, "admin", None, 1)
                )
                conn.commit()
                print(f"✅ Admin usuario creado: {admin_user}")
                print(f"   Contraseña: {admin_password}")
    except Exception as e:
        print(f"❌ Error al crear admin: {e}")

def crear_usuarios_monitores():
    """
    Crea usuarios para todos los monitores existentes.

    La contraseña inicial de cada monitor es su nombre, para repartirla
    fácilmente y cambiarla después con el flujo normal.
    """
    print("📋 Leyendo monitores desde BD...")
    
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                # Leer todos los monitores
                cur.execute(
                    "SELECT id, nombre, apellidos, email FROM public.monitores ORDER BY id"
                )
                monitores = cur.fetchall()
                
                if not monitores:
                    print("⚠️  No hay monitores en la BD. Agrega monitores primero.")
                    return
                
                print(f"✓ Encontrados {len(monitores)} monitores\n")
                
                # Para cada monitor, crear usuario
                for monitor in monitores:
                    monitor_id = monitor[0]
                    nombre = monitor[1]
                    apellidos = monitor[2]
                    email = monitor[3]
                    full_name = f"{nombre} {apellidos}".strip()
                    username_source = email or full_name
                    username = normalizar_username(username_source, f"monitor-{monitor_id}")
                    
                    # Verificar si ya existe usuario para este monitor
                    cur.execute(
                        "SELECT id FROM public.usuarios WHERE monitor_id = %s",
                        (monitor_id,)
                    )
                    if cur.fetchone():
                        print(f"⏭️  {full_name}: ya tiene usuario, saltando...")
                        continue
                    
                    # Contraseña = nombre del monitor
                    password = nombre
                    password_hash = _hash_password(password)
                    
                    # Insertar usuario
                    try:
                        cur.execute(
                            """INSERT INTO public.usuarios 
                               (username, password_hash, rol, monitor_id, activo) 
                               VALUES (%s, %s, %s, %s, %s)""",
                            (username, password_hash, "monitor", monitor_id, 1)
                        )
                        conn.commit()
                        print(f"✅ {full_name}: usuario creado")
                        print(f"   Usuario: {username}")
                        print(f"   Contraseña: {password}")
                    except Exception as e:
                        print(f"❌ {full_name}: error al crear usuario")
                        print(f"   {e}")
    
    except Exception as e:
        print(f"❌ Error al leer monitores: {e}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    print("\n🔐 CREADOR DE USUARIOS - SISTEMA DE MONITORES\n")
    print("="*60)
    
    # Verificar DATABASE_URL
    if not DATABASE_URL:
        print("❌ No encontrado: DATABASE_URL")
        print("\nConfigura:")
        print("  export DATABASE_URL='postgresql://postgres.usuario:password@host:puerto/bd'")
        sys.exit(1)
    
    # Crear admin primero si está configurado
    crear_usuario_admin()
    
    # Luego crear monitores
    crear_usuarios_monitores()
    
    print("\n✨ ¡Listo! Usa la app para login:")
    if ADMIN_USER and ADMIN_PASSWORD:
        print(f"   Admin: {ADMIN_USER} / {ADMIN_PASSWORD}")
    else:
        print("   Admin: define ADMIN_USER y ADMIN_PASSWORD para crearlo")
    print("   Monitor: usuario generado por el script / contraseña = nombre")
