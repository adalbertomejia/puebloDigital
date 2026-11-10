"""Synthetic fixtures with the same explicit identity link required in the UI."""

from apps.core.models import Ciudadano
from .models import PerfilAcceso, UsuarioApp


def asignar_cargo(**kwargs):
    usuario = kwargs["user"]
    perfil = PerfilAcceso.objects.filter(user=usuario).first()
    if perfil is None:
        ciudadano = kwargs.get("ciudadano") or Ciudadano.objects.create(
            nombre="Titular", apellido_paterno=usuario.username
        )
        perfil = PerfilAcceso.objects.create(user=usuario, ciudadano=ciudadano)
    kwargs.setdefault("ciudadano", perfil.ciudadano)
    return UsuarioApp.objects.create(**kwargs)
