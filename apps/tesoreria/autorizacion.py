"""Separate financial consultation from writes within each active committee."""

from functools import wraps
from django.http import Http404
from apps.comites.models import Comite, UsuarioApp

ROLES_ESCRITURA = (UsuarioApp.Roles.PRESIDENTE, UsuarioApp.Roles.TESORERO)
ROLES_CONSULTA = (*ROLES_ESCRITURA, UsuarioApp.Roles.LECTURA)


def comites_financieros(usuario, *, escritura=False):
    if not getattr(usuario, "is_authenticated", False) or not getattr(
        usuario, "is_active", False
    ):
        return Comite.objects.none()
    if usuario.is_superuser:
        return Comite.objects.all()
    from apps.core.autorizacion import responsabilidades_activas

    roles = ROLES_ESCRITURA if escritura else ROLES_CONSULTA
    ids = [
        r.comite.pk
        for r in responsabilidades_activas(usuario)
        if r.tipo == "COMITE" and r.rol in roles
    ]
    return Comite.objects.filter(pk__in=ids)


def tiene_acceso_financiero(usuario):
    return comites_financieros(usuario).exists()


def puede_operar_finanzas(usuario, comite_id=None):
    comites = comites_financieros(usuario, escritura=True)
    return (comites.filter(pk=comite_id) if comite_id is not None else comites).exists()


def limitar_finanzas(queryset, usuario, campo_comite="comite_id", *, escritura=False):
    if (
        getattr(usuario, "is_authenticated", False)
        and getattr(usuario, "is_active", False)
        and usuario.is_superuser
    ):
        return queryset
    return queryset.filter(
        **{
            f"{campo_comite}__in": comites_financieros(
                usuario, escritura=escritura
            ).values("pk")
        }
    )


def acceso_financiero_requerido(vista):
    @wraps(vista)
    def protegida(request, *args, **kwargs):
        if not tiene_acceso_financiero(request.user):
            raise Http404
        return vista(request, *args, **kwargs)

    return protegida
