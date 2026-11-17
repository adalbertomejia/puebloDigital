# Dahiedhi: consolidación operativa para revisión

Rama: `codex/dahiedhi-consolidacion-operativa`.
Base obtenida mediante `git fetch origin codex/dahiedhi-ciclo-ciudadano`:
`fcd051150e28412b33bba55dc59ca4b891207ec4` (seguía siendo el último commit remoto al iniciar).
No se despliega esta entrega.

## Resultado técnico

Se conservaron las interfaces, modelos financieros, validación de duplicados, tokens del ciclo ciudadano, bajas/reactivaciones, generación de participantes, selectores de alcance y regla de cargo activo único existentes.

Se incorporó una política de Secretaría central mediante `core.operar_secretaria_central`, con identidad vinculada a un ciudadano activo. No requiere `is_staff` ni `is_superuser`. Se deniega el alcance de Secretaría mientras haya una responsabilidad territorial o cargo de comité activo; los cargos anteriores inactivos se conservan. El permiso habilita padrón global, alta, correcciones, mudanzas, bajas/reactivaciones y gestión de eventos/asistencias. No concede administración técnica, eliminación física ni Tesorería automáticamente.

Finanzas centrales tiene dos concesiones independientes y expresas:

- `core.consultar_finanzas_centrales`: consulta de finanzas de comités activos.
- `core.operar_finanzas_centrales`: consulta y operaciones financieras existentes de comités activos, incluyendo gestión de conceptos, generación, abonos y eliminación con las confirmaciones vigentes. Es una concesión amplia y debe asignarse solamente a una autoridad financiera competente. No se incluye en el permiso ordinario de Secretaría.

Se extendió `limitar_finanzas` para conceptos, obligaciones y abonos territoriales. Para obligaciones y abonos se exige tanto el territorio del concepto como la manzana actual del ciudadano. La validación se repite en `ObligacionCiudadano.acreditar` cuando existe un usuario ejecutor; los selectores, recibos, CSV, historial y agregaciones parten del mismo alcance. Las llamadas internas sin usuario mantienen compatibilidad; las vistas autenticadas siempre pasan el usuario.

Los responsables no pueden crear/editar/eliminar conceptos ni generar obligaciones desde esas acciones. La capacidad de abonar se separa de la administración de conceptos. Se conservan los cargos y permisos operativos de comité.

Se añadió `CambioManzanaCiudadano`: registra territorio anterior/nuevo, ciudadano, usuario y fecha de captura al editar desde el formulario operativo. La operación y el registro se guardan en la misma transacción. El expediente muestra su historial paginado, conservando parámetros de navegación. No se alteran obligaciones ni movimientos anteriores. Se amplió la comprobación previa de eliminación a relaciones uno a uno, incluidos los vínculos de identidad.

También se corrigieron el título HTML del expediente, que contenía historiales, y la visibilidad de enlaces al expediente para usuarios con autorización contextual.

## Matriz de permisos

| Perfil | Padrón y ciclo ciudadano | Eventos y asistencias | Finanzas | Administración técnica |
|---|---|---|---|---|
| Superusuario activo | Global; eliminación con comprobaciones y confirmación | Global | Global, política existente | Sí |
| Secretaría central | Global; alta/edición/mudanza/baja/reactivación; sin eliminación física por defecto | Gestión comunitaria global | Ninguna por defecto; consulta u operación central mediante concesión expresa adicional | No por este permiso |
| Presidente | No obtiene padrón global ni modificación del ciclo | Eventos generales y asistencias de su comité activo | Consulta y operación del comité activo | No |
| Tesorero | No obtiene padrón global ni modificación del ciclo | Operaciones autorizadas del comité activo | Consulta y operación del comité activo | No |
| Solo lectura | Sin modificación del ciclo | Consulta, impresión y exportación del comité activo | Consulta, impresión, CSV y recibos del comité; sin escritura | No |
| Responsable de manzana | Consulta/expediente de su manzana; sin alta/edición/mudanza/baja/reactivación/eliminación | Crea/gestiona eventos de su manzana; captura y exporta participantes autorizados; conserva captura territorial en eventos generales | Conceptos MANZANA propios; obligaciones y abonos cuyo ciudadano sigue en ese territorio; recibos/CSV; sin conceptos generales ni administración de conceptos | No |

Los permisos globales heredados no amplían el alcance de cargos ni responsables. Identidades inconsistentes, cuentas inactivas y asignaciones inválidas no otorgan alcance operativo. La concesión expresa a un administrador técnico sin responsabilidades conserva la política global previa.

## Preparación de cuentas de prueba

En una instancia de pruebas de **Dahiedhi**, una autoridad técnica debe:

1. Crear cuentas individuales y vincularlas mediante `PerfilAcceso` a ciudadanos activos.
2. Para Secretaría, asignar `operar_secretaria_central`, sin cargo de comité ni responsabilidad territorial activos. No marcar superusuario ni personal por esta función. No asignar permisos de `auth`.
3. Solo si corresponde, conceder consulta u operación financiera central explícitamente.
4. Para responsable, vincular el ciudadano a su manzana activa y asignarlo como responsable de esa misma manzana; no asignar otro cargo activo.
5. Para presidente, tesorero o lectura, registrar un cargo activo identificado en un comité activo. Mantener los cargos anteriores inactivos.

No hay migración que asigne privilegios automáticamente. La preparación de cuentas no se ejecutó sobre instalaciones reales.

## Pruebas y evidencia

Entorno: Python 3.13, Django 5.2.19, SQLite temporal/en memoria. Dependencias instaladas en el entorno virtual local. PostgreSQL no estuvo disponible para ejecutar esta validación.

Comandos ejecutados:

```bash
python -m pip --python .venv/bin/python install -r requirements.txt
.venv/bin/python manage.py test --settings=config.settings_test --noinput
.venv/bin/python manage.py check --settings=config.settings_test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings_test
.venv/bin/python manage.py showmigrations --plan --settings=config.settings_test
git diff --check
```

La línea base, con configuración temporal equivalente, ejecutó 308 pruebas: 4 fallos y 3 errores heredados. El comando sin etiquetas inicialmente descubría cero pruebas porque `apps` no tenía `__init__.py`; se añadió el archivo para que el descubrimiento estándar funcione.

Las correcciones de pruebas heredadas son explícitas:

- Dos referencias apuntaban a un nombre de migración de operación inexistente; se actualizaron al nodo real, sin modificar migraciones históricas.
- La prueba de trazabilidad combinaba un estado histórico con un esquema de otras aplicaciones más reciente y omitía la edad obligatoria del modelo inicial; ahora reproduce consistentemente el esquema inicial y sus datos válidos.
- Dos expectativas de texto correspondían a una versión anterior del resumen financiero: el título vigente es “Aportaciones recientes” y el estado vacío se expresa por su componente actual.
- El control preservado es `ciudadanos_por_pagina`; `limite_ciudadanos` sigue siendo una entrada compatible, no el nombre que se devuelve en el formulario.
- Buscar “Ana” también coincide con el concepto “Feria de manzana”; se corrigió el número esperado sin cambiar la búsqueda existente.
- El expediente territorial ahora permite su sección financiera restringida; se actualizó la expectativa anterior de ocultación completa.

Se añadieron 15 pruebas en `apps/core/test_consolidacion.py`: Secretaría sin privilegios técnicos, concesión financiera explícita, identidad, permisos heredados, POST de padrón, cobros válidos/prohibidos, recibos, mudanza, autorización en el servicio, administración de conceptos denegada, ciclo ciudadano con historial, eventos, flujo integral, manipulación territorial, título HTML y cuentas/identidades inactivas. Las pruebas existentes mantienen cobertura de duplicados/homónimos, CSRF, reenvíos, bajas, eliminación, unicidad de cargo, comités, HTMX, exportaciones y conservación financiera.

**Resultado final: 323 pruebas aprobadas; 0 fallos; 0 errores.** `check` sin incidencias; `makemigrations --check` sin cambios pendientes; grafo de migraciones válido; `git diff --check` sin incidencias.

Se ejecutó un smoke de navegador con Playwright y Chromium sobre un servidor local y una base SQLite separada, con identidades sintéticas para los cinco perfiles. Se comprobó inicio de sesión, alta de Secretaría y expediente, consulta territorial y rechazo de alta del responsable, acceso a Tesorería/asistencias para los tres cargos de comité y rechazo de creación financiera para lectura. Resultado: cinco perfiles OK. No constituye una revisión visual exhaustiva en móviles ni impresión física.

Comandos auxiliares ejecutados sobre scripts temporales fuera del repositorio:

```bash
PYTHONPATH=/workspace/work:$PWD .venv/bin/python /workspace/work/browser_check.py
PYTHONPATH=$PWD .venv/bin/python /workspace/work/benchmark_duplicates.py
```

La detección de duplicados sobre 2,000 ciudadanos sintéticos tardó 0.2275 s en este entorno. Es una medición local, sin umbral garantizado para producción; se conserva el algoritmo lineal y la advertencia confirmable de homónimos.

## Migraciones

Se conservan todas las migraciones históricas.

| Nueva migración | Dependencia | Efecto |
|---|---|---|
| core.0005_alter_ciudadano_options | core.0004_manzana_responsable_activo_una_manzana | Metadatos del permiso de Secretaría |
| core.0006_alter_ciudadano_options | core.0005 | Metadatos de concesiones financieras centrales |
| core.0007_cambiomanzanaciudadano | core.0006 y usuario intercambiable de Django | Nueva tabla de historial territorial |

No hay cambios de asignación de cargos ni migraciones de datos. No se utiliza `--fake`. La tabla nueva protege ciudadano, manzanas y autor frente a eliminaciones que destruyan este historial. Su reversión elimina únicamente ese historial nuevo y debe evaluarse antes de cualquier rollback; no se recomienda revertirla cuando existan registros de uso real.

Antes de integrar en un entorno de Dahiedhi: revisar respaldo, grafo real y `auditar_cargos` en modo de consulta conforme al procedimiento de esa instancia. Aplicar migraciones primero en una copia de pruebas. Esta entrega no ejecuta migraciones en producción.

## Casos que requieren intervención y límites

- Mudanza: la obligación continúa en el concepto original. El responsable anterior pierde acceso al ciudadano trasladado y el nuevo no puede cobrar conceptos de otra manzana. Una autoridad financiera expresamente autorizada debe atender los saldos pendientes. No se crean ni trasladan obligaciones automáticamente.
- El historial territorial registra cambios futuros realizados desde el formulario operativo. No se inventa historial anterior ni se reconstruyen adscripciones históricas desconocidas. Cambios directos en SQL, ORM o administración técnica quedan fuera de ese formulario.
- Los eventos territoriales creados sin comité conservan la captura de asistencia. El mecanismo previo exige comité para generar adeudos de asistencia: una autoridad operativa global puede asignarlo cuando corresponda. Mientras tanto se usan conceptos territoriales ya administrados por una autoridad financiera. El flujo integral prueba esta vía sin añadir una contabilidad paralela.
- Los pagos/cooperaciones antiguos y la bitácora general por comité no tienen vínculo suficiente para acreditar ámbito territorial completo. Se ocultan a responsables; estos consultan sus movimientos mediante abonos, expedientes y recibos autorizados.
- La consulta central opcional se limita a comités activos. Los comités inactivos requieren revisión administrativa; no se amplía su acceso automáticamente.
- No se ejecutó PostgreSQL, una prueba de carga concurrente ni una revisión visual exhaustiva móvil. Los bloqueos financieros ya existentes se mantienen, pero deben verificarse en PostgreSQL antes de integrar en una instalación real.
- No se accedió ni modificó producción, Santa Mónica, padrones reales, cuentas de instancia ni la base local preexistente. Las bases de prueba son temporales y sintéticas.

## Recorrido manual en el navegador

Utilizar una copia aislada de Dahiedhi con datos sintéticos, comités y dos manzanas activas. Crear previamente un concepto general y dos conceptos MANZANA (uno por territorio) con obligaciones válidas. No usar producción.

1. **Secretaría:** iniciar sesión; abrir Ciudadanos; buscar a una persona de cada territorio; crear un ciudadano y confirmar un homónimo solo tras revisar la advertencia; abrir expediente; corregir datos y cambiar manzana; comprobar historial territorial; registrar baja con fecha/motivo y reactivar; comprobar historial. Crear faena y junta generales, generar participantes y capturar asistencia. Confirmar que no hay eliminación física ni acceso técnico. Tesorería debe estar denegada hasta conceder consulta/operación financiera central expresamente.
2. **Responsable:** consultar Ciudadanos y expediente local; intentar URL de ciudadano ajeno y formulario de alta (404). Crear faena territorial; generar participantes y registrar asistencia; comprobar CSV/impresión de la lista. Abrir Tesorería, consultar concepto territorial propio y registrar un abono; abrir/imprimir/compartir su recibo. Probar concepto general/otra manzana, incluyendo POST directo: denegación. No debe aparecer administración de conceptos. Cambiar al ciudadano de manzana con Secretaría y volver a probar obligación/recibo: el responsable anterior pierde acceso.
3. **Presidente:** consultar únicamente eventos generales y finanzas de su comité; crear/editar eventos, generar participantes y capturar. Crear un concepto y generar obligaciones mediante el procedimiento existente. Registrar abono y consultar recibo. Intentar recursos de otro comité y eventos territoriales ajenos: denegación.
4. **Tesorero:** repetir consultas, captura y operaciones financieras de su comité, verificando el mismo aislamiento. Confirmar que su cargo no habilita modificación del padrón global.
5. **Solo lectura:** consultar, imprimir y exportar recursos de su comité; compartir enlaces que exigen autenticación. Intentar crear/editar/generar/abonar con URL y POST directo: denegación y ausencia de cambios. Desactivar cargo o comité y confirmar que deja de conceder acceso.

Compartir un enlace no concede permisos al destinatario. Consultar o imprimir recibos no crea movimientos.

## Archivos de implementación y revisión

- `apps/__init__.py`: descubrimiento de pruebas.
- `apps/core/autorizacion.py`: política central, responsabilidades y bloqueo de permisos heredados.
- `apps/core/ciudadanos.py`: relaciones protegidas uno a uno en eliminación.
- `apps/core/context_processors.py`: enlaces de expediente según capacidad contextual.
- `apps/core/models.py`: permisos centrales e historial territorial.
- `apps/core/views.py`: ciclo ciudadano, autorización central, historial y alcance financiero de consultas/indicadores/CSV/abonos.
- `apps/core/migrations/0005_alter_ciudadano_options.py`, `0006_alter_ciudadano_options.py`, `0007_cambiomanzanaciudadano.py`: migraciones aditivas.
- `apps/core/test_consolidacion.py`, `apps/core/test_padron_alcance.py`: pruebas nuevas y expectativa territorial actualizada.
- `apps/tesoreria/autorizacion.py`: consulta y cobro contextual, concesiones centrales explícitas.
- `apps/tesoreria/models.py`: autorización al acreditar con usuario.
- `apps/tesoreria/queries.py`: agregaciones de tarjetas según obligaciones autorizadas.
- `apps/tesoreria/test_migraciones_financieras.py`, `apps/tesoreria/tests.py`: correcciones de pruebas heredadas documentadas.
- `templates/dashboard/control_asistencias_detalle.html`, `mis_responsabilidades.html`, `perfil_ciudadano.html`, `tesoreria_detalle.html`: enlaces, descripción central, historial y separación de abono/administración.
- `config/settings_test.py`: SQLite aislado para pruebas reproducibles.
- `docs/DAHIEDHI_DIAGNOSTICO.md`: inventario previo.
- `docs/DAHIEDHI_CONSOLIDACION.md`: informe, matriz, validación y recorrido.

Resumen apto para revisión: habilitar Secretaría central identificada sin privilegios técnicos; permitir abonos y consultas territoriales exclusivamente sobre conceptos propios y ciudadanos actualmente adscritos; conservar historial ciudadano y financiero; proteger consultas, recibos, agregaciones y escrituras con las políticas compartidas. Revisar especialmente las concesiones financieras centrales, las migraciones aditivas y los casos de mudanza antes de integrar. No fusionar ni desplegar automáticamente.
