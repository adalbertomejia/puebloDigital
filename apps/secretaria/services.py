import uuid
from functools import wraps
from pathlib import Path
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError, OperationalError, connection
from django.shortcuts import get_object_or_404
from django.utils import timezone
from apps.core.models import Ciudadano
from .models import Solicitud, Seguimiento, Adjunto
from .autorizacion import visibles, comites_gestionables, puede_asignar, responsables
from .archivos import validar_adjunto


class Conflicto(ValidationError):
    pass


def controlar_bloqueo(funcion):
    @wraps(funcion)
    def ejecutar(*args, **kwargs):
        try:
            return funcion(*args, **kwargs)
        except OperationalError as exc:
            if connection.vendor != 'sqlite' or 'locked' not in str(exc).lower():
                raise
            raise Conflicto('Hay otro guardado en curso. Conservamos tu captura; revisa la solicitud y vuelve a intentar sin abrir un formulario nuevo.') from exc
    return ejecutar


def token_nuevo(usuario):
    return signing.dumps({'usuario': usuario.pk, 'nonce': str(uuid.uuid4())}, salt='secretaria-envio')


def leer_token(token, usuario):
    try:
        datos = signing.loads(token, salt='secretaria-envio', max_age=86400)
        if datos['usuario'] != usuario.pk:
            raise ValueError
        return uuid.UUID(datos['nonce'])
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        raise ValidationError('El formulario venció o no es válido. Abre una nueva solicitud.')


def guardar_adjunto(solicitud, usuario, archivo):
    if not archivo:
        return None
    validar_adjunto(archivo)
    adjunto = Adjunto(solicitud=solicitud, autor=usuario, nombre=Path(archivo.name).name[:200])
    adjunto.archivo.save(archivo.name, archivo, save=False)
    try:
        adjunto.save()
    except Exception:
        adjunto.archivo.delete(save=False)
        raise
    return adjunto


def validar_responsable(usuario, comite_id, ciudadano):
    if usuario and not responsables(comite_id, ciudadano).filter(pk=usuario.pk).exists():
        raise ValidationError('El responsable debe tener un cargo activo en el comité y acceso autorizado al ciudadano.')


@controlar_bloqueo
def crear(usuario, datos, token, archivo=None):
    nonce = leer_token(token, usuario)
    adjunto = None
    try:
        with transaction.atomic():
            anterior = Solicitud.objects.filter(token_envio=nonce).first()
            if anterior:
                if anterior.creado_por_id != usuario.pk or not visibles(usuario).filter(pk=anterior.pk).exists():
                    raise ValidationError('No puedes reutilizar este formulario.')
                return anterior, False
            if not comites_gestionables(usuario).filter(pk=datos['comite'].pk).exists() or not Ciudadano.objects.visibles_para(usuario).filter(pk=datos['ciudadano'].pk).exists():
                raise ValidationError('No tienes autorización para registrar esta solicitud.')
            if not datos['tipo'].activo:
                raise ValidationError('El tipo de solicitud ya no está activo.')
            validar_responsable(datos.get('responsable'), datos['comite'].pk, datos['ciudadano'])
            try:
                with transaction.atomic():
                    solicitud = Solicitud.objects.create(token_envio=nonce, creado_por=usuario, **{k: datos[k] for k in ('ciudadano', 'tipo', 'descripcion', 'comite', 'responsable', 'fecha_compromiso')})
            except IntegrityError:
                anterior = Solicitud.objects.filter(token_envio=nonce, creado_por=usuario).first()
                if anterior and visibles(usuario).filter(pk=anterior.pk).exists():
                    return anterior, False
                raise
            adjunto = guardar_adjunto(solicitud, usuario, archivo)
            Seguimiento.objects.create(solicitud=solicitud, autor=usuario, cambios={'Registro': solicitud.folio, 'Estado': solicitud.get_estado_display(), 'Responsable': str(solicitud.responsable or 'Sin asignar'), 'Fecha de compromiso': str(solicitud.fecha_compromiso or 'Sin fecha'), **({'Adjunto': adjunto.nombre} if adjunto else {})})
            return solicitud, True
    except Exception:
        if adjunto:
            adjunto.archivo.delete(save=False)
        raise


@controlar_bloqueo
def actualizar(usuario, pk, version, datos, archivo=None):
    adjunto = None
    try:
        with transaction.atomic():
            solicitud = get_object_or_404(visibles(usuario).select_related(None).select_for_update(), pk=pk)
            if solicitud.version != version:
                raise Conflicto('Otra persona modificó la solicitud. Conservamos tu captura; abre el detalle en otra pestaña y revisa los cambios antes de volver a intentarlo.')
            if solicitud.cerrada:
                raise ValidationError('La solicitud está cerrada y su historial se conserva sin modificaciones.')
            responsable = datos.get('responsable', solicitud.responsable)
            if responsable != solicitud.responsable:
                if not puede_asignar(usuario, solicitud):
                    raise ValidationError('No tienes autorización para reasignar esta solicitud.')
                validar_responsable(responsable, solicitud.comite_id, solicitud.ciudadano)
            estado = datos['estado']
            if estado not in Solicitud.Estados.values:
                raise ValidationError('Estado inválido.')
            cierre = estado in ('RESUELTA', 'CANCELADA')
            motivo = datos.get('motivo_cierre', '').strip()
            if cierre and not datos.get('confirmar_cierre'):
                raise ValidationError('Confirma la resolución o cancelación antes de guardar.')
            if cierre and not motivo:
                raise ValidationError('Indica el motivo para resolver o cancelar.')
            cambios = {}
            for etiqueta, anterior, nuevo in (
                ('Estado', solicitud.get_estado_display(), Solicitud.Estados(estado).label),
                ('Responsable', str(solicitud.responsable or 'Sin asignar'), str(responsable or 'Sin asignar')),
                ('Fecha de compromiso', str(solicitud.fecha_compromiso or 'Sin fecha'), str(datos['fecha_compromiso'] or 'Sin fecha')),
            ):
                if anterior != nuevo:
                    cambios[etiqueta] = {'antes': anterior, 'después': nuevo}
            observaciones = datos.get('observaciones', '').strip()
            if not cambios and not observaciones and not archivo:
                raise ValidationError('Indica un cambio o una observación para guardar el seguimiento.')
            if cierre:
                cambios['Motivo de cierre'] = motivo
            ahora = timezone.now()
            actualizado = Solicitud.objects.filter(pk=pk, version=version).update(estado=estado, responsable=responsable, fecha_compromiso=datos['fecha_compromiso'], motivo_cierre=motivo if cierre else '', fecha_cierre=ahora if cierre else None, version=version+1, updated_at=ahora)
            if not actualizado:
                raise Conflicto('La solicitud cambió durante el guardado. Revisa el detalle antes de continuar.')
            adjunto = guardar_adjunto(solicitud, usuario, archivo)
            if adjunto:
                cambios['Adjunto'] = adjunto.nombre
            Seguimiento.objects.create(solicitud=solicitud, autor=usuario, cambios=cambios, observaciones=observaciones)
            solicitud.refresh_from_db()
            return solicitud
    except Exception:
        if adjunto:
            adjunto.archivo.delete(save=False)
        raise
