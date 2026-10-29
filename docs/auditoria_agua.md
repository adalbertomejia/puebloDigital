# Agua: auditoría y extensión compatible

Revisión del 29 de octubre de 2026 en `codex/permisos-presidente`, base `f85a60e`. Código, migraciones e historial del repositorio; no se inspeccionó la base del VPS. Siete comprobaciones sintéticas ejecutadas en base temporal. No se modifican modelos, migraciones históricas, identificadores ni datos productivos en esta entrega.

## Estado observado en la auditoría inicial

- `Ciudadano.numero_contrato`: texto opcional de hasta 50 caracteres; no tiene unicidad. Conserva ceros iniciales si los datos se ingresaron como texto.
- `Toma.numero_toma`: texto obligatorio único de hasta 30 caracteres. No se calcula a partir del contrato.
- `Toma.ciudadano`: relación uno-a-uno obligatoria al ID de ciudadano. Cada toma tiene un ciudadano y cada ciudadano tiene como máximo una toma. La relación no depende de que ambos números sean iguales.
- `Toma`: ubicación, estado, costo anual y observaciones. No tiene comité, periodo de cobro, historial de titularidad, tarifa por periodo ni vínculo directo a las obligaciones modernas.
- Borrar el ciudadano puede eliminar su toma por CASCADE. Los pagos heredados del ciudadano también tienen CASCADE; una toma referenciada por un pago independiente usa SET_NULL al borrarse. No realizar limpieza de personas/tomas como mecanismo de integración.

Ejemplo válido para el esquema: ciudadano con contrato `000123`, vinculado por ID a una toma `T-099`. Que el caso sea correcto para el pueblo depende del significado real de los dos números. No se deben igualar automáticamente.

## Conexión financiera observada antes de la extensión

1. Flujo heredado: `Pago` tiene ciudadano, comité, importe, periodo opcional y una toma opcional. Puede guardarse un ciudadano distinto del titular de la toma sin que el modelo lo rechace; debe aclararse si representa a un pagador tercero o a un error de captura.
2. Flujo nuevo: `ConceptoTesoreria → ObligacionCiudadano → Abono`. Su `origen=AGUA` es una etiqueta, no una selección de titulares. El generador actual incluye ciudadanos activos del territorio, incluso sin toma, y toma el monto base del concepto, no `Toma.costo_anual`.
3. La pantalla Agua muestra un inventario. La suma de `costo_anual` incluye todas las tomas, también suspendidas/canceladas: no representa recaudación, saldo ni necesariamente el importe exigible del año.
4. El indicador heredado llamado `morosos_agua` cuenta personas con pagos de tipo SERVICIO; no calcula deuda. No debe reutilizarse como indicador de morosidad.
5. Los reportes nuevos de aportaciones leen Abono; no suman automáticamente los Pago heredados. Copiarlos a abonos sin conciliación puede duplicar cobros o perder su relación con la toma.

## Acceso y experiencia observados antes de la extensión

- `/agua/` exige sesión, pero sus listas, métricas y revisión son globales. No aplica todavía comité ni permisos de acción de agua.
- El admin de tomas y el inline en ciudadanos siguen permisos Django por modelo, sin una política contextual de agua.
- La búsqueda de Agua usa número de toma y nombres; no busca el número de contrato del ciudadano. La tabla no muestra ese contrato.
- Los filtros/indicadores «sin ciudadano» no corresponden al esquema normal: `Toma.ciudadano` es obligatorio. No confundir ciudadano sin toma con toma sin ciudadano.
- No hay filtro explícito de canceladas en esa pantalla, aunque el modelo sí contempla ese estado.

## Diagnóstico de solo lectura

En una copia restaurada y aislada de los datos reales, usando el código compatible y el entorno Python del proyecto:

```sh
python manage.py auditar_agua
```

El comando consulta conteos agregados de contratos repetidos, contratos sin toma, números distintos, estados, tarifas negativas, pagos con otra persona y obligaciones de agua sin toma actual. No muestra nombres/números individuales ni ejecuta correcciones. Los conteos informan; no declaran que un número diferente o un contrato repetido sea inválido sin confirmar las reglas del pueblo.

En la prueba sintética se comprobó que el diagnóstico no modifica los registros ni expone números de contrato/toma. No se ha ejecutado sobre producción. El importador `importar_padron` del repositorio solo carga identidad, sexo y manzana; no reconstruye tomas ni la correspondencia contrato-toma. No debe usarse como una restauración de esta relación.

## Extensión propuesta, sin reconstruir los datos existentes

1. **Confirmar significado de los números y reglas de cobro.** Igualdad o separación de contrato/toma, tratamiento de suspendidas, tarifa uniforme o individual, periodo, corte de titulares y posibles pagadores terceros. Conservar el uno-a-uno actual mientras no exista una necesidad real de múltiples tomas por ciudadano.
2. **Inventariar y conciliar con copia restaurada.** Comparar esquema real, historial `django_migrations`, cantidades, IDs, asociaciones, contratos, tomas y pagos. El historial del repositorio contiene regeneraciones de migraciones iniciales; no demuestra por sí solo compatibilidad de una base productiva anterior. Ensayar también restauración antes de actualizar el VPS.
3. **Primera extensión de consulta y acceso.** Ciudadano con hipervínculo, contrato y toma claramente diferenciados; búsqueda por ambos números; filtros de estado reales. Aplicar listas/métricas/admin al comité de Agua autorizado. Si existen varios comités de tipo AGUA, no asignar todas las tomas a cualquiera de ellos por inferencia del tipo.
4. **Conectar el cobro nuevo con la toma existente.** Mantener el flujo de tesorería y añadir una referencia opcional de servicio/toma a la obligación, con conservación del titular, periodo y monto al generarla. Usar un servicio de generación específico de agua y validaciones para seleccionar solo tomas elegibles. No inferir el servicio solo por el nombre del concepto ni aplicar las reglas de agua a todas las cuotas generales.
5. **Idempotencia, trazabilidad y conciliación.** Evitar cobrar dos veces el mismo servicio/periodo conforme a la regla acordada; conservar abonos, autores y referencias. Mantener Pago heredado visible por separado o conciliarlo mediante un proceso explícito, sin importación automática a Abono.
6. **Migraciones nuevas y aditivas.** Si se requiere comité o vínculo a toma, añadir campos inicialmente opcionales; no renombrar/eliminar columnas ni cambiar IDs. Preparar cualquier backfill como una operación separada, con simulación, listado de casos ambiguos y transacción. Añadir restricciones solo después de revisar los conflictos existentes. Probar migración con datos previos y comparar relaciones/importes antes y después; no editar `0001`, resetear tablas ni usar `--fake` como sustituto de reconciliar el esquema.

## Decisiones pendientes antes de implementar cobros

- ¿Una persona distinta del titular puede pagar y debe registrarse como pagador?

Hasta cerrar las reglas y revisar la copia de los datos, esta entrega proporciona auditoría y diagnóstico; no activa generación de cuotas de agua ni reasigna las relaciones existentes.

## Reglas definitivas confirmadas por el cliente

- Número de contrato identifica al ciudadano y número de toma identifica la toma. Son distintos y se relacionan mediante el ID de ciudadano ya existente. Esta decisión corrige la respuesta inicial que los consideraba iguales: no se igualan ni se copian entre sí.
- Hay un único comité de Agua para las tomas existentes. Se verifica que exista exactamente un comité activo de tipo AGUA; una configuración ambigua impide generar cobros sin reasignar datos.
- El cobro es mensual y uniforme. El responsable autorizado introduce el importe del mes al crear la cuota. No se deriva, divide ni actualiza `Toma.costo_anual`.
- Solo tomas activas son elegibles al generar. El estado del servicio es el criterio: una toma activa puede generar obligación aunque su titular esté inactivo en el padrón. Suspender/cancelar una toma no elimina sus obligaciones ni pagos anteriores.

## Extensión implementada

- Agua queda accesible al presidente/tesorero del comité de Agua y al superusuario. El admin de tomas y el inline de ciudadano se reservan al superusuario; los cargos operan el cobro desde el panel.
- Agua permite buscar por contrato o toma, filtrar canceladas y consultar el contrato junto a su toma. Los enlaces al expediente se muestran solo si la cuenta ya tiene permiso sobre ese ciudadano; el cargo no abre todo el padrón.
- «Crear cuota mensual» solicita mes, importe uniforme y descripción. Crea un concepto PAGO / GENERAL / AGUA del comité, genera sus obligaciones y registra autoría dentro de una transacción.
- `periodo_agua` conserva el mes (primer día) y una restricción impide dos conceptos de agua del mismo comité/mes entre los conceptos existentes. Repetir generación no duplica obligaciones ni cambia autores. Los conceptos heredados de origen AGUA sin periodo requieren revisión y no generan cuotas automáticamente.
- Cada obligación nueva de agua referencia la toma mediante FK opcional PROTECT y conserva número de toma y contrato al generar. Los identificadores registrados no se reescriben cuando cambia la ficha actual. El detalle mantiene las seis columnas operativas; el vínculo de servicio aparece junto al ciudadano y se añade al CSV.
- Las obligaciones existentes, pagos heredados, identificadores de tomas, vínculos de titulares y tarifas anuales no se recalculan ni se migran a otro flujo.
- La migración nueva `tesoreria.0003_cuotas_mensuales_agua` añade campos opcionales y la restricción para cuotas mensuales identificadas. No modifica migraciones históricas ni rellena relaciones antiguas por inferencia.

Para probar en la copia local con el entorno del proyecto activado:

```sh
git pull --ff-only origin codex/permisos-presidente
python manage.py migrate
python manage.py test apps.agua.tests --noinput
python manage.py auditar_agua
```

Después, acceder como presidente o tesorero del comité de Agua, abrir Agua y crear una cuota mensual con el importe real acordado. Revisar obligaciones y registrar abonos desde Tesorería. No se programa un cobro automático ni se genera retroactivamente una deuda por cada mes pasado.

## Límites y siguientes decisiones

- La elegibilidad se evalúa con el estado actual de la toma en cada generación. No hay historial de estados para reconstruir qué tomas estuvieron activas en un mes anterior; no generar meses pasados suponiendo que existe esa reconstrucción.
- Cambiar el importe o periodo de un concepto con obligaciones está bloqueado. Las correcciones contables, cancelaciones y reversas requieren el flujo aún pendiente.
- El borrado físico de conceptos conserva la regla financiera previamente acordada y su bitácora. La unicidad mensual protege conceptos existentes; borrar un concepto libera esa clave. Para un cierre contable definitivo que impida recreación después del borrado hay que definir cancelación/cierre de periodo, sin sustituirlo por eliminaciones físicas.
- No se convierten pagos heredados a abonos; siguen requiriendo conciliación para evitar dobles registros.
- La prueba de migración es sobre datos sintéticos previos: verifica conservación de contrato, toma, IDs, ciudadano, tarifa, pagos y obligaciones sin backfill. No acredita haber revisado la base del VPS ni resuelve su historial de migraciones regeneradas.

## Verificación de la extensión

- 12 pruebas de agua: cuota uniforme, solo activas, permisos por comité, mes duplicado, importes inválidos, idempotencia, conservación de pagos al suspender, snapshots de identificadores y migración con datos previos.
- 42 pruebas seleccionadas de agua, aislamiento financiero y trazabilidad aprobadas.
- Suite completa: 224 ejecutadas, 217 aprobadas, 5 fallos y 2 errores; los mismos siete casos de la línea base previa.
- `manage.py check`, coherencia de migraciones y revisión de whitespace sin incidencias. No se han ejecutado migraciones en el VPS.
