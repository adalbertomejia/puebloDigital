"""Atomic custody operations. Existing receivables are never counted twice."""
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import FondoRecurso, MovimientoRecurso, CorteRecurso, EventoCorteRecurso
from .balance_autorizacion import puede_abrir_fondo, puede_gestionar_fondo, puede_preparar_corte, puede_revisar_corte

CERO = Decimal("0.00")


def monto_valido(value, *, cero=False):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value < 0 or (not cero and value == 0) or value != value.quantize(Decimal("0.01")):
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Escribe un importe válido, con hasta dos decimales.")
    return value


def fecha_valida(fondo, fecha):
    if fecha < fondo.fecha_apertura or fecha > timezone.localdate():
        raise ValidationError("La fecha debe estar entre la apertura del fondo y hoy.")
    ultimo = fondo.cortes.filter(estado="CONFIRMADO").order_by("-hasta").first()
    if ultimo and fecha < timezone.localdate(ultimo.hasta):
        raise ValidationError("No se registra efectivo retroactivo anterior a un corte confirmado. Requiere una aclaración documentada.")


def resumen_fondo(fondo, *, hasta=None):
    saldos = {"EFECTIVO": fondo.inicial_efectivo, "TRANSFERENCIA": fondo.inicial_transferencia}
    entradas = {m: CERO for m in saldos}
    salidas = {m: CERO for m in saldos}
    qs = fondo.movimientos.all()
    if hasta:
        qs = qs.filter(created_at__lt=hasta)
    for mov in qs.iterator():
        if mov.tipo == "COBRO":
            entradas[mov.medio] += mov.monto
        else:
            salidas[mov.medio] += mov.monto
    for medio in saldos:
        saldos[medio] += entradas[medio]-salidas[medio]
    return {"efectivo": saldos["EFECTIVO"], "transferencia": saldos["TRANSFERENCIA"], "total": sum(saldos.values(), CERO), "entradas": entradas, "salidas": salidas}


@transaction.atomic
def abrir_fondo(*, usuario, nombre, categoria, comite, manzana, fecha_apertura, inicial_efectivo, inicial_transferencia, evidencia_apertura, clave_apertura=None):
    if not puede_abrir_fondo(usuario, comite, manzana):
        raise PermissionDenied
    if fecha_apertura > timezone.localdate():
        raise ValidationError("La apertura no puede estar en el futuro.")
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=usuario.pk)
    clave_apertura = clave_apertura or uuid.uuid4()
    anterior = FondoRecurso.objects.filter(clave_apertura=clave_apertura).first()
    if anterior:
        if anterior.creado_por_id != usuario.pk or anterior.nombre != nombre or anterior.categoria != categoria or anterior.comite_id != comite.pk or anterior.manzana_id != (manzana.pk if manzana else None) or anterior.fecha_apertura != fecha_apertura or anterior.inicial_efectivo != Decimal(str(inicial_efectivo)) or anterior.inicial_transferencia != Decimal(str(inicial_transferencia)) or anterior.evidencia_apertura != evidencia_apertura:
            raise ValidationError("La referencia de apertura ya corresponde a otro recurso o a otros datos.")
        return anterior
    fondo = FondoRecurso(clave_apertura=clave_apertura, nombre=nombre, categoria=categoria, comite=comite, manzana=manzana, fecha_apertura=fecha_apertura,
        inicial_efectivo=monto_valido(inicial_efectivo, cero=True), inicial_transferencia=monto_valido(inicial_transferencia, cero=True), evidencia_apertura=evidencia_apertura, creado_por=usuario)
    fondo.save()
    return fondo


def _reintento(clave, usuario, fondo, tipo, datos):
    anterior = MovimientoRecurso.objects.filter(clave_operacion=clave).first()
    if anterior:
        if anterior.registrado_por_id != usuario.pk or anterior.fondo_id != fondo.pk or anterior.tipo != tipo or any(getattr(anterior, k) != v for k,v in datos.items()):
            raise ValidationError("La referencia de operación ya se utilizó para otros datos.")
    return anterior


@transaction.atomic
def registrar_salida(*, usuario, fondo, monto, medio, fecha, categoria_salida, descripcion, beneficiario, evidencia, clave_operacion):
    fondo = FondoRecurso.objects.select_for_update().get(pk=fondo.pk)
    if not puede_gestionar_fondo(usuario, fondo):
        raise PermissionDenied
    datos = dict(monto=monto_valido(monto), medio=medio, fecha=fecha, categoria_salida=categoria_salida, descripcion=descripcion.strip(), beneficiario=beneficiario.strip(), evidencia=evidencia.strip())
    anterior = _reintento(clave_operacion, usuario, fondo, "SALIDA", datos)
    if anterior:
        return anterior
    fecha_valida(fondo, fecha)
    saldo = resumen_fondo(fondo)
    disponible = {"EFECTIVO": saldo["efectivo"], "TRANSFERENCIA": saldo["transferencia"]}.get(medio)
    if disponible is None or datos["monto"] > disponible:
        raise ValidationError("La salida supera el disponible del medio seleccionado o el medio es inválido.")
    mov = MovimientoRecurso(fondo=fondo, tipo="SALIDA", registrado_por=usuario, clave_operacion=clave_operacion, **datos)
    mov.save()
    return mov


@transaction.atomic
def registrar_cobro(*, usuario, fondo, abono, medio, clave_operacion):
    from .autorizacion import puede_abonar_obligacion
    fondo = FondoRecurso.objects.select_for_update().get(pk=fondo.pk)
    if not puede_gestionar_fondo(usuario, fondo) or not puede_abonar_obligacion(usuario, abono.obligacion):
        raise PermissionDenied
    concepto = abono.obligacion.concepto
    if concepto.comite_id != fondo.comite_id or (fondo.manzana_id and (concepto.alcance != "MANZANA" or concepto.manzana_id != fondo.manzana_id or abono.obligacion.ciudadano.manzana_id != fondo.manzana_id)):
        raise ValidationError("El concepto y el ciudadano no corresponden al ámbito del fondo seleccionado.")
    if abono.created_at < fondo.created_at:
        raise ValidationError("Los cobros anteriores a la apertura no se incorporan automáticamente: podrían estar incluidos en el saldo inicial.")
    fecha_valida(fondo, abono.fecha)
    if medio not in MovimientoRecurso.Medios.values:
        raise ValidationError("Selecciona efectivo o transferencia.")
    if medio == "TRANSFERENCIA" and not abono.referencia.strip():
        raise ValidationError("Indica la referencia de la transferencia.")
    anterior = MovimientoRecurso.objects.filter(abono=abono).first()
    if anterior:
        if anterior.fondo_id != fondo.pk or anterior.medio != medio:
            raise ValidationError("El abono ya pertenece a otro fondo o medio.")
        return anterior
    mov = MovimientoRecurso(fondo=fondo, abono=abono, tipo="COBRO", medio=medio, monto=abono.monto, fecha=abono.fecha,
        descripcion=f"Abono de {concepto.concepto}"[:250], evidencia=abono.referencia.strip() or abono.folio_recibo, registrado_por=usuario, clave_operacion=clave_operacion)
    mov.save()
    return mov


def manifiesto_corte(fondo):
    anterior = fondo.cortes.filter(estado="CONFIRMADO").order_by("-hasta").first()
    desde = anterior.hasta if anterior else fondo.created_at
    movimientos = list(fondo.movimientos.filter(created_at__gte=desde).order_by("created_at", "pk"))
    inicial = Decimal(anterior.manifiesto["contado"]) if anterior else fondo.inicial_efectivo
    inicial_transfer = Decimal(anterior.manifiesto["cierre_transferencia"]) if anterior else fondo.inicial_transferencia
    entradas = {m: CERO for m in MovimientoRecurso.Medios.values}
    salidas = {m: CERO for m in MovimientoRecurso.Medios.values}
    detalle = []
    for m in movimientos:
        (entradas if m.tipo == "COBRO" else salidas)[m.medio] += m.monto
        detalle.append({"id":str(m.pk), "tipo":m.tipo, "medio":m.medio, "monto":str(m.monto), "fecha":m.fecha.isoformat(), "captura":m.created_at.isoformat(), "categoria":m.categoria_salida})
    data = {"metodologia":"custodia-v1", "fondo":fondo.nombre, "fondo_id":fondo.pk, "comite":fondo.comite.nombre, "comite_id":fondo.comite_id, "manzana":str(fondo.manzana) if fondo.manzana_id else "Comité completo", "desde":desde.isoformat(), "anterior":str(anterior.pk) if anterior else None,
            "inicial_efectivo":format(inicial,".2f"), "inicial_transferencia":format(inicial_transfer,".2f"), "cobros_efectivo":str(entradas["EFECTIVO"]), "cobros_transferencia":str(entradas["TRANSFERENCIA"]), "salidas_efectivo":str(salidas["EFECTIVO"]), "salidas_transferencia":str(salidas["TRANSFERENCIA"]), "esperado":str(inicial+entradas["EFECTIVO"]-salidas["EFECTIVO"]), "cierre_transferencia":str(inicial_transfer+entradas["TRANSFERENCIA"]-salidas["TRANSFERENCIA"]), "movimientos":detalle}
    return data


def huella(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def version_corte(fondo):
    return signing.dumps({"fondo":fondo.pk, "huella":huella(manifiesto_corte(fondo))}, salt="corte-recurso")


@transaction.atomic
def enviar_corte(*, usuario, fondo, contado, aclaracion, evidencia_conteo, clave_operacion, version):
    fondo = FondoRecurso.objects.select_for_update().get(pk=fondo.pk)
    if not puede_preparar_corte(usuario, fondo):
        raise PermissionDenied
    anterior = CorteRecurso.objects.filter(clave_operacion=clave_operacion).first()
    contado = monto_valido(contado, cero=True)
    if anterior:
        if anterior.fondo_id != fondo.pk or anterior.preparado_por_id != usuario.pk or anterior.contado != contado or anterior.aclaracion != aclaracion or anterior.evidencia_conteo != evidencia_conteo:
            raise ValidationError("La referencia de envío ya corresponde a otros datos.")
        return anterior
    if fondo.cortes.filter(estado="EN_REVISION").exists():
        raise ValidationError("Este fondo ya tiene un corte en revisión.")
    data = manifiesto_corte(fondo)
    try:
        token = signing.loads(version, salt="corte-recurso", max_age=7200)
    except signing.BadSignature:
        raise ValidationError("La preparación caducó. Actualiza el corte y revisa el conteo.")
    if token != {"fondo":fondo.pk, "huella":huella(data)}:
        raise ValidationError("Se registraron movimientos o cambió el cierre anterior. Actualiza y vuelve a contar antes de enviar.")
    esperado = Decimal(data["esperado"])
    diferencia = contado-esperado
    if diferencia and not aclaracion.strip():
        raise ValidationError("Explica la aclaración de diferencia antes de enviar a revisión.")
    if not evidencia_conteo.strip():
        raise ValidationError("Indica la evidencia del conteo.")
    data.update(contado=str(contado), diferencia=str(diferencia))
    corte = CorteRecurso(fondo=fondo, desde=data["desde"], hasta=timezone.now(), preparado_por=usuario, contado=contado, esperado=esperado, diferencia=diferencia,
        aclaracion=aclaracion, evidencia_conteo=evidencia_conteo, manifiesto=data, huella=huella(data), clave_operacion=clave_operacion)
    corte.save()
    EventoCorteRecurso.objects.create(corte=corte, usuario=usuario, accion="ENVIAR", motivo=aclaracion.strip() or "Conteo cuadrado; enviado a revisión.")
    return corte


@transaction.atomic
def revisar_corte(*, usuario, corte, accion, motivo):
    FondoRecurso.objects.select_for_update().get(pk=corte.fondo_id)
    corte = CorteRecurso.objects.select_for_update().select_related("fondo__comite").get(pk=corte.pk)
    if not puede_revisar_corte(usuario, corte):
        raise PermissionDenied
    destino = {"CONFIRMAR":"CONFIRMADO", "DEVOLVER":"DEVUELTO"}.get(accion)
    if destino is None or not motivo.strip():
        raise ValidationError("Indica una decisión y el motivo de revisión.")
    if corte.estado == destino and corte.revisado_por_id == usuario.pk:
        return corte
    if corte.estado != "EN_REVISION":
        raise ValidationError("Este corte ya fue revisado.")
    if huella(corte.manifiesto) != corte.huella:
        raise ValidationError("La evidencia del corte no coincide con su huella. Requiere revisión técnica.")
    if destino == "CONFIRMADO" and corte.diferencia:
        raise ValidationError("Hay una diferencia pendiente. Solicita aclaración; no se confirma como cuadrado.")
    corte.estado, corte.revisado_por, corte.revisado_en = destino, usuario, timezone.now()
    corte.save(update_fields=["estado", "revisado_por", "revisado_en", "updated_at"])
    EventoCorteRecurso.objects.create(corte=corte, usuario=usuario, accion=accion, motivo=motivo.strip())
    return corte
