# Hoja de ruta pruebas y referencias UX

## Alternativas de alcance

| Alternativa | Beneficio | Lo que permite afirmar | Datos/requisitos adicionales | Riesgo/complejidad |
|---|---|---|---|---|
| A1 Ingresos y adeudos | Alta reutilización, supervisión inmediata | Recaudación registrada, cartera actual y cumplimiento | Homogeneizar métricas/calidad; permisos de agregado | Baja-media; principal riesgo semántica y privacidad |
| A2 A1 más cortes de recaudación | Rendición y conciliación por caja | Efectivo esperado/contado y transferencias documentadas, desde adopción | Caja, medios, apertura, todas las entradas/salidas de custodia, manifiesto/revisor/protección | Media-alta; cierres, concurrencia e históricos |
| B A2 más egresos y disponibilidad | Visión de recursos y gastos | Flujo neto y saldo por unidad cuando hay cobertura completa | Egreso autorizado, comprobantes, cuenta/custodia y reglas de traslados | Alta; mayor capacitación y control financiero |

Recomendación: A1 y luego A2, con puntos de revisión. No llamar a A1 “saldo de caja”, a A2 “balance general” ni a B contabilidad completa. Incluso A2 necesita documentar salidas de custodia; excluir Egreso no autoriza ignorar dinero retirado. Si no puede registrarse ese libro mínimo, entregar solo informe de recaudación y no un corte conciliado.

## Fases y puertas de aceptación

| Fase | Entrega y dependencia | Riesgo | Complejidad relativa | Beneficio y condición de aceptación |
|---|---|---|---|---|
| 0 Base | Seleccionar/integrar consolidación c50762e; aprobar metodología y D01/D04/D12 | Medio | Baja | No desarrollar sobre permisos antiguos por error; diagnóstico y fixtures acordados |
| 1 Indicadores | A, B y C sobre modelos existentes; selectores con calidad de datos, cohorte y recaudación separadas | Medio | Media | Totales trazables sin doble suma; NULL visible; cifras de ejemplo reproducidas |
| 2 Clasificación y reportes | Origen/periodo/rangos; tablas, dona/barras, mensual; HTML imprimible/CSV con metodología | Medio | Media | Misma autorización y mismos totales en tabla/gráfica/export; datos personales excluidos de transparencia |
| 3 Medios y cajas | D02/D03/D08/D13; alta transaccional de medio/custodia e idempotencia, aperturas y entregas | Alto | Media-alta | Cada cobro nuevo tiene una única atribución y autor; ningún histórico se marca efectivo sin evidencia |
| 4 Cortes | D05–D11; manifiesto, conteo, revisión, confirmación y protección de fuentes en PostgreSQL | Alto | Alta | Cierre reproducible e inmutable; no solapes/doble inclusión; concurrencia real validada; procedimiento de diferencia aprobado |
| 5 Transparencia versionada | InformeFinanciero si requiere persistencia; cortes confirmados, referencias y privacidad D14–D16 | Medio-alto | Media | Enlaces autenticados/revocables, acceso por ámbito, snapshot idéntico al reimprimir; no publicaciones abiertas |
| Opcional Egresos | Opción B y autorización de gastos/proveedores/comprobantes | Alto | Alta | Recursos disponibles solo con cobertura completa; traslados no inflan ingresos/egresos |

No asignar semanas ni fechas de entrega sin conocer la disponibilidad del equipo y las decisiones pendientes. Cada fase termina con revisión funcional, pruebas y criterio de avance; no desplegar todo en una sola entrega.

## Pruebas propuestas para implementación

Estas son pruebas que deberán desarrollarse; no se presentan como ejecutadas en esta investigación.

| Grupo | Casos y resultado esperado |
|---|---|
| Fuentes | Varios abonos por obligación no multiplican asignado; bitácora/asistencia no se suman como ingresos; Pago/Cooperacion no se integran dos veces; traslado no es recaudación |
| Importes | Parciales, cero indebido, negativos, NaN/Infinity, máximo Decimal, sobrepago; un NULL vuelve indeterminado el total correspondiente; conjunto completo vacío sí da cero |
| Estados | Pagado/parcial/pendiente/cancelado; abono preexistente en cancelada sigue como ingreso registrado y excepción; inconsistencia entre estado y saldo se señala |
| Origen | Faena/Junta conserva vínculo tras pagar; solo deuda con importe positivo; ambos vínculos/origen inconsistente se señalan; evento sin comité no genera adeudo |
| Fechas | Fecha de pago vs captura; medianoche/zona local; mes/año/rango inclusivo; cobro retroactivo y captura tardía; cartera actual no se presenta como pasada |
| Autorización | Presidente/tesorero/lector/responsable/Secretaría/superusuario técnico; identidad inactiva, cargo/comité inactivo e inconsistencias; permisos heredados no amplían ámbito; aprobación exige habilitación y segunda persona |
| Territorio | Concepto general nunca cobrable por responsable; concepto ajeno y ciudadano trasladado denegados; filtro/URL/POST/CSV/HTMX/recibo no amplían alcance; total oficial cerrado no se cambia para adaptarlo al padrón actual |
| Caja | Cobro coincide con obligación/caja/medio; transferencia pendiente vs verificada; apertura documentada; salidas y entrega con evidencia; caja inactiva no recibe; clave idempotente devuelve un movimiento y recibo |
| Corte | Borrador/en revisión/confirmado; campos completos; conteo/esperado/diferencia exactos; revisión rechazada no pierde evidencia; no se autoprepara/confirma; diferencia según política; manif. fuente y totales coinciden |
| Inmutabilidad | Editar/eliminar Abono, Obligacion, Concepto, Movimiento o caja con fuente cerrada se bloquea en vistas, servicio, Admin y DB; impresión y snapshot sobreviven a renombres o revocaciones según acceso |
| Concurrencia PostgreSQL | Dos cobros simultáneos; dos confirmaciones; inclusión doble; rangos solapados; abono durante envío/confirmación; reintento tras timeout; orden de bloqueo y reversión completa ante fallo de bitácora |
| Reporte | Mismo snapshot/filtros/alcance/metodología para tarjetas, tabla, gráfica, CSV y PDF; ningún dato individual en transparencia; grupos pequeños y ataques por diferencia; compartir exige autenticación y revocación vigente |
| Migraciones | Grafo real, legado con NULL y vínculos preexistentes; tabla nueva sin importación ficticia; historial financiero conservado; ninguna dependencia/configuración de Santa Mónica |
| UX/accesibilidad | Seis pantallas escritorio y móvil, teclado, etiquetas, focus, errores útiles; gráfica con tabla; impresión sin menús, sin depender de colores; fallback sin Chart.js |
| Rendimiento | Datos sintéticos de 2,000 ciudadanos con varios años de movimientos; EXPLAIN de agregados, conteo de queries, paginación y carga de cierres; volumen de Abonos como variable principal |

Pruebas de caja y cierre deben ejecutarse en bases temporales PostgreSQL y SQLite cuando corresponda; nunca producción. Ninguna prueba financiera se aprueba por ser un mero espejo del código ni por no encontrar tests.

## Referencias UX e implicaciones para Dahiedhi

Consultadas el 23 noviembre de 2026. Las decisiones locales son propuestas de esta investigación; las fuentes son patrones de producto/control, no reglas jurídicas aplicables automáticamente a la comunidad.

| Fuente primaria | Elemento observado | Adaptación concreta |
|---|---|---|
| [YNAB Reports and Data](https://www.ynab.com/blog/ynab-reports-and-data) | Filtros por periodo/categoría, distribución y acceso al detalle | Dona de ingresos por origen con tabla; selección conduce al concepto. No copiar categorías de gasto personal ni patrimonio |
| [Actual Budget Reports](https://actualbudget.org/docs/reports/) | Dashboard de informes con filtros y rangos | Tarjetas simples y tendencia mensual. Mantener organización institucional existente, sin constructor de dashboards para el MVP |
| [Actual Reconciliation](https://actualbudget.org/docs/accounts/reconciliation/) | Comparar saldo registrado con evidencia y mostrar diferencia antes de bloquear movimientos | Corte guiado: esperado/conteo/diferencia y revisión explícita. Para Dahiedhi, cierres confirmados no se desbloquean mediante edición ordinaria |
| [Odoo Point of Sale, fuente oficial 17.0](https://github.com/odoo/documentation/blob/17.0/content/applications/sales/point_of_sale.rst) | Referencia de apertura/cierre de sesión, conteo y entradas/salidas | Separar medio de pago del efectivo físico; acta de apertura y conteo. No trasladar inventario, facturación o toda la contabilidad de Odoo |
| [National Council of Nonprofits Internal Controls](https://www.councilofnonprofits.org/running-nonprofit/administration-and-financial-management/internal-controls-nonprofits) | Responsabilidades escritas y separación de tareas | Persona revisora distinta, evidencia y política de diferencias; administración técnica no equivale a aprobación financiera |
| [Nonprofit Association of Washington](https://nonprofitwa.org/topics/accounting-procedures-and-policies/) | Procedimientos, revisión independiente e informes a la organización | Informe de transparencia con periodo/alcance/metodología, detalles privados por separado; roles y excepciones explícitos |
| [Django 5.2 aggregation](https://docs.djangoproject.com/en/5.2/topics/db/aggregation/) | Agregados y advertencias sobre combinar relaciones | Selectores reutilizables y agregaciones sin multiplicación por joins; validar con fixtures conocidos |
| [Chart.js accessibility](https://www.chartjs.org/docs/latest/general/accessibility.html) | El canvas necesita alternativas accesibles | Tabla equivalente, nombres accesibles, contrastes y fallback si no carga gráfica |

YNAB y Actual no establecen nuestras reglas sobre deuda comunitaria. Odoo es referencia de flujo de caja, no dependencia de software. Las páginas generales de Odoo no respondieron a la consulta; el patrón se contrastó con el archivo fuente oficial de su documentación 17.0 y se limita a apertura/conteo/entradas-salidas. No se afirma haber inspeccionado una aplicación Django externa desplegada: la referencia Django concreta son sus primitivas oficiales y el dashboard real de Pueblo Digital ya revisado.

## Diseño de las seis pantallas

- **A Resumen:** recaudación del periodo, cartera actual de cohorte, cumplimiento separado, distribución por origen y evolución mensual; efectivo/disponibilidad “no capturados” hasta adoptar caja. Último corte confirmado y diferencias de revisión visibles.
- **B Conceptos y adeudos:** lista de conceptos con naturaleza/origen/comité/territorio y asignado/abonado/saldo; búsqueda/filtro autorizados; detalles y canceladas explícitos.
- **C Detalle:** conservar expediente financiero existente, añadir origen/evento/metodología/calidad y acceso a movimientos. Información individual solo para operador autorizado; no exportarla como transparencia.
- **D Corte:** seleccionar caja/periodo; revisar fuentes y medios; apertura/entradas/salidas; conteo y diferencia; explicación y envío; revisor distinto confirma. No totales financieros editables.
- **E Historial:** folio/periodo/caja/responsables/totales/estado/diferencia, acceso al snapshot; no sumas mezcladas de cortes de distinto periodo ni botón de borrar confirmado.
- **F Transparencia:** solo agregados, metodología, periodo de cobros y estado actual de cohorte claramente separados; referencia verificable, versión imprimible y CSV; enlaces privados.

En escritorio: menú lateral, filtros y tarjetas compactas, gráficos con tablas al lado. En móvil: navegación superior que se acomoda, tarjetas apiladas, renglones legibles y controles táctiles. La tabla compleja puede desplazarse dentro de su región, sin hacer desbordar todo el documento. Impresión excluye navegación y controles; incluye alcance, metodología y referencia. No usar dona con demasiadas categorías: cuatro orígenes caben; para muchos conceptos/comités usar barras y tabla.
