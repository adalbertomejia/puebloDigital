# Investigación breve: acceso y operación del padrón con Django

Consulta: 29 de octubre de 2026. Objetivo: pulir el MVP de un ERP comunitario de hasta 2,000 ciudadanos, manteniendo datos y relaciones existentes. No se cambia código funcional ni se instalan dependencias en esta investigación.

## Fuentes verificadas

Los sitios web de documentación y el blog Simple is Better Than Complex devolvieron un bloqueo de red del entorno. Se verificaron directamente las fuentes públicas siguientes; no se presenta el artículo bloqueado como leído. Las recomendaciones de UX y su priorización son una valoración para este ERP, no resultados de una prueba con sus usuarios.

| Fuente | Patrón documentado | Aplicación propuesta |
|---|---|---|
| [Django: optimización de acceso a datos](https://github.com/django/django/blob/stable/4.2.x/docs/topics/db/optimization.txt) | Medir primero, QuerySet.explain, consultas SQL y relaciones precargadas | Mantener paginación y medir consultas del padrón antes de agregar índices, caché o cambiar de buscador |
| [django-filter](https://github.com/carltongibson/django-filter) | FilterSet declarativo que recibe parámetros URL y un queryset | Centralizar validación de filtros sin perder el alcance autorizado del usuario |
| [django-tables2](https://github.com/jieter/django-tables2) | Tablas HTML con columnas personalizadas, ordenación y paginación | Reutilizar el patrón de tabla operativa compacta; valorar la biblioteca cuando haya repetición suficiente |
| [django-htmx: renderizado parcial](https://github.com/adamchainz/django-htmx/blob/main/docs/tips.rst) | Actualizar una parte del HTML manteniendo vistas y plantillas Django | Aprovechar los parciales actuales; no hace falta migrar el JavaScript que ya funciona para adoptar estas ideas |
| [django-autocomplete-light](https://github.com/yourlabs/django-autocomplete-light) | Selectores de relaciones con búsqueda y opciones dependientes | Elegir ciudadano/contrato/toma en formularios sin desplegar miles de opciones; siempre con queryset autorizado |
| [django-import-export](https://github.com/django-import-export/django-import-export) | Importación con vista previa, validación, relaciones y control de creación/actualización | Futura captura por lotes con revisión, detección de conflictos y trazabilidad |

Compatibilidad: los manifiestos consultados de las ramas de desarrollo actuales de django-filter, django-tables2, django-htmx y django-import-export declaran Django >=5.2. El README de django-autocomplete-light distingue series compatibles. Esto no certifica los requisitos de todas sus versiones publicadas. El proyecto declara Django >=4.2,<5.0; antes de instalar hay que seleccionar versiones compatibles o planificar por separado la actualización de Django. No instalar las últimas versiones por defecto como parte del rediseño visual.

## Situación concreta de core

Ya funciona:

- Búsqueda que separa palabras y busca en nombres, apellidos y contrato.
- Paginación de 20 ciudadanos y orden estable con PK como desempate.
- QuerySet visible por usuario y exportación basada en el conjunto autorizado.
- Respuesta parcial para consultas dinámicas, espera de 400 ms, cancelación de solicitudes previas y protección frente a respuestas fuera de orden.
- Formularios GET que también funcionan sin JavaScript; filtros en URL y navegación con historial.
- select_related de toma/manzana y métricas calculadas en SQL.

Aspectos para pulir:

1. Inicio añade número de toma a la búsqueda; el padrón usa el mismo helper sin ese campo adicional. El mismo identificador puede dar resultados distintos según la pantalla.
2. El formulario principal muestra muchos filtros a la vez. Eso aumenta el trabajo visual incluso para una búsqueda cotidiana por nombre o contrato.
3. La tabla mezcla identificación, estado, manzana, motivo de alta, toma, último pago, adeudos, fecha y varias acciones. Conviene distinguir identificación de consulta detallada y operación financiera.
4. Parte de las reglas de edad y de interpretación de parámetros está repetida entre views.py y query_helpers.py. Una sola definición facilita probarlas y evita divergencias.
5. Las tarjetas del padrón describen el universo autorizado y el listado muestra el resultado filtrado. Hay que etiquetar claramente esos dos conjuntos o actualizar también los resúmenes al filtrar.
6. El JavaScript solo comprueba response.ok: una sesión vencida puede terminar en la página de login con HTTP 200 tras redirección. Hay que distinguir ese caso y conservar el contexto de búsqueda.
7. Los botones de alta/edición deben corresponder al permiso real del servidor. Ocultar una acción no sustituye la autorización; mostrar acciones que terminan denegadas tampoco ayuda al operador.

## Recomendación para el primer pase de UX

Conservar Django, las plantillas y la búsqueda existente. Para 2,000 ciudadanos no hay evidencia que justifique agregar un buscador externo o sustituir la interfaz completa.

- Barra principal: búsqueda por nombre/contrato/toma, manzana y estado.
- «Más filtros»: edad, sexo, motivo de alta, toma, fecha de nacimiento y adeudos.
- Accesos por tarea: «Sin manzana», «Sin contrato», «Sin toma» y «Datos por completar». Se representan como URLs filtradas; no exigen tablas nuevas inicialmente.
- Filtros aplicados visibles con etiquetas eliminables, cantidad de resultados y una acción clara de limpiar.
- Tabla sugerida: Ciudadano (contrato como dato secundario), Manzana, Estado, Toma y Acciones. El expediente conserva el resto. No reducir el tamaño de fuente para introducir todas las columnas.
- Una acción principal «Ver expediente», más «Editar» cuando esté permitido. Las acciones financieras quedan en sus recorridos correspondientes.
- Mantener búsqueda y página al volver del expediente; atender estado vacío, carga, error de red y sesión vencida.
- Comprobar el flujo con teclado y en pantallas de 1366×768 y 1440×900. Son tamaños de prueba propuestos; esta investigación no incluye una validación visual en navegador.

## Ajustes del modelo y de las consultas

No comenzar cambiando el esquema de Ciudadano. Primero:

1. Separar consultas, filtros validados y presentación en módulos pequeños; el punto de partida siempre es el queryset autorizado.
2. Unificar la búsqueda de Inicio/padrón y las reglas de edad existentes.
3. Medir resultados relevantes, consultas SQL y tiempo de respuesta con una copia representativa de 2,000 ciudadanos. Los índices ordinarios no garantizan acelerar búsquedas icontains; comprobar el plan según SQLite/PostgreSQL antes de decidir.
4. Mantener fecha de nacimiento como base de edad cuando existe y edad registrada como respaldo; no reemplazar masivamente valores históricos.
5. Conservar separados contrato del ciudadano y número de toma. No deduplicar personas solo por nombre ni imponer unicidad de contrato sin revisar primero los datos y la regla de negocio.
6. Considerar nombres con acentos, apellidos compuestos y coincidencias ambiguas. El comportamiento real de búsqueda debe probarse con la base utilizada; no asumir que icontains equivale a búsqueda sin acentos.

## Captura automatizada posterior

Una importación útil requiere más que subir Excel:

1. Seleccionar archivo y mapear columnas.
2. Validar sin guardar y mostrar errores por fila.
3. Distinguir altas, actualizaciones, duplicados posibles y relaciones ambiguas.
4. Confirmar el lote revisado y aplicar una transacción coherente.
5. Registrar quién importó, qué cambió y qué filas se omitieron. Repetir el mismo lote no debe duplicar personas, tomas o movimientos.

El importador actual de core carga nombres, sexo y manzana; no reconstruye contratos/tomas. No reutilizarlo como importador general del ERP sin ampliar y probar su contrato. Su dependencia openpyxl tampoco aparece en requirements.txt, lo cual debe resolverse al preparar ese trabajo. OCR o extracción asistida pueden proponer datos más adelante; las coincidencias y relaciones deben revisarse antes de guardarse.

## Orden de entrega propuesto

1. Padrón más claro: búsqueda consistente, filtros básicos/avanzados, tabla compacta y conservación del contexto. Sin migraciones de datos.
2. Organización interna de core: filtros/consultas compartidos, permisos y medición de rendimiento.
3. Captura guiada con autocompletado y validaciones de relaciones.
4. Importación por lotes con vista previa y trazabilidad.

Medir éxito por tarea: tiempo para localizar a una persona, abrir su expediente y corregir un dato; número de pasos para aplicar un filtro frecuente; conservación de contexto; ausencia de datos fuera de alcance y de duplicados en captura. No usar solamente cantidad de gráficas o reducción del tamaño de los elementos como medida de mejora.
