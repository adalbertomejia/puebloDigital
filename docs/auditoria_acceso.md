# Auditoría de acceso — Dahiedhi

> Documento histórico: describe el estado anterior a la implementación de autorización contextual. Para las decisiones vigentes y el alcance del segundo paso, consultar [Roles y alcance](pendientes_roles.md).

**Revisión de solo lectura:** rama `dahiedhi_client`, 20-10-2026. No se modificó código ni se ejecutaron pruebas.  
**Mapa de referencia:** [`mapa_dominio_autorizacion_dahiedhi.md`](mapa_dominio_autorizacion_dahiedhi.md). En el repositorio no existe `docs/mapa_dominio_autorizacion.md`; se leyó la versión con sufijo `dahiedhi`.

## Resumen del dominio revisado

- `core.Manzana` existe; `Ciudadano.manzana` es FK opcional.
- `Junta` y `Faena` pertenecen a un comité y expresan `GENERAL` o `MANZANA`; se valida la coherencia entre alcance y manzana. El servicio de generación limita participantes a ciudadanos activos y, para eventos por manzana, a esa manzana.
- Tesorería nueva sigue `ConceptoTesoreria` → `ObligacionCiudadano` → `Abono`. El concepto tiene comité y alcance; obligaciones tienen estado y abonos validan monto/saldo.
- `UsuarioApp` guarda usuario, comité, rol de opciones fijas, ciudadano opcional y `activo`; no tiene manzana ni fechas de vigencia.
- Los filtros por comité/manzana encontrados en las pantallas y exportaciones vienen de parámetros seleccionables. No están intersectados con `UsuarioApp` ni constituyen por sí solos controles de acceso.

## URLs y vistas operativas

Convención: `login_required` solo exige sesión. Las expresiones `has_perm` son permisos globales Django, no permisos condicionados por comité/manzana. “Filtro” describe la consulta actual; si dice “interfaz” es controlado por el parámetro del usuario y no limita el universo autorizado.

| URL / nombre | Vista / modelos que toca | Protección actual | Filtro comité/manzana actual |
|---|---|---|---|
| `/` `home` | Inicio; render estático | `login_required` | No aplica |
| `/login/`, `/logout/` | Login/logout Django | Login público; logout vía `LogoutView` | No aplica |
| `/dashboard/` `dashboard_operativo` | `Ciudadano`, `Toma`, `Faena`, `Junta`, `RegistroFaena`, `AsistenciaJunta`, `Pago` vía relaciones/métricas | `login_required` | Sin filtro de perfil; métricas/listas comunitarias |
| `/ciudadanos/` `padron_ciudadanos` | `Ciudadano`, `Manzana`, `Toma`, `RegistroFaena` | `login_required` | Manzana por parámetro GET (incluye “sin asignar”); no fuerza manzana asignada al usuario. Métricas paralelas globales |
| `/ciudadanos/exportar-csv/` `exportar_ciudadanos_csv` | `Ciudadano` y relaciones usadas en exportación | `login_required` | Reutiliza filtros GET del padrón; exportación global posible |
| `/ciudadanos/nuevo/` `crear_ciudadano_operativo` | Crea `Ciudadano` | `login_required` | Formulario acepta manzana disponible; no limita a territorio del usuario |
| `/ciudadanos/<pk>/editar/` `editar_ciudadano_operativo` | Lee/edita `Ciudadano` | `login_required`; objeto cargado por PK | Sin restricción territorial del usuario |
| `/dashboard/ciudadano/<pk>/` `perfil_ciudadano` | `Ciudadano`, `Toma`, obligaciones, abonos, asistencias/faenas y enlaces a pagos | `login_required`; objeto cargado por PK | Sin filtro de comité/manzana en objeto ni secciones relacionadas |
| `/agua/` `control_agua` | `Toma`, `Ciudadano` | `login_required` | Búsqueda/estado son filtros de interfaz; sin comité/manzana |
| `/control-asistencias/` `control_asistencias` | `Faena`, `Junta`, registros/asistencias, `Manzana` | `login_required` | Filtros GET de fecha, alcance y manzana; elegibles globales, no por perfil |
| `/operacion/faenas/nueva/` `crear_faena_operativa` | Crea `Faena` | `login_required` | Formulario ofrece comités y manzanas; sin límite por perfil |
| `/operacion/juntas/nueva/` `crear_junta_operativa` | Crea `Junta` | `login_required` | Formulario ofrece comités y manzanas; sin límite por perfil |
| `/operacion/faenas/<id>/editar/` `editar_faena_operativa` | Lee/edita `Faena` | `login_required`; carga por PK | Sin alcance aplicado al objeto; el formulario solo valida coherencia/actividad de manzana |
| `/operacion/juntas/<id>/editar/` `editar_junta_operativa` | Lee/edita `Junta` | `login_required`; carga por PK | Sin alcance aplicado al objeto; el formulario solo valida coherencia/actividad de manzana |
| `/operacion/faenas/<id>/eliminar/` `eliminar_faena_operativa` | Elimina `Faena` y cascada relacionada | `login_required` + `operacion.delete_faena` (salvo superusuario), confirmación POST | Permiso Django global; no comité/manzana |
| `/operacion/juntas/<id>/eliminar/` `eliminar_junta_operativa` | Elimina `Junta` y cascada relacionada | `login_required` + `operacion.delete_junta` (salvo superusuario), confirmación POST | Permiso Django global; no comité/manzana |
| `/dashboard/faena/<id>/generar-registros/` `generar_registros_faena` | Crea `RegistroFaena` para ciudadanos | `login_required`; requiere POST por comprobación manual (si no, redirige) | El servicio respeta territorio del evento al generar; no comprueba permiso/alcance del usuario sobre evento |
| `/dashboard/junta/<id>/generar-registros/` `generar_registros_junta` | Crea `AsistenciaJunta` | `login_required`; requiere POST por comprobación manual | El servicio respeta territorio del evento al generar; no comprueba permiso/alcance del usuario sobre evento |
| `/control-asistencias/faena/<id>/` `control_asistencias_faena_detalle` | `Faena`, `RegistroFaena` | `login_required`; evento por PK | Sin filtro por perfil |
| `/control-asistencias/junta/<id>/` `control_asistencias_junta_detalle` | `Junta`, `AsistenciaJunta` | `login_required`; evento por PK | Sin filtro por perfil |
| `/control-asistencias/faena/<id>/exportar-csv/` `exportar_participantes_faena_csv` | `Faena`, `RegistroFaena`, datos ciudadanos | `login_required`; evento por PK | Exporta registros completos del evento, sin filtro de perfil |
| `/control-asistencias/junta/<id>/exportar-csv/` `exportar_participantes_junta_csv` | `Junta`, `AsistenciaJunta`, datos ciudadanos | `login_required`; evento por PK | Exporta registros completos del evento, sin filtro de perfil |
| `/control-asistencias/faena/<id>/captura/` `captura_asistencia_faena` | Lee/actualiza `RegistroFaena` | `login_required`; evento por PK | Sin permiso de acción ni alcance de usuario; POST procesa registros del evento |
| `/control-asistencias/junta/<id>/captura/` `captura_asistencia_junta` | Lee/actualiza `AsistenciaJunta` | `login_required`; evento por PK | Sin permiso de acción ni alcance de usuario; POST procesa registros del evento |
| `/control-asistencias/faena/<id>/captura-presencial/` `captura_asistencia_secuencial_faena` | Lee/actualiza `RegistroFaena` | `login_required`; evento por PK | Igual que captura; sin alcance de usuario |
| `/control-asistencias/junta/<id>/captura-presencial/` `captura_asistencia_secuencial_junta` | Lee/actualiza `AsistenciaJunta` | `login_required`; evento por PK | Igual que captura; sin alcance de usuario |
| `/control-asistencias/<tipo>/<id>/estado/` `editar_estado_evento` | Actualiza estado de `Faena` o `Junta` | `login_required` | Sin permiso de cambio ni filtro de alcance al cargar por PK |
| `/tesoreria/` `tesoreria_operativa` | `ConceptoTesoreria`, obligaciones/abonos para métricas; comité/manzana para opciones | `login_required`; `has_perm` solo controla UI de modificar | Filtros GET de comité/manzana/periodo; se puede omitir para ver todo |
| `/tesoreria/exportar-csv/` `exportar_tesoreria_csv` | Conceptos y métricas de obligaciones/abonos | `login_required` | Reutiliza filtros GET, sin comprobar permiso de exportación ni alcance asignado |
| `/tesoreria/nuevo/` y `/tesoreria/conceptos/<pk>/editar/` `crear_concepto_tesoreria` | Crea/edita `ConceptoTesoreria` | `login_required` + `tesoreria.add_conceptotesoreria` o `change_conceptotesoreria` (o superusuario) | Permisos Django globales; el concepto puede apuntar a cualquier comité/manzana disponible |
| `/tesoreria/conceptos/<pk>/eliminar/` `eliminar_concepto_tesoreria` | Elimina concepto, obligaciones y abonos | `login_required` + `tesoreria.delete_conceptotesoreria` (o superusuario), confirmación POST | Permiso global; sin alcance comité/manzana |
| `/tesoreria/conceptos/<pk>/generar-obligaciones/` `generar_obligaciones_tesoreria` | Crea `ObligacionCiudadano` | `login_required` + `require_POST` + permiso add/change de concepto o superusuario | Genera según alcance del concepto, no según alcance del usuario |
| `/tesoreria/conceptos/<pk>/` `tesoreria_concepto_detalle` | Concepto, obligaciones, abonos | `login_required`; carga concepto por PK | No limita por permiso de lectura ni comité/manzana del usuario; filtros GET de obligaciones son presentación |
| `/tesoreria/conceptos/<pk>/exportar-csv/` `exportar_obligaciones_tesoreria_csv` | Obligaciones, abonos y datos personales ciudadanos | `login_required`; concepto por PK | Filtros GET sobre obligaciones; sin permiso/alcance de exportación |
| `/tesoreria/obligaciones/<pk>/acreditar/` `acreditar_obligacion` | Lee obligación; crea `Abono` | `login_required` + permiso add/change de concepto o superusuario | Permiso global; no valida comité/manzana asignado al usuario |
| `/tesoreria/aportaciones/` `resumen_aportaciones` | `Abono`, `ObligacionCiudadano`, `ConceptoTesoreria`, ciudadanos/manzanas/comités; agregados individuales | `login_required` | Filtros GET de comité/manzana y demás; omitibles y sin intersección con perfil |
| `/tesoreria/aportaciones/buscar/` `buscar_aportaciones` | `Abono` y datos asociados | `login_required` | Filtros GET de comité/manzana/periodo/concepto; solo búsqueda, no autorización |
| `/tesoreria/aportaciones/exportar-csv/` `exportar_aportaciones_csv` | Abonos, concepto, comité y datos personales de ciudadano | `login_required` | Filtros GET; puede descargar conjunto amplio sin permiso separado |

### Admin de Django

El admin se monta en `/admin/`. Django aplica autenticación de staff y permisos estándar por modelo (`view/add/change/delete` según el registro); esos permisos no incorporan comité, manzana ni `UsuarioApp.rol`. Los filtros declarados son filtros de interfaz. No se encontraron `get_queryset()` o `formfield_for_foreignkey()` basados en usuario que apliquen alcance organizativo.

| Sección / modelos registrados | Protección estándar | Filtrado/alcance observado |
|---|---|---|
| Core: `Manzana`, `Ciudadano` (+ inlines de `Toma`, `Pago`, `Cooperacion`, `RegistroFaena`) | Staff + permisos Django por modelo | `CiudadanoAdmin.get_queryset()` solo hace `select_related`; no restringe manzanas. Inline de historial es de solo lectura, salvo inline de toma. |
| Comités: `Comite`, `UsuarioApp` | Staff + permisos Django por modelo | No restringe por comités del usuario ni impide que quien tenga permiso administre perfiles/roles. |
| Agua: `Toma` | Staff + permisos Django por modelo | Filtro de estado únicamente; sin comité/manzana. |
| Operación: `Junta`, `Faena`, `RegistroFaena`, `AsistenciaJunta`, `Actividad` (+ archivos inline) | Staff + permisos Django por modelo | QuerySets de faena/junta anotan métricas, no restringen alcance. `autocomplete_fields` no limita objetos por usuario. Acciones de estado en faenas operan sobre el queryset seleccionado. |
| Tesorería: `ConceptoTesoreria`, `ObligacionCiudadano`, `Abono`, `Pago`, `Cooperacion` | Staff + permisos Django por modelo | Filtros de comité/manzana/estado son visuales. Autocomplete no filtra por responsabilidad. Inline de abonos no aplica política de comité/manzana. |

## Uso de `UsuarioApp.rol`

La búsqueda de referencias de aplicación encontró su definición en `apps/comites/models.py`, su registro/listado en `apps/comites/admin.py` y la representación `__str__`. No encontré lecturas de `perfil.rol`, comparaciones con `UsuarioApp.Roles`, ni consultas `user.perfiles_app` en vistas, servicios, formularios o administradores para autorizar acciones. En la práctica revisada, los roles son datos almacenados y visibles en admin, pero no gobiernan acceso.

Las acciones de tesorería consultan permisos Django convencionales (`tesoreria.add_conceptotesoreria`, `change_conceptotesoreria`, `delete_conceptotesoreria`); borrado de eventos consulta `operacion.delete_faena`/`delete_junta`. Son permisos por modelo globales, sin vínculo automático con los roles de `UsuarioApp`.

## Reutilización de `apps/operacion/alcance.py`

No sirve como filtro central de autorización en su estado actual. Sus funciones hacen tres cosas acotadas:

1. `validar_alcance_y_manzana`: valida la consistencia de los datos del evento.
2. `validar_cambio_territorial` / `validar_territorio_evento`: evita cambiar el territorio de una faena/junta cuando ya tiene participantes.
3. `manzanas_disponibles_para_instancia`: prepara opciones activas del formulario y conserva la manzana de un registro existente.

No recibe usuario, rol, comité ni fechas; no deriva responsabilidades vigentes; no filtra querysets de ciudadanos/eventos/registros; no valida permiso de lectura/escritura. Se pueden reutilizar sus invariantes de modelo y la selección de manzanas en formularios, pero la futura política de autorización debe ser una capa aparte que aplique filtros en QuerySets y validación de objetos/relaciones al guardar.

## Huecos ordenados por riesgo

1. **Crítico — sin aislamiento de datos.** Todas las vistas protegidas operativas verifican sesión, pero ninguna aplica comité/manzana del perfil a los QuerySets. El admin tampoco incorpora ese aislamiento. Un usuario con acceso puede omitir filtros o sustituir IDs.
2. **Crítico — exportaciones y reportes con datos personales/financieros.** CSV de padrón, obligaciones, aportaciones y participantes; páginas de resumen exponen métricas y datos que dependen de filtros GET globales. No hay permiso separado de exportación ni alcance obligatorio.
3. **Crítico — cambios de asistencia por ID.** Captura masiva/secuencial, generación de registros y cambio de estado operan sobre evento cargado por PK, sin permiso de acción contextual ni autorización sobre comité/manzana.
4. **Alto — operaciones financieras.** Crear/modificar/borrar/generar/acreditar usa permisos de modelo globales o solo sesión; detalle y exportación de obligaciones/abonos no exigen permiso de lectura específico. Capturista/validador no está representado.
5. **Alto — edición de padrón y agua.** Alta/edición de ciudadano, asignación de manzana y vista de tomas quedan disponibles a cualquier usuario autenticado en las vistas operativas; IDs directos de perfil no se acotan.
6. **Alto — formularios de comité/manzana.** Crear/editar eventos y conceptos ofrece catálogos de comité/manzana sin limitar opciones según identidad. La validación geográfica garantiza consistencia del registro, no autoridad del usuario.
7. **Medio — métricas de alcance comunitario.** Dashboard, controles de agua, asistencia y resúmenes financieros calculan totales globales. Un filtro visual no cubre métricas independientes del filtro.
8. **Medio — vigencia e historial de roles.** `UsuarioApp.activo` no tiene inicio/fin ni manzana; cambios de rol/pertenencia no son intervalos históricos consultables.

## Cierre de Fase 1

La conclusión de la brecha central queda confirmada: falta una capa común de autorización que relacione rol, comité, manzana y vigencia y la aplique tanto a QuerySets como a formularios, vistas de detalle, escrituras y exportaciones. `alcance.py` aporta validaciones territoriales reutilizables, pero no resuelve esa autorización. No se implementó diseño ni código de Fase 2/3 en esta auditoría.
