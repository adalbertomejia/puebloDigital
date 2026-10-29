"""Policies for operating events, separate from permission to read them."""

from apps.core.autorizacion import responsabilidades_activas


def usuario_activo(usuario):
    return bool(getattr(usuario, "is_authenticated", False) and getattr(usuario, "is_active", False))


def manzanas_responsables(usuario):
    return [r.manzana.pk for r in responsabilidades_activas(usuario) if r.tipo == "MANZANA" and r.manzana]


def comites_presididos(usuario):
    return [
        r.comite.pk for r in responsabilidades_activas(usuario)
        if r.tipo == "COMITE" and r.rol == "PRESIDENTE" and r.comite
    ]


def puede_operar_evento(usuario, evento):
    if not usuario_activo(usuario):
        return False
    if usuario.is_superuser or usuario.has_perm(f"operacion.change_{evento._meta.model_name}"):
        return True
    if evento.alcance == evento.Alcances.MANZANA:
        return evento.manzana_id in manzanas_responsables(usuario)
    return evento.comite_id in comites_presididos(usuario)


def puede_crear_evento(usuario, modelo):
    return usuario_activo(usuario) and bool(
        usuario.is_superuser
        or usuario.has_perm(f"operacion.add_{modelo._meta.model_name}")
        or manzanas_responsables(usuario)
        or comites_presididos(usuario)
    )


def puede_capturar_evento(usuario, evento):
    if not usuario_activo(usuario):
        return False
    relacion = "registros" if evento._meta.model_name == "faena" else "asistencias"
    return getattr(evento, relacion).all().capturables_para(usuario).exists()
