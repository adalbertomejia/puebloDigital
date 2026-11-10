"""Lecturas autorizadas del expediente; reutiliza los cálculos de tesorería."""

from decimal import Decimal
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q, Sum
from apps.operacion.models import AsistenciaJunta, RegistroFaena
from apps.tesoreria.models import Abono, ObligacionCiudadano
from apps.tesoreria.queries import anotar_obligaciones
from .autorizacion import permiso_global_de_modelo
from apps.tesoreria.autorizacion import tiene_acceso_financiero, limitar_finanzas


def puede_ver_finanzas(usuario):
    return tiene_acceso_financiero(usuario)


def registros_asistencia(ciudadano, usuario=None):
    faenas = RegistroFaena.objects.filter(ciudadano=ciudadano)
    juntas = AsistenciaJunta.objects.filter(ciudadano=ciudadano)
    if usuario is not None and not permiso_global_de_modelo(usuario, "core.view_ciudadano"):
        faenas = faenas.visibles_para(usuario)
        juntas = juntas.visibles_para(usuario)
    return faenas, juntas


def obtener_resumen_ciudadano(ciudadano, usuario=None):
    faenas, juntas = registros_asistencia(ciudadano, usuario)
    resumen = {
        "faenas": 0,
        "juntas": 0,
        "asistencias": 0,
        "faltas": 0,
        "justificaciones": 0,
        "pendientes_asistencia": 0,
        "adeudos_asistencia": 0,
    }
    for registros, relacion, clave in (
        (faenas, "faena", "faenas"),
        (juntas, "junta", "juntas"),
    ):
        registros = registros.exclude(**{relacion + "__estado": "CANCELADA"})
        datos = registros.aggregate(
            total=Count("pk"),
            asistencias=Count("pk", filter=Q(estatus="ASISTIO")),
            faltas=Count("pk", filter=Q(estatus="FALTO")),
            justificaciones=Count("pk", filter=Q(estatus="JUSTIFICADO")),
            pendientes_asistencia=Count("pk", filter=Q(estatus="PENDIENTE")),
            adeudos_asistencia=Count("pk", filter=Q(genera_adeudo=True)),
        )
        resumen[clave] = datos.pop("total")
        for key, value in datos.items():
            resumen[key] += value
    if usuario is None or puede_ver_finanzas(usuario):
        obligaciones = obtener_obligaciones_ciudadano(ciudadano, usuario=usuario)
        resumen.update(
            obligaciones.aggregate(
                conceptos=Count("concepto_id", distinct=True),
                pendientes=Count("pk", filter=Q(estado="PENDIENTE")),
                pagadas=Count("pk", filter=Q(estado="PAGADO")),
            )
        )
        # Sum each outstanding balance so an overpayment never offsets another obligation.
        vigentes = obligaciones.exclude(estado="CANCELADO").aggregate(
            saldo=Sum("saldo_pendiente_calc"),
            abonado=Sum("total_abonado_calc"),
            asignado=Sum("monto_asignado"),
        )
        vigentes_qs = obligaciones.exclude(estado="CANCELADO")
        asignado_desconocido = vigentes_qs.filter(monto_asignado__isnull=True).exists()
        abonado_desconocido = Abono.objects.filter(
            obligacion__in=vigentes_qs, monto__isnull=True
        ).exists()
        resumen.update(
            saldo_pendiente=vigentes["saldo"] or Decimal("0.00"),
            total_abonado=vigentes["abonado"] or Decimal("0.00"),
            asignado=vigentes["asignado"] or Decimal("0.00"),
        )
        resumen["importes_desconocidos"] = asignado_desconocido or abonado_desconocido
        if asignado_desconocido:
            resumen["asignado"] = None
        if abonado_desconocido:
            resumen["total_abonado"] = None
        if resumen["importes_desconocidos"]:
            resumen["saldo_pendiente"] = None
    return resumen


def obtener_obligaciones_ciudadano(ciudadano, *, usuario=None):
    obligaciones = ObligacionCiudadano.objects.filter(ciudadano=ciudadano)
    if usuario is not None:
        obligaciones = limitar_finanzas(obligaciones, usuario, "concepto__comite_id")
    return anotar_obligaciones(
        obligaciones.annotate(
            abonos_desconocidos=Exists(
                Abono.objects.filter(obligacion=OuterRef("pk"), monto__isnull=True)
            )
        ).select_related("concepto", "concepto__comite", "concepto__manzana")
    ).order_by("-concepto__fecha", "-concepto_id", "-pk")


def obtener_abonos_ciudadano(ciudadano, *, usuario=None):
    abonos = Abono.objects.filter(obligacion__ciudadano=ciudadano)
    if usuario is not None:
        abonos = limitar_finanzas(abonos, usuario, "obligacion__concepto__comite_id")
    return abonos.select_related(
        "creado_por",
        "obligacion",
        "obligacion__concepto",
        "obligacion__concepto__comite",
        "obligacion__concepto__manzana",
    ).order_by("-fecha", "-created_at", "-pk")


def obtener_asistencias_ciudadano(ciudadano, usuario=None):
    faenas, juntas = registros_asistencia(ciudadano, usuario)
    filas = []
    for registros, relacion, tipo, url in (
        (faenas, "faena", "Faena", "control_asistencias_faena_detalle"),
        (juntas, "junta", "Junta", "control_asistencias_junta_detalle"),
    ):
        modelo_evento = registros.model._meta.get_field(relacion).remote_field.model
        visibles = (
            None
            if usuario is None
            else set(
                modelo_evento.objects.visibles_para(usuario)
                .filter(pk__in=registros.values(relacion + "_id"))
                .values_list("pk", flat=True)
            )
        )
        for registro in registros.select_related(relacion, relacion + "__manzana"):
            evento = getattr(registro, relacion)
            cancelado = evento.estado == "CANCELADA"
            puede_abrir = visibles is None or evento.pk in visibles
            filas.append(
                {
                    "tipo": tipo,
                    "descripcion": (
                        evento.descripcion if tipo == "Faena" else evento.tema
                    ),
                    "fecha": evento.fecha,
                    "fecha_registro": registro.created_at,
                    "territorio": (
                        evento.manzana if evento.manzana_id else "Toda la comunidad"
                    ),
                    "estado": (
                        "Cancelado" if cancelado else registro.get_estatus_display()
                    ),
                    "codigo_estado": "CANCELADO" if cancelado else registro.estatus,
                    "genera_adeudo": registro.genera_adeudo and not cancelado,
                    "monto_adeudo": registro.monto_adeudo,
                    "id": registro.pk,
                    "evento_id": evento.pk,
                    "url_name": url if puede_abrir else "",
                }
            )
    return sorted(filas, key=lambda x: (-x["fecha"].toordinal(), x["tipo"], -x["id"]))


def paginar(queryset, request, parametro, por_pagina=10):
    return Paginator(queryset, por_pagina).get_page(request.GET.get(parametro))
