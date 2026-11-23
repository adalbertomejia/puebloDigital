# Recorrido de revisión del prototipo

## Abrir y recorrer

Descargar [prototipo.html](prototipo.html) y abrirlo en un navegador moderno. Es un archivo autocontenido; no requiere Django, datos reales, dependencias externas ni permisos de producción. Si el navegador bloquea archivos locales, servir únicamente esta carpeta con un servidor estático local y abrir el archivo por localhost.

1. En **A**, comenzar con Secretaría y observar $14,000 recibidos, $20,000 asignados y $6,000 pendientes. Revisar 70% monetario frente a 65% de obligaciones pagadas. Seleccionar Última semana: recaudación cambia a $2,800, la cartera actual no cambia.
2. Cambiar “Calidad del ejemplo” a importe desconocido. El dinero recibido se etiqueta como subtotal conocido y el saldo monetario pasa a indeterminado, no a cero.
3. En **B**, filtrar y abrir conceptos. En **C**, revisar naturaleza, origen, comité, territorio y evento asociado; los renglones individuales son una muestra ficticia, no el total del concepto.
4. Seleccionar Responsable de Manzana Centro. Solo quedan Junta Centro y Cooperación de salud; ni Agua general ni Faena general. La caja principal de Delegación no se abre como si fuera de su territorio.
5. Para **D**, seleccionar Tesorero A. El ejemplo tiene esperado $3,500 y contado $3,400: faltan $100. Enviar exige explicación y evidencia. Después del envío no puede autoaprobarse.
6. Seleccionar Presidente B. El faltante impide confirmar en esta propuesta conservadora. Devolver a borrador para revisar; volver a Tesorero A y simular un nuevo conteo de $3,500 con evidencia; enviar otra vez. Regresar a Presidente B y confirmar.
7. En **E**, consultar la copia cerrada. Los filtros de recaudación no cambian su importe. El documento de octubre y el de noviembre son conjuntos separados; no sumarlos como un mismo periodo. La rectificación no se simula como edición del original.
8. Seleccionar Solo lectura: puede consultar el cierre confirmado pero no preparar, revisar ni confirmar.
9. En **F**, imprimir o guardar PDF y exportar CSV. Solo hay información agregada, alcance y metodología; no contratos ni deudas personales. Copiar enlace copia una referencia de demostración, no publica ni concede permisos reales.
10. Usar el botón Móvil o reducir ancho. Las tarjetas se apilan; las tablas extensas tienen desplazamiento horizontal dentro de una región señalada. Navegar con teclado; los controles principales tienen foco visible.

Los perfiles son parte del prototipo y no crean cuentas. La autorización real en servidor es una prueba pendiente de implementación. Recargar reinicia las simulaciones; no hay persistencia en una base de datos.

## Capturas para comparar escritorio y móvil

| Pantalla | Escritorio | Móvil |
|---|---|---|
| A Resumen financiero | [Ver](capturas/a-escritorio.png) | [Ver](capturas/a-movil.png) |
| B Conceptos y adeudos | [Ver](capturas/b-escritorio.png) | [Ver](capturas/b-movil.png) |
| C Detalle de concepto | [Ver](capturas/c-escritorio.png) | [Ver](capturas/c-movil.png) |
| D Preparación de corte | [Ver](capturas/d-escritorio.png) | [Ver](capturas/d-movil.png) |
| E Historial de cortes | [Ver](capturas/e-escritorio.png) | [Ver](capturas/e-movil.png) |
| F Transparencia | [Ver](capturas/f-escritorio.png) | [Ver](capturas/f-movil.png) |

Ejemplos exportados desde el prototipo: [informe PDF ficticio](ejemplos/informe-ficticio.pdf) y [CSV agregado ficticio](ejemplos/informe-ficticio.csv). Son muestras de diseño, no recibos ni informes oficiales de Dahiedhi.

## Comprobación ejecutada

Se ejecutó Playwright con Chromium sobre un servidor **estático** en localhost, sin arrancar Django. La primera navegación por file:// fue bloqueada por la política del navegador; se utilizó HTTP local para probar el mismo archivo. No se conectó ninguna base de datos y no se ejecutaron migraciones.

Resultado final: **13 grupos de comprobación aprobados, cero errores JavaScript**. Evidencia legible en [validacion-prototipo.json](validacion-prototipo.json):

- Cifras iniciales de muestra y coherencia de filtros.
- Seis pantallas a 1440, 390 y 320 píxeles sin desbordamiento horizontal de todo el documento.
- Importe desconocido distinto de cero.
- Simulación territorial sin conceptos/caja generales.
- Explicación/evidencia de faltante y bloqueo de autoaprobación.
- Confirmación por segundo perfil con diferencia cero y copia cerrada estable frente a filtros.
- Solo lectura sin acciones de cierre.
- CSV agregado con alcance/metodología y sin identificadores individuales.
- Impresión con navegación oculta y generación de PDF de muestra.
- Ausencia de errores JavaScript.

Se revisaron capturas del resumen, detalle, conciliación, historial y transparencia. Esto valida el prototipo, no los servicios financieros futuros, una aplicación móvil nativa, la autorización real ni concurrencia PostgreSQL. La suite Django de la etapa anterior no se volvió a ejecutar: hacerlo habría creado esquemas de prueba, fuera de la restricción de esta investigación.

Comandos de investigación/validación ejecutados:

```bash
git ls-remote origin refs/heads/codex/dahiedhi-ciclo-ciudadano refs/heads/codex/dahiedhi-consolidacion-operativa
git switch -c codex/dahiedhi-diseno-balances-cortes
.venv/bin/python -m http.server 8766 --bind 127.0.0.1 --directory docs/dahiedhi-finanzas-diseno
.venv/bin/python /workspace/work/diseno-finanzas/validar_prototipo.py
git diff --check
```

El script auxiliar de inspección es temporal; los resultados, capturas y ejemplos exportados están incluidos en esta entrega. No se ejecutaron `manage.py migrate`, `makemigrations`, SQL sobre instancias ni cambios de permisos para habilitar la demostración.

## Preguntas recomendadas para revisar primero

1. ¿Aprueban terminar el MVP con ingresos/adeudos y cortes, dejando egresos completos para una ampliación?
2. ¿Quién recibe y conserva efectivo en cada comité o manzana, y cómo documenta sus entregas y salidas?
3. ¿Quién preparará y quién revisará los cortes? ¿Qué se debe hacer con una diferencia y con un cobro capturado tarde?
4. ¿Secretaría necesita solo agregados, consultar datos individuales, cobrar, preparar cortes o también revisarlos? Son concesiones separadas.

La propuesta está preparada para esa revisión. Los modelos y permisos siguen siendo candidatos hasta resolver las decisiones dependientes de cada fase.
