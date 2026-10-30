# Secretaría y solicitudes de Dahiedhi

## Diagnóstico y decisiones

Base revisada: rama `codex/permisos-presidente`, a partir de `a246325`. No se encontraron archivos AGENTS.md en el espacio de trabajo. Se inspeccionaron modelos, autorizaciones, formularios, servicios, expediente, selectores, plantillas y migraciones actuales.

El rol SECRETARIO ya existía en UsuarioApp. PerfilAcceso vincula la cuenta a un ciudadano; UsuarioApp conserva los cargos por comité; la responsabilidad territorial se deriva de la manzana y su responsable. No se crearon roles ni identidades paralelas. La visibilidad del padrón sigue dependiendo de `Ciudadano.objects.visibles_para(usuario)`.

No había un módulo de solicitudes ni almacenamiento privado de documentos. ActividadArchivo usaba FileField sin un flujo autorizado de descarga apropiado para expedientes; no se reutilizó su ruta pública potencial. Se reutilizaron Django, DAL, django-filter, las plantillas y estilos del panel, y la actualización de consultas existente mediante fetch. No se añadieron dependencias.

Se encontró un enlace GET de cierre de sesión y LogoutView admitía GET en Django 4.2. Se sustituyó por formulario POST con CSRF y se restringieron los métodos. GET devuelve 405 sin cerrar la sesión.

También se encontraron 5,517 archivos de `.venv` rastreados. No se borraron del disco, no se retiraron del historial y no se incluyen sus cambios en esta entrega. No se detectaron `.env` ni `db.sqlite3` rastreados en la comprobación dirigida. La limpieza del entorno virtual debe tratarse aparte. El settings.py versionado conserva configuración de desarrollo; no se modificaron ajustes de otra instalación.

## Flujo implementado

Expediente o buscador remoto → registrar solicitud → asignar responsable al recibirla o después → anotar seguimiento → resolver o cancelar con motivo y confirmación → consultar historial y constancia.

- Folio `DHD-S-` con UUID completo e índice único de base de datos. No usa conteos ni `max + 1`.
- Token de envío firmado por usuario, con nonce único persistido y vigencia de 24 horas. El mismo formulario devuelve la solicitud original, sin duplicar solicitud, historial ni archivos. Un formulario nuevo permite otra solicitud legítima para el mismo ciudadano.
- Estados: recibida, en atención, pendiente de información, resuelta y cancelada. Los estados abiertos pueden cambiar entre sí o cerrarse; resuelta y cancelada son terminales en esta entrega. No se borran solicitudes ni se reabren desde la interfaz.
- Tipo, ciudadano, descripción y comité quedan definidos al recibir la solicitud. No se trasladan solicitudes entre comités después de recibirlas; un registro incorrecto se cancela con motivo y se recibe nuevamente.
- Historial propio con autor, fecha, observaciones y cambios antes/después de estado, responsable y compromiso; conserva motivo de cierre y archivos recibidos. No usa ni genera registros financieros.
- «Vencida» se calcula para solicitudes abiertas con compromiso anterior al día local. «Próximas a vencer» cubre desde hoy hasta siete días después, inclusive.
- La bandeja muestra mis pendientes, sin asignar, vencidas y próximas; filtra por texto, estado, tipo, comité y responsable, con 20 filas por página. Sus contadores se calculan sobre el alcance autorizado completo; no son cifras globales ni datos simulados.
- La búsqueda acepta folio y palabras de nombre/apellidos. Expediente, registro y detalle conservan un retorno local validado con búsqueda, filtros y página. Los filtros GET de bandeja actualizan sin recargar el documento y tienen envío convencional como respaldo.
- El autocompletado de ciudadano reutiliza la búsqueda común por nombre, contrato y toma; requiere dos caracteres y pagina resultados de 20 en 20. No incrusta el padrón completo en el formulario.

## Autorización

| Cargo activo | Alcance del módulo |
| --- | --- |
| Administrador general activo | Todas las solicitudes; administra tipos sencillos en Django admin. |
| SECRETARIO / PRESIDENTE | Reciben, consultan, asignan y dan seguimiento dentro de sus comités activos y para ciudadanos que el padrón les permite consultar. |
| TESORERO / CAPTURISTA | Atienden únicamente solicitudes asignadas a su cuenta, con cargo activo en ese mismo comité y acceso existente al ciudadano. No pueden recibir nuevas ni reasignar. |
| LECTURA / DELEGADO o solo responsabilidad de manzana | No obtienen acceso al módulo por ese solo cargo. No se presume una atribución adicional no definida. |

La asignación nunca concede acceso por sí misma. Un permiso estándar `secretaria.view_solicitud` tampoco sustituye un cargo. La elección de responsables incluye cuentas activas con cargos admitidos en el comité y visibilidad existente del ciudadano; los administradores generales activos son elegibles por su alcance global. La responsabilidad de manzana limita el ciudadano visible cuando no hay permiso global de padrón; no otorga acceso a comités nuevos.

Un secretario sin permiso global de padrón ni responsabilidad territorial no recibe ese permiso automáticamente. Administración debe revisar qué acceso de padrón le corresponde; no se conceden permisos para facilitar el flujo. «Mi acceso» describe las nuevas capacidades, distinguiéndolas de las financieras.

Se comprueban permisos en bandeja, expediente, búsquedas de relaciones, creación, seguimiento, constancia y cada descarga. No hay URLs públicas de adjuntos ni rutas de borrado o edición de historial.

## Integridad y concurrencia

Cada creación o seguimiento y su historial comparten una transacción. Los archivos escritos durante una operación se eliminan si falla el guardado o el historial. Un cierre exige motivo y confirmación en formulario y servicio.

Cada solicitud tiene versión. La actualización comprueba la versión esperada y ejecuta una actualización condicional para evitar sobrescrituras. Un conflicto devuelve 409 con el formulario enlazado conservando la captura; el usuario debe revisar el estado actual antes de reintentar. No se actualiza automáticamente la versión oculta para forzar una sobrescritura.

En SQLite, los bloqueos concurrentes conocidos se convierten en conflictos explícitos y permiten reintentar el mismo token. Se probó doble envío simultáneo con dos conexiones, además de una edición con versión desactualizada. No se han probado otros motores en esta entrega.

## Documentos

Constancia imprimible de recepción, protegida por el mismo alcance de la solicitud. No se presenta como constancia oficial de resolución ni inventa atribuciones legales.

Adjuntos opcionales PDF, PNG o JPEG hasta 5 MB, comprobados por extensión y firma inicial. El nombre de almacenamiento usa UUID; el nombre mostrado se conserva separado. Los archivos se entregan como descarga con `nosniff`, autorización y cabeceras de no almacenamiento en caché. Validar firma no equivale a análisis antivirus ni a comprobar toda la estructura interna del documento; ese análisis queda fuera de esta entrega.

Ruta predeterminada: `BASE_DIR/var/solicitudes_privadas`, excluida de Git y sin URL pública. Puede cambiarse con el ajuste Django `SOLICITUDES_PRIVATE_ROOT`. Debe mantenerse fuera de MEDIA_ROOT, STATIC_ROOT y cualquier alias público del servidor web; asignar permisos de sistema solo al usuario de aplicación y respaldar este directorio junto a la base de datos. El módulo no puede controlar una configuración externa de Nginx/Apache que exponga directorios privados.

## Migración y preparación del despliegue posterior

Nueva migración: `secretaria.0001_solicitudes_seguimiento_documentos`, dependiente de core.0001, comites.0002 y el usuario configurable. Crea TipoSolicitud, Solicitud, Seguimiento, Adjunto e índices. No modifica ni renumera migraciones anteriores, no transforma padrones ni genera obligaciones o pagos.

1. Respaldar la base y los documentos existentes según el procedimiento de la instalación.
2. Actualizar la rama de Dahiedhi y activar su entorno virtual. No cambiar la instalación de Santa Mónica ni compartir sus bases o directorios privados. Este módulo no convierte el proyecto en un sistema multicliente dentro de una sola base compartida.
3. Ejecutar `python manage.py migrate` con la configuración de Dahiedhi.
4. Recopilar estáticos con el procedimiento de despliegue existente y la configuración de producción que defina STATIC_ROOT. El settings.py de desarrollo no lo define; no se inventó una ruta de producción.
5. Verificar el directorio privado y sus respaldos. Crear los tipos reales mediante administración; no se cargan tipos oficiales ni catálogo ficticio.
6. Revisar cargos activos, comités y permisos existentes del padrón. Probar una recepción, asignación, cierre, constancia y descarga con cuentas autorizadas antes de habilitar su uso.

No se aplicó ninguna migración ni semilla sobre producción, ni se reinició o desplegó el VPS. La instalación nueva y las semillas de QA se ejecutaron en SQLite separada bajo /tmp. También se probó migrar desde el estado sin tablas de Secretaría, conservando ciudadanos, abonos y saldos previos.

## Validación y límites

El módulo incluye pruebas de Django de autorización por comité y territorio, asignación, intentos directos por URL, filtros y contadores, cierre, folios, reenvío, historial, rollback con archivos, edición obsoleta y dos envíos simultáneos, CSRF, cierre de sesión, autocompletado con 2,000 ciudadanos y migración incremental.

Playwright/Chromium verificó el recorrido real desde expediente hasta cierre y descarga, constancia imprimible, conservación de datos ante error, búsqueda sin recarga y selectores remotos de ciudadano y responsable. Se usó una base aislada con 2,000 ciudadanos sintéticos, a 1366×768 y 390×844. Se bloquearon servicios HTTPS externos durante QA: se comprobó el funcionamiento con recursos locales y no se depende de la disponibilidad del CDN para el flujo. No hubo errores JavaScript ni desbordamiento horizontal en la pantalla móvil comprobada. Esto no certifica todos los dispositivos ni constituye una medición de carga de producción.

Quedan fuera: reapertura de solicitudes, traslado de comité, edición posterior de datos de recepción, eliminación de documentos, antivirus, catálogo oficial, plazos legales, corte de caja, incidencias y acuerdos de juntas. No se añadieron secciones sin comportamiento.

Prueba del módulo:

```bash
python manage.py test apps.secretaria.tests --noinput
```

Para la suite completa, añadir `apps.secretaria.tests` al comando explícito de [auditoria_pruebas.md](auditoria_pruebas.md).

Resultado final: **276 pruebas correctas**, incluidas **22 pruebas nuevas del módulo**. `manage.py check`, `makemigrations --check --dry-run`, comprobación sintáctica del JavaScript y `git diff --check` también pasan. La migración inicial y la actualización desde el estado previo se comprobaron en bases de prueba, no en producción.
