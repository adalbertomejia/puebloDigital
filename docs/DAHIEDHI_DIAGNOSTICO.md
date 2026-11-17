# Diagnóstico previo a la consolidación

Base remota verificada: `fcd051150e28412b33bba55dc59ca4b891207ec4`.
Rama de trabajo: `codex/dahiedhi-consolidacion-operativa`.

- Existentes: formularios operativos de alta/edición, normalización de nombres y confirmación de homónimos; bajas/reactivaciones con historial y token; eliminación protegida; expediente con paginación; eventos generales/territoriales, generación de participantes y captura; conceptos con alcance y manzana, obligaciones y abonos con autoría.
- Reutilizables: `responsabilidades_activas`, `permiso_global_de_modelo`, selectores `visibles_para`/`capturables_para`, `limitar_finanzas`, `acreditar`, formularios y plantillas del dashboard.
- Brechas: Secretaría central carece de política propia; finanzas solo reconoce comités; permisos globales pueden ampliar acceso territorial; agregaciones y listados de obligaciones deben limitarse también por residencia actual.
- Pruebas existentes: ciclo ciudadano, autorización, alcance, interfaz, cargos, recibos, trazabilidad, migraciones y adeudos de asistencia.
- Migraciones: historial con auditoría previa de cargos y restricciones de unicidad. No cambiar identidades, restricciones ni registros históricos. Se prevé únicamente una operación de metadatos para declarar permiso de Secretaría, sin migración de asignaciones.
- Obligaciones tras mudanza: conservar concepto y movimientos originales. El responsable anterior pierde acceso a esa obligación; el nuevo no obtiene acceso al concepto de otra manzana. Resolución por autoridad financiera autorizada.

La primera ejecución de pruebas quedó bloqueada por dependencias ausentes del entorno; se instalarán en el entorno virtual y se repetirá antes de modificar lógica.
