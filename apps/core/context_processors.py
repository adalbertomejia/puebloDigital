def interfaz(request):
    nombre = getattr(getattr(request, "resolver_match", None), "url_name", "")
    from .autorizacion import permiso_global_de_modelo
    from apps.operacion.autorizacion import manzanas_responsables
    return {"puede_consultar_padron": permiso_global_de_modelo(request.user, "core.view_ciudadano") or bool(manzanas_responsables(request.user)), "ui_vista_dinamica": nombre in {
        "padron_ciudadanos", "control_asistencias", "control_agua", "tesoreria_operativa",
        "tesoreria_concepto_detalle", "resumen_aportaciones", "buscar_aportaciones", "actividad_financiera",
        "perfil_ciudadano",
    }}
