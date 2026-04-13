from django.contrib import admin

from apps.comites.admin_security import CommitteeAccessMixin

from .models import Pago, Cooperacion


@admin.register(Pago)
class PagoAdmin(CommitteeAccessMixin, admin.ModelAdmin):
    committee_lookup = "comite"
    committee_fk_fields = ("comite",)
    foreign_key_committee_filters = {
        "registro_faena": "faena__comite",
    }
    treasury_only = True
    list_display = ("fecha", "ciudadano", "comite", "tipo", "monto", "anio_periodo")
    list_filter = ("tipo", "comite", "fecha")
    search_fields = ("ciudadano__nombre", "ciudadano__apellido_paterno", "concepto", "comprobante")


@admin.register(Cooperacion)
class CooperacionAdmin(CommitteeAccessMixin, admin.ModelAdmin):
    committee_lookup = "comite"
    committee_fk_fields = ("comite",)
    treasury_only = True
    list_display = ("fecha", "ciudadano", "comite", "tipo", "monto", "anio_periodo")
    list_filter = ("tipo", "comite", "fecha")
    search_fields = ("ciudadano__nombre", "ciudadano__apellido_paterno", "concepto", "comprobante")
