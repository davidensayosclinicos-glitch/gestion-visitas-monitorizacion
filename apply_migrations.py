#!/usr/bin/env python3
"""
Script para aplicar todas las migraciones SQL a Supabase
"""
import os
import sys
import psycopg
from pathlib import Path

DATABASE_URL = "postgresql://postgres.jpavxmbxckrjlibvayuq:DdCGziXjdBjZVWj6@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def read_sql_file(filepath):
    """Lee un archivo SQL"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def execute_migration(conn, migration_name, sql_content):
    """Ejecuta una migración"""
    try:
        with conn.cursor() as cur:
            cur.execute(sql_content)
        conn.commit()
        print(f"✅ {migration_name}")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ {migration_name}: {e}")
        return False

def main():
    print("\n🚀 Aplicando migraciones a Supabase...\n")
    
    sql_dir = Path(__file__).parent / "sql"
    migrations = [
        ("2026-06-22_migracion_auth_roles.sql", "Crear tablas y estructura de roles"),
        ("2026-06-22_rls_policies.sql", "Aplicar políticas de RLS"),
    ]
    
    try:
        conn = psycopg.connect(
            DATABASE_URL,
            autocommit=False,
            prepare_threshold=None
        )
        
        for filename, description in migrations:
            filepath = sql_dir / filename
            if not filepath.exists():
                print(f"⚠️  {filename}: Archivo no encontrado ({filepath})")
                continue
            
            sql_content = read_sql_file(filepath)
            print(f"Aplicando: {description}")
            execute_migration(conn, f"  {filename}", sql_content)
        
        conn.close()
        print("\n✅ Todas las migraciones completadas\n")
        return 0
    
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
