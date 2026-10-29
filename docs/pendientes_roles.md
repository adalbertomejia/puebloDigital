# Roles y alcance — Dahiedhi

## Decisión vigente del cliente — 29 de octubre de 2026

El **PRESIDENTE opera su comité**. Sustituye la propuesta inicial de un operador separado. En este corte se mantiene el alcance implementado: eventos **generales** de sus comités activos; la operación de eventos de manzana corresponde a su responsable. Tener comité convocante en un evento territorial no concede su gestión al presidente.

## Segundo paso: autorización de operación

- `PerfilAcceso` enlaza cuenta y ciudadano. La responsabilidad territorial se deriva de `Manzana.responsable`, la pertenencia del ciudadano y los estados activos de cuenta, ciudadano y manzana.
- `UsuarioApp` activo y comité activo habilitan al PRESIDENTE para crear y editar eventos generales de ese comité, generar participantes y cambiar estados. Puede capturar todos sus participantes y consultar/exportar dentro del alcance existente.
- El responsable conserva la gestión de los eventos de su manzana. En eventos generales captura únicamente registros de ciudadanos de su manzana; no genera la lista comunitaria ni edita el evento general.
- Una cuenta con ambas responsabilidades conserva ambos ámbitos, también al crear eventos.
- `apps/operacion/autorizacion.py` concentra resolución de ámbitos y decisiones de creación/gestión. Generación, edición y cambio de estado comparten la política de gestión.
- La consulta de participantes (`visibles_para`) y su escritura (`capturables_para`) están separadas. Captura normal, secuencial, selección del siguiente registro y métricas de captura usan el ámbito de escritura. Los permisos `view_*` no habilitan captura ni generación, incluso combinados con un cargo territorial.
- Los permisos Django explícitos de cambio siguen siendo globales: `change_faena`/`change_junta` habilitan gestión y captura del tipo de evento; `change_registrofaena`/`change_asistenciajunta` habilitan captura del tipo de participante. Las vistas siguen exigiendo además visibilidad del evento. No asignar esos permisos esperando restricción por comité. El superusuario conserva acceso global.
- Los controles de interfaz reflejan estos permisos, pero las peticiones de servidor los verifican de forma independiente.
- PRESIDENTE no recibe por este cambio permisos de borrado, tesorería, staff ni administración de usuarios. Los permisos explícitos de borrado existentes se conservan.
- Este paso no modifica el esquema ni requiere migraciones.

## Aclaraciones ya resueltas

- No se creará un rol operativo separado de PRESIDENTE para este recorrido.
- Eventos de manzana pueden crearse sin comité si incluyen motivo. La anterior descripción de comité obligatorio quedó superada por las migraciones/código posteriores.

## Trabajo pendiente, fuera de este paso

1. Tesorería por comité para TESORERO: consultas, exportaciones, escritura y cancelación/reversa con motivo. La consulta financiera aún no queda aislada por este cambio.
2. Decidir si admin será exclusivo del administrador global o aplicará aislamiento contextual en modelos, relaciones, inlines, acciones y autocomplete. Actualmente conserva permisos Django por modelo.
3. Asegurar unicidad de responsable y pertenencia a su manzana, previo inventario y migración revisable de conflictos.
4. Vigencias e historial de cargos y territorio; decidir acceso histórico cuando un participante cambia de manzana.
5. Auditoría de quién creó/actualizó eventos y registros.
6. Reconciliar migraciones regeneradas con el esquema e historial reales del VPS antes del siguiente despliegue; probar sobre una copia restaurada, sin reset ni fake automático.
7. Revisar fallos existentes de la suite general, manteniéndolos separados de la cobertura de autorización de este paso.

## Verificación de este paso

Pruebas sintéticas en `apps/operacion/test_alcance_autorizacion.py`: presidente con generación idempotente, captura normal/secuencial, creación/edición y estado; denegación fuera de comité aun con lectura global; lectores sin escritura; responsable con lectura global sin ampliación de captura; revocación por cargo/comité inactivo; responsabilidades combinadas y permisos de cambio global explícitos. No validan el estado del VPS ni sustituyen la auditoría pendiente de tesorería/admin.

Resultado local del 29 de octubre de 2026: suite completa de nueve módulos, **176 pruebas ejecutadas, 169 aprobadas, 5 fallos y 2 errores**. Los siete casos que no pasan coinciden por nombre y tipo con la línea base previa (166 pruebas); las diez pruebas nuevas pasan. `manage.py check` sin incidencias y `makemigrations --check --dry-run` sin cambios. Estos resultados no equivalen a una certificación completa de seguridad ni a una validación en producción.
