# Plan inicial de roles y alcance — Dahiedhi

**Estado:** propuesta revisada con el cliente; no se ha cambiado código.
**Base:** [`auditoria_acceso.md`](auditoria_acceso.md) y los primeros casos de uso confirmados.

## Confirmado

- El primer alcance funcional será para **responsable de manzana** y **tesorero**. Los cargos de presidente, secretario, delegado, capturista y lectura quedan sin permisos nuevos por ahora.
- El responsable de manzana es un `Ciudadano` guardado en `Manzana.responsable`, tendrá cuenta asociada y podrá capturar asistencias, crear/editar faenas y juntas, generar registros y cambiar estados.
- El tesorero tendrá acceso a tesorería de su comité para las operaciones que se terminen de definir.
- Los datos del cliente ya existen. No se deben reinterpretar ni modificar en bloque sin acordar una migración revisable.

## Aclaración del vínculo cuenta-ciudadano

En el modelo actual `UsuarioApp.ciudadano` es una FK **opcional**. Una fila de `UsuarioApp` además requiere `comite` y `rol`, por lo que puede asociar al tesorero con su ciudadano, pero no ofrece un vínculo general para el responsable de manzana que no tenga cargo de comité. No quise decir que el campo no pueda guardar el vínculo: puede hacerlo dentro de una asignación de comité; la duda es si esa asignación existe para cada responsable y si debe ser la fuente general de identidad.

### Estructura recomendada para evaluar

Mantener separados estos tres hechos:

| Hecho | Fuente de verdad propuesta |
|---|---|
| Cuenta autenticada ↔ ciudadano | Perfil general de acceso, con vínculo obligatorio para las cuentas operativas que actúen como ciudadano. Puede ser un modelo pequeño `PerfilAcceso` o una adaptación no ambigua del existente. |
| Responsable de manzana | `Manzana.responsable`; no duplicar la manzana en el perfil. El alcance se deriva comparando el ciudadano del perfil con responsables de manzana. |
| Cargo dentro de comité | `UsuarioApp` (`user`, `comite`, `rol`, `activo`); inicialmente se aplica solo al tesorero. |

**Recomendación provisional:** preservar las filas actuales de `UsuarioApp` y agregar un vínculo general cuenta-ciudadano si la inspección del esquema/migraciones confirma que es necesario. No añadir todavía `manzana` a `UsuarioApp`, porque `Manzana.responsable` ya asigna ese territorio. Mantener la relación existente como fuente evita datos duplicados y migraciones que reescriban cargos activos.

## Matriz funcional mínima

| Actor | Datos visibles | Acciones aprobadas por el cliente | Restricción que falta cerrar |
|---|---|---|---|
| Responsable de manzana | Operación relacionada con su(s) manzana(s) | Asistencias; crear/editar faenas y juntas; generar registros; cambiar estados | Comité de esos eventos; eventos generales; si “estados” incluye eventos, registros de participantes o ambos. |
| Tesorero | Tesorería de los comités en que tiene cargo activo | “Todas las operaciones” de tesorería | Confirmar si incluye ver/crear/editar concepto, generar obligaciones, registrar abonos y cancelar/revertir. Recomiendo no permitir borrado físico financiero. |

Aunque la operación de juntas/faenas ya tenga alcance `GENERAL` o `MANZANA`, eso describe el evento; no autoriza por sí mismo a un usuario. La autorización debe comprobarse aparte en listado, detalle por ID, formulario, POST, exportación y admin.

## Alternativas para el vínculo de acceso

| Alternativa | Ventaja | Riesgo/costo | Recomendación |
|---|---|---|---|
| 1. `PerfilAcceso` general: usuario uno-a-uno con ciudadano; `UsuarioApp` sigue como asignación comité/rol | Identidad y cargo tienen responsabilidades claras; responsable puede operar sin cargo ficticio de comité | Añade una tabla y requiere decidir cómo completar vínculos existentes | Preferida si las cuentas operativas siempre corresponden a una persona del padrón. |
| 2. Usar `UsuarioApp.ciudadano` como único enlace | Menor cambio inicial | No cubre con claridad cuentas sin cargo de comité; vínculo opcional puede divergir entre filas | Solo viable si se confirma que todos los responsables también tendrán `UsuarioApp` y el enlace ciudadano será consistente en todos sus cargos. |
| 3. Convertir `UsuarioApp` en perfil universal y mover cargos a otra entidad | Dominio más normalizado si identidad y asignaciones crecen | Mayor migración; hay que preservar perfiles existentes y administrar dos tipos de registros | Considerarla si aparecen más responsabilidades independientes de comités/manzanas. No es necesaria para el primer corte. |

## Capa reutilizable propuesta

No crear un motor genérico de permisos administrable todavía. Empezar con un servicio/política del dominio central que reciba usuario, acción y objeto, y que resuelva las fuentes existentes:

1. Identidad: usuario autenticado → perfil → ciudadano.
2. Rol territorial: ciudadano responsable → manzana(s) asignada(s).
3. Rol de comité: `UsuarioApp` activo → comité + tesorero.
4. Acción: consulta/captura/crear/editar/generar/cambiar estado/exportar, con permiso explícito por tipo de actor.
5. Aplicación uniforme: `QuerySet` visible, formulario con relaciones permitidas, validación de guardado y detalle por PK consultado dentro del queryset autorizado (404 fuera de alcance).

La política falla cerrada cuando falta vínculo o asignación. El superusuario conserva un bypass explícito. Los filtros GET y los botones ocultos nunca sustituyen el filtro de servidor. La función de `apps/operacion/alcance.py` puede seguir validando la coherencia evento/manzana, pero no debe convertirse en autorización de usuario.

## Orden ágil de trabajo

1. **Cerrar las decisiones abajo** y revisar migraciones/modelos de la rama sin consultar datos productivos.
2. **Diseñar vínculo cuenta-ciudadano** preservando registros actuales; pruebas sintéticas primero. Si hace falta migración, commit propio solo de migración.
3. **Construir resolución reutilizable** de ciudadano, responsables de manzana y roles de tesorero; pruebas de activo/inactivo y falta de vínculo.
4. **Poner permisos a consultas** de `Faena`, `Junta`, `RegistroFaena` y `AsistenciaJunta`; separar lectura de captura, creación, edición y estado.
5. **Aplicar el primer recorrido de operación** y verificar acceso por URL/ID, formulario, POST y cualquier exportación existente.
6. **Aplicar tesorería por comité**: primero lectura filtrada, luego acciones acordadas para conceptos, obligaciones y abonos. No habilitar todas las acciones solo porque el usuario tenga rol tesorero hasta cerrar su significado.
7. **Revisar admin** como ruta de acceso independiente; no confiar en las pantallas operativas para proteger los mismos modelos.

Cada paso va en un commit pequeño; pruebas sintéticas antes del código; migraciones separadas de la lógica. No usar datos del cliente para pruebas ni tocar producción. Si aparece trabajo ajeno a estos dos casos de uso, se registra como pendiente.

## Decisiones necesarias para implementar el primer corte

Responde con el número y la opción; puedo recomendar, pero no asumir estas reglas:

1. **Cuenta-ciudadano:** (A) crear perfil general uno-a-uno; (B) confirmar que todo responsable tendrá también una fila `UsuarioApp` y usar su FK ciudadano. Recomiendo A.
2. **Comité en eventos:** (A) responsable opera faenas/juntas de cualquier comité en su manzana; (B) solo de un comité asignado; (C) solo si también tiene rol activo en ese comité.
3. **Eventos generales:** (A) puede operar solo los participantes de su manzana en eventos `GENERAL`; (B) evento general queda reservado a roles de comité.
4. **Qué estados cambia:** (A) estado de Faena/Junta; (B) estatus de asistencia/registro; (C) ambos, con permisos diferenciados.
5. **Tesorería del tesorero:** confirmar si incluye ver, crear/editar conceptos, generar obligaciones y registrar abonos. Para cancelaciones/reversiones: (A) tesorero puede con motivo; (B) requiere otra persona; (C) no se habilitan inicialmente. Recomiendo no habilitar borrado físico.
6. **Ciudadano responsable de varias manzanas:** (A) permitido, la cuenta hereda todas; (B) prohibido, validar una sola.
