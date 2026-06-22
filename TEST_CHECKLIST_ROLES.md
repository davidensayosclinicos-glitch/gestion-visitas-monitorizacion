# Checklist de validacion de roles

Objetivo: verificar que admin y monitor ven y hacen solo lo permitido.

## 1) Preparacion

1. Aplica la migracion: sql/2026-06-22_migracion_auth_roles.sql.
2. Si vas a usar RLS estricto con Supabase Auth, aplica tambien: sql/2026-06-22_rls_policies.sql.
3. Configura ADMIN_USER y ADMIN_PASSWORD en secretos.
4. Inicia la app.

## 2) Casos de admin

1. Login con ADMIN_USER.
   Resultado esperado: acceso a Inicio, Visitas, Monitores y Ensayos.
2. Ver calendario y bloquear un dia.
   Resultado esperado: puede bloquear/desbloquear sin error.
3. Crear usuario para monitor desde Monitores.
   Resultado esperado: usuario creado y visible en tabla de usuarios.
4. Editar y eliminar visita de cualquier ensayo.
   Resultado esperado: operación permitida.
5. Exportar CSV en Visitas.
   Resultado esperado: botón disponible y descarga correcta.

## 3) Casos de monitor

1. Login con usuario de monitor.
   Resultado esperado: solo ve Inicio y Visitas.
2. Revisar panel Inicio.
   Resultado esperado: no ve resumen global por ensayo ni gestión de bloqueos.
3. Abrir calendario.
   Resultado esperado: ve disponibilidad, pero no controles de bloquear/desbloquear.
4. Crear visita.
   Resultado esperado: ensayo fijo al suyo y monitor fijo a sí mismo.
5. Intentar editar visita ajena o de otro ensayo.
   Resultado esperado: bloqueado por permisos.
6. Intentar eliminar visita ajena o de otro ensayo.
   Resultado esperado: bloqueado por permisos.
7. Revisar tabla de visitas.
   Resultado esperado: no aparecen ensayos ajenos ni monitores ajenos.
8. Revisar exportación CSV.
   Resultado esperado: botón no disponible.

## 4) Casos de seguridad RLS (si se activó)

1. Con usuario monitor autenticado en Supabase, ejecutar select sobre ensayos.
   Resultado esperado: solo devuelve su ensayo.
2. Con usuario monitor, intentar insert en dias_bloqueados.
   Resultado esperado: error por policy.
3. Con usuario monitor, intentar insert en visitas con monitor_id distinto al suyo.
   Resultado esperado: error por policy.
4. Con usuario admin, repetir insert/update/delete sobre tablas.
   Resultado esperado: permitido.

## 5) Criterio de aceptacion

1. Ningun monitor puede bloquear dias.
2. Ningun monitor puede operar fuera de su ensayo.
3. Ningun monitor puede ver ensayos ajenos.
4. Solo admin puede verlo y gestionarlo todo.
