from .autorizacion import tiene_acceso_financiero, puede_operar_finanzas


def acceso_financiero(request):
    from apps.agua.autorizacion import puede_operar_agua
    return {"puede_operar_agua": puede_operar_agua(request.user), "puede_operar_finanzas": tiene_acceso_financiero(request.user), "puede_escribir_finanzas": puede_operar_finanzas(request.user)}
