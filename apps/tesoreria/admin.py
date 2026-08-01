from django.contrib import admin
from apps.operacion.alcance import manzanas_disponibles_para_instancia

from .models import Abono, ConceptoTesoreria, Cooperacion, ObligacionCiudadano, Pago


class AbonoInline(admin.TabularInline):
    model = Abono
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(ConceptoTesoreria)
class ConceptoTesoreriaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "naturaleza", "alcance", "manzana", "concepto", "comite", "monto_individual", "registros_generados")
    list_filter = ("naturaleza", "alcance", "manzana", "origen", "comite", "fecha", "registros_generados")
    search_fields = ("concepto", "descripcion", "comite__nombre")
    autocomplete_fields = ("comite", "manzana")
    list_select_related = ("manzana", "comite")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["manzana"].queryset = manzanas_disponibles_para_instancia(
            obj or ConceptoTesoreria()
        )
        return form


@admin.register(ObligacionCiudadano)
class ObligacionCiudadanoAdmin(admin.ModelAdmin):
    list_display = ("ciudadano", "concepto", "monto_asignado", "estado")
    list_filter = ("estado", "concepto__naturaleza", "concepto__comite")
    search_fields = ("ciudadano__nombre", "ciudadano__apellido_paterno", "ciudadano__apellido_materno", "concepto__concepto")
    autocomplete_fields = ("concepto", "ciudadano")
    inlines = [AbonoInline]


@admin.register(Abono)
class AbonoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "obligacion", "monto")
    list_filter = ("fecha",)
    search_fields = ("obligacion__ciudadano__nombre", "obligacion__ciudadano__apellido_paterno", "obligacion__concepto__concepto")
    autocomplete_fields = ("obligacion",)


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'ciudadano', 'comite', 'tipo', 'monto', 'anio_periodo')
    list_filter = ('tipo', 'comite', 'fecha')
    search_fields = ('ciudadano__nombre', 'ciudadano__apellido_paterno', 'concepto', 'comprobante')
    autocomplete_fields = ('ciudadano', 'comite', 'registro_faena', 'toma')


@admin.register(Cooperacion)
class CooperacionAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'ciudadano', 'comite', 'tipo', 'monto', 'anio_periodo')
    list_filter = ('tipo', 'comite', 'fecha')
    search_fields = ('ciudadano__nombre', 'ciudadano__apellido_paterno', 'concepto', 'comprobante')
    autocomplete_fields = ('ciudadano', 'comite')
