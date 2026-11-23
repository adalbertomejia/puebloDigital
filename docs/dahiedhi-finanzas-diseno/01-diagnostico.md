# Diagnóstico de la Tesorería existente

## Entidades y servicios reutilizables

| Fuente real | Datos y comportamiento disponibles | Reutilización y límites |
|---|---|---|
| `apps/tesoreria/models.py: ConceptoTesoreria` | Naturaleza PAGO/COOPERACION; origen TESORERIA/FAENA/JUNTA/AGUA; comité, alcance GENERAL/MANZANA, manzana, fecha, año, periodo de agua, autor; vínculo uno a uno a faena/junta | Clasificación canónica. Un concepto no es dinero recibido. No crear otra tabla de categorías que reproduzca estas dimensiones |
| `ObligacionCiudadano` | Ciudadano, concepto, monto asignado, estado PENDIENTE/PAGADO/CANCELADO, autor, datos históricos de toma/contrato; unicidad concepto-ciudadano | Unidad de seguimiento del adeudo. Una obligación parcialmente pagada sigue PENDIENTE; el parcial se deriva de sus abonos |
| `Abono` | Importe Decimal, fecha de pago, fecha de captura heredada, autor, obligación, referencia y notas | Fuente principal de recaudación. No tiene caja ni medio de cobro ni identificador de solicitud idempotente |
| `Pago` y `Cooperacion` | Movimientos independientes anteriores, ciudadano, comité, tipo, fecha, importe, comprobante; Pago puede vincular asistencia/toma | Mantener informe histórico separado. No tienen enlace suficiente para determinar automáticamente equivalencia con Abono, ni autor financiero propio |
| `RegistroFinanciero` | Usuario y nombre al registrar, comité, acción, tipo/id de objeto, concepto registrado, monto, referencia, detalle, fecha y origen PANEL/ADMIN | Evidencia operativa; no es un libro de entradas/salidas. El monto puede representar una obligación, una modificación o un abono: no sumar la bitácora como recaudación |
| `apps/operacion/models.py` | Faena/Junta con territorio y comité opcional; participantes con estado, genera_adeudo y monto_adeudo | Mantener evidencia de participación y causa del adeudo; una falta por sí sola no implica deuda monetaria |
| `apps/tesoreria/services.py` | Generación idempotente de obligaciones faltantes; sincronización de adeudos de asistencia | No recrear generación. Un evento sin comité no genera adeudos; conservar advertencia operativa |
| `apps/tesoreria/queries.py` | Agregación por subconsultas para evitar multiplicar obligaciones con múltiples abonos; filtros y saldos anotados | Reutilizar estructura, añadir cobertura de importes desconocidos y temporalidad explícita |
| `apps/core/views.py` | Tesorería operativa, detalle, resumen, búsqueda, bitácora, CSV y recibos | Extender componentes y selectores; no otro sistema de Tesorería |
| `apps/core/expediente.py` | Indicadores por ciudadano, autorización e identificación de importes desconocidos | Su tratamiento de desconocidos es referencia para unificar otros reportes |
| `static/js/resumen-aportaciones.js`, plantillas del dashboard | Chart.js, resumen por conceptos/manzana/ciudadanos, tablas, controles y fallback sin gráfica | Ya hay base UX. No reemplazar shell ni rediseñar todo el ERP |

## Recorrido real de la obligación al cobro

1. `generar_obligaciones_faltantes` bloquea el concepto y crea solo pares concepto-ciudadano ausentes para ciudadanos activos del alcance. En agua utiliza tomas activas y conserva su número/contrato. No genera indiscriminadamente para un concepto ligado a asistencia.
2. La captura de asistencia llama `sincronizar_adeudo_asistencia` dentro de transacción. Se crea un concepto por evento y una obligación por ciudadano con importe positivo; origen y vínculo con Faena/Junta permanecen. Se exige comité.
3. Al modificar un adeudo, se impide retirar una obligación con abonos o reducirla por debajo de lo cobrado. Sin importe y sin abonos puede quedar CANCELADA; al volver a asignar un importe puede reactivarse.
4. `ObligacionCiudadano.acreditar` bloquea la obligación, valida autorización cuando recibe usuario, estado, importe positivo y saldo, crea Abono, actualiza estado y registra evidencia en transacción. Un fallo en la bitácora revierte la operación.
5. El recibo es una consulta del Abono existente. El folio `PD-A-00000001` deriva de su PK, no de un contador de impresiones. `recibo_abono` exige autenticación y alcance; imprimir no crea pagos. El folio no es un secreto ni autoriza por sí solo; su unicidad es de instancia, no entre clientes.

## Autorización actual y dependencia de rama

En `c50762e`, `limitar_finanzas` delimita comités por cargo activo e identidad. Para responsables exige concepto MANZANA propio y, en obligaciones/abonos, residencia actual coincidente. Los permisos globales heredados no amplían ese alcance. Un traslado conserva el concepto histórico, pero puede quitar acceso al responsable anterior sin conceder cobro al nuevo.

Secretaría tiene capacidad operativa global y concesiones financieras centrales separadas: consulta y operación. La operación central vigente es amplia; no equivale a una capacidad limitada de “cobrar sin administrar conceptos”. Ninguna de ellas debe habilitar automáticamente aprobación de cortes. En la rama `fcd0511` todavía no están esas ampliaciones centrales/territoriales: los cortes no deben desarrollarse asumiendo que ya están integradas allí.

## Riesgos comprobados en el código

| Hallazgo | Consecuencia para el último módulo | Tratamiento propuesto |
|---|---|---|
| Detalle y tarjetas excluyen abonos de obligaciones CANCELADAS; resumen de aportaciones suma Abono sin excluirlos por defecto | Los dos números representan universos diferentes; una cancelación no demuestra devolución de dinero | Separar “recaudación registrada” y “cobros aplicados a obligaciones vigentes”; mostrar excepción y no borrar ingresos |
| `SUM` y `Coalesce(..., 0)` en varias consultas; importes históricos NULL contemplados por migraciones/pruebas | Un subtotal puede parecer un total íntegro | Conteo de desconocidos y valor parcial/indeterminado; nunca deducir que NULL es cero |
| Propiedades simples `total_abonado`/`saldo_pendiente` no expresan cobertura de NULL | Reutilización ciega puede producir saldo engañoso | Selector financiero con valor y calidad; el expediente ya detecta casos desconocidos |
| `eliminar_concepto_tesoreria` elimina concepto, obligaciones y abonos en cascada; conserva evidencia agregada | Un cierre reconstruido desde filas vivas cambiaría o perdería comprobantes | Copia de detalle al cerrar y protección de fuentes incluidas, también en Admin/ORM. Es un cambio de política pendiente de aprobación antes de cortes |
| Abono admite edición administrativa y no hay libro inmutable de liquidaciones | Un snapshot por sí solo no asegura integridad del sistema vivo | Restringir cambios de movimientos incluidos en un corte y usar correcciones posteriores vinculadas |
| No hay medio, caja, apertura, conteo, retiro, entrega ni egreso | Recaudación no equivale al efectivo bajo custodia | Capturar esos hechos antes de ofrecer un corte real; no inferirlos de notas o referencia |
| Fecha de pago y captura son distintas; saldos y estados son actuales | No se puede reconstruir con exactitud un balance pasado solo filtrando fechas | Mostrar recaudación por fecha elegida y adeudos actuales por cohorte; snapshots solo desde su adopción |
| Concepto tiene dos vínculos opcionales separados a evento | No hay XOR de ambos eventos en esa definición de modelo | Auditar inconsistencias antes de métricas por origen; proponer CheckConstraint futuro, sin corregir históricos automáticamente |
| `Abono.acreditar` no tiene clave única de petición | Reintentos de una solicitud válida pueden registrar dos parciales que aún quepan en saldo | Idempotencia futura por usuario/operación y bloqueo; reutilizar un recibo tras reintento, no emitir dos cobros |
| Comité/territorio se consultan a través de las relaciones actuales | Cambios o renombres pueden alterar agrupaciones históricas vivas | Conservar etiquetas/IDs en el detalle cerrado; bloquear reasignación con obligaciones y auditar casos heredados |

## Histórico incompleto y doble contabilización

No sumar `RegistroFaena.monto_adeudo + Obligacion.monto_asignado + Abono.monto`. Son causa, obligación y pago de la misma cadena. No sumar Pago/Cooperacion con Abono sin demostrar disyunción y conciliación; tampoco sumar bitácora y Abono. Un depósito de efectivo a una cuenta bancaria es traslado de custodia, no una nueva recaudación.

Los reportes de históricos independientes deben mostrar fuente, periodo, total conocido y registros por revisar. La conciliación de una equivalencia requiere evidencia y vínculo explícito antes de incluirla en el universo canónico; no migración masiva por coincidencia de nombre/fecha/importe.

## Migraciones y pruebas existentes inspeccionadas

Se revisaron las migraciones de territorio, autoría, agua, vínculos de asistencia y protección de ciudadano de Tesorería (0001 a 0005), las de eventos y las dependencias de core/comités. Destaca `0004_vinculo_adeudos_asistencia`: contempla columnas monetarias históricas nullable y relaciones preexistentes en SQLite; no debe sustituirse ni regenerarse. Las migraciones 0005–0007 de core pertenecen a la consolidación, no al módulo propuesto.

Pruebas reutilizables: `test_autorizacion`, `test_recibos`, `test_trazabilidad`, `test_adeudos_asistencia`, `test_migraciones_financieras`, pruebas de queries/reportes en `tests.py`, `apps/core/test_consolidacion.py`, ciclo ciudadano y alcance de operación. Cubren parciales, sobrepago, cancelaciones, retroceso transaccional, reimpresión, aislamiento y conservación histórica. Las 323 pruebas reportadas en la etapa anterior son evidencia de aquella entrega; no se presentan como una nueva ejecución de esta investigación. Aquí no se ejecuta `migrate` ni pruebas que creen esquemas.
