from .autorizacion import tiene_acceso_financiero


def acceso_financiero(request):
    return {"puede_operar_finanzas": tiene_acceso_financiero(request.user)}
