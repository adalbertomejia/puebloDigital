from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from apps.comites.models import Comite
from apps.tesoreria.models import Pago
from .models import Toma

@admin.register(Toma)
class TomaAdmin(admin.ModelAdmin):
    list_display = ('numero_toma', 'ciudadano', 'costo_anual', 'estado')
    list_filter = ('estado',)
    search_fields = ('numero_toma', 'ciudadano__nombre', 'ciudadano__apellido_paterno')
    actions = ('generar_cuotas_anuales',)

    @admin.action(description='Generar cuotas anuales para tomas activas (año actual)')
    def generar_cuotas_anuales(self, request, queryset):
        anio = timezone.localdate().year
        tomas = queryset.filter(estado=Toma.Estados.ACTIVA).select_related('ciudadano')
        comite_agua = Comite.objects.filter(tipo=Comite.Tipos.AGUA, activo=True).order_by('id').first()
        if not comite_agua:
            self.message_user(request, 'No existe un comité de agua activo para asociar las cuotas.', level=messages.ERROR)
            return

        nuevos_pagos = []
        for toma in tomas:
            nuevos_pagos.append(
                Pago(
                    ciudadano=toma.ciudadano,
                    comite=comite_agua,
                    tipo=Pago.Tipos.CUOTA_ANUAL,
                    estado=Pago.Estados.PENDIENTE,
                    monto=toma.costo_anual,
                    fecha=timezone.localdate(),
                    concepto=f'Cuota anual de agua {anio}',
                    anio_periodo=anio,
                    toma=toma,
                )
            )

        with transaction.atomic():
            Pago.objects.bulk_create(nuevos_pagos, ignore_conflicts=True)

        self.message_user(
            request,
            f'Se procesaron {len(nuevos_pagos)} cuotas anuales para {anio}. Los duplicados fueron omitidos automáticamente.',
            level=messages.SUCCESS,
        )
