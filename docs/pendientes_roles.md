# Pendientes de roles y alcance — Dahiedhi

## Decisiones para la siguiente iteración

1. **Comité al crear faenas o juntas por manzana.** El formulario actual pide un comité responsable. El responsable de manzana puede elegir entre los comités activos; confirmar si esta selección libre es correcta o si debe limitarse a un comité específico.
2. **Rol operativo de comité.** Se acordó que sea un rol distinto de tesorero y de los cargos históricos. Aún no está agregado a `UsuarioApp.Roles` ni recibe permisos de operación. Definir el nombre visible/código y confirmar que podrá gestionar eventos generales y todos sus participantes dentro de su comité.
3. **Persistencia/migración de roles.** El alcance aplicado no requiere cambios de esquema. No generar una migración para el nuevo rol hasta estabilizar el conjunto de migraciones regeneradas localmente.

## Estado implementado

- El responsable de manzana se deriva de `PerfilAcceso.user -> PerfilAcceso.ciudadano -> Ciudadano.manzana`, validando además `Manzana.responsable == Ciudadano`.
- La responsabilidad está activa mientras la cuenta, el ciudadano y la manzana estén activos; no hay fechas de vigencia.
- `Ciudadano.objects.visibles_para(usuario)` aplica el alcance al padrón, métricas, selector de manzanas, expediente y CSV.
- Los QuerySets de `Faena`, `Junta`, `RegistroFaena` y `AsistenciaJunta` derivan el alcance de la misma responsabilidad. En eventos generales se limita cada lista, métrica, captura y exportación a participantes de la manzana.
- Un responsable puede crear y editar eventos de alcance manzana para su manzana y actualizar el estado de esos eventos. En un evento general puede operar los registros de sus ciudadanos, pero no editar ni cambiar el estado del evento.
- Los roles actuales de `UsuarioApp`, incluido tesorero, no habilitan por sí mismos acceso a operación.

## Fuera de este corte

- Permisos del nuevo rol operativo de comité y filtros por comité para tesorería.
- Vigencias con fechas, historial de cambios de manzana y acceso histórico a participantes que cambien de manzana.
- Auditoría de quién creó/actualizó eventos y registros.
