from functools import wraps
from django.core.exceptions import ValidationError
from django.http import Http404
from apps.comites.models import Comite
from apps.tesoreria.autorizacion import comites_financieros


def comite_agua():
    comites = list(Comite.objects.filter(tipo=Comite.Tipos.AGUA, activo=True)[:2])
    if len(comites) != 1:
        raise ValidationError("Debe existir un único comité de Agua activo para operar las cuotas mensuales.")
    return comites[0]


def puede_operar_agua(usuario):
    if not getattr(usuario, "is_authenticated", False) or not getattr(usuario, "is_active", False):
        return False
    if usuario.is_superuser:
        return True
    try:
        comite = comite_agua()
    except ValidationError:
        return False
    return comites_financieros(usuario).filter(pk=comite.pk).exists()


def acceso_agua_requerido(vista):
    @wraps(vista)
    def protegida(request, *args, **kwargs):
        if not puede_operar_agua(request.user):
            raise Http404
        return vista(request, *args, **kwargs)
    return protegida
