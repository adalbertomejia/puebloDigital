def interfaz(request):
    nombre = getattr(getattr(request, "resolver_match", None), "url_name", "")
    return {"ui_vista_dinamica": nombre in {
        "padron_ciudadanos", "control_asistencias", "control_agua", "tesoreria_operativa",
        "tesoreria_concepto_detalle", "resumen_aportaciones", "buscar_aportaciones", "actividad_financiera",
        "perfil_ciudadano",
    }}
