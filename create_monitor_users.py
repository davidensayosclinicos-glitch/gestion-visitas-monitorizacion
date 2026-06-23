#!/usr/bin/env python3
"""
Script para crear usuarios para todos los monitores sin usuario
"""
import os
import sys
import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import _hash_password

DATABASE_URL = "postgresql://postgres.jpavxmbxckrjlibvayuq:DdCGziXjdBjZVWj6@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def normalizar_username(value, fallback):
    """Genera un username estable y legible."""
    import unicodedata
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

def main():
    print("\n👥 Creando usuarios para monitores...\n")
    
    try:
        conn = psycopg.connect(
            DATABASE_URL,
            autocommit=False,
            prepare_threshold=None
        )
        
        with conn.cursor() as cur:
            # Obtener monitores sin usuario
            cur.execute(
                """SELECT m.id, m.nombre, m.apellidos, m.email, e.codigo as ensayo_codigo
                   FROM public.monitores m
                   LEFT JOIN public.ensayos e ON e.id = m.ensayo_id
                   LEFT JOIN public.usuarios u ON u.monitor_id = m.id
                   WHERE u.id IS NULL
                   ORDER BY m.id"""
            )
            
            monitores = cur.fetchall()
            
            if not monitores:
                print("⏭️  Todos los monitores ya tienen usuario")
                return 0
            
            print(f"Encontrados {len(monitores)} monitores sin usuario:\n")
            
            usuarios_creados = []
            
            for mid, nombre, apellidos, email, ensayo_codigo in monitores:
                # Generar username
                username_source = email or f"{nombre} {apellidos}"
                username = normalizar_username(username_source, f"monitor{mid}")
                
                # Contraseña inicial = nombre del monitor
                password = nombre.strip()
                password_hash = _hash_password(password)
                
                try:
                    cur.execute(
                        """INSERT INTO public.usuarios 
                           (username, password_hash, rol, monitor_id, activo) 
                           VALUES (%s, %s, %s, %s, %s)
                           RETURNING id""",
                        (username, password_hash, "monitor", mid, 1)
                    )
                    uid = cur.fetchone()[0]
                    conn.commit()
                    
                    usuarios_creados.append((username, password, nombre, apellidos, ensayo_codigo))
                    print(f"✅ {nombre} {apellidos}")
                    print(f"   Usuario: {username}")
                    print(f"   Contraseña: {password}")
                    print(f"   Ensayo: {ensayo_codigo}")
                    print()
                
                except Exception as e:
                    conn.rollback()
                    print(f"❌ Error con {nombre} {apellidos}: {e}\n")
            
            # Resumen
            if usuarios_creados:
                print(f"\n✅ {len(usuarios_creados)} usuario(s) de monitor creado(s)\n")
                
                # Guardar credenciales en archivo
                creds_file = "USUARIOS_INICIALES.txt"
                with open(creds_file, 'w', encoding='utf-8') as f:
                    f.write("=" * 60 + "\n")
                    f.write("CREDENCIALES DE USUARIOS - Gestión de Visitas\n")
                    f.write("Generadas: 2026-06-23\n")
                    f.write("=" * 60 + "\n\n")
                    
                    f.write("USUARIO ADMIN:\n")
                    f.write("-" * 60 + "\n")
                    f.write("Usuario: CABUEÑES\n")
                    f.write("Contraseña: CABUEÑES\n")
                    f.write("-" * 60 + "\n\n")
                    
                    f.write("USUARIOS DE MONITORES:\n")
                    f.write("-" * 60 + "\n")
                    for username, password, nombre, apellidos, ensayo_codigo in usuarios_creados:
                        f.write(f"\nMonitor: {nombre} {apellidos}\n")
                        f.write(f"Usuario: {username}\n")
                        f.write(f"Contraseña: {password}\n")
                        f.write(f"Ensayo: {ensayo_codigo}\n")
                
                print(f"📄 Credenciales guardadas en: {creds_file}\n")
        
        conn.close()
        print("✅ Completado\n")
        return 0
    
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
