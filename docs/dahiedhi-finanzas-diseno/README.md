# Diseño de recaudación cortes y transparencia para Dahiedhi

Fecha de análisis: 23 de noviembre de 2026. Estado: propuesta para revisión, sin implementación del módulo ni migraciones ejecutadas.

**Recomendación:** terminar el MVP con ingresos, seguimiento de adeudos y cortes de recaudación verificables (opción A). Los indicadores pueden construirse sobre Tesorería. El corte real exige previamente identificar caja y medio de cobro, registrar todo movimiento de efectivo y proteger las operaciones incluidas en cierres. Egresos y disponibilidad neta son una ampliación posterior (opción B).

## Entregables

1. [Diagnóstico del código y riesgos](01-diagnostico.md).
2. [Métricas, clasificación y ejemplos verificables](02-metricas.md).
3. [Arquitectura, entidades y diccionario de datos](03-arquitectura.md).
4. [Permisos, flujo de revisión y decisiones de negocio](04-permisos-decisiones.md).
5. [Fases, pruebas propuestas y referencias UX](05-hoja-de-ruta.md).
6. [Prototipo navegable de seis pantallas](prototipo.html): descargar el archivo y abrirlo en el navegador. Funciona sin servidor, cuentas, bases de datos ni recursos externos. Incluye selector de ancho escritorio/móvil, perfiles simulados, filtros, conciliación ficticia, impresión y exportación agregada. Los cambios se pierden al recargar.
7. [Guía de revisión y comprobaciones del prototipo](06-validacion.md), con doce capturas escritorio/móvil y ejemplos PDF/CSV.

El prototipo es una representación del diseño futuro. Sus botones no modifican Pueblo Digital. Los perfiles simulados no sustituyen autorización de servidor y el enlace de demostración no representa un informe financiero real.

## Base real verificada

`git ls-remote origin` devolvió:

| Rama | Commit remoto |
|---|---|
| codex/dahiedhi-ciclo-ciudadano | fcd051150e28412b33bba55dc59ca4b891207ec4 |
| codex/dahiedhi-consolidacion-operativa | c50762e9ec5c52c3121e9de1d65fc9b8ad3ac62a |

La referencia solicitada no incluye todavía la consolidación de Secretaría y Tesorería territorial realizada en esta conversación. Esta propuesta se prepara en `codex/dahiedhi-diseno-balances-cortes`, descendiente de `c50762e`. Las diferencias de autorización y los nuevos historiales de esa consolidación son una dependencia de implementación, no un hecho comprobado de producción. Antes de desarrollar, integrar o seleccionar explícitamente esa base; no volver a desarrollar sus funciones sobre `fcd0511`.

Se inspeccionaron modelos, servicios, autorización, consultas, vistas, recibos, filtros, plantillas, gráficas, migraciones y pruebas. No se abrió ninguna base de datos de instancia ni se modificó configuración de clientes. Solo se añaden estos documentos y el prototipo estático; no se alteran permisos, modelos, vistas o migraciones de la aplicación.

## Lo que ya existe y lo que falta

| Área | Situación |
|---|---|
| Conceptos, obligaciones, abonos parciales, recibos y bitácora | Existentes; reutilizar |
| Conceptos de faenas/juntas y agua | Existentes; conservar origen y vínculos |
| Consulta, filtros, CSV, reportes por concepto/territorio y Chart.js | Existentes; ampliar y homogeneizar fórmulas |
| Balance de recaudación y adeudos actuales | Datos principales disponibles; resolver calidad histórica y semántica temporal |
| Medio de cobro, caja/custodia, apertura, conteo físico | No registrados estructuradamente |
| Entradas/salidas no procedentes de abonos y entregas de efectivo | No existe un libro de caja completo |
| Corte cerrado con movimientos congelados y revisión independiente | No existe |
| Disponibilidad o balance neto | No calculable con los modelos actuales |
| Publicación abierta | No autorizada; mantener informes privados |

## Decisiones que bloquean cada fase

Para indicadores: aprobar fórmulas, fechas, tratamiento de históricos y acceso de Secretaría a agregados. Para cajas: decidir quién conserva el dinero, qué medios utiliza y cómo documenta entregas/retiros. Para cierres: nombrar preparadores/revisores, decidir tratamiento de diferencias y rectificaciones y aprobar protección contra eliminación. Para egresos: autorización independiente posterior.

No hace falta resolver egresos para iniciar indicadores. Sí hace falta resolver entradas y salidas de efectivo para llamar “conciliado” a un corte de caja.
