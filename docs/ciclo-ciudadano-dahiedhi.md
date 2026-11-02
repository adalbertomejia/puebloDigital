# Ciclo ciudadano de Dahiedhi

Base verificada de GitHub: `275da7dd2c5919effba2def7032a4d6825d3f39d` en `dahiedhi_client`. Se conservan su configuración PostgreSQL/Django 5.2, permisos de presidente/tesorero por comité, recibos, auditoría financiera, selectores, tablas y servicios de adeudos. No se mezclan configuraciones ni datos de Santa Mónica.

## Cambios operativos

Se completan alta, consulta, edición, cambio de manzana, baja/reactivación y eliminación controlada sobre las vistas existentes. La rama ya tenía manzanas, edición operativa, filtros de padrón y tres historiales paginados; se reutilizan.

- Advertencias de duplicados que normalizan acentos, espacios y mayúsculas y comparan nombres parecidos. Se permite confirmar homónimos distintos; no se fusionan registros.
- Edición y cambio de manzana conservan los eventos, territorios históricos, obligaciones y abonos, así como sexo, contrato, motivo de alta, labor social y edad efectiva.
- Baja/reactivación con fecha efectiva no futura, motivo, usuario y fecha de captura. Las bajas antiguas no reciben fechas o motivos inventados. El formulario general ya no cambia el estado indirectamente.
- Eliminación nominativa con permiso explícito, POST y CSRF. Se revisan todas las relaciones al presentar la confirmación y otra vez dentro de la transacción. Se bloquea si hay asistencia, obligación, pago, cooperación, toma, cargo, perfil, responsabilidad territorial o historial de estado. Las relaciones históricas del ciudadano usan PROTECT; no se borran antecedentes por cascada para permitir eliminarlo.
- Retorno seguro al listado con búsqueda/filtros/página; botón deshabilitado al enviar y tokens de sesión contra reenvíos secuenciales.
- Filtros por fechas, tipo y estado en el expediente, con paginación independiente y errores de fechas junto al campo. Se distingue ausencia de registros de ausencia de coincidencias. Los resúmenes cubren todos los registros autorizados y no cambian al filtrar el historial.
- Resumen de asistencia con pendientes y exclusión de eventos cancelados. Una falta no se convierte en deuda por inferencia. Los historiales e indicadores respetan los QuerySets territoriales y los enlaces al origen solo aparecen cuando el evento es visible.
- Se mantienen `limitar_finanzas` y la autorización financiera por comité de la versión actual. El saldo usa `anotar_obligaciones`, suma por obligación vigente y excluye abonos de obligaciones canceladas. Los pagos/cooperaciones históricos siguen separados de obligaciones sin vínculo explícito.
- Los importes históricos desconocidos se muestran como desconocidos y dejan el saldo como «Por revisar», sin sumarlos como cero. Se prueba reproduciendo columnas monetarias históricas nullable en una base temporal.
- El tablero limita padrón, eventos y contadores al alcance del usuario; un cargo financiero no abre el padrón general. Sus movimientos financieros conservan el alcance por comité existente.

## Autorización

No se asignan nuevos permisos automáticamente ni se reemplaza la política de roles existente.

| Acción | Autorización |
| --- | --- |
| Consultar ciudadano | `Ciudadano.objects.visibles_para`, según el permiso global o responsabilidad territorial existente |
| Alta | `core.view_ciudadano` + `core.add_ciudadano` |
| Editar, cambiar manzana, baja/reactivación | `core.view_ciudadano` + `core.change_ciudadano` |
| Eliminar | Superusuario; o personal staff/Secretaría activa de Delegación con `core.view_ciudadano` + **`core.delete_ciudadano` explícito** |
| Finanzas | `tiene_acceso_financiero` y `limitar_finanzas` existentes: superusuario o presidente/tesorero de su comité activo |

Las vistas de asistencia, agua, recibos, auditoría y exportaciones mantienen sus autorizaciones existentes. Un cargo de comité por sí solo no concede edición o eliminación global de ciudadanos. Los responsables no reciben acciones de padrón nuevas automáticamente. Los duplicados con historial requieren revisión manual.

## Migraciones

Se agregan cinco migraciones posteriores al grafo real de Dahiedhi:

- core `0003_ciudadano_fecha_baja_ciudadano_motivo_baja_and_more`.
- operacion `0005_alter_asistenciajunta_ciudadano_and_more`.
- tesoreria `0005_alter_cooperacion_ciudadano_alter_pago_ciudadano`.
- agua `0002_alter_toma_ciudadano`.
- comites `0003_alter_usuarioapp_ciudadano`.

Se conservan las dependencias existentes, incluso cuando su numeración no es cronológica (comites). No se modifica ninguna migración recibida ni se usa `--fake`. Los nuevos campos de baja son nullable para agregar columnas sin reconstruir la tabla histórica de ciudadanos en SQLite. Se revisó `sqlmigrate`: core agrega esas columnas y una tabla de auditoría nueva; cambiar on_delete a PROTECT no genera reconstrucciones de tablas de asistencias.

Antes de desplegar, contrastar `showmigrations --plan` con la base real de Dahiedhi. No se aplicaron migraciones a producción ni a la base local. No se incluyen `.venv`, `.env`, bases SQLite ni respaldos en el diff contra la base de este PR.

## Verificación y límites reales

Se instalaron las dependencias de la rama fuera del repositorio y se verificó con Django 5.2. Las pruebas usan settings temporales externos y SQLite en memoria: no había credenciales de PostgreSQL para validar ese motor.

- **32 pruebas nuevas aprobadas**, incluyendo dos pruebas de importes históricos desconocidos, aislamiento, CSRF, nombres similares, reenvíos, baja/reactivación, permisos de eliminación, relaciones creadas después de confirmar y conservación de territorio/obligaciones/abonos.
- Suite completa: **286 pruebas; 279 aprobadas y siete incidencias heredadas**. Antes de los cambios, la base real ejecutó 254 pruebas con once incidencias. Se corrigieron los fixtures del ciclo ciudadano (sexo y tokens), un fixture que intentaba abonar una obligación pagada y un supuesto dependiente del mes actual. El test del tablero ahora comprueba que un tesorero no obtiene padrón global sin autorización.
- Permanecen cuatro fallos anteriores en `ResumenAportacionesTests`: coincidencias de Ana, texto de estado vacío, título anterior «Movimientos recientes» y parámetro anterior `limite_ciudadanos`.
- Permanecen tres errores anteriores en `test_migraciones_financieras`: dos casos apuntan a `operacion.0002_evento_motivo_comite_opcional`, que no existe en el grafo recibido; otro fixture histórico crea un ciudadano sin el sexo requerido por el esquema de esa prueba. No se reconstruyó el historial para hacerlos pasar.
- `check`, `makemigrations --check --dry-run` y `git diff --check` correctos. Las migraciones nuevas se aplican durante la creación de la base temporal de pruebas.

Comandos normales de verificación (usando una configuración de pruebas adecuada, nunca la conexión de producción):

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.core.test_citizen_cycle
```

No hay validación visual en navegador ni ejecución sobre PostgreSQL/producción. El historial de asistencia y los movimientos antiguos se filtran y paginan en memoria, y la comparación aproximada recorre el padrón. Para grandes volúmenes convendrá mover estas operaciones a consultas indexadas.

Los tokens previenen reenvíos secuenciales; no garantizan idempotencia distribuida ante solicitudes simultáneas. El cambio de estado usa además estado anterior y bloqueo de fila, cuya eficacia depende del motor.

Las eliminaciones de eventos o conceptos completos conservan su comportamiento previo; esta entrega protege la eliminación del ciudadano. Quedan fuera cortes, balances y la extensión financiera por concepto.
