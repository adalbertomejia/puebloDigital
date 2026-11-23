# Métricas clasificación y ejemplos

## Universos autorizados y ejes temporales

Aplicar autorización antes de agregaciones, filtros, autocompletados, gráficas o CSV. `limitar_finanzas` es el punto de partida en la consolidación. Los totales de un responsable nunca se calculan globalmente para luego ocultar filas.

Hay tres preguntas diferentes:

1. **¿Cuánto se registró como recibido en el periodo?** Abonos autorizados por fecha de pago (`Abono.fecha`) o por fecha de captura (`created_at`), elegido y visible. La modalidad por defecto propuesta es fecha de pago.
2. **¿Cuánto queda por cobrar de una cohorte de conceptos?** Obligaciones autorizadas de conceptos seleccionados por su fecha o periodo de agua, con importes, estado y abonos actuales. Su etiqueta será “estado actual de la cohorte”, aunque el concepto sea de otro mes.
3. **¿Qué quedó confirmado en un corte?** Los movimientos y sus importes congelados en el manifiesto del corte, seleccionados por caja y periodo de captura; no por una consulta dinámica al padrón actual.

No dividir la recaudación de un mes entre obligaciones de otro universo. No anunciar un saldo histórico exacto antes de contar con snapshots o una historia completa de cambios. El esquema actual no conserva todas las fechas de cambio de montos y estados para reconstruir un “al día X”.

Fechas UI inclusivas se convierten en intervalos `[inicio, fin_exclusivo)`; los timestamps se interpretan en America/Mexico_City y se almacenan en UTC. Una fecha de pago es DateField, no debe reinterpretarse como timestamp UTC. Toda salida incluye filtros normalizados, base temporal, alcance, hora de generación y versión de metodología.

## Fórmulas propuestas

Sea `V` el conjunto autorizado de obligaciones vigentes (PENDIENTE o PAGADO) de la cohorte y `P` todos los abonos autorizados del intervalo de recaudación. Los campos monetarios se calculan en Decimal; transporte en cadenas decimales o centavos enteros. Solo se convierten a datos de gráfica después de obtener totales exactos.

| Indicador | Definición | Condiciones y presentación |
|---|---|---|
| Recaudación registrada | Σ monto de `P` | Incluye pagos de obligaciones luego canceladas si sus Abonos siguen registrados; no implica efectivo disponible ni ingreso bancario conciliado |
| Obligaciones vigentes asignadas | Σ monto_asignado de `V` | Cohorte y estado actual explícitos |
| Abonado aplicado a vigentes | Σ abonos de las obligaciones de `V` | Sin restringir al mes del cobro salvo que se solicite otra métrica claramente distinta |
| Saldo por obligación | max(asignado − abonado, 0) | Si asignado o algún abono es desconocido, su saldo es indeterminado; el exceso de una obligación no compensa otra |
| Saldo pendiente | Σ saldos por obligación de `V` | No `max(Σasignado−Σabonado,0)` ante datos inconsistentes |
| Cumplimiento monetario | 100 × Σ min(abonado, asignado) / Σ asignado, en el mismo `V` | Si no hay asignación: “No aplica”, no 100%. Si hay desconocidos: porcentaje indeterminado y cobertura conocida por separado |
| Cumplimiento por obligaciones | 100 × #PAGADO / #vigentes | Estados vigentes actuales; validar divergencias entre estado y saldo, mostrar incidencias |
| Obligaciones canceladas | Cantidad y monto asignado conocido de CANCELADO | Fuera de cartera vigente; no confundir cancelación con devolución de un cobro |
| Cobros ligados a canceladas | Σ abonos existentes sobre CANCELADO | Excepción separada y visible; jamás eliminar del historial monetario por omitir la obligación |
| Distribución por origen | Σ `P` agrupada por concepto.origen | Cada Abono aparece en un único grupo; adeudos pagados de faena/junta conservan origen |
| Distribución territorial | Σ `P` por alcance y manzana del concepto | GENERAL se etiqueta “Toda la comunidad”; no repartirlo entre manzanas por domicilio actual |
| Distribución por comité/concepto | Σ `P` por IDs del concepto | Nombres actuales en vivo; IDs/etiquetas congeladas en cierres |
| Evolución mensual | Σ `P` agrupada por mes del eje elegido | Mes sin movimientos es cero solo con cobertura completa; mes no observado o con desconocidos no se inventa |
| Efectivo esperado | Apertura confirmada + entradas efectivo − salidas efectivo | Requiere libro completo, medios y custodia. Transferencias recibidas no se suman al efectivo físico; APERTURA usada como saldo inicial no se suma nuevamente como entrada |
| Diferencia | Conteo físico − efectivo esperado | Negativo = faltante; positivo = sobrante; cero = cuadrado, sujeto a revisión |
| Flujo neto del periodo | Ingresos externos − egresos externos documentados | Solo opción B; excluir traslados entre cajas/cuentas propias |
| Disponibilidad | Saldo inicial verificado + flujos netos + traslados netos por unidad | No disponible hoy; no es balance general contable ni disponibilidad libre de compromisos |

Todos los indicadores deben devolver al menos valor conocido, número de registros desconocidos, cobertura y metodología. Cero significa “conjunto comprobado sin importe”; indeterminado significa “faltan datos”. Si hay un único Abono NULL, mostrar “$14,000.00 conocidos + 1 importe sin determinar”; no “Total $14,000.00”. No inferir medios de pago de notas o referencias.

## Taxonomía mínima

Reutilizar dimensiones independientes: naturaleza (Pago/Cooperación), origen (Tesorería/Faena/Junta/Agua), comité, concepto, alcance, manzana histórica del concepto, periodo y estado. “Parcial” es una etiqueta derivada de obligación PENDIENTE con abonos positivos y saldo; no un nuevo estado de persistencia. “Sin clasificar” es calidad de información, no un nuevo tipo de ingreso. Medio de cobro y caja son dimensiones futuras de custodia, no categorías que sustituyan al concepto.

Origen FAENA/JUNTA debe corresponder a un vínculo de evento compatible y exclusivo. Detectar y reportar contradicciones históricas antes de proponer una corrección autorizada. Una falta con importe cero, pendiente de captura o justificada no produce por sí sola una obligación monetaria.

## Ejemplo coherente de cartera ficticia

Todos los conceptos son de noviembre de 2026; todos los abonos del ejemplo son conocidos y corresponden al mismo periodo. Las canceladas se muestran fuera de las cifras vigentes.

| Concepto | Origen | Comité | Territorio | Vigentes | Pagadas | Pendientes | Asignado | Abonado | Saldo |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| Agua noviembre | Agua | Agua | General | 100 | 60 | 40 | 10,000 | 7,000 | 3,000 |
| Faena de limpieza | Faena | Delegación | General | 40 | 30 | 10 | 4,000 | 3,000 | 1,000 |
| Junta Centro | Junta | Delegación | Manzana Centro | 20 | 10 | 10 | 2,000 | 1,000 | 1,000 |
| Cooperación de salud | Tesorería | Salud | Manzana Centro | 40 | 30 | 10 | 4,000 | 3,000 | 1,000 |
| **Total** | | | | **200** | **130** | **70** | **20,000** | **14,000** | **6,000** |

En Agua: 60 obligaciones de $100 pagadas, 20 con $50 abonados y 20 sin abonos. Asignado $10,000; abonado $7,000; pendiente $3,000. Así se explica que 70% monetario y 65% por cantidad globales sean indicadores distintos.

Otros 10 registros cancelados de $100 (5 de faena, 5 de junta) suman $1,000 y no forman parte de los $20,000 vigentes. En este ejemplo no tienen abonos. El 70% monetario y el 65% por cantidad no incluyen las canceladas.

Distribución de recaudación: Agua 7,000 (50%); Faena 3,000 (21.43%); Junta 1,000 (7.14%); Tesorería 3,000 (21.43%). Por territorio: General 10,000, Centro 4,000. Por comité: Agua 7,000, Delegación 4,000, Salud 3,000. Las dimensiones no se suman entre sí: cada una descompone los mismos $14,000.

En el prototipo, el filtro “Última semana” limita la recaudación a una muestra de $2,800; el saldo de la cohorte actual permanece $6,000. Se muestran los dos universos con etiquetas distintas, sin recalcular falsamente el cumplimiento como 2,800/20,000.

## Ejemplo de corte propuesto ficticio

Caja Delegación principal, alcance comité Delegación, 1–23 noviembre. Movimientos atribuidos a esa caja y comité: $4,000, de los cuales $3,000 en efectivo y $1,000 en transferencias. Las otras cajas no forman parte de este corte.

| Dato | Valor ficticio |
|---|---:|
| Apertura documentada | 500.00 |
| Cobros efectivo | 3,000.00 |
| Otras entradas efectivo | 0.00, supuesto explícito de esta simulación |
| Salidas efectivo | 0.00, ausencia confirmada para la simulación, no dato del sistema actual |
| Efectivo esperado | 3,500.00 |
| Conteo físico | 3,400.00 |
| Diferencia | −100.00 |
| Transferencias informadas por separado | 1,000.00 |

No confirmar silenciosamente: registrar explicación y evidencia, enviar a revisor distinto. Cambiar el conteo a 3,500 cuadra la simulación, pero no sustituye un conteo real. La diferencia no se convierte en egreso ni se compensa modificando un Abono. No sumar apertura ni entrega de efectivo como ingreso recaudado.

## Ejemplo de transparencia

Informe ficticio `DAH-DEMO-202611-v1`: recaudación conocida $14,000; vigentes $20,000; saldo actual de cohorte $6,000; 130/200 pagadas; canceladas $1,000; desglose por origen/comité/territorio. Base de ingresos: fecha de pago en noviembre; base de cartera: estado actual de conceptos de noviembre; generación: 23 noviembre, America/Mexico_City. El corte de Delegación en revisión no se presenta como confirmado. Un corte confirmado de octubre es otro conjunto: apertura 500, cobros efectivo 2,600, transferencias 900, conteo 3,100, diferencia 0; no se suma a noviembre.

No incluir nombres de ciudadanos, contratos, tomas, obligaciones individuales ni notas de cobro. Celdas muy pequeñas podrían revelar identidades por inferencia: proponer agrupación/supresión aprobada (por ejemplo, menos de cinco ciudadanos) y cuidar que los subtotales permitan o no reconstruir valores. No aplicar un umbral como regla definitiva sin aprobación. El informe sigue siendo privado y requiere autorización en cada acceso.
