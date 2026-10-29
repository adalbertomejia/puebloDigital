# Roles y alcance — Dahiedhi

## Decisión vigente del cliente — 29 de octubre de 2026

El **PRESIDENTE opera su comité**. Sustituye la propuesta inicial de un operador separado. En este corte se mantiene el alcance implementado: eventos **generales** de sus comités activos; la operación de eventos de manzana corresponde a su responsable. Tener comité convocante en un evento territorial no concede su gestión al presidente.

## Tercer paso: herencia financiera por comité

**Decisión del cliente:** estructura padre-hijo; PRESIDENTE en primer nivel y TESORERO en segundo nivel. La jerarquía se aplica dentro del comité de cada asignación activa. La autorización financiera está implementada en las vistas operativas mediante `apps/tesoreria/autorizacion.py`. No exige duplicar el cargo TESORERO de una cuenta PRESIDENTE.

| Actor | Capacidades implementadas | Ámbito obligatorio |
|---|---|---|
| PRESIDENTE | Capacidades financieras de TESORERO más gestión de eventos generales ya implementada | Sus comités con presidencia activa |
| TESORERO | Consultar y gestionar conceptos, obligaciones y abonos; reportes y exportaciones financieros | Sus comités con tesorería activa |
| Responsable de manzana | Operación territorial existente; el cargo no concede tesorería | Su manzana y participantes propios según las reglas existentes |
| Superusuario | Administración global explícita | Comunidad completa |

La herencia expresa capacidades, no subordinación entre cuentas: no requiere crear un UsuarioApp TESORERO adicional para un PRESIDENTE, y no concede staff ni administración de cargos. Cancelación/reversa y borrado conservan las condiciones acordadas para cada acción; la jerarquía no implementa automáticamente funciones aún pendientes.

Una cuenta puede tener cargos distintos en comités distintos. Sus capacidades se calculan por cada pareja rol-comité: ser presidente de Agua y tesorero de Feria no convierte a la cuenta en presidente de Feria. No basta con detectar un rol alto en cualquier asignación.

Criterios de implementación y aceptación:

1. Resolver comités financieros desde asignaciones activas PRESIDENTE o TESORERO y comité activo; cuenta inactiva o sin asignaciones no obtiene acceso. Superusuario es la excepción global explícita.
2. Aplicar el ámbito antes de filtros GET, anotaciones, métricas, paginación y exportaciones. Conceptos, obligaciones y abonos derivan su comité del concepto; no duplicar el comité en esos registros.
3. Verificar acciones sobre el objeto autorizado en GET y POST; limitar comités del formulario e impedir cambiar un objeto a un comité ajeno. Ningún permiso Django por modelo debe ampliar silenciosamente el ámbito de un cargo contextual.
4. Cubrir listados, detalle por ID, creación/edición, generación de obligaciones, abonos, búsquedas, CSV, resúmenes y datos financieros relacionados en expediente/dashboard. El admin financiero y sus inlines, la asignación de cargos/vínculos y la administración de cuentas/grupos quedan reservados al superusuario. Los cargos financieros operan desde las vistas del panel, sin necesitar staff.
5. Probar al menos dos comités con presidentes y tesoreros diferentes, cargos combinados, asignaciones/comités inactivos, cuenta sin cargos y superusuario. Comprobar tanto lectura denegada como ausencia de modificaciones ajenas y de importes ajenos en métricas/exportaciones.
6. Mantener los cambios en `codex/permisos-presidente`, con pruebas sintéticas y entrega revisable; no desplegar al VPS sin la revisión acordada.

## Segundo paso (anterior): autorización de operación

- `PerfilAcceso` enlaza cuenta y ciudadano. La responsabilidad territorial se deriva de `Manzana.responsable`, la pertenencia del ciudadano y los estados activos de cuenta, ciudadano y manzana.
- `UsuarioApp` activo y comité activo habilitan al PRESIDENTE para crear y editar eventos generales de ese comité, generar participantes y cambiar estados. Puede capturar todos sus participantes y consultar/exportar dentro del alcance existente.
- El responsable conserva la gestión de los eventos de su manzana. En eventos generales captura únicamente registros de ciudadanos de su manzana; no genera la lista comunitaria ni edita el evento general.
- Una cuenta con ambas responsabilidades conserva ambos ámbitos, también al crear eventos.
- `apps/operacion/autorizacion.py` concentra resolución de ámbitos y decisiones de creación/gestión. Generación, edición y cambio de estado comparten la política de gestión.
- La consulta de participantes (`visibles_para`) y su escritura (`capturables_para`) están separadas. Captura normal, secuencial, selección del siguiente registro y métricas de captura usan el ámbito de escritura. Los permisos `view_*` no habilitan captura ni generación, incluso combinados con un cargo territorial.
- Los permisos Django explícitos de cambio siguen siendo globales: `change_faena`/`change_junta` habilitan gestión y captura del tipo de evento; `change_registrofaena`/`change_asistenciajunta` habilitan captura del tipo de participante. Las vistas siguen exigiendo además visibilidad del evento. No asignar esos permisos esperando restricción por comité. El superusuario conserva acceso global.
- Los controles de interfaz reflejan estos permisos, pero las peticiones de servidor los verifican de forma independiente.
- En el segundo paso, PRESIDENTE no recibió tesorería, staff ni administración de usuarios ni borrado de eventos. El tercer paso incorpora la herencia financiera descrita arriba; no amplía el borrado de eventos ni la administración de cuentas/cargos.
- Este paso no modifica el esquema ni requiere migraciones.

## Aclaraciones ya resueltas

- No se creará un rol operativo separado de PRESIDENTE para este recorrido.
- Eventos de manzana pueden crearse sin comité si incluyen motivo. La anterior descripción de comité obligatorio quedó superada por las migraciones/código posteriores.

## Trabajo pendiente, fuera de este paso

1. Cancelación/reversa financiera con motivo e historial auditable. Este corte implementa el aislamiento de las operaciones existentes; no añade nuevos flujos de cancelación/reversa.
2. Vínculo general cuenta-ciudadano para usuarios con cargo de comité: revisar consistencia entre `PerfilAcceso` y el campo heredado `UsuarioApp.ciudadano`, preservar asignaciones existentes y mantener `Mi acceso` como visualización de la identidad general. No se sincronizan ni reinterpretan esos datos en este corte. Encargados de manzana quedan para pasos futuros según la prioridad del cliente.
3. Asegurar unicidad de responsable y pertenencia a su manzana, previo inventario y migración revisable de conflictos.
4. Vigencias e historial de cargos y territorio; decidir acceso histórico cuando un participante cambia de manzana.
5. Auditoría de quién creó/actualizó eventos y registros.
6. Reconciliar migraciones regeneradas con el esquema e historial reales del VPS antes del siguiente despliegue; probar sobre una copia restaurada, sin reset ni fake automático.
7. Revisar fallos existentes de la suite general, manteniéndolos separados de la cobertura de autorización de este paso.

## Verificación del segundo paso (histórica)

Pruebas sintéticas en `apps/operacion/test_alcance_autorizacion.py`: presidente con generación idempotente, captura normal/secuencial, creación/edición y estado; denegación fuera de comité aun con lectura global; lectores sin escritura; responsable con lectura global sin ampliación de captura; revocación por cargo/comité inactivo; responsabilidades combinadas y permisos de cambio global explícitos. No validan el estado del VPS. La cobertura financiera añadida en el tercer paso se describe debajo.

Resultado local del 29 de octubre de 2026: suite completa de nueve módulos, **176 pruebas ejecutadas, 169 aprobadas, 5 fallos y 2 errores**. Los siete casos que no pasan coinciden por nombre y tipo con la línea base previa (166 pruebas); las diez pruebas nuevas pasan. `manage.py check` sin incidencias y `makemigrations --check --dry-run` sin cambios. Estos resultados no equivalen a una certificación completa de seguridad ni a una validación en producción.

## Uso y límites del tercer paso

- Asignar desde una cuenta superusuaria un `UsuarioApp` activo con PRESIDENTE o TESORERO y el comité correspondiente. El usuario y el comité también deben estar activos. No hace falta conceder permisos Django ni staff para usar tesorería.
- El login de la aplicación abre el dashboard; el menú muestra Tesorería y Resumen de aportaciones solo con acceso financiero. Las vistas financieras deniegan acceso por servidor a cuentas sin cargo, aunque tengan permisos Django por modelo.
- Los datos financieros del expediente no conceden por sí mismos acceso al padrón: conservan la autorización de ciudadano existente y filtran las finanzas dentro de ese conjunto. También se acotan pagos/cooperaciones heredados del inicio y fechas de último pago del padrón.
- La consulta del superusuario incluye comités inactivos. Los cargos ordinarios pierden acceso al desactivar el cargo o comité; no se borran sus movimientos.
- Crear/editar conceptos, generar obligaciones y registrar abonos siguen las validaciones existentes. Un concepto con obligaciones no puede trasladarse a otro comité. Antes de tener obligaciones, solo puede moverse entre comités financieros autorizados de la misma cuenta.
- El borrado físico de conceptos sigue el acuerdo previo: pantalla de advertencia y POST con CSRF; elimina obligaciones y abonos en cascada. Lo heredan tanto tesorero como presidente para sus comités. No equivale a una cancelación/reversa contable.
- No se cambian modelos ni se necesitan migraciones. No se han probado ni modificado datos del VPS.
- Cobertura en `apps/tesoreria/test_autorizacion.py`: lectura y escritura por comité para ambos roles, filtros y respuestas parciales, métricas/fechas/gráficas, consultas vacías, exportaciones, generación idempotente y paginación con 2,000 ciudadanos, POST ajenos sin efectos, formularios, cargos combinados e inactivos, permisos Django sin ampliación, expediente/inicio/padrón, admin/inlines/autocomplete, superusuario y acceso sin staff.

Los permisos Django globales de operación del segundo paso siguen pendientes de una revisión equivalente si se decide eliminar su bypass; el aislamiento financiero no constituye una auditoría completa del resto del ERP.

### Resultado de validación del tercer paso — 29 de octubre de 2026

- 19 pruebas nuevas de autorización financiera aprobadas, incluido el caso de 2,000 ciudadanos.
- Suite completa: **198 ejecutadas, 191 aprobadas, 5 fallos y 2 errores**. Los siete casos que no pasan coinciden por nombre y tipo con la línea base anterior; no se deshabilitan ni se cambian sus aserciones para ocultarlos.
- Los fixtures funcionales existentes de tesorería declaran ahora sus cargos de comité. La cuenta limitada sin cargo espera 404 financiero en lugar de acceso de edición sin botón de borrado.
- `manage.py check` sin incidencias, `makemigrations --check --dry-run` sin cambios y `git diff --check` sin errores.
- Guía manual y comandos: [Probar la herencia financiera por comité](pruebas_tesoreria_comites.md).
