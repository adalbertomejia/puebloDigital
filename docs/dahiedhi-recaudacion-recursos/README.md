# Dahiedhi: recaudación, recursos y cortes

Implementación sobre `codex/dahiedhi-consolidacion-operativa`, conservando la propuesta y prototipos de `codex/dahiedhi-diseno-balances-cortes`. Rama de entrega: `codex/dahiedhi-recaudacion-recursos`.

## Qué se puede probar

Desde el menú de Tesorería: **Balance**, **Recursos** y **Cortes**. Se reutilizan la navegación, estilos, permisos y abonos existentes.

- **Balance** (`/tesoreria/balance/`): ingresos por fecha de pago, cartera del periodo, distribuciones por origen/comité/manzana y evolución mensual.
- **Conceptos** (`/tesoreria/balance/conceptos/`): listado y detalle de cartera; la información individual sigue requiriendo acceso financiero.
- **Transparencia** (`/tesoreria/balance/transparencia/`): informe agregado autenticado, imprimible y exportable a CSV, sin nombres de ciudadanos ni beneficiarios. No es publicación pública.
- **Recursos** (`/tesoreria/recursos/`): apertura documentada de fondos, efectivo y transferencias separados, movimientos, salidas y comprobantes internos reimprimibles.
- **Cortes** (`/tesoreria/cortes/`): preparación, envío real a revisión, lectura, solicitud de aclaración y confirmación por otra persona autorizada.

## Origen y custodia son clasificaciones independientes

El concepto y su obligación conservan su origen: faena, junta, cooperación u otro concepto de Tesorería. El fondo identifica **dónde se administra el recurso**, con comité, manzana opcional y categoría. No se sustituye la clasificación del concepto por la del fondo.

Ejemplo: un abono de una cooperación de Delegación conserva ese origen y puede ingresar al fondo «Operación de Delegación». Una salida de ese fondo para tinta se clasifica como papelería. La cooperación, el fondo y la salida responden preguntas diferentes.

La apertura registra recursos que ya se tenían, con fecha y evidencia de su procedencia. No necesita revisión. Los cobros anteriores siguen visibles en recaudación y **no se copian automáticamente al fondo**: podrían estar ya incluidos en el saldo inicial. Al registrar un abono nuevo se puede seleccionar explícitamente un fondo autorizado y el medio; abono y movimiento se guardan en una sola transacción. La selección es opcional para preservar el flujo existente; el balance informa cuántos cobros carecen de fondo asociado. No es posible asociar retrospectivamente un abono anterior a la creación del fondo mediante este flujo.

Las salidas requieren importe, medio, fecha, categoría, descripción y referencia de evidencia; admiten beneficiario. Se incluyen mantenimiento, papelería, remuneración, servicios y otros gastos. Se genera folio y comprobante interno imprimible: **no es CFDI**. La evidencia es una referencia textual, no una carga de archivos adjuntos.

## Responsabilidades confirmadas

| Ámbito | Prepara/envía | Revisa |
|---|---|---|
| Delegación | Secretaría con operación financiera explícita | Delegado del mismo comité de tipo Delegación |
| Comité | Tesorero del comité | Presidente del mismo comité |
| Manzana | Responsable, únicamente fondos de su territorio | Presidente del comité del fondo o delegado si pertenece a Delegación |

La misma cuenta no puede preparar y revisar su corte. Una cuenta de lectura autorizada puede consultar el corte enviado sin botones de modificación. El superusuario técnico no se convierte automáticamente en operador o revisor de negocio. Se mantienen los controles de identidad, cargos activos y ámbito de la consolidación.

Secretaría continúa requiriendo `core.operar_secretaria_central` y su identidad operativa válida. Para consulta agregada central se incorpora `tesoreria.consultar_balance`; este permiso por sí solo no abre ciudadanos ni detalle de fondos. Para operar fondos de Delegación puede concederse expresamente `tesoreria.gestionar_recursos` o utilizar el permiso existente `core.operar_finanzas_centrales`. El primero no concede por sí mismo las operaciones anteriores de abonos de Tesorería: estas conservan su autorización existente. Las migraciones crean permisos, **no los asignan a usuarios**.

La custodia y el historial del fondo mantienen su comité/manzana de apertura; una mudanza posterior del ciudadano no mueve dinero entre fondos ni permite consultar sus datos individuales fuera del ámbito autorizado.

## Cálculo y revisión del corte

1. Efectivo inicial: apertura del fondo para el primer corte; efectivo contado del último corte confirmado para los siguientes.
2. Cobros en efectivo: movimientos de abonos desde el cierre anterior.
3. Salidas documentadas en efectivo: movimientos de egresos del mismo intervalo.
4. Efectivo esperado = inicial + cobros − salidas.
5. Efectivo contado: captura manual de quien prepara, con evidencia de conteo.
6. Diferencia por aclarar = contado − esperado.

Las transferencias aparecen separadas y no inflan el efectivo esperado. Sus saldos son registros del sistema, sin conciliación con el banco.

Antes de enviar se verifica que no hayan cambiado los movimientos desde que se abrió la pantalla. El envío congela las fuentes, cifras, alcance y huella del corte; no hay borrador persistido por visitar una página. Si existe diferencia, se exige explicación; el revisor puede **Solicitar aclaración**. Un corte devuelto queda en el historial y se prepara un nuevo envío. Solo se confirma un corte cuadrado; devolver uno no altera su fotografía. Solo puede existir un corte en revisión por fondo. No hay vinculación con juntas: se puede imprimir o presentar el corte en una reunión ya programada.

La apertura no sigue ese proceso de revisión. Sus salidas sí conservan comprobante e historial. Aperturas, movimientos, fuentes asociadas y fotografías de cortes están protegidos frente a cambios destructivos mediante servicios, modelos y disparadores de base de datos en SQLite y PostgreSQL. Reintentar la misma operación no duplica aperturas, cobros, salidas o envíos.

## Interpretación de los informes

La recaudación suma abonos por fecha de pago. La cartera toma conceptos fechados dentro del periodo y sus obligaciones/abonos en estado actual: no reconstruye una cartera histórica a una fecha pasada. No suma saldos iniciales, adeudos, pagos históricos independientes ni salidas como si fueran cobros. Los ingresos de obligaciones canceladas se muestran con advertencia, conservando el hecho del cobro.

Un importe histórico desconocido no equivale a cero: se presenta la parte conocida, el número de desconocidos y el saldo indeterminado cuando corresponda. Los importes se calculan con Decimal; las gráficas acompañan tablas de cifras. Los filtros se aplican después de limitar el ámbito autorizado. La referencia del informe identifica su contenido; el informe vivo cambia al registrarse información nueva. El corte enviado sí es una fotografía persistida.

## Probar en tu equipo

Antes de cambiar de rama, guarda tus cambios locales y respalda tu base habitual. No reemplaces tu configuración local ni ejecutes el seed para intentar actualizar esta etapa.

```bash
git status --short
git fetch origin
git switch codex/dahiedhi-recaudacion-recursos
git pull --ff-only origin codex/dahiedhi-recaudacion-recursos
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Utiliza el mismo módulo de configuración que ya usas para Dahiedhi. Si es `config.settings_local_dahiedhi`:

```bash
python3 manage.py check --settings=config.settings_local_dahiedhi
python3 manage.py migrate --plan --settings=config.settings_local_dahiedhi
python3 manage.py migrate --settings=config.settings_local_dahiedhi
python3 manage.py runserver --settings=config.settings_local_dahiedhi
```

Si tu entorno se llama diferente, cambia `.venv` por su ruta real; si usas otro módulo de configuración, sustituye el nombre en los cuatro comandos. Se añaden las migraciones de Tesorería **0006** (modelos y restricciones) y **0007** (protección del historial). No se modifican migraciones previas ni se convierten datos anteriores automáticamente. Evita revertir estas migraciones después de empezar a registrar recursos reales, pues implicaría retirar el nuevo historial.

Configura los cargos activos de los usuarios de prueba mediante el flujo existente, incluyendo un DELEGADO en el mismo comité de Delegación que sus fondos; concede a Secretaría la capacidad financiera escogida. No basta con cambiar el nombre visible del usuario o usar admin.

Recorrido recomendado: abrir un fondo con efectivo existente y referencia; registrar un nuevo abono con fondo/medio; registrar una salida y reimprimir su comprobante; preparar un corte con diferencia; enviarlo; consultar con lectura; devolver con el revisor; preparar un nuevo conteo cuadrado y confirmarlo con la otra cuenta. Revisar después el balance por origen: la apertura no aparece como recaudación y la cooperación conserva su clasificación original. Repetir con un comité y con responsable de manzana para comprobar sus límites.

## Validación

- Suite completa: **356 pruebas en SQLite, OK (3 omitidas: concurrencia real específica de PostgreSQL)**.
- Suite completa: **356 pruebas en PostgreSQL 17, OK (2 omitidas: pruebas de esquema heredado específicas de SQLite)**.
- PostgreSQL verifica carreras reales entre salidas, cobros y revisión; ambas bases prueban restricciones y protección del historial.
- Se corrigió además una incompatibilidad heredada de captura de asistencias en PostgreSQL: el bloqueo de filas ya no se ejecuta sobre una consulta DISTINCT; mantiene el alcance autorizado. La aserción de trazabilidad compara importes decimales independientemente de su representación textual por motor.
- Los ajustes finales de búsqueda y paginación se verifican de nuevo con las pruebas focalizadas del módulo.
- Comprobación de migraciones sin cambios pendientes y revisión de interfaz con Chromium en escritorio y móvil, usando únicamente bases y usuarios sintéticos.

La instancia habitual, sus datos y Santa Mónica no se migraron ni modificaron. Esta entrega no incorpora transferencias entre fondos, conciliación bancaria, correcciones contables con contrapartidas ni adjuntos; esos flujos pueden iterarse sin tratar el prototipo como una definición contable completa.

## Capturas con información sintética

- [Balance y clasificación por origen](capturas/balance.png).
- [Detalle de fondo y salidas](capturas/fondo.png).
- [Corte confirmado en escritorio](capturas/corte.png) y [en móvil](capturas/corte-movil.png).

El recorrido automatizado en Chromium completó 11 grupos de comprobaciones: seis pantallas a 1440, 390 y 320 píxeles, ausencia de datos personales en el informe/CSV, formularios reales de apertura/salida/comprobante, envío con diferencia, lectura sin modificación, devolución y confirmación por delegado, aislamiento territorial, separación tesorero/presidente y ausencia de errores JavaScript. Se comprobó también la impresión PDF. Los ajustes finales pasaron nuevamente las 30 pruebas del módulo en ambos motores.
