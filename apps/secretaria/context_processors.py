from .autorizacion import puede_entrar


def acceso(request):
    return {'acceso_secretaria': puede_entrar(request.user)}
