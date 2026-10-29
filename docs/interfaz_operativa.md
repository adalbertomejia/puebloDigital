# Interfaz operativa

El padrón busca nombre, contrato y toma. Muestra búsqueda, manzana y estado; los otros criterios quedan en «Más filtros». Los accesos sin manzana, contrato, toma y datos por completar usan los mismos filtros de la exportación. Datos por completar significa contrato o manzana ausentes, o ausencia tanto de nacimiento como de edad.

La tabla muestra ciudadano, manzana, estado, toma y acciones. Ordena antes de paginar. Expediente y edición conservan el retorno a la consulta original.

Tesorería ofrece «Registrar abono de un ciudadano»: autocompletado remoto por nombre, contrato o toma, seguido de sus obligaciones pendientes. Ambos selectores y su validación al enviar se limitan al alcance financiero del usuario. Seleccionar no registra dinero: abre el formulario existente de abono. Existe búsqueda alternativa sin JavaScript.

Padrón, agua, eventos y consultas financieras actualizan filtros, páginas y ordenación mediante solicitudes GET al servidor. Conservan la autorización y disponen de navegación convencional como respaldo. Las operaciones POST siguen su flujo habitual.

## Instalación

Instalar requirements.txt en el entorno virtual y recopilar estáticos con `python manage.py collectstatic --noinput`. Se añaden django-filter 24.3, django-tables2 2.7.5 y django-autocomplete-light 3.12.1 compatibles con Django 4.2. No hay cambios de modelos ni nuevas migraciones.

## Verificación

13 pruebas nuevas de interfaz, aislamiento de selectores, paginación y retorno pasan. La suite conjunta ejecuta 237 pruebas y conserva las 5 fallas y 2 errores previamente identificados. El navegador con datos sintéticos de 2,000 ciudadanos valida búsqueda por toma, selectores dependientes, retorno al padrón y filtrado de agua sin recargar el documento. No se ha modificado producción.
