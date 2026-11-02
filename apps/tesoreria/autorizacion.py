"""Financial access is inherited by role within each active committee."""

from functools import wraps

from django.http import Http404

from apps.comites.models import Comite, UsuarioApp


def comites_financieros(usuario):
    if not getattr(usuario, "is_authenticated", False) or not getattr(usuario, "is_active", False):
        return Comite.objects.none()
    if usuario.is_superuser:
        return Comite.objects.all()
    return Comite.objects.filter(
        activo=True, usuarios__user_id=usuario.pk, usuarios__activo=True,
        usuarios__rol__in=[UsuarioApp.Roles.PRESIDENTE, UsuarioApp.Roles.TESORERO],
    ).distinct()


def tiene_acceso_financiero(usuario):
    if not getattr(usuario, "is_authenticated", False) or not getattr(usuario, "is_active", False):
        return False
    return usuario.is_superuser or comites_financieros(usuario).exists()


def limitar_finanzas(queryset, usuario, campo_comite="comite_id"):
    """Scope before filters, aggregates, pagination and object lookup.

    Standard Django model permissions never grant a committee assignment.
    Only an active superuser has global access, including inactive committees.
    """
    if getattr(usuario, "is_authenticated", False) and getattr(usuario, "is_active", False) and usuario.is_superuser:
        return queryset
    return queryset.filter(**{f"{campo_comite}__in": comites_financieros(usuario).values("pk")})


def acceso_financiero_requerido(vista):
    @wraps(vista)
    def protegida(request, *args, **kwargs):
        if not tiene_acceso_financiero(request.user):
            raise Http404
        return vista(request, *args, **kwargs)
    return protegida
