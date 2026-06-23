-- Script auxiliar para crear usuarios de monitores
-- Ejecutar DESPUÉS de aplicar 2026-06-22_migracion_auth_roles.sql
-- 
-- Este archivo es solo de referencia. La creación real de usuarios se hace con:
--   python scripts/crear_usuarios_monitores.py
--
-- Motivo:
-- la app usa hashes PBKDF2-SHA256 y PostgreSQL no los genera de forma nativa
-- sin una función adicional. Si quieres insertar manualmente un usuario,
-- genera el hash con el script CLI o con la propia app.

-- Ejemplo de inserción manual:
-- INSERT INTO public.usuarios (username, password_hash, rol, monitor_id, activo)
-- VALUES ('admin', '<hash_pbkdf2>', 'admin', NULL, 1)
-- ON CONFLICT (username) DO NOTHING;

-- Para crear el usuario ADMIN y los monitores, usa el script CLI y configura:
--   export DATABASE_URL="postgresql://..."
--   export ADMIN_USER="tu_usuario_admin"
--   export ADMIN_PASSWORD="tu_password_admin"
