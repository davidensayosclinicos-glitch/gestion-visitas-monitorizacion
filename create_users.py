#!/usr/bin/env python3
"""
Script para crear usuarios iniciales en Supabase
"""
import os
import sys
import psycopg
from pathlib import Path

# Agregar el directorio padre al path para importar database.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import _hash_password

DATABASE_URL = "postgresql://postgres.jpavxmbxckrjlibvayuq:DdCGziXjdBjZVWj6@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
ADMIN_USER = "CABUEÑES"
ADMIN_PASSWORD = "CABUEÑES"

def main():
    print("\n👤 Configurando usuario ADMIN...\n")
    
    try:
        conn = psycopg.connect(
            DATABASE_URL,
            autocommit=False,
            prepare_threshold=None
        )
        
        with conn.cursor() as cur:
            # Verificar si ya existe el admin
            cur.execute(
                "SELECT id, username FROM public.usuarios WHERE username = %s",
                (ADMIN_USER,)
            )
            existing = cur.fetchone()
            
            if existing:
                print(f"⏭️  Usuario {ADMIN_USER} ya existe (ID: {existing[0]})")
                print(f"   Puedes cambiar la contraseña manualmente en la app")
            else:
                # Crear el usuario admin
                password_hash = _hash_password(ADMIN_PASSWORD)
                
                cur.execute(
                    """INSERT INTO public.usuarios 
                       (username, password_hash, rol, monitor_id, activo) 
                       VALUES (%s, %s, %s, %s, %s)
                       RETURNING id""",
                    (ADMIN_USER, password_hash, "admin", None, 1)
                )
                admin_id = cur.fetchone()[0]
                conn.commit()
                
                print(f"✅ Usuario admin creado:")
                print(f"   Usuario: {ADMIN_USER}")
                print(f"   Contraseña: {ADMIN_PASSWORD}")
                print(f"   ID: {admin_id}")
            
            # Listar usuarios actuales
            print("\n📋 Usuarios actuales en el sistema:\n")
            cur.execute(
                """SELECT u.id, u.username, u.rol, u.activo, 
                          m.nombre as monitor_nombre, e.codigo as ensayo_codigo
                   FROM public.usuarios u
                   LEFT JOIN public.monitores m ON m.id = u.monitor_id
                   LEFT JOIN public.ensayos e ON e.id = m.ensayo_id
                   ORDER BY u.id"""
            )
            
            usuarios = cur.fetchall()
            if not usuarios:
                print("   (Sin usuarios aún)")
            else:
                for uid, username, rol, activo, monitor_nombre, ensayo_codigo in usuarios:
                    estado = "✅ Activo" if activo else "❌ Inactivo"
                    if rol == "admin":
                        print(f"   • {username} [{rol.upper()}] {estado}")
                    else:
                        ensayo_txt = f"Ensayo: {ensayo_codigo}" if ensayo_codigo else "(sin ensayo)"
                        monitor_txt = f"Monitor: {monitor_nombre}" if monitor_nombre else ""
                        print(f"   • {username} [{rol}] {monitor_txt} {ensayo_txt} {estado}")
            
            # Verificar monitores sin usuario
            print("\n📊 Monitores disponibles para crear usuarios:\n")
            cur.execute(
                """SELECT m.id, m.nombre, m.apellidos, e.codigo as ensayo_codigo,
                          CASE WHEN u.id IS NOT NULL THEN 'Sí' ELSE 'No' END as tiene_usuario
                   FROM public.monitores m
                   LEFT JOIN public.ensayos e ON e.id = m.ensayo_id
                   LEFT JOIN public.usuarios u ON u.monitor_id = m.id
                   ORDER BY m.id"""
            )
            
            monitores = cur.fetchall()
            if not monitores:
                print("   (Sin monitores aún)")
            else:
                for mid, nombre, apellidos, ensayo_codigo, tiene_usuario in monitores:
                    user_status = "✅ Tiene usuario" if tiene_usuario == "Sí" else "❌ Sin usuario"
                    ensayo_txt = f"[{ensayo_codigo}]" if ensayo_codigo else "[sin ensayo]"
                    print(f"   • ID {mid}: {nombre} {apellidos} {ensayo_txt} {user_status}")
        
        conn.close()
        print("\n✅ Verificación completada\n")
        return 0
    
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
