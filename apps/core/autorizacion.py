"""Shared, read-only derivation of the user's current access responsibilities."""

from dataclasses import dataclass

from django.db.models import F


@dataclass(frozen=True)
class ResponsabilidadActiva:
    tipo: str
    rol: str
    etiqueta_rol: str
    manzana: object = None
    comite: object = None


def responsabilidades_activas(usuario):
    """Return current block and committee assignments for an authenticated user.

    Block responsibility is derived from the user's one-to-one PerfilAcceso and
    the citizen currently assigned to their own active block. Committee roles
    remain sourced from active UsuarioApp rows and active committees.
    """
    if not getattr(usuario, "is_authenticated", False) or not getattr(
        usuario, "is_active", False
    ):
        return []

    from apps.comites.models import Comite, PerfilAcceso, UsuarioApp

    responsabilidades = []

    if usuario.is_superuser:
        responsabilidades.append(
            ResponsabilidadActiva(
                tipo="GLOBAL",
                rol="ADMINISTRADOR",
                etiqueta_rol="Administrador general",
            )
        )

    perfil = (
        PerfilAcceso.objects.select_related("ciudadano__manzana")
        .filter(
            user_id=usuario.pk,
            ciudadano__activo=True,
            ciudadano__manzana__isnull=False,
            ciudadano__manzana__activa=True,
            ciudadano__manzana__responsable_id=F("ciudadano_id"),
        )
        .first()
    )
    if perfil:
        responsabilidades.append(
            ResponsabilidadActiva(
                tipo="MANZANA",
                rol="RESPONSABLE_MANZANA",
                etiqueta_rol="Responsable de manzana",
                manzana=perfil.ciudadano.manzana,
            )
        )

    cargos = (
        UsuarioApp.objects.select_related("comite")
        .filter(user_id=usuario.pk, activo=True, comite__activo=True)
        .order_by("comite__nombre", "rol")
    )
    responsabilidades.extend(
        ResponsabilidadActiva(
            tipo="COMITE",
            rol=cargo.rol,
            etiqueta_rol=cargo.get_rol_display(),
            comite=cargo.comite,
        )
        for cargo in cargos
    )

    return responsabilidades
