# Roles operativos y cargo único

Esta política es la vigente en `codex/dahiedhi-ciclo-ciudadano` y sustituye las propuestas anteriores de cargos simultáneos. No incorpora el módulo de solicitudes de otras ramas.

## Regla de identidad y responsabilidad

- Cada cuenta operativa se vincula a un ciudadano mediante `PerfilAcceso`, que es uno a uno por cuenta y por ciudadano.
- Cada ciudadano y cuenta pueden tener **un solo cargo activo**. Los cargos inactivos anteriores se conservan.
- Presidente, tesorero y solo lectura siempre se acotan a su comité activo. No se necesita duplicar cuentas para consultar o imprimir.
- La responsabilidad de una manzana activa también cuenta como cargo: no puede acumularse con un cargo de comité ni con otra manzana activa.
- El superusuario mantiene su administración global explícita; no es un cargo de comité. Las asignaciones de negocio siguen validando identidad y unicidad.

| Acción en el comité propio | Presidente | Tesorero | Solo lectura |
| --- | --- | --- | --- |
| Consultar asistencias y aportaciones | Sí | Sí | Sí |
| Buscar participantes y consultar estados | Sí | Sí | Sí |
| Imprimir consultas, exportar CSV y consultar/imprimir recibos existentes | Sí | Sí | Sí |
| Compartir enlaces de consulta | Sí | Sí | Sí |
| Crear/editar eventos generales del comité y generar participantes | Sí | Sí | No |
| Capturar asistencia normal/presencial y cambiar estado del evento | Sí | Sí | No |
| Crear/editar conceptos, generar obligaciones y registrar abonos | Sí | Sí | No |
| Eliminar conceptos según el flujo financiero existente | Sí | Sí | No |
| Asignar cuentas, identidades o cargos; administrar datos globales | No | No | No |

Los eventos territoriales mantienen su alcance por manzana: un cargo de comité no administra un evento territorial solo por aparecer como comité convocante. El borrado de eventos no se concede automáticamente por ser presidente o tesorero. La administración global de ciudadanos y los permisos de modelo de cuentas administrativas independientes se conservan por separado.

Secretaría, Capturista y Delegado se conservan como valores históricos compatibles. No reciben funciones nuevas ni acceso a asistencias/finanzas por su sola asignación; el formulario de nuevos cargos ofrece presidente, tesorero y solo lectura. Los registros antiguos pueden desactivarse sin eliminarse ni convertirse automáticamente a otro rol.

## Configuración de una cuenta

Desde una cuenta superusuaria:

1. Registrar al ciudadano y crear su cuenta individual activa.
2. Crear el **Vínculo de cuenta y ciudadano**. Una cuenta no comparte su vínculo con otra persona.
3. En **Cargos de comité**, elegir la cuenta, su comité y uno de los tres roles vigentes. El ciudadano del cargo se toma del vínculo; si se indica otro, se rechaza.
4. Para cambiar de cargo o comité, desactivar el anterior antes de activar el nuevo. Para volver al mismo cargo ya registrado, reactivar ese registro cuando no exista otro cargo vigente.

No es necesario dar `is_staff`, permisos Django globales ni otra cuenta para que presidente/tesorero impriman o consulten recibos. Los permisos globales heredados de grupos no amplían el alcance de una cuenta con cargos registrados, incluso si están inactivos. Las cuentas con cargo inactivo, comité inactivo, persona inactiva, identidad ausente o combinaciones heredadas contradictorias no reciben capacidades por ese cargo.

El cambio de identidad se valida y bloquea mientras exista un cargo vigente. Los cambios de cargo, vínculo y responsabilidad territorial desde los modelos se validan bajo transacción y bloqueo de las filas de cuenta/ciudadano. PostgreSQL y SQLite no tienen la misma semántica de bloqueo; no se afirma una prueba de concurrencia PostgreSQL en esta entrega.

## Consulta e impresión

Se reutilizan las pantallas existentes de asistencia, conceptos, aportaciones y recibos. En detalle de asistentes hay búsqueda por nombre/contrato/toma, filtro de estado y paginación de 25 registros; el CSV respeta esos filtros. Los indicadores describen todo el conjunto autorizado y no cambian al filtrar el listado.

«Imprimir esta página» imprime los filtros y la página visibles; el CSV permite llevar el conjunto filtrado completo a impresión externa. «Compartir consulta» usa el mecanismo de compartir del dispositivo o copia el enlace. La URL conserva filtros/página y sigue requiriendo una cuenta autorizada; no se publica información ni se crea acceso público.

Los recibos de abonos existentes conservan el formato de 80 mm. Consultar, compartir o imprimir no crea pagos, asistencias ni anotaciones financieras ficticias. Las vistas de selección de obligaciones para cobrar y sus autocompletados se reservan a operadores; solo lectura usa las búsquedas de consulta.

## Separación en el servidor

`comites_financieros(..., escritura=False)` distingue comités consultables de `escritura=True`; cada modificación vuelve a buscar el objeto dentro del alcance de escritura. Formularios y acciones de cada tarjeta también usan ese alcance. No basta con tener algún permiso financiero en la cuenta para modificar cualquier concepto que pueda consultarse.

La lectura de eventos/participantes usa comités consultables; creación, gestión y captura usan exclusivamente los comités operables. Se mantienen las responsabilidades territoriales existentes. Los permisos de lectura no se convierten en captura; los permisos Django globales no permiten a una cuenta de comité saltarse su ámbito. Las autorizaciones se comprueban en el servidor, además de ocultar botones.

El padrón general no se abre por tener un cargo financiero o de solo lectura. Las pantallas operativas ya muestran los nombres y datos necesarios del registro autorizado; los enlaces al expediente general se omiten si no hay permiso de padrón.

## Antes de aplicar las migraciones

Hay dos migraciones nuevas posteriores al ciclo ciudadano:

- `core.0004_manzana_responsable_activo_una_manzana`: preflight de todas las asignaciones y unicidad de responsable territorial activo.
- `comites.0004_usuarioapp_cargo_activo_unico_cuenta_and_more`: unicidad del cargo activo por cuenta y ciudadano, y obligación de ciudadano en cargos activos.

Primero, en la instalación correcta, ejecutar la revisión **sin escrituras**:

```bash
python manage.py auditar_cargos
python manage.py migrate --plan
```

La auditoría devuelve identificadores y códigos de problema; no modifica datos. La migración se detiene antes de tocar asignaciones si encuentra cargos activos simultáneos, identidad contradictoria/ausente o doble responsabilidad territorial/comité. Esos casos requieren revisión administrativa; no se borran cargos ni se elige automáticamente cuál conservar.

Cuando todos los casos son coherentes, la migración solo completa el campo de ciudadano de un cargo si está vacío y ya existe un `PerfilAcceso` inequívoco para esa misma cuenta. No crea ciudadanos, cuentas ni vínculos por inferencia. Desactivar un cargo antiguo permite conservarlo como antecedente.

No se ha aplicado esto en el VPS ni contra datos reales. Durante la migración deben suspenderse las escrituras de asignaciones para que la revisión y la activación de restricciones usen el mismo conjunto. Revisar respaldos, grafo real y asignaciones antes del despliegue acordado. No borrar migraciones, no regenerar iniciales ni usar `--fake` para resolver conflictos.

## Verificación

- 22 pruebas nuevas de roles, identidad, unicidad y migración aprobadas.
- Lectura y escritura por URL directa/POST; captura normal/presencial denegada al lector; preservación de recibos; roles y personas inactivos; permisos globales heredados; asignaciones contradictorias; restricciones también en la base; auditoría sin escrituras.
- Tres pruebas de migración verifican el vínculo inequívoco, el bloqueo por duplicados sin cambiar registros y el bloqueo de cuentas sin identidad.
- Chromium con pantalla móvil de 390 px: consulta de asistencia/aportaciones, controles según rol, impresión sin navegación e impresión de recibos con las mismas cuentas de presidente/tesorero/solo lectura. Se utilizaron datos sintéticos y una base temporal eliminada después de la prueba.
- Suite completa: **308 ejecutadas, 301 aprobadas y siete incidencias heredadas** (cuatro expectativas del resumen de aportaciones y tres pruebas históricas de migraciones). No se cambian esas migraciones para ocultar los fallos.
- Las pruebas existentes se ajustaron a identidades explícitas y un solo cargo activo. Las pruebas de fórmulas multicomité usan una cuenta administradora, no un usuario ordinario con varios cargos. No se amplían permisos reales para acomodar fixtures antiguos.

```bash
python manage.py test apps.comites.test_roles_operativos apps.comites.test_migracion_cargo_unico
python manage.py check
python manage.py makemigrations --check --dry-run
```

La validación se ejecutó con Django 5.2 y SQLite temporal, sin tocar la conexión configurada de producción. No se probó PostgreSQL ni concurrencia entre solicitudes reales. Se mantienen fuera del alcance cortes/balances, reversas contables nuevas y módulos de Secretaría/Capturista.
