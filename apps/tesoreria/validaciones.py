def validar_cambios_con_obligaciones(instancia):
    """Protect financial configuration once real obligations exist."""
    if not instancia.pk:
        return {}
    original = type(instancia).objects.filter(pk=instancia.pk).first()
    if not original or not original.obligaciones.exists():
        return {}
    campos = {
        "naturaleza": ("naturaleza", "la naturaleza"),
        "alcance": ("alcance", "el alcance"),
        "manzana": ("manzana_id", "la manzana"),
        "monto_individual": ("monto_individual", "el monto individual"),
    }
    errors = {}
    for campo_error, (atributo, etiqueta) in campos.items():
        if getattr(original, atributo) != getattr(instancia, atributo):
            errors[campo_error] = f"No puedes cambiar {etiqueta} porque este concepto ya tiene obligaciones generadas."
    return errors
