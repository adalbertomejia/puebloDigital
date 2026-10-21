# Propuesta de diseño — capa de autorización Dahiedhi

**Fase:** propuesta, sin cambios de código.  
**Base:** auditoría [`auditoria_acceso.md`](auditoria_acceso.md) de `dahiedhi_client`.  
**Decisión pendiente principal:** D2, alcance que concede cada rol.

## Recomendación

Recomiendo **Opción A: ampliar `UsuarioApp`**, porque hoy ese modelo ya representa una asignación de rol a un usuario dentro de un comité. Añadir el territorio y la vigencia a esa asignación cubre la brecha sin sumar una entidad paralela ni duplicar comité/rol/usuario.

La recomendación depende de una regla de integridad: cuando una asignación cubra el comité completo, debe quedar explícito en un campo de alcance, no inferirse por `manzana=NULL`. Por ejemplo:

- `alcance=COMITE`, `manzana=NULL`: acceso al comité completo.
- `alcance=MANZANA`, `manzana=<id>`: acceso únicamente a esa manzana del comité.
- Las combinaciones restantes se rechazan.

Así puede implementarse A de forma que admita ambas políticas D2. La decisión de cuál política asignar a los roles queda abierta. Si se elige “solo manzanas explícitas”, una asignación con alcance `COMITE` simplemente no se crea para esos roles; la representación sigue permitiendo que roles administrativos autorizados tengan acceso de comité si se decide más adelante.

## Lo que la auditoría implica para el diseño

1. La fila actual de `UsuarioApp` ya tiene usuario, comité y rol. Por tanto, es el candidato natural a ser una asignación de responsabilidad, no solo un perfil global.
2. No se puede confiar en las vistas/admin actuales para filtrar permisos; la futura lógica debe vivir en servicios/querysets reutilizables y aplicarse también a IDs directos, formularios, exportaciones y agregados.
3. `apps/operacion/alcance.py` contiene validaciones de territorio de eventos, no debe mezclarse con la política de quién puede operar esos eventos.
4. Dado que hoy `UsuarioApp.rol` no autoriza, migrar filas existentes como acceso amplio sin decisión sería una concesión de acceso nueva. Hay que escoger la migración y la semántica D2 antes de activar enforcement.
5. Esta propuesta trata roles como catálogo fijo actual (choices) para la primera base. Convertir permisos en datos administrables es una decisión de producto aparte y no es necesario para centralizar el alcance en esta fase.

## A vs. B

| Criterio | A. Ampliar `UsuarioApp` | B. Crear `Responsabilidad` aparte |
|---|---|---|
| Forma | Una fila representa usuario + comité + rol + territorio + vigencia. | `UsuarioApp` conserva usuario/comité/rol y otra fila representa manzana/vigencia; o se crea una nueva responsabilidad completa y se retira gradualmente el rol de `UsuarioApp`. |
| Ventaja principal | Menos joins, menos conceptos duplicados; corresponde al uso actual de una fila por rol y comité. | Separa claramente membresía/perfil de asignación territorial; más fácil si luego habrá muchos tipos de asignación o historial detallado. |
| Complejidad inicial | Baja a media. Hay que ajustar unicidad y validar alcance explícito. | Media a alta. Se debe definir la relación exacta entre modelos y evitar que el rol/comité queden duplicados o contradictorios. |
| Varias manzanas por el mismo rol | Varias filas `UsuarioApp` por manzana; hay que cambiar la unicidad actual. | Varias filas de `Responsabilidad` ligadas a la asignación o usuario. |
| Vigencias solapadas | Se pueden prohibir con validación por usuario/rol/comité/territorio; evitar solapes en SQL depende del motor y del diseño. | Igual; la entidad separada no resuelve automáticamente solapes. |
| Mantener asignación de comité y territorio coherentes | Todo está en una fila. | Si Responsabilidad referencia `UsuarioApp`, el comité/rol se heredan; si los repite, aumenta riesgo de inconsistencia. |
| Historial/auditoría | Conservar filas inactivas y fechas; guardar cambios como intervalos o bitácora si se requiere historial completo. | Naturalmente admite múltiples filas históricas, aunque igualmente conviene impedir edición destructiva o agregar bitácora. |
| Migrar la estructura actual | Directa; cada fila recibe alcance y vigencia inicial definidos por política. | Requiere crear relaciones nuevas y decidir si se copia cada `UsuarioApp` o se convierte en padre sin efecto autorizador. |
| Riesgo de implementación | Interpretar mal las filas actuales como permisos más amplios. Se reduce con `alcance` explícito y migración condicionada. | Mantener dos fuentes de verdad durante la transición (rol en UsuarioApp y rol en Responsabilidad). |
| Mejor si… | La responsabilidad es una asignación de rol a comité y opcionalmente territorio, que coincide con el dominio actual. | El usuario puede tener membresías independientes de sus responsabilidades, múltiples funciones temporales, delegaciones por actividad o historial/auditoría de asignaciones más sofisticado. |

**Conclusión:** A se ajusta mejor al estado observado y al objetivo mínimo. B aporta separación conceptual útil si se confirma que `UsuarioApp` también debe representar membresía/identidad comunitaria independientemente de los permisos, o si se anticipan asignaciones de varios dominios distintas del comité. No veo esa necesidad demostrada en la auditoría todavía.

## Diseño de A que conserva las dos alternativas D2

### Campos propuestos

Mantener los campos actuales de `UsuarioApp` y añadir:

| Campo | Propuesta | Motivo |
|---|---|---|
| `alcance` | choices explícitas `COMITE` y `MANZANA`; obligatorio, sin default que expanda acceso | Evita interpretar un nulo ambiguo como acceso total. |
| `manzana` | FK nullable a `core.Manzana`, `PROTECT` | Identifica el territorio cuando `alcance=MANZANA`. |
| `vigente_desde` | `DateField`, requerido | Hace explícito el inicio de la asignación. |
| `vigente_hasta` | `DateField` nullable | Nulo significa sin fecha final; fecha final inclusiva propuesta para la consulta diaria. |
| `activo` | Conservar; requerido | Revocación administrativa inmediata, independiente de fechas. |

Restricción de coherencia: `COMITE` exige `manzana IS NULL`; `MANZANA` exige `manzana IS NOT NULL`. `clean()` debe dar error útil y la base debe tener un `CheckConstraint` equivalente para proteger escrituras que no pasen por formularios.

Además, la manzana asignada debe estar dentro del catálogo Dahiedhi. Como `Manzana` no pertenece a un comité en el modelo actual, no hay relación que permita probar una pertenencia comité/manzana. No asumiré que existe. Decisión adicional solo si el negocio requiere que cada manzana pertenezca a un comité específico: habría que modelar esa relación o permitir manzanas compartidas; no lo agregaría en esta base sin confirmación.

### Unicidad

La regla existente `unique_together = (user, comite, rol)` ya no sirve, porque impediría asignar el mismo rol a más de una manzana. Propongo:

- Para alcance `COMITE`: unicidad de `(user, comite, rol)` donde `alcance=COMITE`.
- Para alcance `MANZANA`: unicidad de `(user, comite, rol, manzana)` donde `alcance=MANZANA`.
- Permitir que la misma persona tenga distintos roles en el mismo comité.
- Permitir responsabilidades históricas vencidas/inactivas. No imponer unicidad solo entre filas activas con fechas sin haber decidido cómo se manejarán renovaciones y solapamientos.
- Validar que `vigente_hasta >= vigente_desde`.

Las restricciones condicionales resuelven el problema de unicidad de nulos y dejan una asignación de comité y varias asignaciones territoriales representables. Falta acordar si se permite que una persona tenga simultáneamente `COMITE` y filas `MANZANA` para el mismo rol. Mi recomendación es prohibir esa redundancia mientras la asignación de comité esté vigente, pero implementarla requiere validación contra intervalos de fechas/activación; no la impondría como constraint simple si el ciclo de vida aún no se acuerda.

## D2: elige la regla de alcance

Las dos opciones son válidas con el campo `alcance` explícito:

| Opción | Lectura | Ventajas | Costos/riesgos |
|---|---|---|---|
| **D2-A: el rol cubre todo el comité** | Al crear un perfil se asigna `COMITE`; el rol puede actuar sobre todas las manzanas de ese comité. Las excepciones por territorio usarían `MANZANA` solo si se permiten roles restringidos. | Menos asignaciones administrativas; se parece a la relación actual `UsuarioApp.comite`. | Un error de asignación expone a toda la comunidad; contradice el principio de mínimo privilegio si incluye capturistas o responsables de manzana. |
| **D2-B: solo las manzanas explícitas** | El usuario requiere una fila por cada manzana. Sin filas no hay acceso a datos territoriales. `COMITE` se reserva a roles que se autoricen explícitamente como comunitarios. | Menor exposición y alcance visible/auditable; se adapta a responsables de manzana. | Más trabajo al asignar y mantener cobertura; hay que decidir cómo dar acceso legítimo a funciones globales (tesorero, secretario, delegado). |

**Recomendación de seguridad:** D2-B para roles operativos locales/captura y D2-A solo para roles que la comunidad declare explícitamente de nivel comité. Esto es una recomendación, no una decisión tomada. Si la regla debe ser uniforme para todos los roles, elige A o B y la tabla de roles se ajusta en consecuencia.

## Migración inicial de las filas actuales

La migración no debe interpretar silenciosamente `manzana=NULL` como permiso global. Las filas actuales no tienen territorio ni vigencia y hoy no se usan para autorizar; por eso no hay equivalencia automática segura.

| Política elegida | Transformación de datos sugerida | Efecto hasta configurar |
|---|---|---|
| D2-A: filas actuales conservan alcance de comité | Migración de datos asigna `alcance=COMITE`, `vigente_desde` a la fecha de despliegue o una fecha aprobada; `vigente_hasta=NULL`; conserva `activo`. | Activa acceso amplio inmediatamente cuando el código empiece a aplicar roles. Debe ser una decisión explícita y revisarse usuario por usuario antes de despliegue. |
| D2-B: solo manzanas explícitas | No inferir manzanas. Marcar asignaciones como no autorizadoras / inactivas hasta que administración asigne territorios. Alternativa: mantener un estado pendiente explícito durante rollout. | Cero acceso por responsabilidad hasta cargar manzanas; requiere plan de asignación previo para no interrumpir operación. |
| Política mixta por rol | Migración de datos con tabla rol→alcance aprobada; filas de roles comunitarios pasan a `COMITE`, locales quedan pendientes de manzanas. | Transición menos abrupta y de mínimo privilegio, pero depende de aprobar la matriz de roles. |

La migración de esquema puede añadir campos inicialmente opcionales, ejecutar la conversión aprobada y después aplicar `NOT NULL`/constraints. Dado que en esta tarea cada migración va en su propio commit sin lógica mezclada, se separaría: (1) pruebas que fallen sobre reglas de modelo; (2) migración de esquema sola; (3) migración de datos en commit aparte solo después de aprobar la política de backfill; (4) `clean()` y constraints en un paso posterior según el orden acordado. Antes de crear migraciones se revisará el grafo existente de `comites` y `core` y el backend configurado.

## Política central, independiente de A/B

La forma de consumo que propongo es:

1. `responsabilidades_activas(usuario, fecha=localdate())`: retorna asignaciones `activo=True`, `vigente_desde <= fecha` y (`vigente_hasta IS NULL` o `vigente_hasta >= fecha`). Superusuario se trata como bypass explícito en la política, no como fila inventada.
2. Resolver acciones con una función central (por ejemplo `puede(usuario, accion, objeto=None)`), que consulte rol, acción y alcance. Al inicio, roles y acciones pueden ser constantes Python revisadas en este repositorio; no introducir administración dinámica de permisos sin necesidad confirmada.
3. `QuerySet.visibles_para(usuario)` para cada agregado de datos que lo requiera. Debe fallar cerrado y filtrar por la unión de manzanas autorizadas más el comité completo cuando D2 lo permita.
4. Para detalle por PK, buscar dentro del QuerySet autorizado; fuera de alcance debe resultar 404 para no filtrar existencia.
5. Formularios usan querysets autorizados de comités, manzanas, ciudadanos y eventos. El guardado vuelve a comprobar relaciones y acción; la validación del formulario no es la única defensa.
6. Exportaciones, métricas, autocompletes, admin, HTMX y POST usan la misma política. Ocultar botones y filtrar el HTML no basta.

La fase mínima solicitada puede comenzar por lectura del padrón. Sin embargo, hasta restringir también admin, exportación CSV y acceso a perfil ciudadano desde esa vista, la lectura no estará cerrada de extremo a extremo. El corte acordado para el MVP debe explicitar si la exportación forma parte de esa primera vista (la tarea original pide verificarla, por lo que recomiendo incluirla).

## Decisiones punto por punto para una iteración rápida

Puedes responder con los códigos y modificar cualquier recomendación:

| ID | Decisión | Recomendación inicial | Elección requerida |
|---|---|---|---|
| A/B | Estructura | A, extender `UsuarioApp` | ¿A o B? |
| D2 | Alcance de roles | Mixto: local solo manzanas; comité solo para roles explícitos | ¿D2-A, D2-B o mixto? |
| D3 | Nulo territorial | Añadir `alcance` explícito; nulo sin alcance válido | ¿Confirmas? |
| D4 | Fechas | Vigencia inclusiva; `vigente_hasta=NULL` sin vencimiento | ¿Confirmas o prefieres intervalo con fin exclusivo? |
| D5 | Backfill | Mixto según una tabla rol→alcance aprobada; nunca inferir por nulo | ¿Mixto, todo comité, o reactivar solo tras reasignación? |
| D6 | Responsabilidad vencida | No autoriza aunque `activo=True`; conservar fila histórica | ¿Confirmas? |
| D7 | Múltiples manzanas | Una fila por manzana y rol; varias asignaciones permitidas | ¿Confirmas? |
| D8 | Superusuario | Bypass de alcance; dejar rastros en auditoría futura | ¿Confirmas para todas las acciones de negocio? |
| D9 | Primera entrega | Solo padrón de lectura, incluyendo ruta HTML, detalle enlazado y CSV; no incluir admin dentro del corte si sigue teniendo acceso de staff | ¿Qué nivel de cierre esperas para el primer vertical? |

## Flujo de trabajo propuesto para desarrollo ágil

- **Una tarjeta/decisión por interacción:** presento opciones, recomendación y efecto concreto; tú contestas con códigos (por ejemplo `A, D2 mixto, D4 inclusiva`).
- **Un cambio pequeño por commit:** primero la prueba que falla, después implementación; migración de esquema y migración de datos nunca se mezclan con lógica. Cada resumen indica commit, cambio, suite ejecutada y huecos.
- **Cortes verticales seguros:** esquema → cálculo de vigencia → filtro de ciudadanos → filtro de faenas/registros → 404 en detalle → primera vista real y su CSV. El admin/exportaciones relacionadas se revisan explícitamente para evitar rutas laterales.
- **Automatización/ayuda agentica:** puedo usar análisis en paralelo para revisar superficies distintas (vistas/admin, modelos/migraciones, pruebas) cuando entremos a implementación; consolidaré hallazgos antes de editar y mantendré cambios en commits pequeños. No se usarán datos reales ni se accederá a producción.
- **Punto de control:** al final de cada fase me detengo con decisiones pendientes claras. La implementación no empieza hasta que apruebes este diseño y se cierre, al menos, D2 y la política de migración.

## Fuera de alcance que debe registrarse si aparece

- Rediseñar pagos/cooperaciones antiguos, agregar egresos o cambiar el modelo de tomas.
- Rediseñar catálogo de manzanas o importar datos reales.
- Crear roles editables desde interfaz o un motor genérico de permisos no requerido por la primera matriz.
- Activar producción, modificar datos reales o aplicar migraciones en una base productiva.
