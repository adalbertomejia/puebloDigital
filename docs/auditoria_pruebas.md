# Cierre de las siete incidencias de pruebas

La revisión reprodujo cinco fallas y dos errores. Las siete incidencias correspondían a datos de prueba incompletos o expectativas anteriores al comportamiento vigente; no fue necesario cambiar reglas de la aplicación ni datos reales.

| Caso | Causa comprobada | Corrección |
| --- | --- | --- |
| Alta de ciudadano con manzana | El envío de prueba omitía sexo, obligatorio en el formulario. | Enviar explícitamente «No especificado», conservando las comprobaciones de manzanas activas y asignación opcional. |
| Edición de ciudadano con manzana histórica | El mismo envío incompleto impedía guardar y redirigir. | Completar el dato obligatorio y conservar la comprobación de cambio de manzana. |
| Eliminación de concepto con abonos | Se intentaba agregar un abono a una obligación marcada previamente como pagada. | Crear una obligación pendiente de 10 y liquidarla por el flujo de acreditación antes de probar la eliminación; se mantiene el total exacto de 20 y se comprueba el estado pagado. |
| Cuatro tarjetas del resumen | Se esperaba el título anterior «Movimientos recientes». | Comprobar el título vigente «Aportaciones recientes» y mantener las cuatro tarjetas, descripciones y enlaces. |
| Resumen sin movimientos | Se esperaba una etiqueta retirada, aunque las manzanas se conservan con sus totales en cero. | Comprobar los mensajes de las secciones vacías, territorios visibles y cantidades e importes en cero. |
| Contexto seguro de controles | Se esperaba reenviar el alias antiguo `limite_ciudadanos`. | Verificar su normalización a `ciudadanos_por_pagina`, con valor 5, y mantener la exclusión de parámetros desconocidos. |
| Búsqueda «Ana» | La búsqueda general también encuentra «ana» dentro de «manzana», en el concepto de otro abono autorizado. | Comprobar los identificadores exactos para cada consulta y un caso sin coincidencias. No restringir la búsqueda por nombre artificialmente. |

Se mantienen la validación que impide nuevos abonos sobre obligaciones pagadas, las comprobaciones de importes, el aislamiento de comités y los controles de parámetros permitidos. No se omiten ni desactivan pruebas.

Comando completo de referencia, con módulos explícitos porque `apps` es un paquete de espacio de nombres:

```bash
python manage.py test \
  apps.core.tests apps.core.test_manzanas apps.core.test_autorizacion \
  apps.core.test_padron_alcance apps.core.test_interfaz apps.comites.tests \
  apps.operacion.tests apps.operacion.test_alcance_autorizacion \
  apps.operacion.test_evento_motivo_comite apps.tesoreria.tests \
  apps.tesoreria.test_autorizacion apps.tesoreria.test_trazabilidad \
  apps.tesoreria.test_migraciones_financieras apps.tesoreria.test_recibos \
  apps.tesoreria.test_adeudos_asistencia apps.agua.tests --noinput
```

Esta comprobación usa la base temporal del ejecutor de pruebas de Django; no valida por sí sola el aspecto visual, la concurrencia real en otro motor ni los datos particulares de producción.

Resultado de la revisión del 29 de octubre de 2026: **254 pruebas ejecutadas, todas correctas**, sin pruebas omitidas. La reproducción inicial de los siete casos confirmó las cinco fallas y dos errores documentados; la ejecución completa posterior quedó en verde.
