"""Separate financial consultation from writes within each active committee."""

from functools import wraps
from django.http import Http404
from django.db.models import F
from apps.operacion.autorizacion import manzanas_responsables
from apps.comites.models import Comite, UsuarioApp

ROLES_ESCRITURA = (UsuarioApp.Roles.PRESIDENTE, UsuarioApp.Roles.TESORERO)
ROLES_CONSULTA = (*ROLES_ESCRITURA, UsuarioApp.Roles.LECTURA)


def comites_financieros(usuario, *, escritura=False, incluir_cargo_central=True):
    if not getattr(usuario, "is_authenticated", False) or not getattr(
        usuario, "is_active", False
    ):
        return Comite.objects.none()
    if usuario.is_superuser:
        return Comite.objects.all()
    from apps.core.autorizacion import responsabilidades_activas, es_secretaria_central
    responsabilidades = responsabilidades_activas(usuario)
    if incluir_cargo_central and any(r.operacion_comunitaria for r in responsabilidades):
        return Comite.objects.filter(activo=True)

    permiso = "operar_finanzas_centrales" if escritura else "consultar_finanzas_centrales"
    if es_secretaria_central(usuario) and (usuario.has_perm(f"core.{permiso}") or (not escritura and usuario.has_perm("core.operar_finanzas_centrales"))):
        return Comite.objects.filter(activo=True)

    roles = ROLES_ESCRITURA if escritura else ROLES_CONSULTA
    ids = [
        r.comite.pk
        for r in responsabilidades
        if r.tipo == "COMITE" and r.rol in roles
    ]
    return Comite.objects.filter(pk__in=ids)


def tiene_acceso_financiero(usuario, *, incluir_cargo_central=True):
    return bool(manzanas_responsables(usuario)) or comites_financieros(
        usuario, incluir_cargo_central=incluir_cargo_central,
    ).exists()


def puede_operar_finanzas(usuario, comite_id=None):
    if comite_id is None and manzanas_responsables(usuario):
        return True
    comites = comites_financieros(usuario, escritura=True)
    return (comites.filter(pk=comite_id) if comite_id is not None else comites).exists()


def limitar_finanzas(
    queryset, usuario, campo_comite="comite_id", *, escritura=False, incluir_cargo_central=True,
):
    if (
        getattr(usuario, "is_authenticated", False)
        and getattr(usuario, "is_active", False)
        and usuario.is_superuser
    ):
        return queryset
    manzanas = manzanas_responsables(usuario)
    if manzanas:
        modelo = queryset.model._meta.model_name
        if modelo == "conceptotesoreria":
            return queryset.filter(alcance="MANZANA", manzana_id__in=manzanas)
        if modelo in ("obligacionciudadano", "abono"):
            prefijo = "obligacion__" if modelo == "abono" else ""
            return queryset.filter(**{
                f"{prefijo}concepto__alcance": "MANZANA",
                f"{prefijo}concepto__manzana_id__in": manzanas,
                f"{prefijo}ciudadano__manzana_id": F(f"{prefijo}concepto__manzana_id"),
            })
        # Legacy payments and audit records lack sufficient citizen/territory
        # information to safely expose them to territorial operators.
        return queryset.none()
    return queryset.filter(
        **{
            f"{campo_comite}__in": comites_financieros(
                usuario, escritura=escritura, incluir_cargo_central=incluir_cargo_central,
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


def puede_abonar_obligacion(usuario, obligacion):
    from .models import ObligacionCiudadano
    return limitar_finanzas(
        ObligacionCiudadano.objects.filter(pk=obligacion.pk), usuario,
        "concepto__comite_id", escritura=True,
    ).exists()
