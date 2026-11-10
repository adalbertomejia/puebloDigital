"""Identity and exclusive active responsibility shared by committee and territory."""

from django.core.exceptions import ValidationError


def validar_cargo(cargo):
    from .models import PerfilAcceso, UsuarioApp
    from apps.core.models import Manzana

    if not cargo.activo:
        return
    perfil = PerfilAcceso.objects.filter(user_id=cargo.user_id).first()
    if perfil is None:
        raise ValidationError({"user": "Primero vincula esta cuenta con su ciudadano."})
    if cargo.ciudadano_id not in (None, perfil.ciudadano_id):
        raise ValidationError(
            {"ciudadano": "El ciudadano debe coincidir con el vínculo de la cuenta."}
        )
    cargo.ciudadano_id = perfil.ciudadano_id
    otros = UsuarioApp.objects.filter(activo=True).exclude(pk=cargo.pk)
    if (
        otros.filter(user_id=cargo.user_id).exists()
        or otros.filter(ciudadano_id=cargo.ciudadano_id).exists()
    ):
        raise ValidationError(
            {
                "activo": "Esta cuenta o ciudadano ya tiene un cargo activo. Desactívalo antes de asignar otro."
            }
        )
    if Manzana.objects.filter(activa=True, responsable_id=cargo.ciudadano_id).exists():
        raise ValidationError(
            {"activo": "El ciudadano ya es responsable de una manzana activa."}
        )


def validar_responsable(manzana):
    from .models import UsuarioApp
    from apps.core.models import Manzana

    if not manzana.activa or not manzana.responsable_id:
        return
    if UsuarioApp.objects.filter(
        activo=True, ciudadano_id=manzana.responsable_id
    ).exists():
        raise ValidationError(
            {"responsable": "El ciudadano ya tiene un cargo activo de comité."}
        )
    if (
        Manzana.objects.filter(activa=True, responsable_id=manzana.responsable_id)
        .exclude(pk=manzana.pk)
        .exists()
    ):
        raise ValidationError(
            {"responsable": "El ciudadano ya es responsable de otra manzana activa."}
        )
