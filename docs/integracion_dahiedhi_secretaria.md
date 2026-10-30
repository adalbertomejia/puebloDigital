# Integración de Secretaría sobre la rama real de Dahiedhi

La rama `codex/secretaria-dahiedhi` parte de `275da7d` de `dahiedhi_client`, que incluye los commits locales de producción integrados previamente y las correcciones `be5d53f` (dependencias de migraciones) y `275da7d` (cierre de sesión por POST). Se incorporaron las correcciones de pruebas y Secretaría de `a246325` y `8fcc875`, resolviendo únicamente los conflictos de .gitignore y la representación del formulario de cierre de sesión.

No se reescribió ninguna migración histórica ni se sustituyeron los ajustes de entorno, base de datos o estáticos de Dahiedhi. Requirements conserva Django 5.2 y las dependencias de esa rama. La única migración nueva corresponde a Secretaría. Se adaptaron tres pruebas históricas para apuntar al grafo real de Dahiedhi: core.0002, comites.0003 y operacion.0004, sin omitir comprobaciones ni alterar datos de producción.

## Directorio local con modificaciones pendientes

El diagnóstico recibido mostraba migraciones modificadas/eliminadas, ajustes locales de configuración, cambios de .gitignore y eliminación del índice de archivos de .venv, además de respaldos sin rastrear. Esas modificaciones no están disponibles en el remoto ni se integraron a ciegas. No se debe descartar el directorio ni introducir respaldos en commits para resolver un pull.

Abrir una carpeta de trabajo independiente permite revisar el código conservando intactos archivos, índice, entorno y datos de la carpeta original:

```bash
git fetch origin
git worktree add -b prueba-secretaria ../puebloDigital-secretaria origin/codex/secretaria-dahiedhi
cd ../puebloDigital-secretaria
```

Si ya existe esa carpeta o nombre de rama, el comando debe detenerse: no borrar ni sobrescribir una copia existente. No hace falta ejecutar stash, reset o restaurar las migraciones de la carpeta original. Si el terminal está en el visor de git log, salir primero con q.

La copia nueva usa la configuración remota de Dahiedhi, que permite PostgreSQL mediante variables de entorno. No ejecutar migrate allí hasta revisar qué base selecciona y preparar una copia de SQLite con configuración local explícita si se desea probarla. No activar automáticamente el .venv rastreado de la nueva carpeta; utilizar un entorno virtual independiente. Los respaldos y el archivo original db.sqlite3 permanecen en la carpeta anterior. No se copian ni migran automáticamente.

## Verificación

Se creó un entorno virtual separado con requirements de Dahiedhi (Django 5.2.18 en la ejecución) y configuración de pruebas SQLite bajo /tmp. Las pruebas usan su base temporal, no una base elegida por variables de producción. Se verificó que no hay cambios de modelos pendientes y que ninguna migración histórica difiere de 275da7d.

La prueba en navegador documentada en la entrega original corresponde a su rama original. Esta integración se verifica con pruebas Django; no debe confundirse con una prueba contra el SQLite particular del usuario, cuyo esquema e historial todavía deben inspeccionarse antes de migrar una copia.

## Archivos heredados que requieren un trabajo separado

Esta rama de Dahiedhi ya tenía 12 archivos de .venv rastreados y `padron_importacion.xlsx` rastreado. No se leyó el padrón ni se incluyeron modificaciones a esos archivos. Tampoco se borraron del disco o del historial. La limpieza de archivos sensibles rastreados debe planearse aparte del despliegue de Secretaría.

Resultado final: **276 pruebas correctas en Django 5.2.18**, incluidas las 22 de Secretaría y las tres de migraciones históricas adaptadas al grafo real. `makemigrations --check --dry-run` no detecta cambios pendientes. Ninguna base del usuario ni configuración local se modificó durante esta verificación.
