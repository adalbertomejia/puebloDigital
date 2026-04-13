from django.contrib import admin
from .models import Toma

@admin.register(Toma)
class TomaAdmin(admin.ModelAdmin):
    list_display = ('numero_toma', 'ciudadano', 'costo_anual', 'estado')
    list_filter = ('estado',)
    search_fields = ('numero_toma', 'ciudadano__nombre', 'ciudadano__apellido_paterno', 'ciudadano__curp')
