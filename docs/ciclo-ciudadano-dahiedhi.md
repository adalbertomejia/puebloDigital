# Ciclo ciudadano de Dahiedhi

Esta entrega parte de `dahiedhi_client`, commit `78bf8ae1f4ab8a34e780444f1d09ee53a98f9784`. Conserva sus manzanas, responsabilidades, consultas de asistencia, cálculo financiero, estilos y filtros del padrón. No incorpora configuraciones ni datos de Santa Mónica.

## Diagnóstico y cambios

La rama ya tenía edición operativa, alcance territorial y tres historiales paginados. Faltaban baja/reactivación auditadas, eliminación del ciudadano, advertencias de duplicados y filtros del expediente. El resumen restaba abonos de obligaciones canceladas y exponía un resumen de asistencia sin aplicar el alcance del usuario. Las vistas financieras globales solo exigían sesión.

Se completan los recorridos de alta, consulta, edición, cambio de manzana, baja/reactivación y eliminación controlada sobre las vistas existentes:

- Nombres normalizados por espacios, acentos y mayúsculas para advertir coincidencias aproximadas. La confirmación permite homónimos distintos; no fusiona personas.
- Edición y cambio de manzana conservan los eventos, territorios históricos, obligaciones y abonos. Se mantienen sexo, contrato, motivo de alta, labor social, edad efectiva y los filtros de Dahiedhi.
- Baja y reactivación requieren permiso de cambio, motivo y fecha no futura; registran usuario y fecha de captura. Los registros inactivos anteriores conservan la ausencia de fecha/motivo si no se conocían. El formulario general ya no modifica el estado indirectamente.
- Eliminación nominativa mediante POST, CSRF, autorización explícita y revisión de relaciones tanto al confirmar como dentro de la transacción. No permite borrar ciudadanos con asistencias, obligaciones, pagos, tomas, cargos, perfil de acceso, responsabilidades de manzana o historial de estado. Las relaciones históricas usan PROTECT; no se ejecutan cascadas para habilitar la eliminación.
- Se conserva el regreso al listado con filtros y página. Los formularios deshabilitan el botón al enviar y usan tokens de sesión para evitar reenvíos secuenciales.
- El expediente filtra por fechas, tipo y estado con paginación independiente; mantiene resumen general sin filtrar. Los intervalos inválidos muestran errores sin reutilizar resultados anteriores. Distingue ausencia de registros de ausencia de coincidencias.
- Los estados de asistencia excluyen eventos cancelados del resumen e incluyen pendientes. Una falta no se interpreta como deuda. El saldo suma balances por obligación vigente mediante `anotar_obligaciones`; ningún abono de una obligación cancelada reduce el saldo de otra. Los pagos y cooperaciones antiguos se consultan por separado, sin descontarlos de obligaciones sin vínculo.
- Los responsables conservan el alcance de los QuerySets de Dahiedhi en historial e indicadores. Un cargo de comité, por sí solo, no concede permiso global. Los enlaces al origen solo aparecen si ese evento es visible. El padrón no muestra fechas de pagos sin permiso financiero.

## Permisos

Se reutilizan los permisos globales explícitos y las responsabilidades territoriales existentes, sin asignar permisos a usuarios automáticamente.

| Recorrido | Autorización |
| --- | --- |
| Consultar | `core.view_ciudadano` global o responsabilidad de manzana según el QuerySet existente |
| Crear | `core.view_ciudadano` + `core.add_ciudadano` |
| Editar, mover, dar de baja/reactivar | `core.view_ciudadano` + `core.change_ciudadano` |
| Eliminar | Superusuario, o personal staff/Secretaría activa de Delegación con `core.view_ciudadano` + `core.delete_ciudadano` explícito |
| Obligaciones y abonos | `core.view_ciudadano` + `tesoreria.view_obligacionciudadano` |
| Pagos/cooperaciones históricos | Anteriores + `tesoreria.view_pago` / `tesoreria.view_cooperacion` |

Las pantallas financieras globales y sus exportaciones ahora requieren los permisos de consulta global correspondientes. Las acciones conservan además sus comprobaciones de escritura existentes. Agua requiere `agua.view_toma` y consulta global de ciudadanos; el tablero global requiere los permisos de los datos de pagos, cooperaciones y agua que muestra. La asistencia conserva sus permisos y consultas territoriales existentes.

## Migraciones y producción

Se agregan cinco migraciones posteriores al grafo **de Dahiedhi**: core 0002, operacion 0003, tesoreria 0002, agua 0002 y comites 0002. No se modifica ni reconstruye ninguna migración existente y no se usa `--fake`.

Antes de integrar y desplegar, comparar `showmigrations --plan` y el estado real de la base de Dahiedhi. La rama recibida ya tiene migraciones iniciales consolidadas; no debe aplicarse este grafo a una instalación con un historial diferente sin revisar la discrepancia. No se han ejecutado migraciones sobre la base local ni sobre producción; las pruebas usan una base temporal. No se incluyen entornos virtuales, archivos `.env`, bases SQLite ni respaldos en los cambios.

Los settings recibidos son de desarrollo. Esta entrega no cambia conexiones, no verifica la configuración de producción ni convierte una base compartida en un sistema multicliente.

## Verificación

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.core.test_citizen_cycle
python manage.py test apps.core.tests apps.core.test_autorizacion apps.core.test_manzanas apps.core.test_padron_alcance apps.core.test_citizen_cycle apps.comites.tests apps.operacion.tests apps.operacion.test_evento_motivo_comite apps.operacion.test_alcance_autorizacion apps.tesoreria.tests
```

Las 30 pruebas nuevas pasan: duplicados, homónimos, aislamiento por ciudadano, filtros, paginación, baja/reactivación auditadas, reenvíos, CSRF, autorización de Secretaría, eliminación permitida/bloqueada, relaciones creadas después de confirmar, conservación del territorio/obligaciones/abonos, saldos cancelados y restricciones territoriales/financieras.

Antes de modificar la rama se ejecutaron 166 pruebas: existían siete casos fallidos. Se corrigieron los fixtures del ciclo ciudadano que omitían sexo, los tokens nuevos y un fixture que intentaba crear abonos sobre una obligación ya pagada. Las cuentas de prueba financieras ahora reciben sus permisos de consulta explícitos.

La suite completa ejecuta **196 pruebas: 192 pasan y cuatro fallan**. Conserva cuatro fallos preexistentes en `ResumenAportacionesTests`, fuera de este alcance:

- `test_busqueda_textual_nombre_apellidos_contrato_y_concepto`: esperaba dos coincidencias de Ana y obtiene tres.
- `test_estados_vacios_son_especificos`: espera un texto anterior del resumen.
- `test_renderiza_cuatro_tarjetas_con_jerarquia_y_datos`: espera el título anterior «Movimientos recientes».
- `test_totales_visibles_y_contexto_seguro_de_formularios`: espera el parámetro anterior `limite_ciudadanos`.

No se amplía el módulo de aportaciones para resolver esas discrepancias de su suite.

## Límites

No hay validación visual en navegador ni prueba contra producción. El historial combinado de asistencias y movimientos antiguos se filtra y pagina en memoria; la comparación aproximada recorre el padrón. Para grandes volúmenes conviene trasladar estas operaciones a consultas indexadas.

Los tokens evitan reenvíos secuenciales, no garantizan idempotencia distribuida frente a solicitudes simultáneas; el cambio de estado usa además bloqueo de fila y estado anterior. SQLite no ofrece el bloqueo de fila de PostgreSQL.

Los duplicados con historial requieren revisión manual. Las eliminaciones de eventos o conceptos completos conservan su comportamiento anterior; esta entrega protege la eliminación del ciudadano. Quedan fuera cortes, balances y extensión financiera por concepto.
