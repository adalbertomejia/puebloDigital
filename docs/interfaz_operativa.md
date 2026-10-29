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
