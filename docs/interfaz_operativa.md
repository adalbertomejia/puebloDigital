# Interfaz operativa

El padrón busca nombre, contrato y toma. Muestra búsqueda, manzana y estado; los otros criterios quedan en «Más filtros». Los accesos sin manzana, contrato, toma y datos por completar usan los mismos filtros de la exportación. Datos por completar significa contrato o manzana ausentes, o ausencia tanto de nacimiento como de edad.

La tabla muestra ciudadano, manzana, estado, toma y acciones. Ordena antes de paginar. Expediente y edición conservan el retorno a la consulta original.

Tesorería ofrece «Registrar abono de un ciudadano»: autocompletado remoto por nombre, contrato o toma, seguido de sus obligaciones pendientes. Ambos selectores y su validación al enviar se limitan al alcance financiero del usuario. Seleccionar no registra dinero: abre el formulario existente de abono. Existe búsqueda alternativa sin JavaScript.

Padrón, agua, eventos y consultas financieras actualizan filtros, páginas y ordenación mediante solicitudes GET al servidor. Conservan la autorización y disponen de navegación convencional como respaldo. Las operaciones POST siguen su flujo habitual.

## Instalación

Instalar requirements.txt en el entorno virtual y recopilar estáticos con `python manage.py collectstatic --noinput`. Se añaden django-filter 24.3, django-tables2 2.7.5 y django-autocomplete-light 3.12.1 compatibles con Django 4.2. No hay cambios de modelos ni nuevas migraciones.

## Verificación

13 pruebas nuevas de interfaz, aislamiento de selectores, paginación y retorno pasan. La suite conjunta ejecuta 237 pruebas y conserva las 5 fallas y 2 errores previamente identificados. El navegador con datos sintéticos de 2,000 ciudadanos valida búsqueda por toma, selectores dependientes, retorno al padrón y filtrado de agua sin recargar el documento. No se ha modificado producción.

## Recibos de tesorería de 80 mm

Cada abono tiene un folio `PD-A-` seguido por su identificador con al menos ocho cifras (por ejemplo, `PD-A-00000123`). El folio deriva de la clave primaria del abono: es estable, distingue abonos y también funciona para registros anteriores, sin migraciones. La referencia externa del comprobante sigue siendo independiente.

Después de registrar un abono aparece el enlace para imprimirlo. El historial de abonos, el expediente y los resultados financieros permiten reimprimirlo. Desde Tesorería, «Buscar recibo por folio» localiza el abono dentro de los comités autorizados; conocer un folio ajeno no otorga acceso.

El ticket incluye nombre e ID del ciudadano, contrato, manzana, fecha del abono, comité, concepto, tipo, monto de ese abono, autor y referencia cuando existe. El pie indica «Conserve este recibo». La reimpresión consulta los datos actuales relacionados; no representa una instantánea histórica de nombres o domicilios. No genera ni duplica pagos.

En el diálogo de impresión seleccionar la impresora y papel de 80 mm, escala 100 %, y desactivar encabezados y pies del navegador. El contenido utiliza 72 mm, dejando 4 mm por lado. El largo depende de la configuración de la impresora. Se verificó el ancho y la ocultación de controles en Chromium; falta comprobar el resultado en la impresora física.


## Adeudos de asistencia y Tesorería

Diagnóstico: la captura almacenaba `genera_adeudo` y `monto_adeudo` en RegistroFaena/AsistenciaJunta, sin una integración que creara o actualizara obligaciones financieras. Por ello las métricas de asistencia podían mostrar adeudos ausentes en Tesorería.

La captura normal utiliza un único importe: cero desactiva el adeudo; un valor positivo lo activa. Permite buscar participantes por nombre o contrato, guardar por fila o guardar el formulario mediante solicitudes POST sin recargar. El estado «Sin guardar» distingue la edición del registro confirmado; los contadores se actualizan después de guardar. Sin JavaScript conserva el envío convencional. La captura presencial mantiene su flujo actual.

Un evento crea un concepto vinculado mediante una relación única; cada ciudadano tiene una sola obligación por ese concepto. Las correcciones actualizan su importe. Retirar un adeudo sin abonos cancela la obligación, conservando evidencia; volver a activarlo reutiliza la obligación. No se permite retirar un adeudo con abonos ni reducirlo por debajo de lo recibido. Toda la captura y la sincronización forman una transacción: un error revierte el envío completo. Se conserva el alcance autorizado de participantes y comité. Un evento sin comité requiere asignarlo antes de emitir adeudos.

La migración `tesoreria.0004_vinculo_adeudos_asistencia` añade dos relaciones opcionales a ConceptoTesoreria. No cambia importes ni genera cobros históricos. Al guardar participantes existentes desde captura normal se sincronizan sus adeudos. No se relacionan conceptos anteriores por coincidencia de nombres: cualquier cobro histórico creado manualmente debe revisarse antes de guardar para evitar duplicarlo. Los conceptos vinculados no admiten la generación masiva para todo el padrón. El borrado del evento queda protegido mientras conserve un concepto financiero vinculado.

Esta entrega integra el panel de captura normal; la edición directa del administrador no ejecuta esta sincronización. No se han aplicado migraciones ni cambios sobre la base de producción, ni publicado el borrador.

Verificación de esta entrega: 10 pruebas nuevas pasan; la regresión enfocada de 92 pruebas pasó antes del último caso añadido. La suite explícita completa ejecutó 252 pruebas y conservó las 5 fallas y 2 errores preexistentes. Chromium con datos sintéticos verificó guardar una fila sin guardar la otra, guardar todos los cambios, actualización de contadores, retirada de adeudo y búsqueda por contrato sin recargar el documento. No se probó contra datos de producción.

### Compatibilidad de la migración 0004 con bases SQLite históricas

Si aparece `NOT NULL constraint failed: new__tesoreria_conceptotesoreria.monto_individual`, SQLite está copiando la tabla al añadir una relación única y encuentra un importe histórico NULL, aunque el estado de migraciones declare ese campo obligatorio. La versión corregida de 0004 añade las columnas opcionales sin copiar la tabla y utiliza índices únicos equivalentes; conserva las claves foráneas. Otros motores mantienen la operación estándar de Django.

Esta corrección no sustituye importes por cero ni genera cobros. Los conceptos con importe NULL requieren revisión posterior con sus datos de origen. Hacer respaldo de la base, actualizar la rama y repetir `python manage.py migrate`. No utilizar `--fake`, borrar la base ni marcar 0004 como aplicada manualmente. Si 0004 ya estaba aplicada correctamente, Django la mantiene aplicada y no la ejecuta otra vez.

La verificación reproduce una tabla histórica con monto NULL y comprueba avance y reversión de 0004 en SQLite, conservación de importes y abonos, unicidad por evento e integridad de las claves foráneas. Pasan 17 pruebas de migraciones, adeudos y recibos.
