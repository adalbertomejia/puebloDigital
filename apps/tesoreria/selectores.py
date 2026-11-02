"""Bounded relation searches; every lookup starts from the user's financial scope."""
from dal import autocomplete
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Subquery
from django.http import Http404
from apps.core.models import Ciudadano
from apps.core.query_helpers import filtro_busqueda_ciudadano
from .autorizacion import limitar_finanzas, tiene_acceso_financiero
from .models import ObligacionCiudadano


def identificador_valido(valor):
    texto = str(valor)
    if not texto.isdigit() or len(texto) > 19:
        return None
    numero = int(texto)
    return numero if 0 < numero <= 9223372036854775807 else None


def obligaciones_pendientes(usuario):
    return limitar_finanzas(ObligacionCiudadano.objects.filter(estado="PENDIENTE"), usuario, "concepto__comite_id").select_related("ciudadano", "ciudadano__toma", "concepto", "concepto__comite")


def ciudadanos_con_obligaciones(usuario):
    return Ciudadano.objects.filter(pk__in=Subquery(obligaciones_pendientes(usuario).order_by().values("ciudadano_id"))).select_related("toma").order_by("apellido_paterno", "apellido_materno", "nombre", "pk")


class BusquedaFinanciera(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not tiene_acceso_financiero(request.user):
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class CiudadanoFinancieroAutocomplete(BusquedaFinanciera):
    def get_queryset(self):
        qs = ciudadanos_con_obligaciones(self.request.user)
        if len(self.q.strip()) < 2:
            return qs.none()
        return qs.filter(filtro_busqueda_ciudadano(self.q, extra_fields=("toma__numero_toma",)))

    def get_result_label(self, objeto):
        toma = getattr(objeto, "toma", None)
        return f"{objeto.nombre_completo} · Contrato {objeto.numero_contrato or 'sin registro'} · Toma {toma.numero_toma if toma else 'sin toma'} · ID {objeto.pk}"


class ObligacionFinancieraAutocomplete(BusquedaFinanciera):
    def get_queryset(self):
        ciudadano = identificador_valido(self.forwarded.get("ciudadano"))
        qs = obligaciones_pendientes(self.request.user).order_by("-concepto__fecha", "pk")
        if ciudadano is None:
            return qs.none()
        qs = qs.filter(ciudadano_id=int(ciudadano))
        return qs.filter(concepto__concepto__icontains=self.q) if self.q else qs

    def get_result_label(self, objeto):
        return f"{objeto.concepto.concepto} · {objeto.concepto.comite.nombre} · Obligación #{objeto.pk}"
