from django.contrib.auth import get_user_model
from django.db.models import Q
from apps.comites.models import Comite, UsuarioApp
from apps.core.models import Ciudadano
from .models import Solicitud

GESTORES = ('SECRETARIO', 'PRESIDENTE')
ATENCION = (*GESTORES, 'TESORERO', 'CAPTURISTA')


def cargos(usuario):
    if not usuario.is_authenticated or not usuario.is_active:
        return UsuarioApp.objects.none()
    return UsuarioApp.objects.filter(user=usuario, activo=True, comite__activo=True)


def comites_gestionables(usuario):
    if not usuario.is_authenticated or not usuario.is_active:
        return Comite.objects.none()
    if usuario.is_superuser:
        return Comite.objects.filter(activo=True)
    return Comite.objects.filter(pk__in=cargos(usuario).filter(rol__in=GESTORES).values('comite_id'))


def puede_entrar(usuario):
    return bool(usuario.is_authenticated and usuario.is_active and (usuario.is_superuser or cargos(usuario).filter(rol__in=ATENCION).exists()))


def visibles(usuario):
    qs = Solicitud.objects.select_related('ciudadano', 'tipo', 'comite', 'responsable', 'creado_por')
    if not puede_entrar(usuario):
        return qs.none()
    if usuario.is_superuser:
        return qs
    gestion = comites_gestionables(usuario).values('pk')
    propios = cargos(usuario).filter(rol__in=ATENCION).values('comite_id')
    return qs.filter(Q(comite_id__in=gestion) | Q(comite_id__in=propios, responsable=usuario)).filter(ciudadano__in=Ciudadano.objects.visibles_para(usuario))


def puede_asignar(usuario, solicitud):
    return usuario.is_superuser or comites_gestionables(usuario).filter(pk=solicitud.comite_id).exists()


def responsables(comite_id, ciudadano):
    candidatos = get_user_model().objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(perfiles_app__activo=True, perfiles_app__comite_id=comite_id, perfiles_app__comite__activo=True, perfiles_app__rol__in=ATENCION)).distinct().order_by('username')
    # Reuse the roster's existing global/block permission; assignment grants none.
    ids = [u.pk for u in candidatos if Ciudadano.objects.visibles_para(u).filter(pk=ciudadano.pk).exists()]
    return get_user_model().objects.filter(pk__in=ids).order_by('username')
