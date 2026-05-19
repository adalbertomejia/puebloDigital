from django.contrib import admin
from .models import Pago, Cooperacion


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
