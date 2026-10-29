# Probar la herencia financiera por comité

Estos pasos son para una copia local de desarrollo y no deben ejecutarse sobre los datos del VPS. La migración de nombres de identidad/cargos solo registra opciones de presentación, sin cambios de esquema ni datos.

## Actualizar y ejecutar las pruebas

Con el repositorio local sin cambios pendientes y el entorno Python del proyecto activado:

```sh
git switch codex/permisos-presidente
git pull --ff-only origin codex/permisos-presidente
python manage.py migrate
python manage.py check
python manage.py test apps.tesoreria.test_autorizacion --noinput
```

Las pruebas usan una base temporal de Django y datos sintéticos, incluido un padrón de 2,000 ciudadanos. No crean usuarios en tu base de desarrollo.

## Preparar una comprobación manual

Desde una cuenta superusuaria de tu base local:

1. Crear o elegir dos comités activos, por ejemplo Agua y Feria.
2. Crear cuentas activas diferentes para presidente de Agua, tesorero de Agua, presidente de Feria y tesorero de Feria. No necesitan staff ni permisos Django de tesorería.
3. Asignar sus cargos en **Cargos de comité** (`UsuarioApp`), en `/admin/comites/usuarioapp/`, con el comité y rol correspondientes y la asignación activa.
4. Usar algunos ciudadanos de prueba activos. El vínculo de identidad en **Vínculos de cuenta y ciudadano** (`PerfilAcceso`) no es un requisito nuevo de este corte; su consistencia con cargos se trabajará después.
5. Abrir sesiones separadas para cada cuenta, en diferentes perfiles de navegador o cerrando sesión entre pruebas. El login de la aplicación lleva al dashboard; Tesorería aparece en el menú de quienes tienen cargo financiero.

## Recorrido esperado

| Prueba | Resultado |
|---|---|
| Presidente y tesorero de Agua crean conceptos de Agua | Permitido; el selector de comité ofrece sus comités financieros activos |
| Generar obligaciones dos veces sobre el mismo concepto | Sin duplicados; ciudadanos inactivos excluidos |
| Registrar abonos parciales | Totales/saldos reflejan los abonos y conservan las validaciones de importe |
| Consultar conceptos, búsquedas, resúmenes y exportaciones | Solo datos e importes de los comités autorizados de esa cuenta |
| Intentar acceder por URL al concepto u obligación de Feria desde Agua | 404, sin permitir abonos, edición, generación o borrado ajenos |
| Seleccionar un comité ajeno por filtros GET | No amplía los resultados; en búsqueda validada puede aparecer error de selección |
| Desactivar el cargo o comité y volver a solicitar una página financiera | Se revoca el acceso; no se borran los movimientos |
| Una cuenta es presidente de Agua y tesorero de Feria | Gestiona finanzas de ambos; no obtiene gestión de eventos de Feria por ser tesorero |
| Cuenta sin cargos, o solo secretario/capturista/lectura/delegado | No accede a las vistas financieras por esos cargos, aunque tenga permisos Django por modelo |
| Intentar usar el admin financiero desde una cuenta staff ordinaria | Denegado; el mantenimiento administrativo de finanzas y autoridad queda reservado al superusuario |
| Concepto con obligaciones: intentar cambiar su comité | Rechazado incluso si la cuenta tiene cargos en ambos comités |

Presidente hereda las capacidades financieras de tesorero dentro de su comité; no necesita una asignación TESORERO duplicada. No hereda administración de cuentas, cargos ni borrado de eventos.

El borrado físico de concepto conserva el comportamiento previamente acordado: confirmación en pantalla y POST, con eliminación de obligaciones y abonos en cascada. Para comprobarlo, usar solo datos desechables. Una cancelación/reversa con motivo e historial contable es un flujo diferente y sigue pendiente.

## Alcance de esta entrega

Se acotan conceptos, obligaciones, abonos, métricas, fechas disponibles, búsquedas, CSV y la información financiera relacionada del inicio, padrón y expediente. El expediente conserva su requisito de acceso al ciudadano: un cargo financiero no concede acceso global al padrón.

El superusuario conserva lectura y mantenimiento global, incluso para comités inactivos. Las pantallas administrativas financieras, sus inlines, la asignación de cargos/vínculos y la administración de usuarios/grupos se reservan al superusuario; no se usa staff como sustituto de un cargo financiero.

No se modifica el vínculo cuenta-ciudadano ni la operación de responsables de manzana. No se añaden cancelaciones/reversas ni bitácoras de movimientos en este corte. Estos pasos no equivalen a haber probado el VPS ni a desplegar el cambio.
