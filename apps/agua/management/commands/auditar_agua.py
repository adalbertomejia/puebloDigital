"""Read-only aggregate inventory; never prints citizen identifiers or names."""
import json

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q

from apps.agua.models import Toma
from apps.core.models import Ciudadano
from apps.tesoreria.models import ObligacionCiudadano, Pago


class Command(BaseCommand):
    help = "Diagnóstico de agua de solo lectura: conteos agregados, sin datos personales ni correcciones."

    def handle(self, *args, **options):
        contratos = Ciudadano.objects.exclude(numero_contrato__isnull=True).exclude(numero_contrato="")
        grupos = contratos.values("numero_contrato").annotate(cantidad=Count("pk")).filter(cantidad__gt=1)
        tomas = Toma.objects.all()
        resultado = {
            "ciudadanos": Ciudadano.objects.count(),
            "ciudadanos_con_numero_contrato": contratos.count(),
            "numeros_contrato_repetidos": grupos.count(),
            "ciudadanos_con_contrato_sin_toma": contratos.filter(toma__isnull=True).count(),
            "tomas": tomas.count(),
            "tomas_por_estado": {fila["estado"]: fila["cantidad"] for fila in tomas.values("estado").annotate(cantidad=Count("pk"))},
            "tomas_sin_contrato_en_ciudadano": tomas.filter(Q(ciudadano__numero_contrato__isnull=True) | Q(ciudadano__numero_contrato="")).count(),
            "tomas_cuyo_numero_difiere_del_contrato": tomas.exclude(ciudadano__numero_contrato__isnull=True).exclude(ciudadano__numero_contrato="").exclude(numero_toma=F("ciudadano__numero_contrato")).count(),
            "tomas_con_costo_anual_negativo": tomas.filter(costo_anual__lt=0).count(),
            "pagos_heredados_con_toma": Pago.objects.filter(toma__isnull=False).count(),
            "pagos_con_ciudadano_distinto_del_titular": Pago.objects.filter(toma__isnull=False).exclude(ciudadano_id=F("toma__ciudadano_id")).count(),
            "obligaciones_origen_agua_sin_toma_actual": ObligacionCiudadano.objects.filter(concepto__origen="AGUA", ciudadano__toma__isnull=True).count(),
        }
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True))
