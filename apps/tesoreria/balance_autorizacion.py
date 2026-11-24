"""Reuse identity/responsibility derivation without global permission bypasses."""
from django.db.models import Q
from django.http import Http404
from apps.comites.models import Comite
from apps.core.autorizacion import responsabilidades_activas, es_secretaria_central
from .autorizacion import limitar_finanzas, tiene_acceso_financiero


def permiso_explicito(user, codigo):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    app, codename = codigo.split(".")
    return user.user_permissions.filter(content_type__app_label=app, codename=codename).exists() or user.groups.filter(permissions__content_type__app_label=app, permissions__codename=codename).exists()


def secretaria(user):
    return es_secretaria_central(user) and permiso_explicito(user, "core.operar_secretaria_central")


def secretaria_financiera(user):
    return secretaria(user) and any(permiso_explicito(user, p) for p in ("core.operar_finanzas_centrales", "tesoreria.gestionar_recursos"))


def delegaciones(user):
    return [r.comite.pk for r in responsabilidades_activas(user) if r.tipo == "COMITE" and r.rol == "DELEGADO" and r.comite.tipo == "DELEGACION"]


def consulta_central(user):
    return secretaria(user) and any(permiso_explicito(user, p) for p in ("tesoreria.consultar_balance", "core.consultar_finanzas_centrales", "core.operar_finanzas_centrales", "tesoreria.gestionar_recursos"))


def puede_consultar_balance(user):
    return tiene_acceso_financiero(user) or consulta_central(user) or bool(delegaciones(user))


def limitar_balance(qs, user, campo="comite_id"):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return qs.none()
    if user.is_superuser or consulta_central(user):
        return qs.filter(**{campo.removesuffix("_id") + "__activo": True}) if not user.is_superuser else qs
    ids = delegaciones(user)
    if ids:
        return qs.filter(**{campo+"__in": ids})
    return limitar_finanzas(qs, user, campo)


def fondos_visibles(user):
    from .models import FondoRecurso
    qs = FondoRecurso.objects.select_related("comite", "manzana", "creado_por")
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return qs.none()
    if user.is_superuser:
        return qs
    if secretaria(user) and any(permiso_explicito(user, p) for p in ("core.consultar_finanzas_centrales", "core.operar_finanzas_centrales", "tesoreria.gestionar_recursos")):
        return qs.filter(comite__activo=True)
    responsabilidades = responsabilidades_activas(user)
    comites = [r.comite.pk for r in responsabilidades if r.tipo == "COMITE" and (r.rol in ("PRESIDENTE", "TESORERO", "LECTURA") or r.comite.pk in delegaciones(user))]
    manzanas = [r.manzana.pk for r in responsabilidades if r.tipo == "MANZANA"]
    return qs.filter(Q(comite_id__in=comites) | Q(manzana_id__in=manzanas, manzana__activa=True), comite__activo=True)


def puede_gestionar_fondo(user, fondo):
    if not fondo.activo or not fondos_visibles(user).filter(pk=fondo.pk).exists():
        return False
    if secretaria_financiera(user) and fondo.comite.tipo == "DELEGACION":
        return True
    return any((r.tipo == "COMITE" and r.comite.pk == fondo.comite_id and r.rol in ("PRESIDENTE", "TESORERO")) or (r.tipo == "MANZANA" and r.manzana.pk == fondo.manzana_id) for r in responsabilidades_activas(user))


def puede_preparar_corte(user, fondo):
    if not puede_gestionar_fondo(user, fondo):
        return False
    return (secretaria_financiera(user) and fondo.comite.tipo == "DELEGACION") or any((r.tipo == "COMITE" and r.comite.pk == fondo.comite_id and r.rol == "TESORERO") or (r.tipo == "MANZANA" and r.manzana.pk == fondo.manzana_id) for r in responsabilidades_activas(user))


def puede_revisar_corte(user, corte):
    if corte.preparado_por_id == user.pk or not fondos_visibles(user).filter(pk=corte.fondo_id).exists():
        return False
    return any(r.tipo == "COMITE" and ((r.rol == "PRESIDENTE" and r.comite.pk == corte.fondo.comite_id) or (r.rol == "DELEGADO" and r.comite.tipo == "DELEGACION" and corte.fondo.comite.tipo == "DELEGACION" and r.comite.pk == corte.fondo.comite_id)) for r in responsabilidades_activas(user))


def exigir_balance(user):
    if not puede_consultar_balance(user):
        raise Http404


def puede_abrir_fondo(user, comite, manzana=None):
    if not getattr(user, "is_authenticated", False) or not user.is_active or not comite.activo or (manzana and not manzana.activa):
        return False
    if secretaria_financiera(user) and comite.tipo == "DELEGACION":
        return True
    return any((r.tipo == "COMITE" and r.comite.pk == comite.pk and r.rol in ("PRESIDENTE", "TESORERO")) or (r.tipo == "MANZANA" and manzana and r.manzana.pk == manzana.pk) for r in responsabilidades_activas(user))
